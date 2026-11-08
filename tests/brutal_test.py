#!/usr/bin/env python3
"""Brutal robustness test: 20 harder messages (tests/brutal_events.json), strict verdicts.

    python tests/brutal_test.py --extractor rules|gemini|cascade [--model ...]

PASS = expected incident(s), ids, dates and outcome. SAFE = expected action but the system escalated with no writes
(no harm, but points lost). FAIL = wrong or harmful action (writes where none belong, wrong ids/dates, missed escalation).
Writes are also replayed by tests/verify_log.py so every action follows the handbook for the parameters found.
In-process only (organizer Enterprise class): never touches a server or the official log.
"""
import argparse
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
from ripple.client import ToolClient  # noqa: E402
from ripple.coordinator import Coordinator  # noqa: E402
from ripple.extract import make_extractor  # noqa: E402
from ripple.graph import KnowledgeGraph  # noqa: E402
from ripple.world import World  # noqa: E402


def verdict(exp, t):
    ok_w = [r for r in t["execution"] if r["kind"] == "write" and r["status"] == "confirmed"]
    esc = any(r["tool"] == "escalate" for r in t["execution"])
    types = sorted(i["incident"]["type"] for i in t["incidents"])
    ents, dates = {}, {}
    for i in t["incidents"]:
        ents.update(i["incident"]["entities"])
        dates.update({k: v["value"] for k, v in i["incident"]["dates"].items()})
    harm = []
    if not exp["writes"] and ok_w:
        harm.append(f"{len(ok_w)} writes where none belong ({sorted({r['tool'] for r in ok_w})})")
    if exp.get("calls") == 0 and t["execution"]:
        harm.append(f"{len(t['execution'])} calls on noise")
    if exp.get("escalate") is True and not esc:
        harm.append("did not escalate")
    if exp.get("escalate") is False and esc and exp["writes"] is False:
        harm.append("escalated noise")
    if ok_w:   # acted: what it acted on must be right
        for k, v in exp.get("entities", {}).items():
            if ents.get(k) != v:
                harm.append(f"acted with {k}={ents.get(k)}, expected {v}")
        for k, v in exp.get("dates", {}).items():
            if dates.get(k) != v:
                harm.append(f"acted with {k}={dates.get(k)}, expected {v}")
    if harm:
        return "FAIL", harm
    if exp["writes"] and not ok_w:
        return ("SAFE" if esc else "FAIL"), [f"escalated instead of acting (types {types})" if esc else "no action and no escalation"]
    miss = []
    real = sorted(x for x in types if x != "noise") if "noise" not in exp.get("types", []) else types
    if exp.get("types") and real != sorted(exp["types"]):   # an extra no-action "noise" segment is harmless
        miss.append(f"types {types} != {sorted(exp['types'])}")
    if exp["writes"] and exp.get("escalate") is False and esc:
        miss.append("also escalated")
    return ("PASS" if not miss else "PART"), miss


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--extractor", default="cascade", choices=["rules", "gemini", "cascade"])
    ap.add_argument("--model", default=None)
    a = ap.parse_args()
    w = World.load("data")
    kg = KnowledgeGraph(w)
    ex = make_extractor(w, a.extractor, a.model)
    client = ToolClient(None, data_dir="data")
    coord = Coordinator(w, kg, ex, client)
    events = json.load(open("tests/brutal_events.json", encoding="utf-8"))
    out = os.path.join("runs", f"brutal_{a.extractor}")
    os.makedirs(out, exist_ok=True)
    print(f"extractor: {ex.model_id}\n")
    traces, tally, llm = [], {}, 0
    for ev in events:
        t = coord.handle({k: v for k, v in ev.items() if k not in ("expect", "why")})
        traces.append(t)
        llm += bool((t["understanding"].get("cascade") or {"llm_called": a.extractor != "rules"})["llm_called"])
        v, notes = verdict(ev["expect"], t)
        tally[v] = tally.get(v, 0) + 1
        print(f"  {ev['event_id']} {v:4s}  {ev['why']}")
        for n in notes:
            print(f"        - {n}")
    with open(os.path.join(out, "event_traces.jsonl"), "w", encoding="utf-8") as f:
        for t in traces:
            f.write(json.dumps(t, default=str) + "\n")
    with open(os.path.join(out, "action_log.jsonl"), "w", encoding="utf-8") as f:
        for r in client.calls:
            if r["status"] != "unknown":
                f.write(json.dumps({"event_id": r["event_id"], "tool": r["tool"], "args": r["args"], "ok": r["status"] == "confirmed"}) + "\n")
    v = subprocess.run([sys.executable, "tests/verify_log.py", "--log", os.path.join(out, "action_log.jsonl"),
                        "--traces", os.path.join(out, "event_traces.jsonl")], capture_output=True, text=True)
    print("\n  handbook replay:", v.stdout.strip().splitlines()[-1] if v.stdout.strip() else v.stderr[-300:])
    for line in v.stdout.splitlines():
        if "FAIL" in line:
            print("   ", line)
    failed = sum(1 for r in client.calls if r["status"] != "confirmed")
    print(f"\n  {tally}  llm_calls={llm}/{len(events)}  failed_tool_calls={failed}")
    json.dump({"extractor": ex.model_id, "tally": tally, "llm_calls": llm, "failed_calls": failed},
              open(os.path.join(out, "summary.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
