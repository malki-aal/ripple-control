"""Ripple: control tower UI.

    streamlit run app.py -- --run submission --events data/events.json [--similar path/to/similar_incidents.json]

Reads only recorded run artifacts (event_traces.jsonl, action_log.jsonl, client_calls.jsonl, graph/,
similar_incidents.json), so it shows exactly what the agents did. No tool calls are made from the UI.

The screen is calm (tan and beige) until it shows a live problem: a real disruption, an escalation, or a failed
check. Then it switches to mission control (dark with red).
"""
import argparse
import csv
import json
import os
import re
from collections import Counter

import pandas as pd
import streamlit as st

from ui import components as C
from ui.components import TYPE_LABEL, esc
from ui.graph import dot_graph, incident_edges, legend, nid, ntype, ontology_dot
from ui.similar import load_similar, neighbours
from ui.theme import css, logo_svg, palette

st.set_page_config(page_title="Ripple", page_icon=":material/waves:", layout="wide", initial_sidebar_state="collapsed")

REAL = {"supplier_delay", "plant_outage", "quality_hold"}
VIEWS = ["Event feed", "Human review", "Audit trail", "Knowledge graph", "Run summary"]


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="runs/run1")
    ap.add_argument("--events", default="data/events.json")
    ap.add_argument("--similar", default=None, help="optional path to a similar_incidents.json")
    try:
        return ap.parse_args()
    except SystemExit:
        return ap.parse_args([])


@st.cache_data
def load(run_dir, events_path):
    def rl(p):
        if not os.path.exists(p):
            return []
        with open(p, encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]

    def rj(p):
        if not os.path.exists(p):
            return {}
        with open(p, encoding="utf-8") as f:
            return json.load(f)

    traces = rl(os.path.join(run_dir, "event_traces.jsonl"))
    log_path = os.path.join(run_dir, "action_log.jsonl")
    log = rl(log_path)
    calls = rl(os.path.join(run_dir, "client_calls.jsonl"))
    manifest = rj(os.path.join(run_dir, "run_manifest.json"))
    onto = rj(os.path.join(run_dir, "graph", "ontology.json"))
    events = {e["event_id"]: e for e in (rj(events_path) or [])}
    return traces, log, os.path.exists(log_path), calls, manifest, onto, events


@st.cache_data
def load_names(data_dir):
    """Display names for IDs, read from the organizer's reference CSVs (read-only)."""
    out = {}
    for fname, key in [("parts.csv", "part_id"), ("plants.csv", "plant_id"), ("suppliers.csv", "supplier_id"),
                       ("dealers.csv", "dealer_id")]:
        p = os.path.join(data_dir, fname)
        if os.path.exists(p):
            with open(p, encoding="utf-8", newline="") as f:
                for row in csv.DictReader(f):
                    out[row[key]] = row.get("name", "")
    return out


# ============================================================================ data
args = parse_args()
traces, log, log_exists, calls, manifest, onto, events = load(args.run, args.events)
NAMES = load_names(os.path.dirname(os.path.abspath(args.events)))
SIM = load_similar(args.run, args.similar)
MEANINGS = {k: v.get("meaning", "") for k, v in (onto.get("edge_types") or {}).items()}

if not traces:
    st.html(css(palette("calm")))
    st.error(f"No event_traces.jsonl in {args.run}. Run `python run.py ...` first.")
    st.stop()
by_id = {t["event_id"]: t for t in traces}


def name(i):
    n = NAMES.get(i)
    return f"{esc(i)} <span class='rp-sub'>· {esc(n)}</span>" if n else esc(i)


def kinds(t):
    return sorted({r["tool"] for r in t["execution"] if r["kind"] != "read" and r["status"] == "confirmed"})


def n_writes(t):
    return sum(1 for r in t["execution"] if r["kind"] == "write" and r["status"] == "confirmed")


def n_failed(t):
    return sum(1 for r in t["execution"] if r["status"] != "confirmed") + len(t["blocked"])


def types_of(t):
    return [i["incident"]["type"] for i in t["incidents"]]


def is_problem(t):
    return bool(REAL & set(types_of(t)) or t["escalations"] or n_failed(t))


def is_noise(t):
    return all(x == "noise" for x in types_of(t)) and not t["execution"]


def safe(s):
    return re.sub(r"[^A-Za-z0-9]", "_", s)


# headline numbers, computed from the files (never hard-coded)
TOT = {
    "events": len(traces),
    "calls": len(calls),
    "failed": sum(1 for r in calls if r["status"] != "confirmed"),
    "log_failed": sum(1 for r in log if not r.get("ok", True)),
    "writes": sum(n_writes(t) for t in traces),
    "escalated": sum(1 for t in traces if t["escalations"]),
    "noise": sum(1 for t in traces if is_noise(t)),
}
SAME = bool(log and calls) and [(r["event_id"], r["tool"]) for r in log] == [(r["event_id"], r["tool"]) for r in calls]


# ============================================================================ state and mode
def select(eid):
    st.session_state.sel = eid
    st.session_state.view = "Event feed"


def clear_sel():
    st.session_state.sel = None


st.session_state.setdefault("sel", None)
st.session_state.setdefault("view", VIEWS[0])
if st.session_state.sel not in by_id:
    st.session_state.sel = None
view, sel = st.session_state.view, st.session_state.sel

if view == "Event feed":
    mode = "mission" if sel and is_problem(by_id[sel]) else "calm"
elif view == "Human review":
    mode = "mission" if TOT["escalated"] else "calm"
elif view == "Audit trail":
    mode = "mission" if (not log_exists or not SAME or TOT["log_failed"] or TOT["failed"]) else "calm"
else:
    mode = "calm"
P = palette(mode)
st.html(css(P))

# ============================================================================ header
hl, hr = st.columns([1, 2.3], vertical_alignment="center")
with hl:
    st.html(f'<div class="rp-brand">{logo_svg(P, 70)}<div><div class="rp-word">RIPPLE</div>'
            f'<div class="rp-tag">Wacky Wheels Co. control tower</div></div></div>')
with hr:
    with st.container(key="topnav"):
        st.radio("View", VIEWS, key="view", horizontal=True, label_visibility="collapsed",
                 format_func=lambda v: f"{v} ({TOT['escalated']})" if v == "Human review" and TOT["escalated"] else v)
st.html('<div class="rp-rule"></div>')

if mode == "mission":
    if view == "Event feed":
        t = by_id[sel]
        what = "escalated to a human" if t["escalations"] and not REAL & set(types_of(t)) else "active disruption"
        msg = f"{esc(sel)} · {what} · {len(t['incidents'])} incident(s) · {n_writes(t)} confirmed writes"
    elif view == "Human review":
        msg = f"{TOT['escalated']} event(s) waiting on a human · no operational changes made for them"
    else:
        msg = "audit check needs attention"
    st.html(f'<div class="rp-banner"><span class="rp-dot"></span><b>MISSION CONTROL</b><span>{msg}</span></div>')


# ============================================================================ shared renderers
def similar_panel(iid):
    rows = neighbours(SIM, iid)
    label = "Similar past incidents" + (" · MOCK data" if SIM["mock"] else "")
    with st.expander(label, expanded=False):
        if SIM["status"] == "missing":
            st.html('<div class="rp-note">Precedent search not available for this run.</div>')
            return
        if SIM["status"] != "ok":
            st.html(C.callout("warn", f"Precedent file could not be read ({esc(SIM['path'])}): {esc(SIM['status'].removeprefix('error: '))}"))
            return
        if SIM["mock"]:
            st.html(f'<div class="rp-row">{C.mock_badge()}<span class="rp-sub">Fixture data for UI development. '
                    f'Scores and reasons are invented. Real results replace this automatically.</span></div>')
        if not rows:
            st.html('<div class="rp-note">No similar past incidents.</div>')
            return
        for k, r in enumerate(rows):
            score = r.get("score") or 0
            c1, c2 = st.columns([5, 1], vertical_alignment="center")
            c1.html(
                f'<div class="rp-card" style="padding:12px 14px;margin-top:8px">'
                f'<div class="rp-head"><div class="rp-row"><span class="rp-h3">{esc(r.get("event_id"))}</span>'
                f'{C.type_pill(P, r.get("type"))}<span class="rp-sub">{esc(r.get("incident_id"))}</span></div>'
                f'<div class="rp-row"><span class="rp-sub">similarity</span><b>{score:.2f}</b>'
                f'<span style="display:inline-block;width:90px;height:8px;border-radius:4px;background:var(--raised)">'
                f'<span style="display:block;height:8px;border-radius:4px;width:{100 * score:.0f}%;background:var(--primary)">'
                f'</span></span></div></div>'
                f'<div class="rp-body" style="margin-top:6px"><b>Decision:</b> {esc(r.get("decision"))}</div>'
                f'<div class="rp-body"><b>Outcome:</b> {esc(r.get("outcome"))}</div>'
                f'<div class="rp-note">Why similar: {esc(r.get("why_similar"))}</div></div>')
            eid = r.get("event_id")
            c2.button(f"Open {eid}", key=f"sim_{safe(iid)}_{k}", on_click=select, args=(eid,),
                      disabled=eid not in by_id, width="stretch")


def moves_table(moves):
    rows = [[f"{esc(p['production_order_id'])}", esc(p["tool"].split(".")[-1]), esc(" ".join(p["from"])),
             esc(" ".join(p["to"])), esc(p.get("rationale"))] for p in moves]
    return C.table([("Order", "id"), ("Action", ""), ("From (plant, day)", "id"), ("To (plant, day)", "id"),
                    ("Why it moved there", "wrap")], rows, max_height=380)


def incident_header(e):
    inc, imp = e["incident"], e.get("impact") or {}
    t = inc["type"]
    ents = inc.get("entities") or {}
    dis = imp.get("disruption") or {}
    if t == "supplier_delay":
        kicker, title = "Part delayed", name(ents.get("part", "?"))
    elif t == "plant_outage":
        kicker, title = "Plant dark", name(ents.get("plant", "?"))
    elif t == "quality_hold":
        lot = imp.get("lot") or ents.get("lot", "?")
        part = (imp.get("evidence") or {}).get("lot", {}).get("part_id") or ents.get("part")
        kicker, title = "Lot on hold", f"{esc(lot)} <span class='rp-sub'>· {esc(NAMES.get(part, part))}</span>"
    elif t == "noise":
        kicker, title = "Not operational", "No action needed"
    else:
        kicker, title = "Unconfirmed report", "Escalated to a human"
    right = (f'<div class="rp-row">{C.type_pill(P, t)}{C.tone_pill(P, e.get("agent") or "Coordinator", "primary")}</div>')
    return (f'<div class="rp-head"><div><div class="rp-kicker">{esc(inc["incident_id"])} · {kicker}</div>'
            f'<div class="rp-h1" style="font-size:22px">{title}</div>'
            f'<div class="rp-sub">{esc(dis.get("label") or "")}</div></div>{right}</div>'
            f'<div class="rp-body" style="margin-top:10px"><b>Decision:</b> {esc(e.get("decision"))}</div>')


def incident_facts(e):
    inc, imp = e["incident"], e.get("impact") or {}
    t, ents, ev = inc["type"], inc.get("entities") or {}, imp.get("evidence") or {}
    d = {k: (v or {}).get("value") for k, v in (inc.get("dates") or {}).items()}
    if t == "supplier_delay":
        sh = ev.get("shipment") or {}
        return C.facts([
            ("Supplier", name(ents.get("supplier"))), ("Plant", name(ents.get("plant"))),
            ("Shipment", esc(sh.get("shipment_id")) + (f"<div class='rp-sub'>{esc(sh.get('matched_by'))}</div>" if sh.get("matched_by") else "")),
            ("ETA", f"{esc(d.get('original_eta'))} → {esc(d.get('new_eta'))}"),
            ("Blocked window", esc(ev.get("window"))), ("Recovery date", esc(ev.get("recovery_date"))),
            ("Models needing the part", esc(", ".join(ev.get("models_needing_part") or []))),
            ("Already built, unmovable", esc(len(ev.get("already_built_unmovable") or []))),
        ])
    if t == "plant_outage":
        return C.facts([
            ("Plant", name(ents.get("plant"))), ("Outage window", esc(ev.get("window"))),
            ("Blocked days", esc(", ".join(ev.get("blocked_days") or []))), ("Restart (recovery)", esc(ev.get("recovery_date"))),
            ("Already built, unmovable", esc(len(ev.get("already_built_unmovable") or []))),
        ])
    if t == "quality_hold":
        lot = ev.get("lot") or {}
        return C.facts([
            ("Lot matched by", esc(lot.get("matched_by"))), ("Part", name(lot.get("part_id"))),
            ("Supplier", name(lot.get("supplier_id"))), ("Plant", name(lot.get("plant_id"))),
            ("Build window", f"{esc(lot.get('first_build_date'))} → {esc(lot.get('last_build_date'))}"),
            ("Models using the part", esc(", ".join(ev.get("models_using_part") or []))),
        ])
    return C.facts([(k.replace("_", " ").capitalize(), esc(v if not isinstance(v, (dict, list)) else C.short_json(v, 120)))
                    for k, v in ev.items()])


def quality_block(e):
    imp = e["impact"]
    ev = imp.get("evidence") or {}
    veh = imp.get("vehicles") or []
    stop, owners = imp.get("stop_sale") or {}, imp.get("owners") or {}
    out = [C.section("What the lot touched", "Rule 6"),
           C.stats([(ev.get("vehicles_total", len(veh)), "vehicles built with the lot", None),
                    (ev.get("in_stock", "–"), f"unsold, stop-sale at {len(stop)} dealers", "warn"),
                    (ev.get("sold", "–"), f"sold, {len(owners)} owners contacted", "accent")], n=3)]
    st.html("".join(out))
    cl, cr = st.columns(2, gap="medium")
    with cl:
        rows = sorted(stop.items(), key=lambda kv: (-len(kv[1]), kv[0]))
        st.html(C.section("Unsold: stop-sale by dealer", f"{sum(len(v) for v in stop.values())} vehicles")
                + C.table([("Dealer", "id"), ("Vehicles", "num"), ("VINs", "small")],
                          [[f"{esc(d)}<div class='rp-sub'>{esc(NAMES.get(d, ''))}</div>", len(v), esc(", ".join(v))]
                           for d, v in rows], max_height=340))
    with cr:
        rows = sorted(owners.items())
        st.html(C.section("Sold: owners contacted", f"{len(owners)} owners")
                + C.table([("Customer", "id"), ("Vehicles", "num"), ("VINs", "small")],
                          [[esc(c), len(v), esc(", ".join(v))] for c, v in rows], max_height=340))
    with st.expander(f"All {len(veh)} vehicles (VIN, status, dealer, production order)"):
        st.html(C.table([("VIN", "id"), ("Status", ""), ("Dealer", "id"), ("Production order", "id")],
                        [[esc(v.get("vin")), C.tone_pill(P, "sold", "primary") if v.get("status") == "sold"
                          else C.tone_pill(P, "in stock", "warn"), esc(v.get("dealer_id")), esc(v.get("po"))]
                         for v in veh], max_height=420))


def edge_list(edges):
    cnt = Counter(x["etype"] for x in edges)
    return '<div class="rp-note"><b>Traversed edges:</b> ' + ", ".join(
        f"{esc(k.lower().replace('_', ' '))} ×{v}" for k, v in cnt.items()) + "</div>"


# ============================================================================ event feed + detail
def overview():
    with st.container(key="page_overview"):
        st.html(
            f'<div class="rp-card"><div class="rp-kicker">Run summary</div>'
            f'<div class="rp-h1">Every message read, every action logged</div>'
            f'<div class="rp-body">{TOT["events"]} operational messages came in. Each one was read, traced through the '
            f'knowledge graph, and acted on under the policy handbook, or deliberately left alone.</div>'
            f'<div class="rp-gap"></div>'
            + C.stats([(TOT["events"], "events handled", None), (TOT["calls"], "tool calls logged", None),
                       (TOT["failed"], "failed calls", "ok" if not TOT["failed"] else "bad")], hero=True)
            + '<div class="rp-gap"></div>'
            + C.stats([(TOT["writes"], "confirmed writes", None),
                       (TOT["escalated"], "escalated to a human", "warn" if TOT["escalated"] else "ok"),
                       (TOT["noise"], "noise events, 0 calls", None)])
            + "</div>")
        inc_types = Counter(x for t in traces for x in types_of(t))
        chips = "".join(f'<span class="rp-row">{C.type_pill(P, k)}<b>{v}</b></span>' for k, v in inc_types.most_common())
        st.html(
            f'<div class="rp-card" style="margin-top:12px"><div class="rp-h2">What came in</div>'
            f'<div class="rp-row" style="gap:18px">{chips}</div>'
            + C.facts([("Run", esc(manifest.get("run_id"))), ("Mode", esc(manifest.get("mode"))),
                       ("Extractor", esc(manifest.get("extractor"))), ("Snapshot", esc(manifest.get("snapshot_id")))])
            + '<div class="rp-note">Pick an event on the left to see what we understood, what it touched, what we did '
              'and why, and what we deliberately did not do. Planning, graph traversal and policy checks are '
              'deterministic code; the language model only proposes incident facts.</div></div>')


def feed_card(t, selected):
    types = types_of(t)
    pills = "".join(C.type_pill(P, x) for x in types)
    w = n_writes(t)
    foot = [f"{len(t['execution'])} calls · {w} writes"]
    if t["escalations"]:
        foot.append(C.tone_pill(P, "escalated", "warn", dashed=True))
    elif not t["execution"]:
        foot.append(C.tone_pill(P, "ignored, 0 calls", "ok"))
    if n_failed(t):
        foot.append(C.tone_pill(P, f"{n_failed(t)} failed", "bad"))
    return (f'<div class="rp-feed{" sel" if selected else ""}"><div class="top"><span class="id">{esc(t["event_id"])}</span>'
            f'<span class="meta">{esc(t["received_at"][11:16])} · {esc(t["source"])}</span></div>'
            f'<div class="types">{pills}</div><div class="foot">{"".join(f"<span>{x}</span>" for x in foot)}</div></div>')


def tab_understanding(t):
    u = t.get("understanding") or {}
    cc = u.get("cross_check") or {}
    tok = (u.get("tokens") or {}).get("totalTokenCount")
    agree = cc.get("agree")
    st.html(
        '<div class="rp-row" style="margin:4px 0 10px">'
        f'<span class="rp-sub">Extractor <b>{esc(u.get("extractor"))}</b> · {esc(u.get("extract_ms"))} ms'
        + (f" · {tok} tokens" if tok else "") + "</span>"
        + (C.tone_pill(P, "LLM and rules agree", "ok") if agree else
           C.tone_pill(P, "LLM and rules disagree", "warn") if agree is False else "")
        + "</div>"
        + (C.callout("warn", f"<b>The language model failed, so rules were used instead.</b> {esc(u['fallback'])}")
           if u.get("fallback") else ""))
    for e in t["incidents"]:
        inc = e["incident"]
        with st.container(key=f"card_u_{safe(inc['incident_id'])}"):
            out = [f'<div class="rp-head"><div><div class="rp-kicker">{esc(inc["incident_id"])}</div>'
                   f'<div class="rp-h2" style="margin:2px 0 0">{esc(TYPE_LABEL.get(inc["type"], inc["type"]))}</div></div>'
                   f'<div class="rp-row">{C.type_pill(P, inc["type"])}'
                   + (C.tone_pill(P, "confirmed", "ok") if inc["confirmed"] else C.tone_pill(P, "unconfirmed", "warn", True))
                   + "</div></div>",
                   f'<div class="rp-section"><div class="t">What the message said</div></div>'
                   f'<div class="rp-quote" style="margin-top:8px">{esc(inc.get("evidence_span"))}</div>',
                   f'<div class="rp-note">Classifier reason: {esc(inc.get("extractor_reason"))}</div>']
            ents = inc.get("entity_evidence") or []
            if ents:
                out.append(C.section("Resolved names", f"{len(ents)} matched"))
                out.append(C.table([("Type", ""), ("Phrase in text", ""), ("Resolved ID", "id"), ("Matched via", ""),
                                    ("Source", "")],
                                   [[esc(x.get("type")), f"“{esc(x.get('phrase'))}”", name(x.get("id")) if x.get("id") else "–",
                                     esc(x.get("matched")), esc(x.get("source"))] for x in ents]))
            elif inc["type"] not in ("noise",):
                out.append(C.section("Resolved names") + '<div class="rp-note">No entity could be resolved from the text.</div>')
            dates = inc.get("dates") or {}
            if dates:
                out.append(C.section("Resolved dates"))
                out.append(C.table([("Role", ""), ("Phrase in text", ""), ("Date", "id"), ("Rule", "wrap")],
                                   [[esc(k.replace("_", " ")), f"“{esc(v.get('phrase'))}”",
                                     esc(v["value"]) if v.get("value") else C.tone_pill(P, "not resolved", "warn", True),
                                     esc(v.get("rule")) + (" " + C.tone_pill(P, "ambiguous", "warn") if v.get("ambiguous") else "")]
                                    for k, v in dates.items()]))
            if inc.get("unresolved"):
                out.append(C.callout("warn", "<b>Needs a human check:</b> " + "; ".join(esc(x) for x in inc["unresolved"])))
            st.html("".join(out))


def tab_impact(t):
    moves_all = [p for p in t["plan"] if "production_order_id" in p]
    used = set()
    for e in t["incidents"]:
        inc, imp = e["incident"], e.get("impact")
        iid = inc["incident_id"]
        with st.container(key=f"card_i_{safe(iid)}"):
            st.html(incident_header(e) + C.policy_lines((imp or {}).get("policy", e.get("policy", []))))
            if not imp:
                kind = "ok" if inc["type"] == "noise" else "warn"
                st.html(C.callout(kind, f"<b>Why nothing was changed:</b> {esc(e.get('reason', ''))}"))
                similar_panel(iid)
                continue
            if imp.get("unresolved"):
                st.html(C.callout("warn", "<b>Unresolved:</b> " + "; ".join(esc(x) for x in imp["unresolved"])))
            st.html(incident_facts(e))
            if imp.get("status") == "actionable":
                edges = incident_edges(t, e)
                pos = imp.get("affected_pos") or sorted({nid(x["dst"]) for x in edges if x["etype"] == "LOT_USED_IN_ORDER"})
                st.html(C.section("Graph path", f"{len(edges)} edges · {len(pos)} production orders"))
                focus = st.selectbox("Graph focus", ["All orders, leaves grouped"] + pos, key=f"f{safe(iid)}")
                vstat = {v["vin"]: v.get("status") for v in imp.get("vehicles") or []}
                one = None if focus.startswith("All") else focus
                kept = sorted({ntype(x) for ed in edges for x in (ed["src"], ed["dst"])})
                st.html(legend(P, kept, derived=any(x.get("derived") for x in edges)))
                st.graphviz_chart(dot_graph(P, edges, one, MEANINGS, vstat), width="content")
                st.html(edge_list(edges))
                with st.expander("Edge evidence (source table and record key)"):
                    st.html(C.table([("Edge type", ""), ("From", "id"), ("To", "id"), ("Source table", ""),
                                     ("Record key", "id"), ("Derived", "")],
                                    [[esc(x["etype"].lower()), esc(x["src"]), esc(x["dst"]), esc(x.get("source_table")),
                                      esc(x.get("source_key")), "yes" if x.get("derived") else ""] for x in edges],
                                    max_height=420))
            if inc["type"] == "quality_hold":
                quality_block(e)
            mine =[p for p in moves_all if iid in p.get("incidents", [])]
            used.update(id(p) for p in mine)
            if mine:
                st.html(C.section("Slot decisions: where each order moved and why", "Rule 3") + moves_table(mine))
            elif inc["type"] == "quality_hold":
                st.html('<div class="rp-note">Quality holds move no production orders; they hold the lot, stop sale '
                        'of unsold vehicles and contact owners.</div>')
            with st.expander("Raw evidence record"):
                st.html(C.pre_json({k: v for k, v in (imp.get("evidence") or {}).items() if k != "shipment_candidates"}))
            similar_panel(iid)
    rest = [p for p in moves_all if id(p) not in used]
    if rest:
        with st.container(key=f"card_rest_{safe(t['event_id'])}"):
            st.html(C.section("Other slot decisions", "Rule 3") + moves_table(rest))
    dp = t.get("dealer_plan") or {}
    loaners = t.get("loaners") or []
    if loaners or dp.get("path"):
        with st.container(key=f"card_dealer_{safe(t['event_id'])}"):
            notified = sum(1 for r in t["execution"] if r["tool"] == "dealer.notify" and r["status"] == "confirmed")
            got = sum(1 for x in loaners if x.get("assigned"))
            miss = [x for x in loaners if not x.get("assigned")]
            std = dp.get("standard_no_loaner") or []
            ordered = sorted(loaners, key=lambda x: (x.get("assigned", False), x.get("dealer_id") or "", x.get("rank") or 0))
            pol = dp.get("policy")
            st.html(
                '<div class="rp-kicker">Downstream</div><div class="rp-h1" style="font-size:22px">Dealers and loaner cars</div>'
                + C.policy_lines(pol if isinstance(pol, list) else [pol] if pol else [])
                + '<div class="rp-gap"></div>'
                + C.stats([(notified, "dealer notices sent", None), (got, "loaners assigned", "ok"),
                           (len(miss), "eligible, missed out (pool empty)", "warn" if miss else None),
                           (len(std), "Standard tier, notice only", None)])
                + C.section("Loaner allocation, by priority", "Rule 5")
                + C.table([("Rank", "num"), ("Dealer", "id"), ("Customer order", "id"), ("Tier", ""), ("Promised", "id"),
                           ("Loaner", ""), ("Why", "wrap")],
                          [[esc(x.get("rank")), esc(x.get("dealer_id")), esc(x.get("customer_order_id")), esc(x.get("tier")),
                            esc(x.get("promised_date")),
                            C.tone_pill(P, "assigned", "ok") if x.get("assigned") else C.tone_pill(P, "missed out", "warn", True),
                            esc(x.get("why"))]
                           for x in ordered],
                          max_height=380, row_class=lambda i: "" if ordered[i].get("assigned") else "miss")
                + f'<div class="rp-note">{len(std)} Standard-tier customer orders were included in dealer notices and '
                  f'received no loaner, by policy.</div>')


def tab_execution(t):
    ex = t["execution"]
    reads = sum(1 for r in ex if r["kind"] == "read")
    writes = sum(1 for r in ex if r["kind"] == "write")
    escs = sum(1 for r in ex if r["kind"] == "escalation")
    bad = sum(1 for r in ex if r["status"] != "confirmed")
    st.html(C.stats([(len(ex), "tool calls", None), (reads, "reads", None), (writes, "writes", None),
                     (escs, "escalations", "warn" if escs else None),
                     (bad + len(t["blocked"]), "failed or blocked", "bad" if bad or t["blocked"] else "ok")]))
    if not ex:
        reason = " ".join(esc(e.get("reason", "")) for e in t["incidents"])
        st.html(C.callout("ok", f"<b>No tool calls were made, on purpose.</b> {reason}"))
    else:
        show_reads = st.toggle("Show read calls", value=False, key=f"rd{safe(t['event_id'])}")
        rows = [r for r in ex if show_reads or r["kind"] != "read"]
        def call_detail(r):
            a = esc(C.short_json({k: v for k, v in (r.get("args") or {}).items() if k != "message"}, 150))
            res = (esc(C.short_json(r.get("body"), 110)) if r["status"] == "confirmed" else esc(r.get("error")))
            return f"<div>args {a}</div><div style='margin-top:4px'>→ {res}</div>"

        st.html(C.table(
            [("#", "num"), ("Status", ""), ("Tool and agent", "id"), ("Purpose", "wrap"),
             ("Arguments → result", "small"), ("ms", "num")],
            [[esc(r["seq"]), C.status_pill(P, r["status"]),
              f"{esc(r['tool'])}<div class='rp-sub'>{esc(r['kind'])} · {esc(r.get('agent'))}</div>",
              esc(r.get("purpose")), call_detail(r), esc(r.get("ms"))] for r in rows],
            max_height=520))
        if not rows:
            st.html('<div class="rp-note">Only read calls for this event. Turn on "Show read calls" to see them.</div>')
    if t["blocked"]:
        st.html(C.callout("bad", "<b>Blocked by validation before sending:</b>") + C.pre_json(t["blocked"]))
    for r in t["escalations"]:
        st.html(C.callout("warn", f"<b>Escalated to a human:</b> {esc(r)}"))


def detail(t):
    ev = events.get(t["event_id"])
    st.button("← All events", key="back", on_click=clear_sel, type="tertiary")
    dur = t.get("duration_ms")
    status = (C.tone_pill(P, "escalated to a human", "warn", True) if t["escalations"]
              else C.tone_pill(P, "no action, by design", "ok") if not t["execution"] else "")
    st.html(
        f'<div class="rp-card"><div class="rp-head"><div><div class="rp-kicker">Event · {esc(t["source"])}</div>'
        f'<div class="rp-h1">{esc(t["event_id"])}</div>'
        f'<div class="rp-sub">Received {esc(t["received_at"].replace("T", " "))}'
        + (f" · handled in {dur:,.0f} ms" if isinstance(dur, (int, float)) else "") + "</div></div>"
        f'<div class="rp-row">{"".join(C.type_pill(P, x) for x in types_of(t))}{status}</div></div>'
        '<div class="rp-gap"></div>'
        + (f'<div class="rp-quote">{esc(ev["text"])}</div>' if ev else
           '<div class="rp-note">Raw message text not available (events file missing).</div>')
        + f'<div class="rp-section"><div class="t">Summary</div></div><div class="rp-body" style="margin-top:6px">'
          f'{esc(t.get("summary"))}</div></div>')
    st.html('<div class="rp-gap"></div>' + C.stats([
        (len(t["incidents"]), "incidents in this message", None), (n_writes(t), "confirmed writes", None),
        (len(kinds(t)), "kinds of action", None), (n_failed(t), "failed or blocked", "bad" if n_failed(t) else "ok")]))
    tu, ti, tx = st.tabs(["1 · Event understanding", "2 · Impact and policy", "3 · Execution and outcome"])
    with tu:
        tab_understanding(t)
    with ti:
        tab_impact(t)
    with tx:
        tab_execution(t)


def page_feed():
    left, right = st.columns([1, 2.6], gap="large")
    with left:
        with st.container(key="feed"):
            types_all = sorted({x for t in traces for x in types_of(t)}, key=lambda x: list(TYPE_LABEL).index(x)
                               if x in TYPE_LABEL else 99)
            flt = st.pills("Filter by type", types_all, selection_mode="multi", key="flt",
                           format_func=lambda x: TYPE_LABEL.get(x, x))
            rows = [t for t in traces if not flt or any(x in flt for x in types_of(t))]
            st.html(f'<div class="rp-section" style="margin-top:2px"><div class="t">Event feed</div>'
                    f'<div class="r">{len(rows)} of {len(traces)}</div></div>')
            if not rows:
                st.html('<div class="rp-note">No events match this filter.</div>')
            for t in rows:
                with st.container(key=f"feeditem_{safe(t['event_id'])}"):
                    st.html(feed_card(t, sel == t["event_id"]))
                    st.button(f"Open {t['event_id']}", key=f"b{t['event_id']}", on_click=select, args=(t["event_id"],))
    with right:
        if sel is None:
            overview()
        else:
            with st.container(key=f"detail_{safe(sel)}"):
                detail(by_id[sel])


# ============================================================================ other pages
def page_review():
    with st.container(key="page_review"):
        esc_ev = [t for t in traces if t["escalations"]]
        st.html('<div class="rp-kicker">Human in the loop</div><div class="rp-h1">Human review queue</div>'
                '<div class="rp-sub">Every escalate call, with what a person has to check. No operational change was '
                'made for any of these.</div><div class="rp-gap"></div>')
        if not esc_ev:
            st.html(C.callout("ok", "<b>Nothing escalated in this run.</b> Every message was either acted on under "
                                    "policy or recognised as noise."))
            return
        for t in esc_ev:
            with st.container(key=f"card_rev_{safe(t['event_id'])}"):
                writes = [r for r in t["execution"] if r["kind"] == "write"]
                checks = []
                for r in t["escalations"]:
                    head, _, ask = r.partition("Human should ")
                    checks.append((head.strip(), ask.strip()))
                body = "".join(
                    f'<div class="rp-body" style="margin-top:10px"><b>Why it was escalated:</b> {esc(h)}</div>'
                    + (C.callout("warn", f"<b>A human should</b> {esc(a)}") if a else "") for h, a in checks)
                unres = [x for e in t["incidents"] for x in e["incident"].get("unresolved") or []]
                st.html(
                    f'<div class="rp-head"><div><div class="rp-kicker">{esc(t["source"])} · {esc(t["received_at"].replace("T", " "))}</div>'
                    f'<div class="rp-h1" style="font-size:22px">{esc(t["event_id"])}</div></div>'
                    f'<div class="rp-row">{"".join(C.type_pill(P, x) for x in types_of(t))}'
                    f'{C.tone_pill(P, "waiting on a human", "warn", True)}</div></div><div class="rp-gap"></div>'
                    + (f'<div class="rp-quote">{esc(events[t["event_id"]]["text"])}</div>' if t["event_id"] in events else "")
                    + body
                    + (C.callout("warn", "<b>Unresolved:</b> " + "; ".join(esc(x) for x in unres)) if unres else "")
                    + '<div class="rp-gap"></div>'
                    + C.stats([(len(writes), "operational writes", "ok" if not writes else "bad"),
                               (len(t["execution"]), "tool calls (the escalation itself)", None)], n=2))
                st.button(f"Open {t['event_id']} in the event feed", key=f"rev_{safe(t['event_id'])}", on_click=select,
                          args=(t["event_id"],))


def page_audit():
    with st.container(key="page_audit"):
        st.html('<div class="rp-kicker">Audit ready</div><div class="rp-h1">Audit trail</div>'
                '<div class="rp-sub">The organizer\'s official log (action_log.jsonl) next to our own record of the same '
                'calls (client_calls.jsonl).</div><div class="rp-gap"></div>')
        if not log_exists:
            st.html(C.callout("bad", f"<b>Official log missing.</b> No action_log.jsonl in {esc(args.run)}, so the "
                                     "match check cannot run."))
        elif SAME:
            st.html(C.callout("ok", f"<b>Client record matches the organizer log row for row.</b> "
                                    f"{len(log)} rows in both, same event and tool in the same order."))
        elif log and calls:
            st.html(C.callout("bad", "<b>Client record and organizer log differ.</b> For example client-only timeouts, "
                                     "or requests that never reached the server."))
        st.html('<div class="rp-gap"></div>' + C.stats([
            (len(log), "logged calls (official)", None),
            (TOT["log_failed"], "failed (ok: false)", "ok" if not TOT["log_failed"] else "bad"),
            (sum(1 for r in calls if r["kind"] == "write"), "writes", None),
            (sum(1 for r in calls if r["status"] == "unknown"), "client timeouts", None)]) + '<div class="rp-gap"></div>')
        if not calls:
            st.html('<div class="rp-note">No client_calls.jsonl in this run folder.</div>')
            return
        f1, f2 = st.columns(2)
        ev_f = f1.multiselect("Events", sorted(by_id), default=[])
        tool_f = f2.multiselect("Tools", sorted({r["tool"] for r in calls}), default=[])
        rows = [r for r in calls if (not ev_f or r["event_id"] in ev_f) and (not tool_f or r["tool"] in tool_f)]
        st.html(C.section("Client record", f"{len(rows)} of {len(calls)} calls"))
        df = pd.DataFrame([{"seq": r["seq"], "event": r["event_id"], "status": r["status"], "tool": r["tool"],
                            "agent": r.get("agent"), "rule": (r.get("rule") or "")[:40],
                            "incidents": ", ".join(r.get("incidents") or []), "args": json.dumps(r["args"])[:200],
                            "ms": r.get("ms")} for r in rows])
        if len(df):
            st.dataframe(df, hide_index=True, width="stretch", height=520)
        else:
            st.html('<div class="rp-note">No calls match these filters.</div>')


def page_graph():
    with st.container(key="page_graph"):
        st.html('<div class="rp-kicker">Knowledge graph</div><div class="rp-h1">Ontology and counts</div>'
                '<div class="rp-sub">Every entity type in the graph, with how many of each exist in this snapshot. '
                'Hover an arrow for its meaning and count.</div>')
        g = manifest.get("graph") or {}
        if not onto:
            st.html(C.callout("warn", "No graph export (graph/ontology.json) in this run folder."))
            return
        types = sorted({v["src"] for v in onto["edge_types"].values()} | {v["dst"] for v in onto["edge_types"].values()})
        with st.container(key="card_onto"):
            st.html(legend(P, types, derived=True))
            st.graphviz_chart(ontology_dot(P, onto, g), width="content")
            st.html(f'<div class="rp-note">Schema {esc(onto.get("schema_version"))} · snapshot {esc(g.get("snapshot_id"))}</div>')
        st.html('<div class="rp-gap"></div>' + C.table(
            [("Edge type", ""), ("From", ""), ("To", ""), ("Meaning", "wrap"), ("Count", "num")],
            [[esc(k.lower()), esc(v["src"]), esc(v["dst"]), esc(v.get("meaning")), f'{g.get("edges", {}).get(k, 0):,}']
             for k, v in onto["edge_types"].items()]))


def page_summary():
    with st.container(key="page_summary"):
        st.html('<div class="rp-kicker">Run summary</div><div class="rp-h1">Totals for this run</div><div class="rp-gap"></div>'
                + C.stats([(TOT["events"], "events", None), (TOT["writes"], "confirmed writes", None),
                           (TOT["failed"], "failed calls", "ok" if not TOT["failed"] else "bad"),
                           (TOT["escalated"], "escalations", "warn" if TOT["escalated"] else None),
                           (TOT["noise"], "noise events, 0 calls", None)]))
        c1, c2 = st.columns([3, 2], gap="large")
        with c1:
            rows = []
            for t in traces:
                ex = t["execution"]
                rows.append([esc(t["event_id"]), "".join(C.type_pill(P, x) for x in types_of(t)), n_writes(t),
                             sum(1 for r in ex if r["kind"] == "read"), n_failed(t),
                             C.tone_pill(P, "yes", "warn", True) if t["escalations"] else "",
                             esc(", ".join(kinds(t))), f'{t.get("duration_ms") or 0:,.0f}'])
            st.html(C.section("Per event") + C.table(
                [("Event", "id"), ("Type", ""), ("Writes", "num"), ("Reads", "num"), ("Failed", "num"),
                 ("Escalated", ""), ("Action kinds", "wrap"), ("ms", "num")], rows))
        with c2:
            tc = Counter(r["tool"] for r in calls if r["status"] == "confirmed")
            st.html(C.section("Confirmed calls per tool") + '<div class="rp-card" style="margin-top:10px">'
                    + C.bars(tc.most_common()) + "</div>")


{"Event feed": page_feed, "Human review": page_review, "Audit trail": page_audit,
 "Knowledge graph": page_graph, "Run summary": page_summary}[view]()

st.html(f'<div class="rp-note" style="margin-top:28px;text-align:center">Read-only view of recorded run files '
        f'({esc(args.run)}). No tools are called from this screen. Run {esc(manifest.get("run_id", "?"))}.</div>')
