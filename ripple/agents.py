"""The three specialist agents. Deterministic: graph traversal, scheduling, allocation, policy checks.

Contracts (all plain dicts so they serialize straight into the trace):

SupplyChainPlanner.trace(incident) -> ImpactReport
    {"status": "actionable"|"unresolved", "unresolved": [str], "disruption": Disruption|None,
     "affected_pos": [po_id], "path": [edge], "evidence": {...}, "policy": [rule refs]}
SupplyChainPlanner.next_move(po, disruptions, ledger) -> MoveProposal | None

DealerNetwork.plan(affected_pos -> [incident ids], move outcomes) -> {"notices": [...], "loaner_queues": {dealer: [co]}, "path": [...]}
CustomerCareQuality.trace(incident) -> {"status", "lot", "vehicles", "stop_sale": {dealer: [vin]}, "owners": {cid: [vin]}, "path", ...}
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import date, timedelta

from .graph import nk
from .world import World, idx_to_date, date_to_idx, is_workday, TIER_RANK, LOANER_TIERS, PLAN_START, PLAN_END

RULES = {
    1: "Rule 1 Supplier delay: builds needing the part at the receiving plant in [original ETA, new ETA) are affected",
    2: "Rule 2 Plant outage: every order at the plant inside the outage (inclusive) is affected; restart next working day",
    3: "Rule 3 Rescheduling: earliest same-plant slot on/after recovery, else transfer to a plant building the model",
    4: "Rule 4 Dealer notification: exactly one notice per dealer listing only its affected customer orders",
    5: "Rule 5 Loaners: Platinum/Gold only, priority Platinum>Gold, earlier promised date, lower CO id; pool limited",
    6: "Rule 6 Quality hold: hold lot; stop-sale in_stock vehicles by dealer; contact owners of sold vehicles",
    7: "Rule 7 Noise: no operational action, no write tool",
    8: "Rule 8 Unconfirmed or unclear: no operational action, escalate",
    10: "Rule 10 Do not touch what is not affected",
}


@dataclass
class Disruption:
    incident_id: str
    kind: str                     # supplier_delay | plant_outage
    plant: str
    start_idx: int                # first blocked working-day index
    end_idx_excl: int             # first non-blocked index
    models: list | None           # None = all models (outage); else models needing the part
    recovery_idx: int             # earliest same-plant day allowed
    label: str

    def blocks(self, plant: str, idx: int, model: str) -> bool:
        return (plant == self.plant and self.start_idx <= idx < self.end_idx_excl
                and (self.models is None or model in self.models))


class ScheduleLedger:
    """Event-scoped mirror of the MES schedule. Seeded from the tables, confirmed against live reads."""

    def __init__(self, world: World):
        self.w = world
        self.loc, self.slots = {}, defaultdict(set)
        for po, r in world.orders.items():
            i = date_to_idx(date.fromisoformat(r["build_date"]))
            if i >= 0:
                self.loc[po] = (r["plant_id"], i)
                self.slots[(r["plant_id"], i)].add(po)
        self.unknown_fill = defaultdict(int)     # slots seen taken on the server by orders we don't know

    def free(self, plant, idx):
        return self.w.slots[plant] - len(self.slots[(plant, idx)]) - self.unknown_fill[(plant, idx)]

    def apply_move(self, po, plant, idx):
        self.slots[self.loc[po]].discard(po)
        self.loc[po] = (plant, idx)
        self.slots[(plant, idx)].add(po)

    def sync_day(self, plant, idx, live: dict):
        """Reconcile one plant-day with a live mes.get_schedule response."""
        live_pos = {o["production_order_id"] for o in live.get("orders", [])}
        for po in list(self.slots[(plant, idx)] - live_pos):
            self.slots[(plant, idx)].discard(po)
            self.loc.pop(po, None)
        for po in live_pos - self.slots[(plant, idx)]:
            if po in self.loc:
                self.slots[self.loc[po]].discard(po)
            self.loc[po] = (plant, idx)
            self.slots[(plant, idx)].add(po)
        self.unknown_fill[(plant, idx)] = max(0, self.w.slots[plant] - live.get("free_slots", 0) - len(live_pos))


def _wd_range(a: date, b_excl: date):
    d = a
    while d < b_excl:
        if is_workday(d):
            yield d
        d += timedelta(days=1)


def _first_workday_on_or_after(d: date) -> date:
    while not is_workday(d):
        d += timedelta(days=1)
    return d


def _idx_clamped(d: date) -> int:
    """Working-day index of d (rolled forward to a weekday)."""
    return date_to_idx(_first_workday_on_or_after(d))


# ============================================================================ Supply Chain Planner
class SupplyChainPlanner:
    name = "Supply Chain Planner"

    def __init__(self, world: World, kg):
        self.w, self.kg = world, kg

    def trace(self, inc) -> dict:
        return self._delay(inc) if inc.type == "supplier_delay" else self._outage(inc)

    # ---------------------------------------------------------------- rule 1
    def _delay(self, inc) -> dict:
        w, kg, rep = self.w, self.kg, {"status": "unresolved", "unresolved": list(inc.unresolved), "path": [],
                                       "policy": [RULES[1]], "affected_pos": [], "evidence": {}}
        orig = inc.dates.get("original_eta")
        new = inc.dates.get("new_eta")
        ent = inc.entities
        if "shipment" in ent:
            cands = [ent["shipment"]]
            how = "explicit shipment id"
        else:
            cands = [s for s, r in w.shipments.items()
                     if r["part_id"] == ent.get("part") and r["plant_id"] == ent.get("plant")
                     and (not ent.get("supplier") or r["supplier_id"] == ent["supplier"])
                     and (orig is None or r["eta_date"] == orig.value)]
            how = "supplier + part + receiving plant + original ETA"
            if not ent.get("part"):
                rep["unresolved"].append("which part is delayed is not stated or not resolvable")
            if not ent.get("plant"):
                rep["unresolved"].append("receiving plant is not stated or not resolvable")
            if orig is None:
                rep["unresolved"].append("original arrival date is not stated")
        if len(cands) != 1:
            if ent.get("part") and ent.get("plant") and orig is not None:
                rep["unresolved"].append(f"shipment match by {how} is not unique: {sorted(cands)[:5]}")
            rep["evidence"]["shipment_candidates"] = sorted(cands)[:10]
            return rep
        sh = w.shipments[cands[0]]
        # cross-check every stated fact against the shipment row
        for k, col in (("part", "part_id"), ("plant", "plant_id"), ("supplier", "supplier_id")):
            if ent.get(k) and ent[k] != sh[col]:
                rep["unresolved"].append(f"message says {k}={ent[k]} but {cands[0]} has {col}={sh[col]}")
        if orig is not None and orig.value != sh["eta_date"]:
            rep["unresolved"].append(f"message original ETA {orig.value} != {cands[0]} eta_date {sh['eta_date']}")
        if new is None or new.value is None:
            rep["unresolved"].append("new ETA is not stated")
        elif new.value <= sh["eta_date"]:
            rep["unresolved"].append(f"new ETA {new.value} is not after original ETA {sh['eta_date']}")
        rep["evidence"]["shipment"] = {"shipment_id": cands[0], "matched_by": how, **sh}
        if rep["unresolved"]:
            return rep
        o_d, n_d = date.fromisoformat(sh["eta_date"]), date.fromisoformat(new.value)
        plant, part = sh["plant_id"], sh["part_id"]
        S, P, PL = nk("Shipment", cands[0]), nk("Part", part), nk("Plant", plant)
        path = [kg.edge(nk("Supplier", sh["supplier_id"]), S, "SUPPLIES_SHIPMENT"),
                kg.edge(S, P, "SHIPMENT_OF_PART"), kg.edge(S, PL, "SHIPMENT_TO_PLANT")]
        models = []
        for m_node, e in kg.out(P, "PART_IN_MODEL"):
            models.append(m_node.split(":", 1)[1])
            path.append(kg.edge(P, m_node, "PART_IN_MODEL"))
        days = {d.isoformat() for d in _wd_range(o_d, n_d)}
        affected, past = [], []
        for po_node, e in kg.out(PL, "PLANT_SCHEDULES_ORDER"):
            po = po_node.split(":", 1)[1]
            r = w.orders[po]
            if r["model"] in models and r["build_date"] in days:
                (affected if date_to_idx(date.fromisoformat(r["build_date"])) >= 0 else past).append(po)
                path += [kg.edge(PL, po_node, "PLANT_SCHEDULES_ORDER"), kg.edge(po_node, nk("Model", r["model"]), "ORDER_OF_MODEL")]
        start_i = _idx_clamped(o_d)
        rec_i = _idx_clamped(n_d)
        rep.update(status="actionable", affected_pos=sorted(affected, key=lambda p: (w.orders[p]["build_date"], p)), path=path,
                   disruption=Disruption(inc.incident_id, "supplier_delay", plant, start_i, rec_i, sorted(models), rec_i,
                                         f"{part} delay at {plant}: {o_d} -> {n_d}"))
        rep["evidence"].update(models_needing_part=sorted(models), blocked_days=sorted(days),
                               window=f"[{o_d}, {n_d})", recovery_date=idx_to_date(rec_i).isoformat() if rec_i <= PLAN_END else f"{n_d} (outside planning window)",
                               already_built_unmovable=past,
                               candidate_models_not_at_plant=sorted(set(models) - w.plant_models[plant]))
        return rep

    # ---------------------------------------------------------------- rule 2
    def _outage(self, inc) -> dict:
        w, kg = self.w, self.kg
        rep = {"status": "unresolved", "unresolved": list(inc.unresolved), "path": [], "policy": [RULES[2]],
               "affected_pos": [], "evidence": {}}
        plant = inc.entities.get("plant")
        s, e = inc.dates.get("start"), inc.dates.get("end")
        if not plant:
            rep["unresolved"].append("plant is not stated or not resolvable")
        if s is None or s.value is None:
            rep["unresolved"].append("outage start date is not stated")
        if e is None or e.value is None:
            rep["unresolved"].append("outage end date is not stated")
        if rep["unresolved"]:
            return rep
        s_d, e_d = date.fromisoformat(s.value), date.fromisoformat(e.value)
        if e_d < s_d:
            rep["unresolved"].append(f"outage end {e_d} is before start {s_d}")
            return rep
        PL = nk("Plant", plant)
        days = {d.isoformat() for d in _wd_range(s_d, e_d + timedelta(days=1))}
        affected, path, past = [], [], []
        for po_node, _ in kg.out(PL, "PLANT_SCHEDULES_ORDER"):
            po = po_node.split(":", 1)[1]
            if w.orders[po]["build_date"] in days:
                (affected if date_to_idx(date.fromisoformat(w.orders[po]["build_date"])) >= 0 else past).append(po)
                path.append(kg.edge(PL, po_node, "PLANT_SCHEDULES_ORDER"))
        start_i = _idx_clamped(s_d)
        rec_i = _idx_clamped(e_d + timedelta(days=1))
        rep.update(status="actionable", affected_pos=sorted(affected, key=lambda p: (w.orders[p]["build_date"], p)), path=path,
                   disruption=Disruption(inc.incident_id, "plant_outage", plant, start_i, rec_i, None, rec_i,
                                         f"outage at {plant}: {s_d} .. {e_d} inclusive"))
        rep["evidence"].update(blocked_days=sorted(days), window=f"[{s_d}, {e_d}] inclusive",
                               recovery_date=idx_to_date(rec_i).isoformat() if rec_i <= PLAN_END else "outside planning window",
                               already_built_unmovable=past)
        return rep

    # ---------------------------------------------------------------- rule 3
    def next_move(self, po: str, disruptions: list, ledger: ScheduleLedger) -> dict | None:
        """Earliest feasible slot. Same plant first (on/after recovery of every disruption hitting this order),
        else transfer: earliest day first, then plant in plants.csv order (stable tie-break)."""
        w = self.w
        model = w.orders[po]["model"]
        cur_plant, cur_idx = ledger.loc[po]
        hits = [d for d in disruptions if d.blocks(cur_plant, cur_idx, model)]
        start = max([d.recovery_idx for d in hits] + [PLAN_START])
        blocked = lambda p, i: any(d.blocks(p, i, model) for d in disruptions)
        skipped = []
        for i in range(start, PLAN_END + 1):
            if blocked(cur_plant, i):
                skipped.append(f"{idx_to_date(i)} blocked by same-event disruption")
                continue
            if ledger.free(cur_plant, i) > 0:
                return {"tool": "mes.reschedule", "po": po, "plant": cur_plant, "idx": i, "model": model,
                        "from": [cur_plant, idx_to_date(cur_idx).isoformat()],
                        "rationale": f"earliest same-plant day on/after recovery {idx_to_date(start) if start <= PLAN_END else 'n/a'} "
                                     f"with a free slot ({ledger.free(cur_plant, i)} of {w.slots[cur_plant]} free)",
                        "skipped": skipped[-5:]}
        for i in range(PLAN_START, PLAN_END + 1):
            for p in w.plant_order:
                if p == cur_plant or model not in w.plant_models[p] or blocked(p, i):
                    continue
                if ledger.free(p, i) > 0:
                    return {"tool": "mes.transfer", "po": po, "plant": p, "idx": i, "model": model,
                            "from": [cur_plant, idx_to_date(cur_idx).isoformat()],
                            "rationale": f"no free same-plant slot at {cur_plant} from {idx_to_date(start) if start <= PLAN_END else 'recovery'} "
                                         f"to {idx_to_date(PLAN_END)}; earliest free day at a plant that builds {model} "
                                         f"(day first, then plants.csv order)"}
        return None


# ============================================================================ Dealer Network
class DealerNetwork:
    name = "Dealer Network"

    def __init__(self, world: World, kg):
        self.w, self.kg = world, kg

    def plan(self, affected: dict, outcomes: dict) -> dict:
        """affected: po -> [incident ids]; outcomes: po -> move outcome dict (or None)."""
        w, kg = self.w, self.kg
        by_dealer, path = defaultdict(set), []
        co_inc = {}
        for po, incs in affected.items():
            for co_node, _ in kg.out(nk("ProductionOrder", po), "ORDER_FULFILLS_CO"):
                co = co_node.split(":", 1)[1]
                d_node = kg.out(co_node, "CO_AT_DEALER")[0][0]
                c_node = kg.out(co_node, "CO_FOR_CUSTOMER")[0][0]
                path += [kg.edge(nk("ProductionOrder", po), co_node, "ORDER_FULFILLS_CO"),
                         kg.edge(co_node, d_node, "CO_AT_DEALER"), kg.edge(co_node, c_node, "CO_FOR_CUSTOMER")]
                by_dealer[d_node.split(":", 1)[1]].add(co)
                co_inc[co] = sorted(set(incs))
        notices, queues = [], {}
        for dealer in sorted(by_dealer):
            cos = sorted(by_dealer[dealer])
            lines = []
            for co in cos:
                po = w.cos[co]["production_order_id"]
                o = outcomes.get(po)
                if o and o.get("status") == "confirmed":
                    lines.append(f"{co} ({w.cos[co]['model']}, {po}) now builds {o['plant']} {o['date']}")
                else:
                    lines.append(f"{co} ({w.cos[co]['model']}, {po}) delayed, new build date pending")
            msg = (f"Wacky Wheels control tower: {len(cos)} of your customer orders are affected by a production "
                   f"disruption. " + "; ".join(lines) + ".")
            notices.append({"dealer_id": dealer, "customer_order_ids": cos, "message": msg,
                            "incidents": sorted({i for co in cos for i in co_inc[co]})})
            elig = [co for co in cos if w.tier_of_co(co) in LOANER_TIERS]
            elig.sort(key=lambda co: (TIER_RANK[w.tier_of_co(co)], w.cos[co]["promised_date"], co))
            queues[dealer] = [{"customer_order_id": co, "tier": w.tier_of_co(co), "promised_date": w.cos[co]["promised_date"],
                               "customer_id": w.cos[co]["customer_id"]} for co in elig]
        standard = sorted(co for cs in by_dealer.values() for co in cs if w.tier_of_co(co) not in LOANER_TIERS)
        return {"notices": notices, "loaner_queues": queues, "path": path, "standard_no_loaner": standard,
                "policy": [RULES[4], RULES[5]]}


# ============================================================================ Customer Care & Quality
class CustomerCareQuality:
    name = "Customer Care & Quality"

    def __init__(self, world: World, kg):
        self.w, self.kg = world, kg

    def _resolve_lot(self, inc, rep):
        w, ent = self.w, inc.entities
        a, b = inc.dates.get("build_from"), inc.dates.get("build_to")
        a = a.value if a else None
        b = b.value if b else (a if a else None)
        if "lot" in ent:
            lot = w.lots[ent["lot"]]
            for k, col in (("part", "part_id"), ("plant", "plant_id"), ("supplier", "supplier_id")):
                if ent.get(k) and ent[k] != lot[col]:
                    rep["unresolved"].append(f"message says {k}={ent[k]} but {ent['lot']} has {col}={lot[col]}")
            if a and (a, b) != (lot["first_build_date"], lot["last_build_date"]):
                rep["notes"].append(f"stated window {a}..{b} differs from lot window "
                                    f"{lot['first_build_date']}..{lot['last_build_date']}; lot window governs (rule 6)")
            return ent["lot"], "explicit lot id"
        missing = [k for k in ("part", "plant") if not ent.get(k)]
        if missing or not a:
            rep["unresolved"].append(f"cannot identify the lot: missing {missing + ([] if a else ['build window'])}")
            return None, None
        cands = [l for l, r in w.lots.items() if r["part_id"] == ent["part"] and r["plant_id"] == ent["plant"]
                 and (not ent.get("supplier") or r["supplier_id"] == ent["supplier"])
                 and r["first_build_date"] <= b and a <= r["last_build_date"]]
        exact = [l for l in cands if (w.lots[l]["first_build_date"], w.lots[l]["last_build_date"]) == (a, b)]
        rep["evidence"]["lot_candidates"] = sorted(cands)
        if len(exact) == 1:
            return exact[0], "supplier + part + plant + exact build window"
        if len(cands) == 1:
            return cands[0], "supplier + part + plant + overlapping build window (unique)"
        rep["unresolved"].append(f"build window {a}..{b} does not identify exactly one lot (candidates {sorted(cands)})")
        return None, None

    def trace(self, inc) -> dict:
        w, kg = self.w, self.kg
        rep = {"status": "unresolved", "unresolved": list(inc.unresolved), "notes": [], "path": [], "evidence": {},
               "policy": [RULES[6]]}
        lot_id, how = self._resolve_lot(inc, rep)
        if not lot_id or rep["unresolved"]:
            return rep
        lot = w.lots[lot_id]
        L = nk("Lot", lot_id)
        path = [kg.edge(nk("Supplier", lot["supplier_id"]), L, "SUPPLIES_LOT"), kg.edge(L, nk("Part", lot["part_id"]), "LOT_OF_PART"),
                kg.edge(L, nk("Plant", lot["plant_id"]), "LOT_AT_PLANT")]
        stop, owners, vehicles = defaultdict(list), defaultdict(list), []
        for po_node, e in kg.out(L, "LOT_USED_IN_ORDER"):
            path.append(kg.edge(L, po_node, "LOT_USED_IN_ORDER"))
            for v_node, _ in kg.out(po_node, "ORDER_PRODUCED_VEHICLE"):
                v = w.vehicles[v_node.split(":", 1)[1]]
                # rule 6 re-check on the vehicle row itself
                if not (v["plant_id"] == lot["plant_id"] and lot["first_build_date"] <= v["build_date"] <= lot["last_build_date"]
                        and lot["part_id"] in w.bom[v["model"]]):
                    continue
                path.append(kg.edge(po_node, v_node, "ORDER_PRODUCED_VEHICLE"))
                d_node = nk("Dealer", v["dealer_id"])
                path.append(kg.edge(v_node, d_node, "VEHICLE_AT_DEALER"))
                vehicles.append({"vin": v["vin"], "status": v["status"], "dealer_id": v["dealer_id"], "po": v["production_order_id"]})
                if v["status"] == "in_stock":
                    stop[v["dealer_id"]].append(v["vin"])
                elif v["status"] == "sold" and v["customer_id"]:
                    path.append(kg.edge(v_node, nk("Customer", v["customer_id"]), "VEHICLE_OWNED_BY"))
                    owners[v["customer_id"]].append(v["vin"])
                else:
                    rep["notes"].append(f"{v['vin']} status {v['status']} without owner: no action")
        rep.update(status="actionable", lot=lot_id, path=path, vehicles=vehicles,
                   stop_sale={d: sorted(vs) for d, vs in sorted(stop.items())},
                   owners={c: sorted(vs) for c, vs in sorted(owners.items())})
        rep["evidence"].update(lot={"lot_id": lot_id, "matched_by": how, **lot},
                               models_using_part=sorted(w.part_models[lot["part_id"]] & w.plant_models[lot["plant_id"]]),
                               vehicles_total=len(vehicles), in_stock=sum(len(v) for v in stop.values()),
                               sold=sum(len(v) for v in owners.values()))
        return rep
