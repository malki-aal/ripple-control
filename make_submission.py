#!/usr/bin/env python3
"""Assemble the portal upload from a completed run.

    python make_submission.py --run runs/run1 --out submission

submission/
  action_log.jsonl          official organizer log (copied byte for byte)
  event_traces.jsonl        machine-readable trace per event
  event_summaries.md        human-readable summary + reason per event (generated from the traces)
  client_calls.jsonl        client-side record of every call (bodies, timing, status)
  run_manifest.json
  ontology.md / ontology.dot  ontology diagram (Mermaid + Graphviz) with counts
  graph/                    graph_nodes.jsonl, graph_edges.jsonl, ontology.json
  design_card.md
  verification.txt          output of tests/verify_log.py
  source_code.zip           ripple/, run.py, app.py, tests/, integrations/, docs
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import zipfile

SRC = ["ripple", "tests", "integrations", "ui", "ui_fixtures", ".streamlit", "run.py", "app.py", "make_submission.py", "RIPPLE_README.md", "DESIGN_CARD.md", "DESIGN_CARD_DETAILED.md",
       "requirements.txt", "requirements-cloud.txt", ".env.example"]


def ontology(manifest, onto):
    g = manifest["graph"]
    mm = ["# Ripple Control ontology", "", f"Schema `{onto['schema_version']}` · snapshot `{g['snapshot_id']}` · "
          f"{sum(g['nodes'].values()):,} nodes · {sum(g['edges'].values()):,} edges", "", "```mermaid", "flowchart LR"]
    for t, n in g["nodes"].items():
        mm.append(f'  {t}["{t}<br/>{n:,}"]')
    for k, v in onto["edge_types"].items():
        arrow = "-.->" if k == "LOT_USED_IN_ORDER" else "-->"
        mm.append(f'  {v["src"]} {arrow}|"{k.lower()} ({g["edges"].get(k, 0):,})"| {v["dst"]}')
    mm += ["```", "", "Dashed edge = derived (same plant, build date in the lot's inclusive window, model BOM contains the part).", "",
           "| Edge type | From | To | Meaning | Count |", "|---|---|---|---|---|"]
    mm += [f"| `{k}` | {v['src']} | {v['dst']} | {v['meaning']} | {g['edges'].get(k, 0):,} |" for k, v in onto["edge_types"].items()]
    mm += ["", "Every edge stores `source_table` and `source_key` (the CSV row that justifies it). Keys: node `Type:id`, edge `TYPE|src|dst`."]
    dot = ["digraph Ontology { rankdir=LR; node [shape=box, style=rounded];"]
    dot += [f'  "{t}" [label="{t}\\n{n}"];' for t, n in g["nodes"].items()]
    dot += [f'  "{v["src"]}" -> "{v["dst"]}" [label="{k.lower()}\\n{g["edges"].get(k, 0)}"'
            + (', style=dashed' if k == "LOT_USED_IN_ORDER" else "") + "];" for k, v in onto["edge_types"].items()]
    return "\n".join(mm) + "\n", "\n".join(dot + ["}"]) + "\n"


def summaries(traces, events):
    out = ["# Event summaries", "", "Generated from `event_traces.jsonl`. One section per event: what it was, what we did, and why.", ""]
    for t in traces:
        ex = t["execution"]
        kinds = sorted({r["tool"] for r in ex if r["kind"] != "read" and r["status"] == "confirmed"})
        out += [f"## {t['event_id']} · {t['source']} · {t['received_at']}", "",
                f"> {events.get(t['event_id'], {}).get('text', '').replace(chr(10), ' ')}", ""]
        for e in t["incidents"]:
            inc, imp = e["incident"], e.get("impact") or {}
            dates = ", ".join(f"{k} = {v['value']} (\"{v['phrase']}\")" for k, v in inc["dates"].items())
            out.append(f"- **{inc['incident_id']} · {inc['type']}** · handled by {e.get('agent')} · decision: {e.get('decision')}")
            if inc["entities"]:
                out.append(f"  - resolved: {', '.join(f'{k}={v}' for k, v in inc['entities'].items())}" + (f"; {dates}" if dates else ""))
            if imp.get("path"):
                types = {}
                for x in imp["path"]:
                    types[x["etype"]] = types.get(x["etype"], 0) + 1
                out.append(f"  - graph path: " + " → ".join(f"{k} ×{v}" for k, v in types.items()))
            if imp.get("policy") or e.get("policy"):
                out.append(f"  - policy: {'; '.join(p.split(':')[0] for p in imp.get('policy', e.get('policy', [])))}")
            if e.get("reason"):
                out.append(f"  - reason: {e['reason']}")
        writes = sum(1 for r in ex if r["kind"] == "write" and r["status"] == "confirmed")
        out += ["", f"**Outcome.** {t['summary']}", "",
                f"Writes confirmed: {writes} · action kinds: {', '.join(kinds) or 'none'} · failed calls: "
                f"{sum(1 for r in ex if r['status'] != 'confirmed')}" + (" · escalated to a human" if t["escalations"] else ""), ""]
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="runs/run1")
    ap.add_argument("--out", default="submission")
    a = ap.parse_args()
    if not os.path.exists(os.path.join(a.run, "action_log.jsonl")):
        sys.exit("no organizer action_log.jsonl in the run folder; this must be a server run, not a dry run")
    os.makedirs(a.out, exist_ok=True)
    for f in ["action_log.jsonl", "event_traces.jsonl", "client_calls.jsonl", "run_manifest.json"]:
        shutil.copyfile(os.path.join(a.run, f), os.path.join(a.out, f))
    shutil.copytree(os.path.join(a.run, "graph"), os.path.join(a.out, "graph"), dirs_exist_ok=True)
    manifest = json.load(open(os.path.join(a.run, "run_manifest.json")))
    onto = json.load(open(os.path.join(a.run, "graph", "ontology.json")))
    md, dot = ontology(manifest, onto)
    open(os.path.join(a.out, "ontology.md"), "w", encoding="utf-8").write(md)
    open(os.path.join(a.out, "ontology.dot"), "w", encoding="utf-8").write(dot)
    traces = [json.loads(l) for l in open(os.path.join(a.run, "event_traces.jsonl"), encoding="utf-8")]
    events = {e["event_id"]: e for e in json.load(open("data/events.json", encoding="utf-8"))}
    open(os.path.join(a.out, "event_summaries.md"), "w", encoding="utf-8").write(summaries(traces, events))
    shutil.copyfile("DESIGN_CARD.md", os.path.join(a.out, "design_card.md"))
    v = subprocess.run([sys.executable, "tests/verify_log.py", "--log", os.path.join(a.run, "action_log.jsonl"),
                        "--traces", os.path.join(a.run, "event_traces.jsonl")], capture_output=True, text=True)
    open(os.path.join(a.out, "verification.txt"), "w").write(v.stdout + v.stderr)
    with zipfile.ZipFile(os.path.join(a.out, "source_code.zip"), "w", zipfile.ZIP_DEFLATED) as z:
        for s in SRC:
            if os.path.isfile(s):
                z.write(s)
            elif os.path.isdir(s):
                for root, _, files in os.walk(s):
                    for f in files:
                        if "__pycache__" not in root and not f.endswith((".pyc", ".sqlite")):
                            z.write(os.path.join(root, f))
        for f in ["enterprise.py", "enterprise_server.py"]:
            z.write(f)
    print("\n".join(sorted(os.listdir(a.out))))
    print(v.stdout.strip().splitlines()[-1])


if __name__ == "__main__":
    main()
