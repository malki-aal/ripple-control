#!/usr/bin/env python3
"""Independent policy checker for an action log.

Re-derives the expected outcome straight from the CSVs with the handbook rules (no ripple imports
for the policy logic), using only the incident *parameters* recorded in the trace (plant, window,
shipment, lot). Then replays the log on a fresh organizer Enterprise and diffs final state.

  python tests/verify_log.py --log runs/run1/action_log.jsonl --traces runs/run1/event_traces.jsonl
"""
import argparse
import csv
import json
import os
import sys
from collections import defaultdict
from datetime import date, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from enterprise import Enterprise, ToolError, idx_to_date, date_to_idx  # organizer code only

rd = lambda n: list(csv.DictReader(open(os.path.join(ROOT, "data", n), encoding="utf-8")))


def expected(ent: Enterprise, incidents):
    """incidents: list of dicts from trace. Returns expected final-state pieces."""
    orders = {r["production_order_id"]: r for r in rd("production_orders.csv")}
    plants = [r["plant_id"] for r in rd("plants.csv")]
    blocks, affected = [], {}
    held, stop, owners = set(), set(), set()
    for inc in incidents:
        imp = inc.get("impact") or {}
        t = inc["incident"]["type"]
        if t in ("supplier_delay", "plant_outage") and imp.get("status") == "actionable":
            d = imp["disruption"]
            plant = d["plant"]
            if t == "supplier_delay":
                sh = imp["evidence"]["shipment"]
                a, b = date.fromisoformat(sh["eta_date"]), date.fromisoformat(inc["incident"]["dates"]["new_eta"]["value"])
                models = {m for m, p in ((r["model"], r["part_id"]) for r in rd("bom.csv")) if p == sh["part_id"]}
                days = [a + timedelta(i) for i in range((b - a).days)]
                rec = b
            else:
                a = date.fromisoformat(inc["incident"]["dates"]["start"]["value"])
                b = date.fromisoformat(inc["incident"]["dates"]["end"]["value"])
                models, days, rec = None, [a + timedelta(i) for i in range((b - a).days + 1)], b + timedelta(1)
            while rec.weekday() > 4:
                rec += timedelta(1)
            dset = {x.isoformat() for x in days if x.weekday() < 5}
            bi = [date_to_idx(x) for x in days if x.weekday() < 5]
            blocks.append((plant, min(bi), max(bi), models))
            for po, r in sorted(orders.items(), key=lambda kv: (kv[1]["build_date"], kv[0])):
                if r["plant_id"] == plant and r["build_date"] in dset and (models is None or r["model"] in models) \
                        and r["build_date"] >= "2027-03-08":
                    affected.setdefault(po, date_to_idx(rec))
        if t == "quality_hold" and imp.get("status") == "actionable":
            lot = ent.lots[imp["lot"]]
            held.add(imp["lot"])
            for v in ent.vehicles.values():
                if v["plant_id"] == lot["plant_id"] and lot["first_build_date"] <= v["build_date"] <= lot["last_build_date"] \
                        and lot["part_id"] in ent.bom[v["model"]]:
                    (stop.add(v["vin"]) if v["status"] == "in_stock" else owners.add(v["customer_id"]))
    # rule 3 sequential placement
    s = ent.state("__expected__")
    blocked = lambda p, i, m: any(p == bp and lo <= i <= hi and (ms is None or m in ms) for bp, lo, hi, ms in blocks)
    moves = {}
    for po, rec in affected.items():
        m, (cp, ci) = orders[po]["model"], s["loc"][po]
        dest = None
        for i in range(rec, 20):
            if not blocked(cp, i, m) and len(s["slots"][(cp, i)]) < ent.plants[cp]["slots"]:
                dest = (cp, i); break
        if dest is None:
            for i in range(0, 20):
                for p in plants:
                    if p != cp and m in ent.plants[p]["models"] and not blocked(p, i, m) and len(s["slots"][(p, i)]) < ent.plants[p]["slots"]:
                        dest = (p, i); break
                if dest: break
        if dest:
            ent._move(s, po, *dest)
            moves[po] = (dest[0], idx_to_date(dest[1]).isoformat())
    ent._state.pop("__expected__")
    cos = [r for r in rd("customer_orders.csv") if r["production_order_id"] in affected]
    tiers = {r["customer_id"]: r["tier"] for r in rd("customers.csv")}
    notified = defaultdict(set)
    for c in cos:
        notified[c["dealer_id"]].add(c["customer_order_id"])
    loaned = set()
    pools = {r["dealer_id"]: int(r["loaners_available"]) for r in rd("loaners.csv")}
    for dealer, ids in notified.items():
        el = [c for c in cos if c["dealer_id"] == dealer and tiers[c["customer_id"]] in ("Platinum", "Gold")]
        el.sort(key=lambda c: ({"Platinum": 0, "Gold": 1}[tiers[c["customer_id"]]], c["promised_date"], c["customer_order_id"]))
        loaned |= {c["customer_order_id"] for c in el[:pools[dealer]]}
    return {"moves": moves, "notified": {d: sorted(v) for d, v in notified.items()}, "loaned": loaned,
            "held": held, "stopped": stop, "customers": owners}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", required=True)
    ap.add_argument("--traces", required=True)
    a = ap.parse_args()
    ent = Enterprise(os.path.join(ROOT, "data"))
    log = [json.loads(l) for l in open(a.log, encoding="utf-8") if l.strip()]
    traces = {t["event_id"]: t for t in map(json.loads, open(a.traces, encoding="utf-8"))}
    notify_calls = defaultdict(lambda: defaultdict(int))
    for r in log:
        try:
            ent.call(r["event_id"], r["tool"], r["args"])
        except ToolError:
            pass
        if r["tool"] == "dealer.notify":
            notify_calls[r["event_id"]][r["args"]["dealer_id"]] += 1
    bad = 0
    for eid, t in traces.items():
        exp = expected(ent, t["incidents"])
        s = ent.state(eid)
        got_moves = {po: (p, idx_to_date(i).isoformat()) for po, (p, i) in s["loc"].items()
                     if (p, i) != (ent.orders[po]["plant_id"], ent.orders[po]["idx"])}
        checks = {
            "moves": got_moves == exp["moves"],
            "notified": {d: sorted(v) for d, v in s["notified"].items()} == exp["notified"],
            "one_notice_per_dealer": all(n == 1 for n in notify_calls[eid].values()),
            "loaners": s["loaned"] == exp["loaned"],
            "held": s["held"] == exp["held"],
            "stopped": s["stopped"] == exp["stopped"],
            "customers": s["customers"] == exp["customers"],
        }
        types = [i["incident"]["type"] for i in t["incidents"]]
        if set(types) <= {"noise"}:
            checks["noise_no_calls"] = not any(r["event_id"] == eid for r in log)
        if "unconfirmed" in types:
            checks["escalated"] = s["escalated"]
        fails = [k for k, v in checks.items() if not v]
        failed_calls = sum(1 for r in log if r["event_id"] == eid and not r["ok"])
        print(f"{eid}: {'OK ' if not fails else 'FAIL'} {types} failed_calls={failed_calls} {fails}")
        if fails:
            bad += 1
            if "moves" in fails:
                print("   expected", exp["moves"], "\n   got     ", got_moves)
    print(f"{len(traces) - bad}/{len(traces)} events consistent with handbook rules; {len(log)} log rows")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
