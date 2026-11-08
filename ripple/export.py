"""Versioned, sanitized export of a completed run for the optional cloud workflows.

    python -m ripple.export --run runs/run1

Writes <run>/export/:
  manifest.json                         schema version, run id, snapshot id, source hashes, row counts
  graph_nodes.csv / graph_edges.csv     canonical namespaced keys + provenance (Databricks parity input)
  audit_events.csv                      key (run_id, event_id)
  audit_incidents.csv                   key (run_id, event_id, incident_id)
  audit_actions.csv                     key (run_id, event_id, action_seq)

Privacy: original event text, raw tool arguments, messages and direct identifiers (customer ids,
customer order ids, VINs) never leave the machine. They are replaced by keyed pseudonyms
(HMAC-SHA256, key from RIPPLE_PSEUDONYM_KEY) so joins survive. Business ids that are not about a
person (plants, parts, suppliers, dealers, production orders, lots, shipments) are kept.
Re-exporting the same run produces identical rows and keys (action_seq = order within the event).
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import hmac
import json
import os
from collections import Counter, defaultdict

from .world import CSV_FILES

EXPORT_SCHEMA = "ripple-export/1.0"
PERSONAL_ARGS = {"customer_id": "cust", "customer_order_id": "co"}
PERSONAL_LIST_ARGS = {"customer_order_ids": "co", "vins": "vin"}
DROP_ARGS = {"message", "reason"}


def _rl(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()] if os.path.exists(p) else []


class Pseudonymizer:
    def __init__(self, key: str):
        self.key = key.encode()

    def __call__(self, kind: str, value: str) -> str:
        return f"{kind}_" + hmac.new(self.key, f"{kind}:{value}".encode(), hashlib.sha256).hexdigest()[:12]


def sanitize_args(args: dict, ps: Pseudonymizer) -> dict:
    out = {}
    for k, v in args.items():
        if k in DROP_ARGS:
            out[k + "_chars"] = len(v) if isinstance(v, str) else None
        elif k in PERSONAL_ARGS:
            out[k + "_ref"] = ps(PERSONAL_ARGS[k], v)
        elif k in PERSONAL_LIST_ARGS:
            out[k + "_count"] = len(v)
            out[k + "_refs"] = [ps(PERSONAL_LIST_ARGS[k], x) for x in v]
        else:
            out[k] = v
    return out


def _sanitize_text(s: str, ps: Pseudonymizer) -> str:
    import re
    s = re.sub(r"\bC\d{4}\b", lambda m: ps("cust", m.group(0)), s or "")
    s = re.sub(r"\bCO-\d{5}\b", lambda m: ps("co", m.group(0)), s)
    s = re.sub(r"\b[A-Z]{3}\d{7}\b", lambda m: ps("vin", m.group(0)), s)
    return s


def write_csv(path, rows, fields):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: (json.dumps(v, sort_keys=True) if isinstance(v, (list, dict)) else v) for k, v in r.items()})


def match_log(calls: list, log: list) -> dict:
    """Pair each client call with its organizer log row (same event, tool, args, in order).
    A client-side timeout that never reached the server stays unmatched (server_logged False)."""
    pending = defaultdict(list)
    for i, r in enumerate(log):
        pending[(r["event_id"], r["tool"], json.dumps(r["args"], sort_keys=True))].append(i)
    out = {}
    for c in calls:
        k = (c["event_id"], c["tool"], json.dumps(c["args"], sort_keys=True))
        if pending.get(k):
            out[c["seq"]] = log[pending[k].pop(0)]
    return out


def export_run(run_dir: str, data_dir: str = "data") -> dict:
    out_dir = os.path.join(run_dir, "export")
    os.makedirs(out_dir, exist_ok=True)
    traces = _rl(os.path.join(run_dir, "event_traces.jsonl"))
    calls = _rl(os.path.join(run_dir, "client_calls.jsonl"))
    log = _rl(os.path.join(run_dir, "action_log.jsonl"))
    man = json.load(open(os.path.join(run_dir, "run_manifest.json")))
    run_id, snap = man["run_id"], man["snapshot_id"]
    ps = Pseudonymizer(os.environ.get("RIPPLE_PSEUDONYM_KEY") or f"ripple-default-key:{snap}")
    paired = match_log(calls, log)

    events, incidents, actions = [], [], []
    for t in traces:
        ex = t["execution"]
        types = [i["incident"]["type"] for i in t["incidents"]]
        writes = [r for r in ex if r["kind"] == "write"]
        if all(x == "noise" for x in types) and not ex:
            outcome = "no_action_noise"
        elif t["escalations"] and not any(r["status"] == "confirmed" for r in writes):
            outcome = "escalated_no_change"
        elif t["escalations"]:
            outcome = "acted_with_escalation"
        elif any(r["status"] != "confirmed" for r in ex) or t["blocked"]:
            outcome = "acted_with_failures"
        else:
            outcome = "acted"
        events.append({
            "run_id": run_id, "event_id": t["event_id"], "received_at": t["received_at"], "source": t["source"],
            "incident_types": "+".join(types), "incident_count": len(types), "is_compound": len(types) > 1,
            "outcome": outcome, "writes_confirmed": sum(1 for r in writes if r["status"] == "confirmed"),
            "writes_rejected": sum(1 for r in writes if r["status"] == "rejected"),
            "writes_unknown": sum(1 for r in writes if r["status"] == "unknown"),
            "reads": sum(1 for r in ex if r["kind"] == "read"), "blocked_by_validation": len(t["blocked"]),
            "escalated": bool(t["escalations"]),
            "action_kinds": "+".join(sorted({r["tool"] for r in ex if r["kind"] != "read" and r["status"] == "confirmed"})),
            "extractor": t.get("understanding", {}).get("extractor"), "duration_ms": t.get("duration_ms"),
            "summary": _sanitize_text(t["summary"], ps), "snapshot_id": snap})
        for e in t["incidents"]:
            inc, imp = e["incident"], e.get("impact") or {}
            path = imp.get("path", [])
            keys = sorted(x["edge_id"] for x in path)
            d = imp.get("disruption") or {}
            ev = imp.get("evidence", {})
            incidents.append({
                "run_id": run_id, "event_id": t["event_id"], "incident_id": inc["incident_id"], "type": inc["type"],
                "confirmed": inc["confirmed"], "agent": e.get("agent"), "decision": e.get("decision"),
                "policy_refs": [p.split(":")[0] for p in imp.get("policy", e.get("policy", []))],
                "plant_id": inc["entities"].get("plant") or d.get("plant"), "part_id": inc["entities"].get("part"),
                "supplier_id": inc["entities"].get("supplier"),
                "shipment_id": (ev.get("shipment") or {}).get("shipment_id") or inc["entities"].get("shipment"),
                "lot_id": imp.get("lot") or inc["entities"].get("lot"),
                "impact_window": ev.get("window") or (f"{ev['lot']['first_build_date']}..{ev['lot']['last_build_date']}" if ev.get("lot") else None),
                "date_phrases": {k: [v["phrase"], v["value"]] for k, v in inc["dates"].items()},
                "affected_orders": len(imp.get("affected_pos", [])) or None,
                "vehicles_traced": ev.get("vehicles_total"),
                "path_edge_count": len(path), "path_edge_types": dict(Counter(x["etype"] for x in path)),
                "path_ref": hashlib.sha256("\n".join(keys).encode()).hexdigest()[:16] if keys else None,
                "unresolved": "; ".join(imp.get("unresolved", []) or inc["unresolved"]) or None,
                "reason": _sanitize_text(e.get("reason") or "", ps) or None})
        for n, r in enumerate(ex, 1):
            lg = paired.get(r["seq"])
            actions.append({
                "run_id": run_id, "event_id": t["event_id"], "action_seq": n, "client_seq": r["seq"], "tool": r["tool"],
                "kind": r["kind"], "status": r["status"], "http_status": r.get("http"),
                "server_logged": lg is not None, "server_ok": lg["ok"] if lg else None,
                "failure_class": (None if r["status"] == "confirmed" else
                                  "server_rejection" if r["status"] == "rejected" else "client_timeout_unknown"),
                "error": r.get("error"), "duration_ms": r.get("ms"), "agent": r.get("agent"),
                "policy_rule": (r.get("rule") or "").split(":")[0] or None, "incident_ids": r.get("incidents") or [],
                "purpose": _sanitize_text(r.get("purpose") or "", ps), "args_sanitized": sanitize_args(r["args"], ps)})
        for b in t["blocked"]:
            actions.append({"run_id": run_id, "event_id": t["event_id"], "action_seq": len(ex) + 1 + t["blocked"].index(b),
                            "client_seq": None, "tool": b["tool"], "kind": "write", "status": "blocked",
                            "server_logged": False, "failure_class": "blocked_by_validation", "error": b["reason"],
                            "agent": b.get("agent"), "args_sanitized": sanitize_args(b["args"], ps)})

    ef = ["run_id", "event_id", "received_at", "source", "incident_types", "incident_count", "is_compound", "outcome",
          "writes_confirmed", "writes_rejected", "writes_unknown", "reads", "blocked_by_validation", "escalated",
          "action_kinds", "extractor", "duration_ms", "summary", "snapshot_id"]
    inf = ["run_id", "event_id", "incident_id", "type", "confirmed", "agent", "decision", "policy_refs", "plant_id", "part_id",
           "supplier_id", "shipment_id", "lot_id", "impact_window", "date_phrases", "affected_orders", "vehicles_traced",
           "path_edge_count", "path_edge_types", "path_ref", "unresolved", "reason"]
    af = ["run_id", "event_id", "action_seq", "client_seq", "tool", "kind", "status", "http_status", "server_logged", "server_ok",
          "failure_class", "error", "duration_ms", "agent", "policy_rule", "incident_ids", "purpose", "args_sanitized"]
    write_csv(os.path.join(out_dir, "audit_events.csv"), events, ef)
    write_csv(os.path.join(out_dir, "audit_incidents.csv"), incidents, inf)
    write_csv(os.path.join(out_dir, "audit_actions.csv"), actions, af)

    # graph: canonical keys + provenance (no attributes, so nothing personal beyond ids Databricks already ingests)
    gdir = os.path.join(run_dir, "graph")
    nodes = _rl(os.path.join(gdir, "graph_nodes.jsonl"))
    edges = _rl(os.path.join(gdir, "graph_edges.jsonl"))
    write_csv(os.path.join(out_dir, "graph_nodes.csv"), nodes, ["snapshot_id", "node_key", "ntype", "sid"])
    write_csv(os.path.join(out_dir, "graph_edges.csv"), edges,
              ["snapshot_id", "edge_key", "etype", "src", "dst", "source_table", "source_key", "derived"])

    src_hashes = {}
    for name in CSV_FILES + ["events.json", "policy_handbook.md"]:
        p = os.path.join(data_dir, name)
        if os.path.exists(p):
            src_hashes[name] = hashlib.sha256(open(p, "rb").read()).hexdigest()[:16]
    unmatched_log = len(log) - len(paired)
    manifest = {"schema_version": EXPORT_SCHEMA, "graph_schema": man["graph"].get("schema_version"), "run_id": run_id,
                "snapshot_id": snap, "mode": man["mode"], "extractor": man["extractor"], "source_files": src_hashes,
                "row_counts": {"audit_events": len(events), "audit_incidents": len(incidents), "audit_actions": len(actions),
                               "graph_nodes": len(nodes), "graph_edges": len(edges), "official_log_rows": len(log)},
                "official_log_reconciliation": {"client_calls": len(calls), "paired_with_log": len(paired),
                                                "log_rows_without_client_record": unmatched_log},
                "keys": {"AUDIT_EVENTS": ["run_id", "event_id"], "AUDIT_INCIDENTS": ["run_id", "event_id", "incident_id"],
                         "AUDIT_ACTIONS": ["run_id", "event_id", "action_seq"], "GRAPH_NODES": ["snapshot_id", "node_key"],
                         "GRAPH_EDGES": ["snapshot_id", "edge_key"]},
                "privacy": "event text, messages, raw args and customer/CO/VIN identifiers are excluded or HMAC-pseudonymized",
                "pseudonym_key_source": "env RIPPLE_PSEUDONYM_KEY" if os.environ.get("RIPPLE_PSEUDONYM_KEY") else "default (snapshot-derived; set RIPPLE_PSEUDONYM_KEY for real use)"}
    json.dump(manifest, open(os.path.join(out_dir, "manifest.json"), "w"), indent=2)
    return manifest


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="runs/run1")
    ap.add_argument("--data", default="data")
    m = export_run(ap.parse_args().run, ap.parse_args().data)
    print(json.dumps({"run_id": m["run_id"], **m["row_counts"], **m["official_log_reconciliation"]}, indent=1))


if __name__ == "__main__":
    main()
