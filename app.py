"""Ripple: control tower UI.

    streamlit run app.py -- --run submission --events data/events.json [--similar path/to/similar_incidents.json]

Reads only recorded run artifacts (event_traces.jsonl, action_log.jsonl, client_calls.jsonl, graph/,
similar_incidents.json), so it shows exactly what the agents did. No tool calls are made from the UI.
"""
import argparse
import datetime
import json
import os
import re
from collections import Counter

import pandas as pd
import streamlit as st

from ui import components as C
from ui import labels as L
from ui.components import TYPE_LABEL, esc
from ui.graph import dot_graph, incident_edges, legend, nid, ntype, ontology_dot
from ui.similar import load_similar, neighbours
from ui.theme import P, css

st.set_page_config(page_title="Ripple", page_icon=":material/waves:", layout="wide", initial_sidebar_state="collapsed")

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


# ============================================================================ data
args = parse_args()
traces, log, log_exists, calls, manifest, onto, events = load(args.run, args.events)
L.load_reference_names(os.path.dirname(os.path.abspath(args.events)))
SIM = load_similar(args.run, args.similar)
MEANINGS = {k: v.get("meaning", "") for k, v in (onto.get("edge_types") or {}).items()}

st.html(css())
if not traces:
    st.error(f"No event_traces.jsonl in {args.run}. Run `python run.py ...` first.")
    st.stop()
by_id = {t["event_id"]: t for t in traces}


def name(i):
    """Plain name for a coded ID (no prefixes like P_TX or PO-0058 on screen)."""
    return esc(L.plain(i)) if i else "–"


def source(s):
    """Source name with a hover explanation (the name itself stays as received, e.g. 'ops chat')."""
    tip = L.SOURCE_HELP.get(s)
    return (f'<span class="rp-src" tabindex="0" data-tip="{esc(tip)}">{esc(s)}</span>' if tip else esc(s))


def pt(text):
    """Escape a sentence after swapping coded IDs and ISO dates for plain words."""
    return esc(L.plain_text(text))


def kinds(t):
    return sorted({r["tool"] for r in t["execution"] if r["kind"] != "read" and r["status"] == "confirmed"})


def n_writes(t):
    return sum(1 for r in t["execution"] if r["kind"] == "write" and r["status"] == "confirmed")


def n_failed(t):
    return sum(1 for r in t["execution"] if r["status"] != "confirmed") + len(t["blocked"])


def types_of(t):
    return [i["incident"]["type"] for i in t["incidents"]]


def is_noise(t):
    return all(x == "noise" for x in types_of(t)) and not t["execution"]


def safe(s):
    return re.sub(r"[^A-Za-z0-9]", "_", s)


def title(text, right=""):
    return f'<div class="rp-head"><div class="rp-h1">{esc(text)}</div><div class="rp-row">{right}</div></div>'


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


# ============================================================================ state
def select(eid):
    st.session_state.sel = eid
    st.session_state.view = "Event feed"


def clear_sel():
    st.session_state.sel = None
    st.session_state["_scrolled_for"] = None


st.session_state.setdefault("sel", None)
st.session_state.setdefault("view", VIEWS[0])
if st.session_state.sel not in by_id:
    st.session_state.sel = None
view, sel = st.session_state.view, st.session_state.sel

# ============================================================================ header band
with st.container(key="hero"):
    hl, hr = st.columns([1, 3], vertical_alignment="center")
    hl.html('<div class="rp-word">RIPPLE</div>')
    with hr:
        with st.container(key="topnav"):
            st.radio("View", VIEWS, key="view", horizontal=True, label_visibility="collapsed",
                     format_func=lambda v: f"{v} ({TOT['escalated']})" if v == "Human review" and TOT["escalated"] else v)


# ============================================================================ shared renderers
def similar_panel(iid):
    rows = neighbours(SIM, iid)
    with st.expander("Similar past incidents" + (" · MOCK" if SIM["mock"] else ""), expanded=False):
        if SIM["status"] == "missing":
            st.html('<div class="rp-note">Precedent search not available.</div>')
            return
        if SIM["status"] != "ok":
            st.html(C.callout("warn", f"Precedent file could not be read ({esc(SIM['path'])}): "
                                      f"{esc(SIM['status'].removeprefix('error: '))}"))
            return
        if SIM["mock"]:
            st.html(C.mock_badge())
        if not rows:
            st.html('<div class="rp-note">No similar past incidents.</div>')
            return
        for k, r in enumerate(rows):
            score = r.get("score") or 0
            c1, c2 = st.columns([5, 1], vertical_alignment="center")
            c1.html(
                f'<div class="rp-card rp-stack" style="padding:14px 16px;gap:8px">'
                f'<div class="rp-head"><div class="rp-row"><span class="rp-h3">{name(r.get("event_id"))}</span>'
                f'{C.type_pill(P, r.get("type"))}</div><b>{score:.0%} similar</b></div>'
                f'<div class="rp-body"><b>Decision:</b> {pt(r.get("decision"))}</div>'
                f'<div class="rp-body"><b>Outcome:</b> {pt(r.get("outcome"))}</div>'
                f'<div class="rp-note">{pt(r.get("why_similar"))}</div></div>')
            eid = r.get("event_id")
            c2.button(f"Open {L.plain(eid).lower()}", key=f"sim_{safe(iid)}_{k}", on_click=select, args=(eid,),
                      disabled=eid not in by_id, width="stretch")


def moves_table(moves):
    where = lambda pl_day: f"{name(pl_day[0])}, {esc(L.plain_date(pl_day[1]))}"  # noqa: E731
    rows = [[name(p["production_order_id"]), esc(L.tool_label(p["tool"])), where(p["from"]), where(p["to"]),
             pt(p.get("rationale"))] for p in moves]
    return C.table([("Build", "id"), ("Action", "nowrap"), ("From", "nowrap"), ("To", "nowrap"), ("Why", "wrap")],
                   rows, max_height=380)


def incident_header(e):
    inc, imp = e["incident"], e.get("impact") or {}
    t = inc["type"]
    ents = inc.get("entities") or {}
    if t == "supplier_delay":
        head = name(ents.get("part", "?"))
    elif t == "plant_outage":
        head = name(ents.get("plant", "?"))
    elif t == "quality_hold":
        lot = imp.get("lot") or ents.get("lot", "?")
        part = (imp.get("evidence") or {}).get("lot", {}).get("part_id") or ents.get("part")
        head = f"{name(lot)} of {name(part)}"
    elif t == "noise":
        head = "No action needed"
    else:
        head = "Escalated to a human"
    right = C.type_pill(P, t) + C.tone_pill(P, e.get("agent") or "Coordinator", "primary")
    return (f'<div class="rp-head"><div class="rp-h2" style="font-size:22px">{head}</div>'
            f'<div class="rp-row">{right}</div></div>'
            f'<div class="rp-body"><b>Decision:</b> {pt(e.get("decision"))}</div>')


def incident_facts(e):
    inc, imp = e["incident"], e.get("impact") or {}
    t, ents, ev = inc["type"], inc.get("entities") or {}, imp.get("evidence") or {}
    d = {k: (v or {}).get("value") for k, v in (inc.get("dates") or {}).items()}
    if t == "supplier_delay":
        sh = ev.get("shipment") or {}
        return C.facts([
            ("Supplier", name(ents.get("supplier"))), ("Plant", name(ents.get("plant"))),
            ("Shipment", name(sh.get("shipment_id"))),
            ("Arrival", f"{esc(L.plain_date(d.get('original_eta')))} → {esc(L.plain_date(d.get('new_eta')))}"),
            ("Blocked days", pt(", ".join(ev.get("blocked_days") or []))), ("Back on", pt(ev.get("recovery_date"))),
            ("Car models", esc(", ".join(L.plain(m) for m in ev.get("models_needing_part") or []))),
        ])
    if t == "plant_outage":
        return C.facts([
            ("Plant", name(ents.get("plant"))), ("Down", pt(", ".join(ev.get("blocked_days") or []))),
            ("Restarts", pt(ev.get("recovery_date"))),
        ])
    if t == "quality_hold":
        lot = ev.get("lot") or {}
        return C.facts([
            ("Part", name(lot.get("part_id"))), ("Supplier", name(lot.get("supplier_id"))),
            ("Plant", name(lot.get("plant_id"))),
            ("Cars built", f"{esc(L.plain_date(lot.get('first_build_date')))} → "
                           f"{esc(L.plain_date(lot.get('last_build_date')))}"),
            ("Car models", esc(", ".join(L.plain(m) for m in ev.get("models_using_part") or []))),
        ])
    return C.facts([(k.replace("_", " ").capitalize(), pt(v if not isinstance(v, (dict, list)) else C.short_json(v, 120)))
                    for k, v in ev.items()])


def quality_block(e):
    imp = e["impact"]
    ev = imp.get("evidence") or {}
    veh = imp.get("vehicles") or []
    stop, owners = imp.get("stop_sale") or {}, imp.get("owners") or {}
    st.html(C.stats([(ev.get("vehicles_total", len(veh)), "vehicles built with the lot", None),
                     (ev.get("in_stock", "–"), f"unsold · stop-sale at {len(stop)} dealers", "warn"),
                     (ev.get("sold", "–"), f"sold · {len(owners)} owners contacted", "accent")]))
    cl, cr = st.columns(2, gap="medium")
    with cl:
        rows = sorted(stop.items(), key=lambda kv: (-len(kv[1]), kv[0]))
        st.html(f'<div class="rp-stack" style="gap:10px">{C.section("Stop-sale by dealer")}'
                + C.table([("Dealer", "id"), ("Vehicles", "num"), ("VINs", "small")],
                          [[name(d), len(v), esc(", ".join(v))] for d, v in rows], max_height=340) + "</div>")
    with cr:
        st.html(f'<div class="rp-stack" style="gap:10px">{C.section("Owners contacted")}'
                + C.table([("Customer", "id"), ("Vehicles", "num"), ("VINs", "small")],
                          [[name(c), len(v), esc(", ".join(v))] for c, v in sorted(owners.items())], max_height=340)
                + "</div>")
    with st.expander(f"All {len(veh)} vehicles"):
        st.html(C.table([("VIN", "id"), ("Status", ""), ("Dealer", "nowrap"), ("Build", "id")],
                        [[esc(v.get("vin")), C.tone_pill(P, "sold", "primary") if v.get("status") == "sold"
                          else C.tone_pill(P, "in stock", "warn"), name(v.get("dealer_id")), name(v.get("po"))]
                         for v in veh], max_height=420))


# ============================================================================ event feed + detail
def overview():
    with st.container(key="page_overview"):
        inc_types = Counter(x for t in traces for x in types_of(t))
        chips = "".join(f'<span class="rp-row" style="gap:6px">{C.type_pill(P, k)}<b>{v}</b></span>'
                        for k, v in inc_types.most_common())
        st.html(
            '<div class="rp-card rp-stack">' + title("Run summary")
            + C.stats([(TOT["events"], "messages handled", None), (TOT["calls"], "actions taken", None),
                       (TOT["failed"], "failed actions", "ok" if not TOT["failed"] else "bad"),
                       (TOT["writes"], "changes made", None),
                       (TOT["escalated"], "escalated to a human", "warn" if TOT["escalated"] else "ok"),
                       (TOT["noise"], "junk messages ignored", None)], hero=True)
            + f'<div class="rp-row" style="gap:18px">{chips}</div>'
            + "</div>")


def feed_card(t, selected):
    pills = "".join(C.type_pill(P, x) for x in types_of(t))
    foot = [f"{n_writes(t)} changes made"]
    if t["escalations"]:
        foot.append(C.tone_pill(P, "sent to a person", "warn", dashed=True))
    elif not t["execution"]:
        foot.append(C.tone_pill(P, "ignored", "ok"))
    if n_failed(t):
        foot.append(C.tone_pill(P, f"{n_failed(t)} failed", "bad"))
    return (f'<div class="rp-feed{" sel" if selected else ""}"><div class="top"><span class="id">{name(t["event_id"])}</span>'
            f'<span class="meta">{esc(t["received_at"][11:16])} · {source(t["source"])}</span></div>'
            f'<div class="types">{pills}</div><div class="foot">{"".join(f"<span>{x}</span>" for x in foot)}</div></div>')


def tab_understanding(t):
    u = t.get("understanding") or {}
    if u.get("fallback"):  # only shown when the language model failed and rules were used instead
        st.html(C.callout("warn", f"<b>Language model failed; rules were used.</b> {esc(u['fallback'])}"))
    for e in t["incidents"]:
        inc = e["incident"]
        with st.container(key=f"card_u_{safe(inc['incident_id'])}"):
            out = [f'<div class="rp-head"><div class="rp-h2">{esc(TYPE_LABEL.get(inc["type"], inc["type"]))}</div>'
                   f'<div class="rp-row">'
                   + (C.tone_pill(P, "confirmed", "ok") if inc["confirmed"] else C.tone_pill(P, "unconfirmed", "warn", True))
                   + "</div></div>",
                   f'<div class="rp-quote">{esc(inc.get("evidence_span"))}</div>']
            ents = inc.get("entity_evidence") or []
            if ents:
                out.append(C.section("Names we recognised"))
                out.append(C.table([("In the message", ""), ("Means", "nowrap"), ("Kind", "")],
                                   [[f"“{esc(x.get('phrase'))}”", name(x.get("id")) if x.get("id") else "–",
                                     esc(str(x.get("type", "")).capitalize())] for x in ents]))
            dates = inc.get("dates") or {}
            if dates:
                out.append(C.section("Dates we worked out"))
                out.append(C.table([("In the message", ""), ("Date", "nowrap"), ("Meaning", "")],
                                   [[f"“{esc(v.get('phrase'))}”",
                                     esc(L.plain_date(v["value"])) if v.get("value")
                                     else C.tone_pill(P, "unclear", "warn", True),
                                     esc(k.replace("_", " ").replace("eta", "arrival").capitalize())]
                                    for k, v in dates.items()]))
            if inc.get("unresolved"):
                out.append(C.callout("warn", "<b>Needs a human check:</b> " + "; ".join(pt(x) for x in inc["unresolved"])))
            st.html('<div class="rp-stack">' + "".join(out) + "</div>")


def tab_impact(t):
    moves_all = [p for p in t["plan"] if "production_order_id" in p]
    used = set()
    for e in t["incidents"]:
        inc, imp = e["incident"], e.get("impact")
        iid = inc["incident_id"]
        with st.container(key=f"card_i_{safe(iid)}"):
            st.html('<div class="rp-stack" style="gap:10px">' + incident_header(e)
                    + C.policy_lines((imp or {}).get("policy", e.get("policy", []))) + "</div>")
            if not imp:
                st.html(C.callout("ok" if inc["type"] == "noise" else "warn", pt(e.get("reason", ""))))
                similar_panel(iid)
                continue
            if imp.get("unresolved"):
                st.html(C.callout("warn", "<b>Unresolved:</b> " + "; ".join(pt(x) for x in imp["unresolved"])))
            st.html(incident_facts(e))
            if imp.get("status") == "actionable":
                edges = incident_edges(t, e)
                pos = imp.get("affected_pos") or sorted({nid(x["dst"]) for x in edges if x["etype"] == "LOT_USED_IN_ORDER"})
                focus = st.selectbox("Show", ["All builds"] + pos, key=f"f{safe(iid)}",
                                     format_func=lambda v: v if v == "All builds" else L.plain(v))
                vstat = {v["vin"]: v.get("status") for v in imp.get("vehicles") or []}
                kept = sorted({ntype(x) for ed in edges for x in (ed["src"], ed["dst"])})
                st.html(legend(P, kept, derived=any(x.get("derived") for x in edges)))
                st.graphviz_chart(dot_graph(P, edges, None if focus == "All builds" else focus, MEANINGS, vstat),
                                  width="content")
                with st.expander("Where each link comes from"):
                    node = lambda k: esc(L.plain(nid(k)))  # noqa: E731
                    st.html(C.table([("Link", ""), ("From", "nowrap"), ("To", "nowrap"), ("Data file", "")],
                                    [[esc(x["etype"].lower().replace("_", " ")) + (" (worked out)" if x.get("derived") else ""),
                                      node(x["src"]), node(x["dst"]), esc(x.get("source_table"))]
                                     for x in edges], max_height=420))
            if inc["type"] == "quality_hold":
                quality_block(e)
            mine = [p for p in moves_all if iid in p.get("incidents", [])]
            used.update(id(p) for p in mine)
            if mine:
                st.html(f'<div class="rp-stack" style="gap:10px">{C.section("Where each build moved")}{moves_table(mine)}</div>')
            similar_panel(iid)
    rest = [p for p in moves_all if id(p) not in used]
    if rest:
        with st.container(key=f"card_rest_{safe(t['event_id'])}"):
            st.html(f'<div class="rp-stack" style="gap:10px">{C.section("Other build moves")}{moves_table(rest)}</div>')
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
                '<div class="rp-stack">'
                + '<div class="rp-h2" style="font-size:22px">Dealers and loaners</div>'
                + C.policy_lines(pol if isinstance(pol, list) else [pol] if pol else [])
                + C.stats([(notified, "dealer notices", None), (got, "loaners assigned", "ok"),
                           (len(miss), "missed out (pool empty)", "warn" if miss else None),
                           (len(std), "Standard tier, notice only", None)])
                + C.table([("Priority", "num"), ("Dealer", "nowrap"), ("Customer order", "nowrap"), ("Tier", ""),
                           ("Promised", "nowrap"), ("Loaner", ""), ("Why", "wrap")],
                          [[esc(x.get("rank")), name(x.get("dealer_id")), name(x.get("customer_order_id")),
                            esc(x.get("tier")), esc(L.plain_date(x.get("promised_date"))),
                            C.tone_pill(P, "assigned", "ok") if x.get("assigned") else C.tone_pill(P, "missed out", "warn", True),
                            pt(x.get("why"))] for x in ordered],
                          max_height=380, row_class=lambda i: "" if ordered[i].get("assigned") else "miss")
                + "</div>")


def tab_execution(t):
    ex = t["execution"]
    bad = sum(1 for r in ex if r["status"] != "confirmed")
    st.html(C.stats([(len(ex), "actions in total", None),
                     (sum(1 for r in ex if r["kind"] == "write"), "changes made", None),
                     (sum(1 for r in ex if r["kind"] == "read"), "look-ups", None),
                     (sum(1 for r in ex if r["kind"] == "escalation"), "sent to a person", None),
                     (bad + len(t["blocked"]), "failed or blocked", "bad" if bad or t["blocked"] else "ok")]))
    if not ex:
        reason = " ".join(pt(e.get("reason", "")) for e in t["incidents"])
        st.html(C.callout("ok", f"<b>No actions taken, on purpose.</b> {reason}"))
    else:
        show_reads = st.toggle("Show look-ups too", value=False, key=f"rd{safe(t['event_id'])}")
        rows = [r for r in ex if show_reads or r["kind"] != "read"]
        if rows:
            st.html(C.table(
                [("#", "num"), ("Result", ""), ("Action", "nowrap"), ("Details", "nowrap"), ("Why", "wrap"),
                 ("Done by", "nowrap")],
                [[esc(r["seq"]), C.tone_pill(P, L.outcome(r["tool"], r.get("body"), r["status"]),
                                             "ok" if r["status"] == "confirmed" else "bad"),
                  f"<b>{esc(L.tool_label(r['tool']))}</b>", esc(L.describe(r["tool"], r.get("args"))),
                  pt(r.get("purpose")), esc(r.get("agent"))] for r in rows],
                max_height=520))
        else:
            st.html('<div class="rp-note">Only look-ups for this event.</div>')
    if t["blocked"]:
        st.html(C.callout("bad", "<b>Blocked by validation before sending:</b>") + C.pre_json(t["blocked"]))
    for r in t["escalations"]:
        st.html(C.callout("warn", f"<b>Sent to a person:</b> {pt(r)}"))


def nice_date(s):
    try:
        d = datetime.date.fromisoformat(str(s)[:10])
        return f"{d:%b} {d.day}"
    except ValueError:
        return esc(s) if s else "?"


def plural(n, word):
    return f"{n} {word}{'' if n == 1 else 's'}"


def event_story(t):
    """Plain-language summary built from the trace: what happened, what we did, how it ended."""
    happened = []
    for e in t["incidents"]:
        inc, imp = e["incident"], e.get("impact") or {}
        ents, ev = inc.get("entities") or {}, imp.get("evidence") or {}
        d = {k: (v or {}).get("value") for k, v in (inc.get("dates") or {}).items()}
        n_pos = len(imp.get("affected_pos") or [])
        nm = lambda i: esc(L.plain(i) or "?")  # noqa: E731
        if inc["type"] == "supplier_delay":
            happened.append(
                f"<b>Supplier delay.</b> {nm(ents.get('supplier'))} can't deliver the {nm(ents.get('part'))} "
                f"to {nm(ents.get('plant'))} on time: it now arrives {nice_date(d.get('new_eta'))} instead of "
                f"{nice_date(d.get('original_eta'))}. {plural(n_pos, 'car build')} affected.")
        elif inc["type"] == "plant_outage":
            happened.append(
                f"<b>Plant outage.</b> {nm(ents.get('plant'))} is down {nice_date(d.get('start'))} to "
                f"{nice_date(d.get('end'))} and restarts {nice_date(ev.get('recovery_date'))}. "
                f"{plural(n_pos, 'car build')} affected.")
        elif inc["type"] == "quality_hold":
            lot = ev.get("lot") or {}
            happened.append(
                f"<b>Quality problem.</b> {nm(lot.get('lot_id') or imp.get('lot'))} of the "
                f"{nm(lot.get('part_id'))} from {nm(lot.get('supplier_id'))} went into cars built at "
                f"{nm(lot.get('plant_id'))} from {nice_date(lot.get('first_build_date'))} to "
                f"{nice_date(lot.get('last_build_date'))}. {ev.get('vehicles_total', '?')} vehicles have it: "
                f"{ev.get('in_stock', '?')} still unsold, {ev.get('sold', '?')} already with owners.")
        elif inc["type"] == "noise":
            happened.append(f"<b>Not an operational problem.</b> {esc(inc.get('extractor_reason'))}")
        else:
            happened.append(f"<b>Unconfirmed report.</b> {esc(inc.get('extractor_reason'))} "
                            "No part, plant or dates could be confirmed.")

    ok = Counter(r["tool"] for r in t["execution"] if r["status"] == "confirmed")
    missed = sum(1 for x in t.get("loaners") or [] if not x.get("assigned"))
    did = []
    if ok["mes.reschedule"]:
        did.append(f"Moved {plural(ok['mes.reschedule'], 'car build')} to the next open day at the same plant.")
    if ok["mes.transfer"]:
        did.append(f"Moved {plural(ok['mes.transfer'], 'car build')} to another plant that builds the model.")
    if ok["quality.hold_lot"]:
        did.append("Put the faulty batch of parts on hold.")
    if ok["dealer.stop_sale"]:
        did.append(f"Stopped sale of the unsold cars at {plural(ok['dealer.stop_sale'], 'dealer')}.")
    if ok["dealer.notify"]:
        did.append(f"Told {plural(ok['dealer.notify'], 'dealer')} which of their customer orders are affected.")
    if ok["crm.notify_customer"]:
        who = "owner" if "quality_hold" in types_of(t) else "customer"
        did.append(f"Contacted {plural(ok['crm.notify_customer'], who)}.")
    if ok["crm.assign_loaner"]:
        did.append(f"Gave loaner cars to {plural(ok['crm.assign_loaner'], 'priority customer')}"
                   + (f"; {missed} more were eligible but their dealer had none left." if missed else "."))
    if ok["escalate"]:
        did.append("Sent it to a person to check. No operational changes were made.")
    if not t["execution"]:
        did.append("Nothing, on purpose.")

    fails = n_failed(t)
    if n_writes(t):
        result = f"{plural(n_writes(t), 'change')} confirmed, {fails} failed."
    else:
        result = "No operational changes made." + (f" {fails} failed." if fails else "")
    lis = lambda xs: "<ul>" + "".join(f"<li>{x}</li>" for x in xs) + "</ul>"  # noqa: E731
    return (f'<div class="rp-sum"><div class="t">What happened</div>{lis(happened)}'
            f'<div class="t">What we did</div>{lis(did)}'
            f'<div class="t">Result</div><p>{result}</p></div>')


def scroll_to_top_once(token):
    """After a message is opened, jump the page back to the top so its title and details are in view.
    Runs once per newly opened message (a tiny invisible script; the app stays read-only)."""
    if st.session_state.get("_scrolled_for") == token:
        return
    st.session_state["_scrolled_for"] = token
    with st.container(key="scrolltop"):  # fixed script, no user or data text inside except a sanitised id
        st.iframe(
            f"<script>/* {safe(token)} */ const go = () => {{ const d = window.parent.document;"
            "const m = d.querySelector('[data-testid=\"stMain\"]'); if (m) m.scrollTop = 0;"
            "window.parent.scrollTo(0, 0); }; go(); [150, 400, 900].forEach(t => setTimeout(go, t));</script>",
            height=1)


def detail(t):
    scroll_to_top_once(t["event_id"])
    ev = events.get(t["event_id"])
    st.button("← All events", key="back", on_click=clear_sel, type="tertiary")
    status = (C.tone_pill(P, "sent to a person", "warn", True) if t["escalations"]
              else C.tone_pill(P, "no action", "ok") if not t["execution"] else "")
    pills = "".join(C.type_pill(P, x) for x in types_of(t)) + status
    st.html(
        '<div class="rp-card rp-stack">'
        + title(L.plain(t["event_id"]), pills)
        + f'<div class="rp-sub">{esc(t["received_at"].replace("T", " "))} · {source(t["source"])}</div>'
        + (f'<div class="rp-quote">{esc(ev["text"])}</div>' if ev else "")
        + event_story(t) + "</div>")
    st.html(C.stats([(len(t["incidents"]), "problems in this message", None), (n_writes(t), "changes made", None),
                     (len(kinds(t)), "types of action", None),
                     (n_failed(t), "failed or blocked", "bad" if n_failed(t) else "ok")]))
    tu, ti, tx = st.tabs(["1 · What we understood", "2 · What it affected, and why", "3 · What we did"])
    with tu:
        tab_understanding(t)
    with ti:
        tab_impact(t)
    with tx:
        tab_execution(t)


def type_filter():
    """A labelled dropdown filter (reads as a filter, not as a row of buttons). Returns the matching events."""
    types_all = sorted({x for t in traces for x in types_of(t)},
                       key=lambda x: list(TYPE_LABEL).index(x) if x in TYPE_LABEL else 99)
    flt = st.multiselect("Filter by event type", types_all, key="flt", placeholder="All event types",
                         format_func=lambda x: TYPE_LABEL.get(x, x))
    return [t for t in traces if not flt or any(x in flt for x in types_of(t))]


def feed_item(t):
    with st.container(key=f"feeditem_{safe(t['event_id'])}"):
        st.html(feed_card(t, sel == t["event_id"]))
        st.button(f"Open {t['event_id']}", key=f"b{t['event_id']}", on_click=select, args=(t["event_id"],))


def page_feed():
    if sel is None:
        # front page: run summary across the full width, then the events as a section underneath
        overview()
        with st.container(key="card_events"):
            fl, fr = st.columns([2, 1], vertical_alignment="bottom")
            with fr:
                rows = type_filter()
            fl.html(f'<div class="rp-head"><div class="rp-h1">Events</div></div>'
                    f'<div class="rp-sub">{len(rows)} of {len(traces)} shown</div>')
            if not rows:
                st.html('<div class="rp-note">No events match this filter.</div>')
            per_row = 4
            for i in range(0, len(rows), per_row):
                cols = st.columns(per_row)
                for col, t in zip(cols, rows[i:i + per_row]):
                    with col:
                        feed_item(t)
        return
    left, right = st.columns([1, 2.6], gap="large")
    with left:
        with st.container(key="feed"):
            rows = type_filter()
            if not rows:
                st.html('<div class="rp-note">No events match this filter.</div>')
            for t in rows:
                feed_item(t)
    with right:
        with st.container(key=f"detail_{safe(sel)}"):
            detail(by_id[sel])


# ============================================================================ other pages
def page_review():
    with st.container(key="page_review"):
        esc_ev = [t for t in traces if t["escalations"]]
        st.html(title("Human review"))
        if not esc_ev:
            st.html(C.callout("ok", "<b>Nothing escalated in this run.</b>"))
            return
        for t in esc_ev:
            with st.container(key=f"card_rev_{safe(t['event_id'])}"):
                writes = [r for r in t["execution"] if r["kind"] == "write"]
                checks = []
                for r in t["escalations"]:
                    head, _, ask = r.partition("Human should ")
                    checks.append((head.strip(), ask.strip()))
                body = "".join(
                    f'<div class="rp-body"><b>Why:</b> {pt(re.sub(r"^\[E-\d+#\d+\]\s*", "", h))}</div>'
                    + (C.callout("warn", f"<b>To verify:</b> {pt(a)}") if a else "") for h, a in checks)
                unres = [x for e in t["incidents"] for x in e["incident"].get("unresolved") or []]
                st.html(
                    '<div class="rp-stack">'
                    + f'<div class="rp-head"><div class="rp-h2" style="font-size:22px">{name(t["event_id"])}</div>'
                    f'<div class="rp-row">{"".join(C.type_pill(P, x) for x in types_of(t))}'
                    f'{C.tone_pill(P, "waiting on a human", "warn", True)}</div></div>'
                    + (f'<div class="rp-quote">{esc(events[t["event_id"]]["text"])}</div>' if t["event_id"] in events else "")
                    + body
                    + (C.callout("warn", "<b>Unresolved:</b> " + "; ".join(esc(x) for x in unres)) if unres else "")
                    + C.stats([(len(writes), "changes made", "ok" if not writes else "bad"),
                               (len(t["execution"]), "actions (the hand-off)", None)])
                    + "</div>")
                st.button(f"Open {L.plain(t['event_id']).lower()}", key=f"rev_{safe(t['event_id'])}", on_click=select,
                          args=(t["event_id"],))


def page_audit():
    with st.container(key="page_audit"):
        st.html(title("Audit trail"))
        if not log_exists:
            st.html(C.callout("bad", f"<b>Official log missing.</b> No action_log.jsonl in {esc(args.run)}."))
        elif SAME:
            st.html(C.callout("ok", f"<b>Our record matches the organizers' official log exactly</b> "
                                    f"({len(log)} actions, same order)."))
        elif log and calls:
            st.html(C.callout("bad", "<b>Our record and the organizers' official log differ.</b>"))
        st.html(C.stats([
            (len(log), "actions in the official log", None),
            (TOT["log_failed"], "failed", "ok" if not TOT["log_failed"] else "bad"),
            (sum(1 for r in calls if r["kind"] == "write"), "changes made", None),
            (sum(1 for r in calls if r["status"] == "unknown"), "no reply", None)]))
        if not calls:
            st.html('<div class="rp-note">No client_calls.jsonl in this run folder.</div>')
            return
        f1, f2 = st.columns(2)
        ev_f = f1.multiselect("Message", sorted(by_id), default=[], placeholder="All messages", format_func=L.plain)
        tool_f = f2.multiselect("Action", sorted({r["tool"] for r in calls}, key=L.tool_label), default=[],
                                placeholder="All actions", format_func=L.tool_label)
        rows = [r for r in calls if (not ev_f or r["event_id"] in ev_f) and (not tool_f or r["tool"] in tool_f)]
        df = pd.DataFrame([{"#": r["seq"], "Message": L.plain(r["event_id"]),
                            "Result": L.outcome(r["tool"], r.get("body"), r["status"]),
                            "Action": L.tool_label(r["tool"]), "Details": L.describe(r["tool"], r["args"]),
                            "Done by": r.get("agent"), "Time (ms)": r.get("ms")}
                           for r in rows])
        if len(df):
            st.dataframe(df, hide_index=True, width="stretch", height=520)
        else:
            st.html('<div class="rp-note">No actions match.</div>')


def page_graph():
    with st.container(key="page_graph"):
        st.html(title("Knowledge graph"))
        g = manifest.get("graph") or {}
        if not onto:
            st.html(C.callout("warn", "No graph export in this run folder."))
            return
        types = sorted({v["src"] for v in onto["edge_types"].values()} | {v["dst"] for v in onto["edge_types"].values()})
        with st.container(key="card_onto"):
            st.html(legend(P, types, derived=True))
            st.graphviz_chart(ontology_dot(P, onto, g), width="content")
        st.html(C.table(
            [("Link", ""), ("From", ""), ("To", ""), ("How many", "num")],
            [[esc(k.lower().replace("_", " ")), esc(v["src"]), esc(v["dst"]), f'{g.get("edges", {}).get(k, 0):,}']
             for k, v in onto["edge_types"].items()]))


def page_summary():
    with st.container(key="page_summary"):
        st.html(title("Run summary") + '<div style="height:14px"></div>'
                + C.stats([(TOT["events"], "messages", None), (TOT["writes"], "changes made", None),
                           (TOT["failed"], "failed actions", "ok" if not TOT["failed"] else "bad"),
                           (TOT["escalated"], "sent to a person", "warn" if TOT["escalated"] else None),
                           (TOT["noise"], "junk ignored", None)]))
        c1, c2 = st.columns([3, 2], gap="large")
        with c1:
            rows = []
            for t in traces:
                ex = t["execution"]
                esc_pill = C.tone_pill(P, "sent to a person", "warn", True) if t["escalations"] else ""
                rows.append(
                    f'<div class="rp-li"><div class="id">{name(t["event_id"])}</div>'
                    f'<div class="rp-row">{"".join(C.type_pill(P, x) for x in types_of(t))}{esc_pill}</div>'
                    f'<div class="nums"><span><b>{n_writes(t)}</b> changes</span>'
                    f'<span><b>{sum(1 for r in ex if r["kind"] == "read")}</b> look-ups</span>'
                    f'<span><b>{n_failed(t)}</b> failed</span></div></div>')
            st.html(f'<div class="rp-stack" style="gap:10px">{C.section("Each message")}'
                    f'<div class="rp-list">{"".join(rows)}</div></div>')
        with c2:
            tc = Counter(L.tool_label(r["tool"]) for r in calls if r["status"] == "confirmed")
            st.html(f'<div class="rp-stack" style="gap:10px">{C.section("Actions taken")}'
                    f'<div class="rp-card">{C.bars(tc.most_common())}</div></div>')


{"Event feed": page_feed, "Human review": page_review, "Audit trail": page_audit,
 "Knowledge graph": page_graph, "Run summary": page_summary}[view]()
