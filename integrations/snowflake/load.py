#!/usr/bin/env python3
"""Publish one completed, exported run to the Snowflake audit schema. Repeat-safe.

    python -m ripple.export --run runs/run1                           # local, always first
    python integrations/snowflake/load.py --export runs/run1/export --print-ddl > integrations/snowflake/schema.sql
    python integrations/snowflake/load.py --export runs/run1/export --dry-run   # local SQLite rehearsal, no credentials
    python integrations/snowflake/load.py --export runs/run1/export             # real publish (env vars, see .env.example)

Flow per table: dedupe input on the row key -> truncate STG_<table> -> bound executemany insert ->
MERGE into the target on the key (update when matched, insert when not) -> verify row count for the
run_id equals the exported count. Republishing the same run updates rows in place and never double-counts.
The official action log and local traces are never modified; a failed publish can simply be retried.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sqlite3
import sys

# table -> (key columns, [(column, snowflake type)])
TABLES = {
    "AUDIT_EVENTS": (["run_id", "event_id"], [
        ("run_id", "VARCHAR"), ("event_id", "VARCHAR"), ("received_at", "TIMESTAMP_NTZ"), ("source", "VARCHAR"),
        ("incident_types", "VARCHAR"), ("incident_count", "INTEGER"), ("is_compound", "BOOLEAN"), ("outcome", "VARCHAR"),
        ("writes_confirmed", "INTEGER"), ("writes_rejected", "INTEGER"), ("writes_unknown", "INTEGER"), ("reads", "INTEGER"),
        ("blocked_by_validation", "INTEGER"), ("escalated", "BOOLEAN"), ("action_kinds", "VARCHAR"), ("extractor", "VARCHAR"),
        ("duration_ms", "FLOAT"), ("summary", "VARCHAR"), ("snapshot_id", "VARCHAR")]),
    "AUDIT_INCIDENTS": (["run_id", "event_id", "incident_id"], [
        ("run_id", "VARCHAR"), ("event_id", "VARCHAR"), ("incident_id", "VARCHAR"), ("type", "VARCHAR"), ("confirmed", "BOOLEAN"),
        ("agent", "VARCHAR"), ("decision", "VARCHAR"), ("policy_refs", "VARIANT"), ("plant_id", "VARCHAR"), ("part_id", "VARCHAR"),
        ("supplier_id", "VARCHAR"), ("shipment_id", "VARCHAR"), ("lot_id", "VARCHAR"), ("impact_window", "VARCHAR"),
        ("date_phrases", "VARIANT"), ("affected_orders", "INTEGER"), ("vehicles_traced", "INTEGER"),
        ("path_edge_count", "INTEGER"), ("path_edge_types", "VARIANT"), ("path_ref", "VARCHAR"), ("unresolved", "VARCHAR"),
        ("reason", "VARCHAR")]),
    "AUDIT_ACTIONS": (["run_id", "event_id", "action_seq"], [
        ("run_id", "VARCHAR"), ("event_id", "VARCHAR"), ("action_seq", "INTEGER"), ("client_seq", "INTEGER"), ("tool", "VARCHAR"),
        ("kind", "VARCHAR"), ("status", "VARCHAR"), ("http_status", "INTEGER"), ("server_logged", "BOOLEAN"),
        ("server_ok", "BOOLEAN"), ("failure_class", "VARCHAR"), ("error", "VARCHAR"), ("duration_ms", "FLOAT"),
        ("agent", "VARCHAR"), ("policy_rule", "VARCHAR"), ("incident_ids", "VARIANT"), ("purpose", "VARCHAR"),
        ("args_sanitized", "VARIANT")]),
}

VIEWS = {
    "V_RUN_SUMMARY": """
SELECT e.run_id, MIN(e.snapshot_id) AS snapshot_id, MIN(e.extractor) AS extractor, COUNT(*) AS events,
       SUM(IFF(e.outcome = 'no_action_noise', 1, 0)) AS noise_events,
       SUM(IFF(e.escalated, 1, 0)) AS escalated_events,
       SUM(e.writes_confirmed) AS writes_confirmed, SUM(e.writes_rejected) AS writes_rejected,
       SUM(e.writes_unknown) AS writes_unknown, SUM(e.reads) AS reads, ROUND(SUM(e.duration_ms) / 1000, 2) AS seconds
FROM AUDIT_EVENTS e GROUP BY e.run_id""",
    "V_EVENT_OUTCOMES": """
SELECT e.run_id, e.event_id, e.received_at, e.source, e.incident_types, e.is_compound, e.outcome, e.action_kinds,
       e.writes_confirmed, e.writes_rejected + e.writes_unknown AS writes_failed, e.escalated, e.summary,
       COUNT(i.incident_id) AS incidents, SUM(i.path_edge_count) AS graph_edges_cited
FROM AUDIT_EVENTS e LEFT JOIN AUDIT_INCIDENTS i ON i.run_id = e.run_id AND i.event_id = e.event_id
GROUP BY ALL""",
    "V_FAILED_CALLS": """
SELECT run_id, event_id, action_seq, tool, status, failure_class, http_status, server_logged, server_ok, error, agent,
       policy_rule, incident_ids
FROM AUDIT_ACTIONS WHERE status <> 'confirmed'""",
    "V_ESCALATIONS": """
SELECT a.run_id, a.event_id, a.action_seq, e.source, e.incident_types, e.outcome, i.incident_id, i.type, i.unresolved,
       i.reason, e.writes_confirmed AS operational_writes
FROM AUDIT_ACTIONS a
JOIN AUDIT_EVENTS e ON e.run_id = a.run_id AND e.event_id = a.event_id
LEFT JOIN AUDIT_INCIDENTS i ON i.run_id = a.run_id AND i.event_id = a.event_id
     AND (i.decision LIKE 'escalate%' OR i.unresolved IS NOT NULL)
WHERE a.tool = 'escalate'""",
    "V_ACTION_POLICY": """
SELECT x.run_id, x.event_id, x.action_seq, x.tool, x.status, x.agent, x.policy_rule, x.purpose,
       x.incident_id, i.type AS incident_type, i.path_ref, x.args_sanitized
FROM (SELECT a.*, f.value::STRING AS incident_id
      FROM AUDIT_ACTIONS a, LATERAL FLATTEN(input => a.incident_ids, outer => TRUE) f
      WHERE a.kind <> 'read') x
LEFT JOIN AUDIT_INCIDENTS i ON i.run_id = x.run_id AND i.event_id = x.event_id AND i.incident_id = x.incident_id""",
}


def ddl(schema: str = "RIPPLE_AUDIT") -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_$]*", schema):
        raise ValueError(f"unsafe schema identifier {schema!r}")
    out = ["-- Ripple Control audit schema (generated by integrations/snowflake/load.py --print-ddl)",
           f"CREATE SCHEMA IF NOT EXISTS {schema};", f"USE SCHEMA {schema};", ""]
    for t, (key, cols) in TABLES.items():
        body = ",\n  ".join(f"{c} {ty}" for c, ty in cols)
        out.append(f"CREATE TABLE IF NOT EXISTS {t} (\n  {body},\n  loaded_at TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP(),\n"
                   f"  CONSTRAINT pk_{t.lower()} PRIMARY KEY ({', '.join(key)})\n);")
        stg = ",\n  ".join(f"{c} VARCHAR" for c, _ in cols)
        out.append(f"CREATE TRANSIENT TABLE IF NOT EXISTS STG_{t} (\n  {stg}\n);\n")
    for v, sql in VIEWS.items():
        out.append(f"CREATE OR REPLACE VIEW {v} AS{sql};\n")
    return "\n".join(out)


def merge_sql(t: str) -> str:
    key, cols = TABLES[t]
    conv = lambda c, ty: (f"PARSE_JSON(s.{c})" if ty == "VARIANT" else f"TRY_CAST(s.{c} AS {ty})" if ty != "VARCHAR" else f"s.{c}")
    names = [c for c, _ in cols]
    src = ", ".join(f"{conv(c, ty)} AS {c}" for c, ty in cols)
    on = " AND ".join(f"t.{k} = s.{k}" for k in key)
    upd = ", ".join(f"{c} = s.{c}" for c in names if c not in key) + ", loaded_at = CURRENT_TIMESTAMP()"
    return (f"MERGE INTO {t} t USING (SELECT {src} FROM STG_{t} s "
            f"QUALIFY ROW_NUMBER() OVER (PARTITION BY {', '.join(key)} ORDER BY {key[0]}) = 1) s ON {on} "
            f"WHEN MATCHED THEN UPDATE SET {upd} "
            f"WHEN NOT MATCHED THEN INSERT ({', '.join(names)}) VALUES ({', '.join('s.' + c for c in names)})")


def read_rows(export_dir: str, t: str) -> list[tuple]:
    key, cols = TABLES[t]
    names = [c for c, _ in cols]
    with open(os.path.join(export_dir, t.lower() + ".csv"), newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    seen, out = set(), []
    for r in rows:                                   # dedupe input keys (last one wins)
        k = tuple(r[c] for c in key)
        if k in seen:
            out = [o for o in out if tuple(o[names.index(c)] for c in key) != k]
        seen.add(k)
        out.append(tuple((r.get(c) if r.get(c) != "" else None) for c in names))
    return out


# ---------------------------------------------------------------------------- publishers
class SnowflakePublisher:
    def __init__(self):
        import snowflake.connector                                  # optional dependency
        env = os.environ
        missing = [k for k in ("SNOWFLAKE_ACCOUNT", "SNOWFLAKE_USER", "SNOWFLAKE_WAREHOUSE", "SNOWFLAKE_DATABASE") if not env.get(k)]
        if missing:
            sys.exit(f"Snowflake not configured, missing {missing}. Local artifacts are untouched.")
        auth = {"password": env["SNOWFLAKE_PASSWORD"]} if env.get("SNOWFLAKE_PASSWORD") else {}
        if env.get("SNOWFLAKE_PRIVATE_KEY_FILE"):
            auth = {"private_key_file": env["SNOWFLAKE_PRIVATE_KEY_FILE"]}
        if env.get("SNOWFLAKE_AUTHENTICATOR"):
            auth["authenticator"] = env["SNOWFLAKE_AUTHENTICATOR"]
        self.schema = env.get("SNOWFLAKE_SCHEMA", "RIPPLE_AUDIT")
        # warehouse/database are selected in setup() after create-if-missing, so a fresh trial account works
        self.cn = snowflake.connector.connect(account=env["SNOWFLAKE_ACCOUNT"], user=env["SNOWFLAKE_USER"],
                                              role=env.get("SNOWFLAKE_ROLE"), paramstyle="qmark",
                                              client_store_temporary_credential=True, **auth)
        self.cur = self.cn.cursor()
        self.wh, self.db = env["SNOWFLAKE_WAREHOUSE"], env["SNOWFLAKE_DATABASE"]

    def setup(self):
        for ident in (self.wh, self.db):
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_$]*", ident):
                raise ValueError(f"unsafe identifier {ident!r}")
        # idempotent: XSMALL warehouse that suspends after 60 s idle, and the database
        self.cur.execute(f"CREATE WAREHOUSE IF NOT EXISTS {self.wh} WAREHOUSE_SIZE = XSMALL AUTO_SUSPEND = 60 "
                         f"AUTO_RESUME = TRUE INITIALLY_SUSPENDED = TRUE")
        self.cur.execute(f"USE WAREHOUSE {self.wh}")
        self.cur.execute(f"CREATE DATABASE IF NOT EXISTS {self.db}")
        self.cur.execute(f"USE DATABASE {self.db}")
        for stmt in ddl(self.schema).split(";\n"):
            s = "\n".join(l for l in stmt.splitlines() if not l.strip().startswith("--")).strip().rstrip(";")
            if s:
                self.cur.execute(s)

    def publish(self, t, rows):
        names = [c for c, _ in TABLES[t][1]]
        self.cur.execute(f"TRUNCATE TABLE STG_{t}")
        self.cur.executemany(f"INSERT INTO STG_{t} ({', '.join(names)}) VALUES ({', '.join('?' * len(names))})", rows)
        self.cur.execute(merge_sql(t))
        self.cur.execute(f"TRUNCATE TABLE STG_{t}")

    def count(self, t, run_id):
        self.cur.execute(f"SELECT COUNT(*), COUNT(DISTINCT {', '.join(TABLES[t][0])}) FROM {t} WHERE run_id = ?", (run_id,))
        return self.cur.fetchone()

    def query(self, sql):
        self.cur.execute(sql)
        return self.cur.fetchall()


class SqlitePublisher:
    """Offline rehearsal of the same staging -> dedupe -> keyed upsert flow, to prove repeat safety without credentials."""

    def __init__(self, path):
        self.cn = sqlite3.connect(path)

    def setup(self):
        for t, (key, cols) in TABLES.items():
            self.cn.execute(f"CREATE TABLE IF NOT EXISTS {t} ({', '.join(c for c, _ in cols)}, PRIMARY KEY ({', '.join(key)}))")
            self.cn.execute(f"CREATE TABLE IF NOT EXISTS STG_{t} ({', '.join(c for c, _ in cols)})")

    def publish(self, t, rows):
        key, cols = TABLES[t]
        names = [c for c, _ in cols]
        self.cn.execute(f"DELETE FROM STG_{t}")
        self.cn.executemany(f"INSERT INTO STG_{t} VALUES ({', '.join('?' * len(names))})", rows)
        upd = ", ".join(f"{c}=excluded.{c}" for c in names if c not in key)
        self.cn.execute(f"INSERT INTO {t} SELECT * FROM STG_{t} WHERE true ON CONFLICT ({', '.join(key)}) DO UPDATE SET {upd}")
        self.cn.execute(f"DELETE FROM STG_{t}")
        self.cn.commit()

    def count(self, t, run_id):
        return self.cn.execute(f"SELECT COUNT(*), COUNT(DISTINCT {' || '.join(TABLES[t][0])}) FROM {t} WHERE run_id = ?",
                               (run_id,)).fetchone()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--export", default="runs/run1/export")
    ap.add_argument("--dry-run", action="store_true", help="rehearse on local SQLite (no credentials, no network)")
    ap.add_argument("--print-ddl", action="store_true")
    ap.add_argument("--repeat", type=int, default=1, help="publish N times to demonstrate idempotence")
    a = ap.parse_args()
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    from ripple.extract import load_dotenv           # same minimal .env reader as the run (never overrides real env)
    load_dotenv()
    if a.print_ddl:
        print(ddl())
        return
    man = json.load(open(os.path.join(a.export, "manifest.json")))
    run_id = man["run_id"]
    pub = SqlitePublisher(os.path.join(a.export, "snowflake_rehearsal.sqlite")) if a.dry_run else SnowflakePublisher()
    pub.setup()
    status = {"run_id": run_id, "target": "sqlite-rehearsal" if a.dry_run else "snowflake", "tables": {}}
    for attempt in range(1, a.repeat + 1):
        for t in TABLES:
            rows = read_rows(a.export, t)
            pub.publish(t, rows)
            n, distinct = pub.count(t, run_id)
            expected = man["row_counts"][t.lower()]
            status["tables"][t] = {"exported": expected, "in_target": n, "distinct_keys": distinct, "ok": n == distinct == expected}
        print(f"publish #{attempt}: " + ", ".join(f"{t}={v['in_target']}/{v['exported']}{'' if v['ok'] else ' MISMATCH'}"
                                                  for t, v in status["tables"].items()))
    status["ok"] = all(v["ok"] for v in status["tables"].values())
    json.dump(status, open(os.path.join(a.export, "snowflake_publish_status.json"), "w"), indent=2)
    sys.exit(0 if status["ok"] else 1)


if __name__ == "__main__":
    main()
