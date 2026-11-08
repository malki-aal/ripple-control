#!/usr/bin/env python3
"""Sandbox model comparison, scored against the Hack the Highway rubric.

    python tests/compare_models.py --models gemini-3.1-flash-lite gemma-4-26b-a4b-it

Everything runs in-process on the organizer's Enterprise class (fresh world, no server, the official
action_log.jsonl is never touched). Each model runs the full pipeline on:
  * the 15 official events, compared action-for-action with the verified reference log
    (submission/action_log.jsonl, 15/15 on the independent handbook replay), and
  * the 15 reworded / edge-case stress events (tests/stress_events.json) with their expected outcomes.
"Model alone": an event where the model failed and the rules fallback rescued it counts as wrong.
Writes runs/model_comparison.json.
"""
import argparse
import json
import os
import sys
import time
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))
os.chdir(ROOT)
from ripple.client import ToolClient  # noqa: E402
from ripple.coordinator import Coordinator  # noqa: E402
from ripple.extract import CascadeExtractor, GeminiExtractor, RuleExtractor, load_dotenv  # noqa: E402
from ripple.graph import KnowledgeGraph  # noqa: E402
from ripple.world import World  # noqa: E402
from stress_test import check  # noqa: E402

INFO = {
    "gemini-3.1-flash-lite": "Google Gemini 3.1 Flash-Lite (hosted, smallest Gemini tier, size not published)",
    "gemma-4-26b-a4b-it": "Google Gemma 4 26B-A4B (open weights, mixture-of-experts, ~4B parameters active per token)",
    "cascade:gemini-3.1-flash-lite": "Rules first, Gemini 3.1 Flash-Lite only when the rules are not sure",
}


def actions(rows):
    """Comparable action multiset: non-read calls, args without free-text message/reason."""
    return Counter((r["tool"], json.dumps({k: v for k, v in r["args"].items() if k not in ("message", "reason")},
                                          sort_keys=True)) for r in rows if not r["tool"].startswith(("mes.get_", "crm.loaner_av")))


def run_model(model, w, kg, gold, stress, originals):
    cascade = model.startswith("cascade:")
    llm = GeminiExtractor(model=model.split(":", 1)[1] if cascade else model, fallback=RuleExtractor(w))
    if not llm.available():
        sys.exit(f"{model} not available on this key")
    ex = CascadeExtractor(RuleExtractor(w), llm) if cascade else llm
    client = ToolClient(None, data_dir="data")
    coord = Coordinator(w, kg, ex, client)
    res = {"model": model, "model_id": None, "official": [], "stress": []}
    t_start = time.time()
    traces = {}
    for ev in originals:
        t = coord.handle(ev)
        traces[ev["event_id"]] = t
        u = t["understanding"]
        got = actions([r for r in t["execution"] if r["status"] == "confirmed"])
        want = actions(gold.get(ev["event_id"], []))
        missing, extra = sum((want - got).values()), sum((got - want).values())
        res["official"].append({"event_id": ev["event_id"], "fallback": bool(u.get("fallback")),
                                "correct": missing == 0 and extra == 0 and not u.get("fallback"),
                                "missing": missing, "extra": extra, "calls": len(t["execution"]),
                                "failed": sum(r["status"] != "confirmed" for r in t["execution"]) + len(t["blocked"]),
                                "tokens": (u.get("tokens") or {}).get("totalTokenCount") or 0,
                                "extract_ms": u.get("extract_ms"), "llm_called": (u.get("cascade") or {}).get("llm_called", True), "agree_rules": (u.get("cross_check") or {}).get("agree")})
        print(f"  {model:24s} {ev['event_id']} {'OK ' if res['official'][-1]['correct'] else 'BAD'} "
              f"missing={missing} extra={extra} fallback={bool(u.get('fallback'))}", flush=True)
    for ev in stress:
        t = coord.handle({k: v for k, v in ev.items() if k not in ("expect", "why")})
        u = t["understanding"]
        probs = check(ev, t, traces)
        res["stress"].append({"event_id": ev["event_id"], "why": ev["why"], "fallback": bool(u.get("fallback")),
                              "correct": not probs and not u.get("fallback"), "problems": probs,
                              "calls": len(t["execution"]),
                              "failed": sum(r["status"] != "confirmed" for r in t["execution"]) + len(t["blocked"]),
                              "tokens": (u.get("tokens") or {}).get("totalTokenCount") or 0,
                              "extract_ms": u.get("extract_ms"), "llm_called": (u.get("cascade") or {}).get("llm_called", True)})
        print(f"  {model:24s} {ev['event_id']} {'OK ' if res['stress'][-1]['correct'] else 'BAD'} "
              f"fallback={bool(u.get('fallback'))} {probs}", flush=True)
    res["model_id"] = ex.model_id
    res["wall_s"] = round(time.time() - t_start, 1)
    return res


def score(r, best_tokens, best_ms):
    ev = r["official"] + r["stress"]
    n_ok = sum(e["correct"] for e in ev)
    calls = sum(e["calls"] for e in ev)
    waste = sum(e["failed"] for e in ev) + sum(e.get("extra", 0) for e in r["official"])
    tokens = sum(e["tokens"] for e in ev)
    ms = [e["extract_ms"] for e in ev if e["extract_ms"] is not None and not e["fallback"]]
    med_ms = sorted(ms)[len(ms) // 2] if ms else None
    acc = 50 * n_ok / len(ev)
    call_eff = 5 * (1 - waste / calls) if calls else 0
    light = 2.5 * (best_tokens / tokens if tokens else 0) + 2.5 * (best_ms / med_ms if med_ms else 0)
    return {"events_correct": n_ok, "events_total": len(ev),
            "official_correct": sum(e["correct"] for e in r["official"]), "stress_correct": sum(e["correct"] for e in r["stress"]),
            "fallbacks": sum(e["fallback"] for e in ev), "llm_calls": sum(e["llm_called"] for e in ev), "tool_calls": calls, "wasted_or_failed_calls": waste,
            "llm_tokens": tokens, "median_extract_ms": med_ms, "wall_s": r["wall_s"],
            "accuracy_50": round(acc, 1), "efficiency_10": round(call_eff + light, 1),
            "model_dependent_60": round(acc + call_eff + light, 1)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", default=["gemini-3.1-flash-lite", "cascade:gemini-3.1-flash-lite", "gemma-4-26b-a4b-it"])
    a = ap.parse_args()
    load_dotenv()
    w = World.load("data")
    kg = KnowledgeGraph(w)
    gold = {}
    for r in map(json.loads, open("submission/action_log.jsonl", encoding="utf-8")):
        if r["ok"]:
            gold.setdefault(r["event_id"], []).append(r)
    stress = json.load(open("tests/stress_events.json", encoding="utf-8"))
    originals = json.load(open("data/events.json", encoding="utf-8"))
    results = [run_model(m, w, kg, gold, stress, originals) for m in a.models]
    tok = [sum(e["tokens"] for e in r["official"] + r["stress"]) for r in results]
    mss = []
    for r in results:
        ms = sorted(e["extract_ms"] for e in r["official"] + r["stress"] if e["extract_ms"] is not None and not e["fallback"])
        mss.append(ms[len(ms) // 2] if ms else None)
    best_tokens, best_ms = min(t for t in tok if t), min(m for m in mss if m)
    out = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "results": []}
    for r in results:
        r["score"] = score(r, best_tokens, best_ms)
        r["about"] = INFO.get(r["model"], r["model"])
        out["results"].append(r)
    os.makedirs("runs", exist_ok=True)
    json.dump(out, open("runs/model_comparison.json", "w", encoding="utf-8"), indent=1)
    print("\n" + json.dumps([{"model": r["model"], **r["score"]} for r in out["results"]], indent=1))


if __name__ == "__main__":
    main()
