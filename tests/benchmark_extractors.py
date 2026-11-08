#!/usr/bin/env python3
"""Benchmark extractors on the event feed: what each one resolves to after code resolution.

    python tests/benchmark_extractors.py                       # rules vs Gemini (needs GEMINI_API_KEY)
    python tests/benchmark_extractors.py --model gemini-3.1-flash-lite --repeat 3

Compares, per incident: type, resolved entity ids and resolved dates, against the rules extractor,
plus latency and token usage. Makes no tool calls. Writes runs/benchmark.json.
"""
import argparse
import json
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ripple.extract import GeminiExtractor, RuleExtractor, load_dotenv  # noqa: E402
from ripple.resolve import Resolver  # noqa: E402
from ripple.world import World  # noqa: E402


def signature(ex, rs, ev):
    raw = ex.extract(ev["text"])
    out = []
    for i, r in enumerate(raw["incidents"], 1):
        inc = rs.resolve(ev, r, i)
        out.append({"type": inc.type, "entities": dict(sorted(inc.entities.items())),
                    "dates": {k: v.value for k, v in inc.dates.items()}, "unresolved": inc.unresolved})
    return sorted(out, key=lambda x: (x["type"], json.dumps(x["entities"])))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=None)
    ap.add_argument("--repeat", type=int, default=1)
    a = ap.parse_args()
    load_dotenv()
    w = World.load("data")
    rs, rules = Resolver(w), RuleExtractor(w)
    g = GeminiExtractor(model=a.model, fallback=rules)
    if not g.available():
        sys.exit("Gemini unavailable: set GEMINI_API_KEY (and check --model against models.list).")
    events = json.load(open("data/events.json", encoding="utf-8"))
    rows, lat, toks, agree = [], [], [], 0
    for ev in events:
        ref = signature(rules, rs, ev)
        runs = []
        for _ in range(a.repeat):
            t0 = time.perf_counter()
            try:
                runs.append(signature(g, rs, ev))
            except Exception as e:  # noqa: BLE001
                runs.append({"error": f"{type(e).__name__}: {e}"})
            lat.append((time.perf_counter() - t0) * 1000)
            toks.append((getattr(g, "last_usage", {}) or {}).get("totalTokenCount") or 0)
        same = all(r == ref for r in runs)
        stable = all(r == runs[0] for r in runs)
        agree += same
        rows.append({"event_id": ev["event_id"], "agrees_with_rules": same, "stable_across_repeats": stable,
                     "rules": ref, "gemini": runs[0]})
        print(f"{ev['event_id']}: {'same' if same else 'DIFF'}{'' if stable else ' (unstable)'}  "
              f"rules={[x['type'] for x in ref]}  gemini={[x.get('type') for x in runs[0]] if isinstance(runs[0], list) else runs[0]}")
    summary = {"model": g.model_id, "events": len(events), "agree_with_rules": agree,
               "latency_ms_median": round(statistics.median(lat), 1), "tokens_total": sum(toks),
               "tokens_per_call_median": statistics.median(toks) if toks else None}
    print(json.dumps(summary, indent=1))
    os.makedirs("runs", exist_ok=True)
    json.dump({"summary": summary, "rows": rows}, open("runs/benchmark.json", "w"), indent=2)


if __name__ == "__main__":
    main()
