#!/usr/bin/env python3
"""Stress tests: reworded / edge-case events and injected tool failures. Never touches a scored server.

    python tests/stress_test.py                    # rules extractor
    python tests/stress_test.py --extractor gemini # Gemini (paced; ~5 s per event)

Part A  tests/stress_events.json: each variant has an expected understanding (types, entities, dates) and expected
        behaviour (writes or not, escalation, zero calls). Every run is then replayed through tests/verify_log.py,
        which re-derives the handbook outcome from the CSVs independently of the agent code.
Part B  failure injection on the in-process Enterprise: stale schedule, write timeout that did apply, write timeout that
        did not apply, server rejection.
"""
import argparse
import copy
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

PASS, FAIL = "PASS", "FAIL"


def writes(t):
    return [r for r in t["execution"] if r["kind"] == "write"]


def check(ev, t, ref_traces):
    exp, problems = ev["expect"], []
    types = sorted(i["incident"]["type"] for i in t["incidents"])
    if types != sorted(exp["types"]):
        problems.append(f"types {types} != {sorted(exp['types'])}")
    ents, dates = {}, {}
    for i in t["incidents"]:
        ents.update(i["incident"]["entities"])
        dates.update({k: v["value"] for k, v in i["incident"]["dates"].items()})
    for k, v in exp.get("entities", {}).items():
        if ents.get(k) != v:
            problems.append(f"entity {k}={ents.get(k)} expected {v}")
    for k, v in exp.get("dates", {}).items():
        if dates.get(k) != v:
            problems.append(f"date {k}={dates.get(k)} expected {v}")
    ok_w = [r for r in writes(t) if r["status"] == "confirmed"]
    if exp["writes"] and not ok_w:
        problems.append("expected operational writes, got none")
    if not exp["writes"] and writes(t):
        problems.append(f"expected NO writes, got {len(writes(t))} ({sorted({r['tool'] for r in writes(t)})})")
    esc = any(r["tool"] == "escalate" for r in t["execution"])
    if exp["escalate"] != esc:
        problems.append(f"escalate={esc} expected {exp['escalate']}")
    if "calls" in exp and len(t["execution"]) != exp["calls"]:
        problems.append(f"{len(t['execution'])} calls, expected {exp['calls']}")
    if exp["writes"]:
        kinds = {r["tool"] for r in ok_w}
        if len(kinds) < 3 and not any(i["incident"]["type"] == "quality_hold" for i in t["incidents"]):
            # rule 9 is a target, not a hard rule: fewer kinds is only legitimate when no customer is loaner-eligible
            elig = sum(len(q) for q in (t.get("dealer_plan") or {}).get("loaner_queues", {}).values())
            if elig:
                problems.append(f"only {len(kinds)} action kinds although {elig} loaner-eligible orders")
    bad = [r for r in t["execution"] if r["status"] != "confirmed"] + t["blocked"]
    if bad:
        problems.append(f"{len(bad)} failed/blocked calls")
    if exp.get("same_actions_as"):
        strip = lambda rows: [(r["tool"], json.dumps({k: v for k, v in r["args"].items() if k not in ("message", "reason")},
                                                       sort_keys=True)) for r in rows if r["kind"] != "read"]
        if strip(t["execution"]) != strip(ref_traces[exp["same_actions_as"]]["execution"]):
            problems.append(f"actions differ from {exp['same_actions_as']} (injection changed behaviour?)")
    return problems


# ---------------------------------------------------------------------------- Part B: failure injection
class FlakyClient(ToolClient):
    """Local client that misbehaves once, in a chosen way."""

    def __init__(self, mode, **kw):
        super().__init__(None, **kw)
        self.fault, self.fired = mode, False

    def call(self, event_id, tool, args, purpose=""):
        if not self.fired and self.fault == "stale_schedule" and tool == "mes.get_schedule":
            self.fired = True
            rec = super().call(event_id, tool, args, purpose)
            rec["body"] = {**rec["body"], "free_slots": 0}          # pretend someone else took the slot
            return rec
        if not self.fired and tool == "mes.reschedule" and self.fault in ("timeout_applied", "timeout_lost"):
            self.fired = True
            if self.fault == "timeout_applied":
                self.local.call(event_id, tool, args)                  # server did it, but the reply was lost
            self.seq += 1
            rec = {"seq": self.seq, "event_id": event_id, "tool": tool, "args": args, "purpose": purpose, "kind": "write",
                   "http": None, "body": None, "error": "client-side failure, outcome unknown: timed out", "status": "unknown", "ms": 15000}
            self.calls.append(rec)
            return rec
        if not self.fired and self.fault == "rejected" and tool == "dealer.notify":
            self.fired = True
            self.seq += 1
            rec = {"seq": self.seq, "event_id": event_id, "tool": tool, "args": args, "purpose": purpose, "kind": "write",
                   "http": 400, "body": {"error": "simulated rejection"}, "error": "simulated rejection", "status": "rejected", "ms": 1}
            self.calls.append(rec)
            return rec
        return super().call(event_id, tool, args, purpose)


def failure_tests(w, kg, ex, base_event):
    out = []
    for mode in ("stale_schedule", "timeout_applied", "timeout_lost", "rejected"):
        cl = FlakyClient(mode, data_dir="data")
        t = Coordinator(w, kg, ex, cl).handle(copy.deepcopy(base_event))
        resched = [r for r in t["execution"] if r["tool"] == "mes.reschedule"]
        first_po = resched[0]["args"]["production_order_id"] if resched else None
        dup = sum(1 for r in resched if r["args"]["production_order_id"] == first_po)
        st = cl.local.state(base_event["event_id"])
        esc = [r for r in t["execution"] if r["tool"] == "escalate"]
        if mode == "stale_schedule":
            ok = all(r["status"] == "confirmed" for r in t["execution"]) and not esc
            note = "stale read -> ledger resynced, next free day used, no failed write"
        elif mode == "timeout_applied":
            recon = any("reconcile" in (r.get("purpose") or "") for r in t["execution"])
            ok = recon and dup == 1 and not esc and first_po in st["loc"]
            note = "timeout but applied -> reconciled by read, NOT re-sent, no escalation"
        elif mode == "timeout_lost":
            ok = dup == 1 and bool(esc) and "unknown" in esc[0]["args"]["reason"]
            note = "timeout and not applied -> NOT blindly retried, escalated for a human"
        else:
            ok = bool(esc) is False and any(r["status"] == "rejected" for r in t["execution"]) and "failed" in t["summary"]
            note = "server rejection -> recorded as rejected and surfaced in the summary"
        out.append((mode, ok, note))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--extractor", default="rules", choices=["rules", "gemini", "auto", "cascade"])
    ap.add_argument("--model", default=None)
    a = ap.parse_args()
    w = World.load("data")
    kg = KnowledgeGraph(w)
    ex = make_extractor(w, a.extractor, a.model)
    out_dir = os.path.join("runs", f"stress_{a.extractor}")
    os.makedirs(out_dir, exist_ok=True)
    print(f"extractor: {ex.model_id}\n")

    stress = json.load(open("tests/stress_events.json", encoding="utf-8"))
    originals = json.load(open("data/events.json", encoding="utf-8"))
    ref_ids = {e["expect"]["same_actions_as"] for e in stress if e["expect"].get("same_actions_as")}
    client = ToolClient(None, data_dir="data")
    coord = Coordinator(w, kg, ex, client)
    ref = {e["event_id"]: coord.handle(e) for e in originals if e["event_id"] in ref_ids}
    traces, n_fail = [], 0
    print("Part A: reworded and edge-case events")
    for ev in stress:
        t = coord.handle({k: v for k, v in ev.items() if k not in ("expect", "why")})
        traces.append(t)
        probs = check(ev, t, ref)
        n_fail += bool(probs)
        print(f"  {ev['event_id']} {PASS if not probs else FAIL}  {ev['why']}")
        for p in probs:
            print(f"        - {p}")
    with open(os.path.join(out_dir, "event_traces.jsonl"), "w", encoding="utf-8") as f:
        for t in traces:
            f.write(json.dumps(t, default=str) + "\n")
    with open(os.path.join(out_dir, "action_log.jsonl"), "w", encoding="utf-8") as f:
        for r in client.calls:
            if r["event_id"] in {t["event_id"] for t in traces} and r["status"] != "unknown":
                f.write(json.dumps({"event_id": r["event_id"], "tool": r["tool"], "args": r["args"], "ok": r["status"] == "confirmed"}) + "\n")
    v = subprocess.run([sys.executable, "tests/verify_log.py", "--log", os.path.join(out_dir, "action_log.jsonl"),
                        "--traces", os.path.join(out_dir, "event_traces.jsonl")], capture_output=True, text=True)
    print("\n  independent handbook replay (tests/verify_log.py):")
    for line in v.stdout.strip().splitlines():
        print("   ", line)
    n_fail += v.returncode != 0

    print("\nPart B: injected tool failures (on E-04)")
    base = next(e for e in originals if e["event_id"] == "E-04")
    for mode, ok, note in failure_tests(w, kg, make_extractor(w, "rules"), base):
        n_fail += not ok
        print(f"  {mode:16s} {PASS if ok else FAIL}  {note}")
    print(f"\n{'ALL PASS' if not n_fail else f'{n_fail} FAILURES'}")
    sys.exit(1 if n_fail else 0)


if __name__ == "__main__":
    main()
