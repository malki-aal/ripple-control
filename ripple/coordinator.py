"""Coordinator agent: understand -> resolve -> route -> combine -> validate -> execute -> trace.

The LLM (or rule extractor) only proposes incident facts. Everything that decides a write is
deterministic code here and in agents.py, and every write is validated before it is sent.
"""
from __future__ import annotations

import time
from collections import defaultdict

from .agents import (RULES, CustomerCareQuality, DealerNetwork, ScheduleLedger, SupplyChainPlanner)
from .extract import RuleExtractor, validate_raw
from .resolve import Resolver
from .world import idx_to_date, PLAN_END

EXPECTED_TOOLS = {
    "mes.get_schedule": {"plant_id", "date"}, "mes.reschedule": {"production_order_id", "new_date"},
    "mes.transfer": {"production_order_id", "to_plant_id", "new_date"},
    "dealer.notify": {"dealer_id", "customer_order_ids", "message"}, "dealer.stop_sale": {"dealer_id", "vins"},
    "crm.loaner_availability": {"dealer_id"}, "crm.assign_loaner": {"customer_order_id"},
    "crm.notify_customer": {"customer_id", "message"}, "quality.hold_lot": {"lot_id"}, "escalate": {"reason"},
}


def check_tool_schema(tools) -> list[str]:
    """Compare the runtime /tools schema with the mapping this code was written against."""
    if isinstance(tools, dict):
        live = {k: set(v["args"]) for k, v in tools.items()}
    else:
        live = {t["tool"]: set(t["args"]) for t in tools}
    problems = []
    for name, keys in EXPECTED_TOOLS.items():
        if name not in live:
            problems.append(f"missing tool {name}")
        elif live[name] != keys:
            problems.append(f"{name} args {sorted(live[name])} != expected {sorted(keys)}")
    return problems


class Coordinator:
    name = "Coordinator"

    def __init__(self, world, kg, extractor, client):
        self.w, self.kg, self.ex, self.client = world, kg, extractor, client
        self.rules = RuleExtractor(world)
        self.resolver = Resolver(world)
        self.planner = SupplyChainPlanner(world, kg)
        self.dealer = DealerNetwork(world, kg)
        self.quality = CustomerCareQuality(world, kg)

    # ------------------------------------------------------------------ helpers
    def _call(self, trace, tool, args, purpose, agent, rule=None, incidents=()):
        rec = self.client.call(trace["event_id"], tool, args, purpose)
        rec.update(agent=agent, rule=rule, incidents=list(incidents))
        trace["execution"].append(rec)
        return rec

    def _validate(self, tool, args) -> str | None:
        w = self.w
        if set(args) != EXPECTED_TOOLS[tool]:
            return f"arg keys {sorted(args)} do not match schema"
        if tool in ("mes.reschedule", "mes.transfer") and args["production_order_id"] not in w.orders:
            return "unknown production order"
        if tool == "mes.transfer" and w.orders[args["production_order_id"]]["model"] not in w.plant_models[args["to_plant_id"]]:
            return "destination plant does not build the model"
        if tool == "dealer.notify":
            if not args["customer_order_ids"]:
                return "empty customer order list"
            if any(w.cos[c]["dealer_id"] != args["dealer_id"] for c in args["customer_order_ids"]):
                return "customer order not at this dealer"
        if tool == "dealer.stop_sale":
            if not args["vins"] or any(w.vehicles[v]["dealer_id"] != args["dealer_id"] or w.vehicles[v]["status"] != "in_stock"
                                       for v in args["vins"]):
                return "VIN not an unsold vehicle at this dealer"
        if tool == "crm.notify_customer" and args["customer_id"] not in w.customers:
            return "unknown customer"
        if tool == "quality.hold_lot" and args["lot_id"] not in w.lots:
            return "unknown lot"
        return None

    def _write(self, trace, tool, args, purpose, agent, rule, incidents):
        problem = self._validate(tool, args)
        if problem:
            trace["blocked"].append({"tool": tool, "args": args, "reason": problem, "agent": agent})
            return {"status": "blocked", "error": problem}
        return self._call(trace, tool, args, purpose, agent, rule, incidents)

    # ------------------------------------------------------------------ understanding
    def understand(self, event) -> tuple[list, dict]:
        meta = {"extractor": getattr(self.ex, "model_id", "?"), "fallback": None}
        t0 = time.perf_counter()
        try:
            raw = self.ex.extract(event["text"])
            validate_raw(raw)
        except Exception as e:                       # LLM down or invalid JSON -> deterministic fallback
            meta["fallback"] = f"{type(e).__name__}: {e}"
            meta["extractor"] = self.rules.model_id
            raw = self.rules.extract(event["text"])
        meta["extract_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        meta["extractor"] = getattr(self.ex, "model_id", meta["extractor"]) if not meta["fallback"] else meta["extractor"]
        if getattr(self.ex, "last_usage", None) and not meta["fallback"]:
            meta["tokens"] = {k: self.ex.last_usage.get(k) for k in ("promptTokenCount", "candidatesTokenCount", "totalTokenCount")}
        if self.ex is not self.rules and not meta["fallback"]:
            # second opinion: deterministic extractor on the same text (recorded, used for review, never for writes)
            second = [r["type"] for r in self.rules.extract(event["text"])["incidents"]]
            first = [r["type"] for r in raw["incidents"]]
            meta["cross_check"] = {"llm": first, "rules": second, "agree": sorted(first) == sorted(second)}
        incs = [self.resolver.resolve(event, r, i) for i, r in enumerate(raw["incidents"], 1)]
        return incs, meta

    # ------------------------------------------------------------------ main entry
    def handle(self, event: dict) -> dict:
        t0 = time.perf_counter()
        trace = {"event_id": event["event_id"], "received_at": event["received_at"], "source": event["source"],
                 "incidents": [], "plan": [], "execution": [], "blocked": [], "escalations": [], "summary": ""}
        incs, meta = self.understand(event)
        trace["understanding"] = meta
        disruptions, affected, quality_reps, escalate_reasons = [], defaultdict(list), [], []

        # ---- route each incident to its specialist
        for inc in incs:
            entry = {"incident": inc.to_dict(), "agent": None, "impact": None, "decision": None}
            if inc.type == "noise":
                entry.update(agent=self.name, decision="no action", policy=[RULES[7]],
                             reason=f"Not operational: {inc.extractor_reason}. No supplier, plant, part, shipment or lot "
                                    f"incident language with a resolvable entity.")
            elif inc.type == "unconfirmed" or not inc.confirmed:
                need = "confirm the source, the affected part/plant/supplier, and concrete dates"
                ents = {k: v for k, v in inc.entities.items()}
                reason = (f"Unconfirmed report ({inc.extractor_reason}); entities named: {ents or 'none'}. "
                          f"No operational action taken. Human should {need}.")
                entry.update(agent=self.name, decision="escalate", policy=[RULES[8]], reason=reason)
                escalate_reasons.append(f"[{inc.incident_id}] {reason}")
            elif inc.type in ("supplier_delay", "plant_outage"):
                rep = self.planner.trace(inc)
                entry.update(agent=self.planner.name, impact=_jsonable(rep))
                if rep["status"] == "actionable":
                    entry["decision"] = f"act on {len(rep['affected_pos'])} affected production orders"
                    disruptions.append(rep["disruption"])
                    for po in rep["affected_pos"]:
                        affected[po].append(inc.incident_id)
                else:
                    entry["decision"] = "escalate (unresolved)"
                    escalate_reasons.append(f"[{inc.incident_id}] {inc.type} could not be resolved: "
                                            + "; ".join(rep["unresolved"]) + ". Human must verify before any change.")
            elif inc.type == "quality_hold":
                rep = self.quality.trace(inc)
                entry.update(agent=self.quality.name, impact=_jsonable(rep))
                if rep["status"] == "actionable":
                    entry["decision"] = f"hold {rep['lot']}, stop-sale {rep['evidence']['in_stock']} VINs, contact {len(rep['owners'])} owners"
                    quality_reps.append((inc, rep))
                else:
                    entry["decision"] = "escalate (unresolved)"
                    escalate_reasons.append(f"[{inc.incident_id}] quality hold could not be resolved: "
                                            + "; ".join(rep["unresolved"]) + ". Human must verify before any change.")
            trace["incidents"].append(entry)

        # ---- Supply Chain Planner: sequential moves on one event-scoped ledger
        outcomes = {}
        if affected:
            ledger = ScheduleLedger(self.w)
            order = sorted(affected, key=lambda p: (min(i for i in affected[p]), self.w.orders[p]["build_date"], p))
            for po in order:
                outcomes[po] = self._move(trace, po, disruptions, ledger, affected[po])

        # ---- Dealer Network: one notice per dealer (union across incidents), loaners by priority
        if affected:
            dplan = self.dealer.plan(dict(affected), outcomes)
            trace["dealer_plan"] = {"path": dplan["path"], "standard_no_loaner": dplan["standard_no_loaner"],
                                    "loaner_queues": dplan["loaner_queues"], "policy": dplan["policy"]}
            for n in dplan["notices"]:
                trace["plan"].append({"agent": self.dealer.name, "tool": "dealer.notify", "dealer_id": n["dealer_id"],
                                      "customer_order_ids": n["customer_order_ids"], "rule": RULES[4]})
                self._write(trace, "dealer.notify", {"dealer_id": n["dealer_id"], "customer_order_ids": n["customer_order_ids"],
                                                     "message": n["message"]},
                            f"notify dealer of {len(n['customer_order_ids'])} affected customer orders", self.dealer.name,
                            RULES[4], n["incidents"])
            trace["loaners"] = []
            for dealer, queue in dplan["loaner_queues"].items():
                if not queue:
                    continue
                avail = self._call(trace, "crm.loaner_availability", {"dealer_id": dealer},
                                   f"check pool before assigning to {len(queue)} eligible customers", self.dealer.name, RULES[5])
                n = avail["body"]["available"] if avail["status"] == "confirmed" else 0
                for rank, q in enumerate(queue):
                    if rank >= n:
                        trace["loaners"].append({**q, "dealer_id": dealer, "rank": rank + 1, "assigned": False,
                                                 "why": f"pool exhausted ({n} available at {dealer})"})
                        continue
                    r = self._write(trace, "crm.assign_loaner", {"customer_order_id": q["customer_order_id"]},
                                    f"loaner rank {rank + 1} at {dealer} ({q['tier']}, promised {q['promised_date']})",
                                    self.dealer.name, RULES[5], affected[self.w.cos[q['customer_order_id']]['production_order_id']])
                    trace["loaners"].append({**q, "dealer_id": dealer, "rank": rank + 1, "assigned": r.get("status") == "confirmed",
                                             "why": f"rank {rank + 1} of {len(queue)} eligible; {n} in pool"})

        # ---- Customer Care & Quality
        held = set()
        for inc, rep in quality_reps:
            iid = [inc.incident_id]
            if rep["lot"] not in held:
                self._write(trace, "quality.hold_lot", {"lot_id": rep["lot"]}, "hold defective lot", self.quality.name, RULES[6], iid)
                held.add(rep["lot"])
            for dealer, vins in rep["stop_sale"].items():
                self._write(trace, "dealer.stop_sale", {"dealer_id": dealer, "vins": vins},
                            f"stop sale of {len(vins)} unsold affected vehicles", self.quality.name, RULES[6], iid)
            for cid, vins in rep["owners"].items():
                msg = (f"Wacky Wheels Customer Care: your vehicle ({', '.join(vins)}) was built with a part from lot "
                       f"{rep['lot']} that is under quality hold. Please contact your dealer to schedule an inspection.")
                self._write(trace, "crm.notify_customer", {"customer_id": cid, "message": msg},
                            f"contact owner of {len(vins)} affected sold vehicle(s)", self.quality.name, RULES[6], iid)

        # ---- failed / unknown writes and unmovable orders need a human
        for rec in trace["execution"]:
            if rec["kind"] == "write" and rec["status"] == "unknown" and not rec.get("reconciled"):
                escalate_reasons.append(f"write {rec['tool']} {rec['args']} timed out; outcome unknown and not retried")
        for po, o in outcomes.items():
            if o["status"] != "confirmed":
                escalate_reasons.append(f"{po} could not be moved ({o.get('why')}); needs manual planning")

        if escalate_reasons:
            reason = " | ".join(escalate_reasons)
            trace["escalations"].append(reason)
            self._call(trace, "escalate", {"reason": reason[:2000]}, "human review", self.name, RULES[8])

        trace["summary"] = summarize(trace)
        trace["duration_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        return trace

    # ------------------------------------------------------------------ one order move
    def _move(self, trace, po, disruptions, ledger, incs, attempts=3) -> dict:
        for _ in range(attempts):
            prop = self.planner.next_move(po, disruptions, ledger)
            if prop is None:
                return {"status": "no_slot", "why": "no feasible slot at any compatible plant in the planning window"}
            day = idx_to_date(prop["idx"]).isoformat()
            # live read before writing: confirm the slot really is free
            live = self._call(trace, "mes.get_schedule", {"plant_id": prop["plant"], "date": day},
                              f"confirm free slot for {po}", self.planner.name, RULES[3], incs)
            if live["status"] == "confirmed":
                ledger.sync_day(prop["plant"], prop["idx"], live["body"])
                if live["body"]["free_slots"] <= 0:
                    continue                                # ledger was stale; re-plan
            args = ({"production_order_id": po, "new_date": day} if prop["tool"] == "mes.reschedule"
                    else {"production_order_id": po, "to_plant_id": prop["plant"], "new_date": day})
            trace["plan"].append({"agent": self.planner.name, "tool": prop["tool"], "production_order_id": po,
                                  "from": prop["from"], "to": [prop["plant"], day], "rationale": prop["rationale"],
                                  "rule": RULES[3], "incidents": incs})
            rec = self._write(trace, prop["tool"], args, prop["rationale"], self.planner.name, RULES[3], incs)
            if rec.get("status") == "confirmed":
                ledger.apply_move(po, prop["plant"], prop["idx"])
                return {"status": "confirmed", "tool": prop["tool"], "plant": prop["plant"], "date": day, "from": prop["from"]}
            if rec.get("status") == "unknown":
                # reconcile through a supported read instead of blindly retrying the write
                chk = self._call(trace, "mes.get_schedule", {"plant_id": prop["plant"], "date": day},
                                 f"reconcile unknown outcome for {po}", self.planner.name, RULES[3], incs)
                if chk["status"] == "confirmed" and any(o["production_order_id"] == po for o in chk["body"]["orders"]):
                    rec["reconciled"] = "applied (confirmed by mes.get_schedule)"
                    ledger.apply_move(po, prop["plant"], prop["idx"])
                    return {"status": "confirmed", "tool": prop["tool"], "plant": prop["plant"], "date": day,
                            "from": prop["from"], "reconciled": True}
                return {"status": "unknown", "why": "write timed out and could not be reconciled"}
            if rec.get("status") == "blocked":
                return {"status": "blocked", "why": rec["error"]}
            # rejected: refresh this day and try the next candidate
            ledger.unknown_fill[(prop["plant"], prop["idx"])] = ledger.w.slots[prop["plant"]]
        return {"status": "failed", "why": "slot attempts exhausted"}


def _jsonable(rep):
    from dataclasses import asdict, is_dataclass
    return {k: (asdict(v) if is_dataclass(v) else v) for k, v in rep.items()}


def summarize(trace) -> str:
    """One concise explanation per event, generated only from recorded facts."""
    parts = []
    ex = trace["execution"]
    ok = lambda t: [r for r in ex if r["tool"] == t and r["status"] == "confirmed"]
    for e in trace["incidents"]:
        inc = e["incident"]
        if e["decision"] == "no action":
            parts.append(f"{inc['incident_id']} noise: {e['reason']}")
        elif e["decision"] == "escalate" or (e["decision"] or "").startswith("escalate"):
            why = e.get("reason") or "; ".join((e.get("impact") or {}).get("unresolved", []))
            parts.append(f"{inc['incident_id']} {inc['type']}: escalated to a human, no operational change. {why}")
        else:
            imp = e["impact"]
            ev = imp.get("evidence", {})
            if inc["type"] == "quality_hold":
                parts.append(f"{inc['incident_id']} quality hold: lot {imp['lot']} ({ev['lot']['matched_by']}), "
                             f"{ev['vehicles_total']} vehicles traced via derived lot->order edges; "
                             f"{ev['in_stock']} unsold VINs at {len(imp['stop_sale'])} dealers stopped, {len(imp['owners'])} owners contacted.")
            else:
                d = imp["disruption"]
                parts.append(f"{inc['incident_id']} {inc['type'].replace('_', ' ')}: {d['label']}; window {ev.get('window')}; "
                             f"{len(imp['affected_pos'])} production orders affected"
                             + (f" (models {', '.join(ev['models_needing_part'])})" if ev.get('models_needing_part') else "") + ".")
    moves = ok("mes.reschedule") + ok("mes.transfer")
    if moves:
        parts.append(f"Moves: {len(ok('mes.reschedule'))} rescheduled, {len(ok('mes.transfer'))} transferred. "
                     f"Dealers notified: {len(ok('dealer.notify'))}. Loaners assigned: {len(ok('crm.assign_loaner'))}"
                     + (f" ({sum(1 for l in trace.get('loaners', []) if not l['assigned'])} eligible customers left without one: pool exhausted)"
                        if any(not l['assigned'] for l in trace.get('loaners', [])) else "") + ".")
    fails = [r for r in ex if r["status"] in ("rejected", "unknown")]
    if fails:
        parts.append(f"{len(fails)} tool calls failed: " + "; ".join(f"{r['tool']} {r.get('error')}" for r in fails[:3]))
    if trace["blocked"]:
        parts.append(f"{len(trace['blocked'])} proposed writes blocked by validation.")
    return " ".join(parts)
