#!/usr/bin/env python3
"""Deploy and run the graph notebook on Databricks (Free Edition / serverless) through the REST API. Stdlib only.

    python integrations/databricks/deploy.py --export runs/run2/export

Needs DATABRICKS_HOST and DATABRICKS_TOKEN (env or .env). Steps, all idempotent:
  1. SQL (first available SQL warehouse): CREATE SCHEMA / VOLUME workspace.ripple(.files)
  2. upload the 16 extracts -> /Volumes/workspace/ripple/files/extracts/
     upload graph_nodes.csv, graph_edges.csv, manifest.json -> /Volumes/workspace/ripple/files/exports/run2/
  3. import integrations/databricks/ripple_graph_build.py as a notebook in the caller's home folder
  4. one-time serverless job run of the notebook, polled to completion
  5. download databricks_parity_report.json from the Volume into the export folder and print the verdict
The token is sent only in the Authorization header to DATABRICKS_HOST and never printed.
"""
import argparse
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
from ripple.extract import load_dotenv  # noqa: E402

CATALOG, SCHEMA, VOLUME = "workspace", "ripple", "files"
VOL = f"/Volumes/{CATALOG}/{SCHEMA}/{VOLUME}"


class DBX:
    def __init__(self):
        load_dotenv()
        self.host = (os.environ.get("DATABRICKS_HOST") or "").rstrip("/")
        self.token = os.environ.get("DATABRICKS_TOKEN")
        if not self.host.startswith("https://") or not self.token or self.token.startswith("<"):
            sys.exit("Set DATABRICKS_HOST (https://...) and DATABRICKS_TOKEN in .env first.")

    def req(self, method, path, body=None, raw=None, ctype="application/json"):
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        r = urllib.request.Request(self.host + path, data=data, method=method,
                                   headers={"Authorization": f"Bearer {self.token}", "Content-Type": ctype})
        try:
            with urllib.request.urlopen(r, timeout=120) as resp:
                out = resp.read()
                return json.loads(out) if out and resp.headers.get_content_type() == "application/json" else out
        except urllib.error.HTTPError as e:
            msg = e.read()[:500].decode(errors="replace")
            raise SystemExit(f"{method} {path.split('?')[0]} -> HTTP {e.code}: {msg}") from None

    # --- SQL statement execution on the first SQL warehouse
    def sql(self, statement):
        whs = self.req("GET", "/api/2.0/sql/warehouses").get("warehouses", [])
        if not whs:
            raise SystemExit("No SQL warehouse in this workspace (Free Edition normally has a Serverless Starter Warehouse).")
        wid = whs[0]["id"]
        r = self.req("POST", "/api/2.0/sql/statements", {"warehouse_id": wid, "statement": statement, "wait_timeout": "50s"})
        while r["status"]["state"] in ("PENDING", "RUNNING"):
            time.sleep(3)
            r = self.req("GET", f"/api/2.0/sql/statements/{r['statement_id']}")
        if r["status"]["state"] != "SUCCEEDED":
            raise SystemExit(f"SQL failed: {statement}\n{r['status']}")
        return r

    def mkdir(self, path):
        self.req("PUT", "/api/2.0/fs/directories" + urllib.parse.quote(path))

    def upload(self, local, remote):
        with open(local, "rb") as f:
            self.req("PUT", "/api/2.0/fs/files" + urllib.parse.quote(remote) + "?overwrite=true", raw=f.read(),
                     ctype="application/octet-stream")

    def download(self, remote):
        return self.req("GET", "/api/2.0/fs/files" + urllib.parse.quote(remote))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--export", default="runs/run2/export")
    ap.add_argument("--run-name", default="run2")
    a = ap.parse_args()
    d = DBX()
    me = d.req("GET", "/api/2.0/preview/scim/v2/Me")["userName"]
    print(f"workspace {urllib.parse.urlparse(d.host).netloc} as {me}")

    print("1. schema + volume")
    d.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA}")
    d.sql(f"CREATE VOLUME IF NOT EXISTS {CATALOG}.{SCHEMA}.{VOLUME}")

    print("2. upload files")
    ext_dir, exp_dir = f"{VOL}/extracts", f"{VOL}/exports/{a.run_name}"
    d.mkdir(ext_dir)
    d.mkdir(exp_dir)
    csvs = sorted(f for f in os.listdir("data") if f.endswith(".csv"))
    for f in csvs:
        d.upload(os.path.join("data", f), f"{ext_dir}/{f}")
    for f in ("graph_nodes.csv", "graph_edges.csv", "manifest.json"):
        d.upload(os.path.join(a.export, f), f"{exp_dir}/{f}")
    print(f"   {len(csvs)} extracts + 3 export files")

    print("3. import notebook")
    nb_path = f"/Users/{me}/ripple_graph_build"
    src = open("integrations/databricks/ripple_graph_build.py", "rb").read()
    d.req("POST", "/api/2.0/workspace/import", {"path": nb_path, "format": "SOURCE", "language": "PYTHON",
                                                 "content": base64.b64encode(src).decode(), "overwrite": True})
    print(f"   {nb_path}")

    print("4. run on serverless")
    run = d.req("POST", "/api/2.1/jobs/runs/submit", {
        "run_name": f"ripple graph build ({a.run_name})",
        "tasks": [{"task_key": "graph_build", "notebook_task": {"notebook_path": nb_path, "base_parameters": {
            "source": ext_dir, "local_export": exp_dir, "target": f"{CATALOG}.ripple_graph"}}}]})
    rid = run["run_id"]
    t0 = time.time()
    while True:
        st = d.req("GET", f"/api/2.1/jobs/runs/get?run_id={rid}")
        life, result = st["state"]["life_cycle_state"], st["state"].get("result_state")
        if life in ("TERMINATED", "SKIPPED", "INTERNAL_ERROR"):
            break
        print(f"   {life} ... {int(time.time() - t0)}s", flush=True)
        time.sleep(15)
    print(f"   {life} / {result}  {st.get('run_page_url', '')}")
    if result != "SUCCESS":
        task_run = st["tasks"][0]["run_id"]
        out = d.req("GET", f"/api/2.1/jobs/runs/get-output?run_id={task_run}")
        sys.exit(f"notebook failed: {out.get('error', '')}\n{out.get('error_trace', '')[-1500:]}")

    print("5. parity report")
    rep = json.loads(d.download(f"{exp_dir}/databricks_parity_report.json"))
    json.dump(rep, open(os.path.join(a.export, "databricks_parity_report_cloud.json"), "w"), indent=2, default=str)
    p = rep["parity"]
    print(json.dumps({"on_databricks": rep["on_databricks"], "validation_ok": rep["validation_ok"], "parity": p.get("status"),
                      "nodes": p.get("nodes"), "edges": p.get("edges"), "provenance_mismatches": p.get("provenance_mismatches"),
                      "impact_checks": rep["impact_checks"], "published_rows": rep["published_rows"]}, indent=1))


if __name__ == "__main__":
    main()
