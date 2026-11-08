"""'Why this action': everything that justifies one recorded tool call, read from the trace only.

For a call it returns:
  rule      the handbook rule the agent cited, with the rule's full text from data/policy_handbook.md
  evidence  the words in the message, how names became ids (and from which table), how dates were resolved
  chain     the knowledge-graph edges linking the incident's root (shipment, lot or plant) to the call's target,
            each with the CSV table and row that justify it
  checks    the guardrails this call passed before it was sent, plus the server's answer
Read-only: nothing is recomputed against the data, so it explains exactly what the run did.
"""
from __future__ import annotations

import re

import networkx as nx

ARG_TYPES = {"production_order_id": "ProductionOrder", "customer_order_id": "CustomerOrder", "customer_order_ids": "CustomerOrder",
             "dealer_id": "Dealer", "vins": "Vehicle", "customer_id": "Customer", "lot_id": "Lot", "plant_id": "Plant"}
ROOTS = ("Shipment", "Lot")

# Exactly what Coordinator._validate checks before a write is sent (a failed check blocks the call).
KEYS = "argument keys match the live /tools schema"
CHECKS = {
    "mes.reschedule": [KEYS, "production order exists"],
    "mes.transfer": [KEYS, "production order exists", "destination plant builds this model (plant_models.csv)"],
    "dealer.notify": [KEYS, "customer order list is not empty", "every customer order listed belongs to this dealer"],
    "crm.assign_loaner": [KEYS],
    "dealer.stop_sale": [KEYS, "every VIN is an unsold (in_stock) vehicle at this dealer"],
    "crm.notify_customer": [KEYS, "customer exists"],
    "quality.hold_lot": [KEYS, "lot exists"],
}


def handbook_rules(path: str = "data/policy_handbook.md") -> dict:
    text = open(path, encoding="utf-8").read()
    sec = text.split("## Rules", 1)[1].split("\n## ", 1)[0]
    return {int(m.group(1)): m.group(2).strip() for m in re.finditer(r"^(\d+)\.\s+(.+)$", sec, re.M)}


def _targets(args: dict) -> list:
    out = []
    for k, v in args.items():
        if k in ARG_TYPES:
            for x in (v if isinstance(v, list) else [v]):
                out.append(f"{ARG_TYPES[k]}:{x}")
    return out


def _edges(trace: dict, incident_ids: list) -> list:
    es = []
    for e in trace["incidents"]:
        if not incident_ids or e["incident"]["incident_id"] in incident_ids:
            es += (e.get("impact") or {}).get("path", [])
    es += (trace.get("dealer_plan") or {}).get("path", [])
    return es


def chain(trace: dict, rec: dict) -> dict:
    """Provenance chains (over the edges the run used) from the incident root to the call's first target.

    Returns every simple path at most one hop longer than the shortest, so a supplier delay shows both
    why the plant (shipment -> plant -> order) and why the part (shipment -> part -> model <- order)."""
    edges = _edges(trace, rec.get("incidents") or [])
    every = _targets(rec["args"])
    more = max(0, len([x for x in every if not x.startswith("Dealer:")] or every) - 1)
    if not edges:
        return {"paths": [], "target": None, "more_targets": 0}
    g = nx.Graph()
    for e in edges:
        g.add_edge(e["src"], e["dst"], **e)
    roots = [n for n in g if n.split(":")[0] in ROOTS] or [n for n in g if n.startswith("Plant:")]
    targets = [t for t in every if t in g]
    # the orders / vehicles are the interesting target; the dealer is appended at the end of the chain
    targets = [t for t in targets if not t.startswith("Dealer:")] or targets
    if not targets:
        return {"paths": [], "target": None, "more_targets": 0}
    t = targets[0]
    if t in roots:                               # e.g. quality.hold_lot: show the facts about the lot itself
        own = [dict(g.edges[t, n]) for n in g[t] if g.edges[t, n]["etype"] != "LOT_USED_IN_ORDER"]
        return {"paths": [own] if own else [], "target": t, "more_targets": more}
    found = []
    for r in roots:
        try:
            n = nx.shortest_path_length(g, r, t)
        except nx.NetworkXNoPath:
            continue
        found += list(nx.all_simple_paths(g, r, t, cutoff=n + 1))
    if not found:
        return {"paths": [], "target": t, "more_targets": more}
    found = sorted(found, key=len)[:3]
    if "dealer_id" in rec["args"]:
        d = f"Dealer:{rec['args']['dealer_id']}"
        found = [p + [d] if g.has_edge(p[-1], d) else p for p in found]
    paths = [[dict(g.edges[a, b]) for a, b in zip(p, p[1:])] for p in found]
    return {"paths": paths, "target": t, "more_targets": more}


def explain(trace: dict, seq: int, rules: dict | None = None, where: str = "organizer server") -> dict:
    rec = next(r for r in trace["execution"] if r["seq"] == seq)
    rules = rules or handbook_rules()
    m = re.match(r"Rule (\d+)", rec.get("rule") or "")
    num = int(m.group(1)) if m else None
    incs = [e for e in trace["incidents"] if e["incident"]["incident_id"] in (rec.get("incidents") or [])]
    evidence = [{"incident_id": e["incident"]["incident_id"], "type": e["incident"]["type"],
                 "quote": e["incident"].get("evidence_span", ""),
                 "names": [{"phrase": x["phrase"], "id": x["id"], "source": x.get("source")} for x in e["incident"].get("entity_evidence", [])],
                 "dates": [{"role": k, "phrase": v["phrase"], "value": v["value"], "rule": v.get("rule")}
                           for k, v in e["incident"].get("dates", {}).items()]} for e in incs]
    checks = list(CHECKS.get(rec["tool"], []))
    extra = []
    if rec["tool"] in ("mes.reschedule", "mes.transfer"):
        po = rec["args"]["production_order_id"]
        read = next((r for r in reversed(trace["execution"]) if r["seq"] < seq and r["tool"] == "mes.get_schedule"
                     and po in (r.get("purpose") or "")), None)
        if read and read.get("body"):
            extra.append(f"live mes.get_schedule read just before (call #{read['seq']}): "
                         f"{read['body'].get('free_slots')} free slot(s) at {read['args']['plant_id']} on {read['args']['date']}")
    if rec["tool"] == "crm.assign_loaner":
        q = next((x for x in trace.get("loaners", []) if x["customer_order_id"] == rec["args"]["customer_order_id"]), None)
        if q:
            extra.append(f"priority queue: {q['tier']}, promised {q['promised_date']}, {q['why']}")
    if rec["tool"] == "quality.hold_lot":
        for e in incs:
            lot = ((e.get("impact") or {}).get("evidence") or {}).get("lot")
            cands = ((e.get("impact") or {}).get("evidence") or {}).get("lot_candidates", [])
            if lot:
                extra.append(f"lot matched by {lot['matched_by']} ({len(cands)} candidate)")
    srv = (f"{where} accepted it (HTTP {rec.get('http')})" if rec["status"] == "confirmed"
           else f"{rec['status']}: {rec.get('error')}")
    return {"seq": seq, "tool": rec["tool"], "args": rec["args"], "kind": rec["kind"], "agent": rec.get("agent"),
            "purpose": rec.get("purpose"), "rule_label": rec.get("rule"), "rule_number": num,
            "rule_text": rules.get(num) if num else None, "evidence": evidence, "chain": chain(trace, rec),
            "checks": checks, "observed": extra, "server": srv}
