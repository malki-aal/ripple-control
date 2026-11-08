#!/usr/bin/env python3
"""Ripple Control: run the whole event feed end to end.

  # judged run against the organizer server (start it first with a fresh --out)
  python run.py --server http://127.0.0.1:8000 --out runs/run1

  # dry run: same code path, organizer Enterprise class in-process, no server, no log written by it
  python run.py --dry-run --out runs/dry

Writes into --out: event_traces.jsonl, client_calls.jsonl, run_manifest.json, graph/ (nodes, edges, ontology).
The organizer server writes action_log.jsonl into its own --out; use the same folder.
"""
import argparse
import json
import os
import sys
import time
import uuid

from ripple.client import ToolClient
from ripple.coordinator import Coordinator, check_tool_schema
from ripple.extract import make_extractor
from ripple.graph import KnowledgeGraph
from ripple.world import World


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data")
    ap.add_argument("--events", default=None, help="defaults to the server feed, or data/events.json in dry-run")
    ap.add_argument("--server", default="http://127.0.0.1:8000")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--out", default="runs/run1")
    ap.add_argument("--extractor", default="auto", choices=["auto", "rules", "gemini", "ollama"])
    ap.add_argument("--model", default=None, help="LLM model id (default: best available Flash-Lite, or qwen2.5:3b for Ollama)")
    ap.add_argument("--only", nargs="*", help="event ids to run (debug)")
    a = ap.parse_args()

    os.makedirs(a.out, exist_ok=True)
    w = World.load(a.data)
    kg = KnowledgeGraph(w)
    client = ToolClient(None if a.dry_run else a.server, data_dir=a.data)
    problems = check_tool_schema(client.tools())
    if problems:
        sys.exit("tool schema mismatch: " + "; ".join(problems))
    if a.events:
        events = json.load(open(a.events, encoding="utf-8"))
    else:
        events = json.load(open(os.path.join(a.data, "events.json"), encoding="utf-8")) if a.dry_run else client.events()
    if a.only:
        events = [e for e in events if e["event_id"] in a.only]

    ex = make_extractor(w, a.extractor, a.model)
    coord = Coordinator(w, kg, ex, client)
    run_id = time.strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:6]
    snap = w.snapshot_id()
    print(f"run {run_id}  mode={client.mode}  extractor={ex.model_id}  snapshot={snap}")

    traces = []
    with open(os.path.join(a.out, "event_traces.jsonl"), "w", encoding="utf-8") as f:
        for ev in events:
            t = coord.handle(ev)
            t["run_id"] = run_id
            traces.append(t)
            f.write(json.dumps(t, default=str) + "\n")
            n_w = sum(1 for r in t["execution"] if r["kind"] == "write" and r["status"] == "confirmed")
            n_f = sum(1 for r in t["execution"] if r["status"] != "confirmed")
            kinds = sorted({r["tool"] for r in t["execution"] if r["kind"] != "read" and r["status"] == "confirmed"})
            print(f"  {ev['event_id']}  {'+'.join(i['incident']['type'] for i in t['incidents']):32s} "
                  f"writes={n_w:3d} failed={n_f}  {', '.join(kinds)}")
    with open(os.path.join(a.out, "client_calls.jsonl"), "w", encoding="utf-8") as f:
        for r in client.calls:
            f.write(json.dumps(r, default=str) + "\n")
    gstats = kg.export(os.path.join(a.out, "graph"), snap)
    manifest = {"run_id": run_id, "schema_version": "ripple-run/1.0", "mode": client.mode, "server": None if a.dry_run else a.server,
                "extractor": ex.model_id, "snapshot_id": snap, "events": len(events), "graph": gstats,
                "files": ["event_traces.jsonl", "client_calls.jsonl", "graph/graph_nodes.jsonl", "graph/graph_edges.jsonl",
                          "graph/ontology.json"] + ([] if a.dry_run else ["action_log.jsonl (written by organizer server)"]),
                "calls": {"total": len(client.calls),
                          "writes_ok": sum(1 for r in client.calls if r["kind"] == "write" and r["status"] == "confirmed"),
                          "failed": sum(1 for r in client.calls if r["status"] != "confirmed")}}
    json.dump(manifest, open(os.path.join(a.out, "run_manifest.json"), "w"), indent=2)
    print(json.dumps(manifest["calls"]))


if __name__ == "__main__":
    main()
