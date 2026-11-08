"""Ripple: control tower UI.

    streamlit run app.py -- --run submission --events data/events.json [--similar path/to/similar_incidents.json]

Reads only recorded run artifacts (event_traces.jsonl, action_log.jsonl, client_calls.jsonl, graph/,
similar_incidents.json), so it shows exactly what the agents did. The UI never calls the organizer server.
The one exception to "read only" is Human review: a confirmed message is previewed on a fresh in-process sandbox
copy of the organizer's system (ripple/review.py), and decisions are saved to runs/reviews/decisions.jsonl.
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
from ui import charts as CH
from ui import forecast as FC
from ui import labels as L
from ui.components import TYPE_LABEL, esc
from ui.graph import dot_graph, incident_edges, legend, nid, ntype, ontology_dot
from ui.similar import load_similar, neighbours
from ui.theme import P, css
from ui.why import why_html
from ripple import review

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
DATA_DIR = os.path.dirname(os.path.abspath(args.events))
L.load_reference_names(DATA_DIR)
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
    def shift(p):
        d = (datetime.date.fromisoformat(p["to"][1]) - datetime.date.fromisoformat(p["from"][1])).days
        return f"{d:+d} d"

    rows = [[name(p["production_order_id"]) + f"<div class='rp-sub'>{esc(p['production_order_id'])}</div>",
             esc(L.tool_label(p["tool"])) + f"<div class='rp-sub'>{esc(p['tool'])}</div>",
             where(p["from"]), where(p["to"]), shift(p), esc(L.move_reason(p.get("rationale")))] for p in moves]
    return C.table([("Car build", "id"), ("What we did", "nowrap"), ("Was planned for", "nowrap"),
                    ("Now planned for", "nowrap"), ("Shift", "num"), ("Why there", "wrap")], rows, max_height=380)


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
def message_about(t):
    """Short plain description of what a message was about, e.g. 'Plant outage, San Antonio plant'."""
    out = []
    for e in t["incidents"]:
        inc, imp = e["incident"], e.get("impact") or {}
        ents, ev = inc.get("entities") or {}, imp.get("evidence") or {}
        kind = TYPE_LABEL.get(inc["type"], inc["type"])
        if inc["type"] == "plant_outage":
            out.append(f"{kind}, {L.plain(ents.get('plant'))}")
        elif inc["type"] == "supplier_delay":
            out.append(f"{kind}, {L.plain(ents.get('part'))}")
        elif inc["type"] == "quality_hold":
            out.append(f"{kind}, {L.plain((ev.get('lot') or {}).get('part_id') or ents.get('part'))}")
        else:
            out.append(kind)
    return "; ".join(dict.fromkeys(out))


def open_from_chart():
    """Click on a bar in the per-message chart: open that message (a callback, so it runs before the page draws)."""
    state = st.session_state.get(f"permsg_{st.session_state.get('pm_n', 0)}") or {}
    selection = (state.get("selection") if hasattr(state, "get") else getattr(state, "selection", None)) or {}
    picked = selection.get("pick") or []
    eid = picked[0].get("eid") if picked else None
    if eid in by_id:
        st.session_state.pm_n = st.session_state.get("pm_n", 0) + 1  # fresh chart next time, so the click doesn't stick
        select(eid)


def ripple_numbers():
    """Headline 'how far did each message ripple' figures, computed from the trace and call files."""
    builds, orders = set(), set()
    for t in traces:
        for e in t["incidents"]:
            imp = e.get("impact") or {}
            builds.update(imp.get("affected_pos") or [])
            builds.update(nid(x["dst"]) for x in imp.get("path", []) if x["etype"] == "LOT_USED_IN_ORDER")
    for r in calls:
        if r["tool"] == "dealer.notify":
            orders.update(r["args"].get("customer_order_ids") or [])
    durs = [t.get("duration_ms") or 0 for t in traces]
    return {
        "messages": len(traces),
        "disruptions": sum(1 for t in traces for e in t["incidents"]
                           if e["incident"]["type"] in ("supplier_delay", "plant_outage", "quality_hold")),
        "builds": len(builds),
        "moved": sum(1 for r in calls if r["tool"] in ("mes.reschedule", "mes.transfer") and r["status"] == "confirmed"),
        "orders": len(orders),
        "dealers": len({r["args"].get("dealer_id") for r in calls if r["tool"] in ("dealer.notify", "dealer.stop_sale")}),
        "customers": sum(1 for r in calls if r["tool"] == "crm.notify_customer" and r["status"] == "confirmed"),
        "vehicles": sum(((e.get("impact") or {}).get("evidence") or {}).get("vehicles_total", 0)
                        for t in traces for e in t["incidents"] if e["incident"]["type"] == "quality_hold"),
        "stopped": sum(len(r["args"].get("vins") or []) for r in calls if r["tool"] == "dealer.stop_sale"),
        "loaners": sum(1 for r in calls if r["tool"] == "crm.assign_loaner" and r["status"] == "confirmed"),
        "missed": sum(1 for t in traces for x in t.get("loaners") or [] if not x.get("assigned")),
        "agree": sum(1 for t in traces if ((t.get("understanding") or {}).get("cross_check") or {}).get("agree")),
        "blocked": sum(len(t["blocked"]) for t in traces),
        "avg_s": (sum(durs) / len(durs) / 1000) if durs else 0,
        "edges": sum(len((e.get("impact") or {}).get("path", [])) for t in traces for e in t["incidents"])
        + sum(len((t.get("dealer_plan") or {}).get("path", [])) for t in traces),
    }


RIPPLE = ripple_numbers()


def overview():
    with st.container(key="card_overview"):
        st.html(
            '<div class="rp-stack">' + title("Run summary")
            + C.stats([(TOT["events"], "Messages received", None, f"{TOT['noise']} ignored as noise"),
                       (TOT["calls"], "Actions taken", "bad" if TOT["failed"] else None, f"{TOT['failed']} failed"),
                       (TOT["writes"], "Changes made", None, "builds, dealers, customers"),
                       (TOT["escalated"], "Sent to a person", None, "for a human to check")], hero=True)
            + "</div>")
        R = RIPPLE
        # full-width row: the ripple effect as one clean step line across the page
        with st.container(key="card_ripple"):
            step = lambda n, l, s="": (f'<div class="st"><div class="n">{n:,}</div><div class="l">{esc(l)}</div>'  # noqa: E731
                                       + (f'<div class="s">{esc(s)}</div>' if s else "") + "</div>")
            st.html(
                C.section("The ripple effect", "how far 15 messages reached, traced through the knowledge graph")
                + '<div class="rp-steps">'
                + step(R["messages"], "Messages received")
                + step(R["disruptions"], "Real disruptions found")
                + step(R["builds"], "Car builds affected", f"{R['moved']} moved to a new slot")
                + step(R["orders"], "Customer orders reached")
                + step(R["dealers"], "Dealers notified")
                + step(R["customers"], "Customers contacted")
                + "</div>"
                + '<div class="rp-steps-sub">'
                + f'<div><b>Quality holds:</b> {R["vehicles"]:,} vehicles checked for a faulty part, '
                  f'{R["stopped"]:,} unsold cars pulled from sale</div>'
                + f'<div><b>Loaner cars:</b> {R["loaners"]:,} given to priority customers, '
                  f'{R["missed"]:,} eligible with none left</div>'
                + "</div>")
        cl, cr = st.columns([1.7, 1], gap="medium")
        with cr:
            with st.container(key="card_checks"):
                row = lambda l, v, ok=True: (f'<div class="rp-check"><span class="d{"" if ok else " bad"}"></span>'  # noqa: E731
                                             f'<span class="l">{esc(l)}</span><span class="v">{esc(v)}</span></div>')
                st.html(
                    C.section("Checks and speed")
                    + row("Language model and rule check agreed on the message type", f"{R['agree']} / {TOT['events']}",
                          R["agree"] == TOT["events"])
                    + row("Actions accepted by the company systems", f"{TOT['calls'] - TOT['failed']} / {TOT['calls']}",
                          not TOT["failed"])
                    + row("Unsafe changes stopped before sending", f"{R['blocked']}")
                    + row("Matches the organizers' official log", f"{len(log)} / {len(calls)}" if SAME else "differs", SAME)
                    + row("Average time to handle a message", f"{R['avg_s']:.1f} s")
                    + row("Knowledge-graph links followed", f"{R['edges']:,}"))
        with cl, st.container(key="card_permsg"):
            st.html(C.section("Actions taken for each message", "click a bar to open the message"))
            bars = []
            for t in traces:
                k = Counter(r["kind"] for r in t["execution"])
                for kind, label in (("write", "Changes made"), ("read", "Look-ups"), ("escalation", "Sent to a person")):
                    bars.append({"eid": t["event_id"], "num": int(t["event_id"].split("-")[1]), "kind": label,
                                 "n": k.get(kind, 0), "total": len(t["execution"]), "about": message_about(t),
                                 "source": t["source"]})
            n = st.session_state.setdefault("pm_n", 0)
            st.altair_chart(CH.actions_per_message(bars), on_select=open_from_chart, selection_mode=["pick"],
                            key=f"permsg_{n}", theme=None, width="stretch")


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


CHAIN_ORDER = ["Supplier", "Lot", "Shipment", "Part", "Plant", "Model", "ProductionOrder", "CustomerOrder",
               "Vehicle", "Dealer", "Customer"]
CHAIN_WORD = {"Supplier": ("supplier", "suppliers"), "Lot": ("parts batch", "parts batches"),
              "Shipment": ("shipment", "shipments"), "Part": ("part", "parts"), "Plant": ("plant", "plants"),
              "Model": ("car model", "car models"), "ProductionOrder": ("car build", "car builds"),
              "CustomerOrder": ("customer order", "customer orders"), "Vehicle": ("finished car", "finished cars"),
              "Dealer": ("dealer", "dealers"), "Customer": ("customer", "customers")}


def spread_chain(edges):
    """Compact version of the impact graph: one step per kind of thing, in the order the problem travels.
    A single item is named; a group shows its count."""
    groups = {}
    for ed in edges:
        for k in (ed["src"], ed["dst"]):
            groups.setdefault(ntype(k), set()).add(nid(k))
    steps = []
    for t in CHAIN_ORDER:
        ids = groups.get(t)
        if not ids:
            continue
        one, many = CHAIN_WORD[t]
        if len(ids) == 1:
            value = L.plain(next(iter(ids)))
            if t == "Plant":
                value = value.removesuffix(" plant")
            steps.append((one.capitalize(), value, "name"))
        else:
            steps.append((many.capitalize(), f"{len(ids):,}", "count"))
    cells = "".join(f'<div class="st {kind}"><div class="l">{esc(lbl)}</div><div class="n">{esc(v)}</div></div>'
                    for lbl, v, kind in steps)
    return f'<div class="rp-chain">{cells}</div>'


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
                kept = sorted({ntype(x) for ed in edges for x in (ed["src"], ed["dst"])})
                st.html(C.section("How the problem spreads", f"{len(edges):,} graph links traversed")
                        + spread_chain(edges)
                        + f'<div class="rp-note">{esc(L.graph_caption(kept))}</div>')
                with st.expander("Show the full graph"):
                    focus = st.selectbox("Focus on", ["All affected builds"] + pos, key=f"f{safe(iid)}",
                                         format_func=lambda v: v if v == "All affected builds" else L.plain(v))
                    vstat = {v["vin"]: v.get("status") for v in imp.get("vehicles") or []}
                    st.html(legend(P, kept, derived=any(x.get("derived") for x in edges))
                            + '<div class="rp-note">Boxes with a count stand for a group, e.g. "10 customer orders". '
                              'Pick one build to see each order, dealer and customer behind it.</div>')
                    st.graphviz_chart(dot_graph(P, edges, None if focus == "All affected builds" else focus, MEANINGS,
                                                vstat), width="content")
                with st.expander(f"Every connection in the graph, and the data file it comes from ({len(edges)})"):
                    st.html('<div class="rp-note">Each line is one arrow in the full graph, written as a sentence. '
                            '"Worked out" means the data has no direct column for it: we inferred it from the plant, '
                            'the build dates and the parts list.</div>'
                            + C.table([("Connection", "wrap"), ("Link type", "small"), ("Source table", "nowrap"),
                                       ("Record key", "id")],
                                      [[esc(L.link_sentence(x["etype"], nid(x["src"]), nid(x["dst"])))
                                        + (" <span class='rp-sub'>(worked out)</span>" if x.get("derived") else ""),
                                        esc(x["etype"]),
                                        f"{esc(L.data_file(x.get('source_table')))}"
                                        f"<div class='rp-sub'>{esc(x.get('source_table'))}</div>",
                                        esc(x.get("source_key"))] for x in edges], max_height=420))
            if inc["type"] == "quality_hold":
                quality_block(e)
            mine = [p for p in moves_all if iid in p.get("incidents", [])]
            used.update(id(p) for p in mine)
            if mine:
                n_tr = sum(1 for p in mine if p["tool"] == "mes.transfer")
                slips = [(datetime.date.fromisoformat(p["to"][1]) - datetime.date.fromisoformat(p["from"][1])).days
                         for p in mine]
                st.html(C.section("Where each build moved", "hover a dot for the reason")
                        + C.stats([(len(mine), "Builds rescheduled", None),
                                   (f"{sum(slips) / len(slips):+.1f} d", "Average shift", None),
                                   (f"{max(slips):+d} d", "Largest shift", None),
                                   (n_tr, "Moved to another plant", None)])
                        + f'<div class="rp-note">One row per car build. The <b>gray dot</b> is the day it was planned; '
                          f'the <b>colored dot</b> is its new day. Blue means a later day at the same plant'
                          + (f'; orange means it moved to another plant ({n_tr} build{"s" if n_tr != 1 else ""})'
                             if n_tr else "") + ". The longer the line, the bigger the shift."
                          + (" A negative shift means another plant could build the car sooner than first planned."
                             if min(slips) < 0 else "") + "</div>")
                st.altair_chart(CH.build_moves([{
                    "build": L.plain(p["production_order_id"]), "from_day": p["from"][1], "to_day": p["to"][1],
                    "from_txt": f"{L.plain(p['from'][0])}, {L.plain_date(p['from'][1])}",
                    "to_txt": f"{L.plain(p['to'][0])}, {L.plain_date(p['to'][1])}",
                    "how": "Another plant" if p["tool"] == "mes.transfer" else "Later day, same plant",
                    "shift": f"{(datetime.date.fromisoformat(p['to'][1]) - datetime.date.fromisoformat(p['from'][1])).days:+d} days",
                    "why": L.move_reason(p.get("rationale"))} for p in mine]), theme=None, width="stretch")
                with st.expander("Same moves as a table"):
                    st.html(moves_table(mine))
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
                + '<div class="rp-h2" style="font-size:22px">Dealers and loaner cars</div>'
                + C.policy_lines(pol if isinstance(pol, list) else [pol] if pol else [])
                + C.stats([(notified, "Dealer notices sent", None), (got, "Loaner cars given", None),
                           (len(miss), "Eligible, but none left", None),
                           (len(std), "Standard tier, notice only", None)])
                + '<div class="rp-note">Every dealer with a delayed order got one notice. Loaner cars go to Platinum '
                  'and Gold customers only: Platinum first, then the earliest promised delivery date, until that '
                  "dealer's loaners run out. Rows still waiting for a loaner are listed first.</div>"
                + C.table([("Place in line", "num"), ("Dealer", "nowrap"), ("Customer order", "nowrap"), ("Tier", ""),
                           ("Promised for", "nowrap"), ("Loaner", ""), ("Why", "wrap")],
                          [[esc(x.get("rank")), name(x.get("dealer_id")), name(x.get("customer_order_id")),
                            esc(x.get("tier")), esc(L.plain_date(x.get("promised_date"))),
                            C.tone_pill(P, "given", "ok") if x.get("assigned") else C.tone_pill(P, "none left", "warn"),
                            esc(L.loaner_reason(x.get("why")))] for x in ordered],
                          max_height=380, row_class=lambda i: "" if ordered[i].get("assigned") else "miss")
                + "</div>")


def why_picker(t, rows, key, where="organizer system"):
    """'Why this action?': pick one action, see the rule, the message evidence, the graph links and the checks."""
    with st.container(key=f"card_{key}"):
        st.html(C.section("Why this action?", "rule · evidence · graph links · checks"))
        seq = st.selectbox("Pick an action", [None] + [r["seq"] for r in rows], key=key, label_visibility="collapsed",
                           format_func=lambda s: "Pick an action to see why it was taken" if s is None else
                           f"#{s} · " + next(f"{L.tool_label(r['tool'])} · {L.describe(r['tool'], r.get('args'))}"
                                             for r in rows if r["seq"] == s))
        if seq is not None:
            st.html(why_html(t, seq, DATA_DIR, where))


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
        if rows:
            why_picker(t, rows, key=f"why{safe(t['event_id'])}")
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
        embed = getattr(st, "iframe", None)
        if embed is None:  # Streamlit < 1.56 has no st.iframe
            import streamlit.components.v1 as components
            embed = components.html
        embed(
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
        # invisible button stretched over the whole card, so clicking anywhere on it opens the message
        st.button(f"Open {L.plain(t['event_id']).lower()}", key=f"b{t['event_id']}", on_click=select,
                  args=(t["event_id"],))


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
        decisions = review.load()
        decided = {d["incident_id"]: d for d in decisions}
        items = review.pending(traces, decisions)
        with st.container(key="card_reviewer"):
            r1, r2 = st.columns([2, 3])
            reviewer = r1.text_input("Your name (recorded with every decision)", key="reviewer").strip()
            r2.radio("Read confirmed messages with", ["rules", "cascade"], key="rev_kind", horizontal=True,
                     help="rules: no network. cascade: rules first, the language model only when the rules are unsure.")
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
                    f'{review_pill(t, decided)}</div></div>'
                    + (f'<div class="rp-quote">{esc(events[t["event_id"]]["text"])}</div>' if t["event_id"] in events else "")
                    + body
                    + (C.callout("warn", "<b>Unresolved:</b> " + "; ".join(esc(x) for x in unres)) if unres else "")
                    + C.stats([(len(writes), "changes made", "ok" if not writes else "bad"),
                               (len(t["execution"]), "actions (the hand-off)", None)])
                    + "</div>")
                st.button(f"Open {L.plain(t['event_id']).lower()}", key=f"rev_{safe(t['event_id'])}", on_click=select,
                          args=(t["event_id"],))
                for it in [i for i in items if i["event_id"] == t["event_id"]]:
                    review_controls(it, reviewer, decided.get(it["incident_id"]))
        decision_log(decisions)


def review_pill(t, decided):
    ds = [decided[e["incident"]["incident_id"]] for e in t["incidents"] if e["incident"]["incident_id"] in decided]
    if not ds:
        return C.tone_pill(P, "waiting on a human", "warn", True)
    return C.tone_pill(P, f"reviewed: {ds[-1]['decision']}", "ok")


@st.cache_resource
def sandbox_engine(data_dir):
    from ripple.graph import KnowledgeGraph
    from ripple.world import World
    w = World.load(data_dir)
    return w, KnowledgeGraph(w)


@st.cache_resource
def sandbox_extractor(data_dir, kind):
    from ripple.extract import make_extractor
    return make_extractor(sandbox_engine(data_dir)[0], kind)


def review_controls(it, reviewer, done):
    """Dismiss, or confirm with the missing facts -> preview on a sandbox copy -> approve or reject."""
    k = safe(it["incident_id"])
    with st.container(key=f"card_act_{k}"):
        if done:
            st.html(C.callout("ok", f"<b>{esc(done['decision'].capitalize())}</b> by {esc(done['reviewer'])} at "
                                    f"{esc(done['at'][11:16])}" + (f": {esc(done['note'])}" if done["note"] else "")
                              + (f" · {done['outcome']['writes']} changes approved in the sandbox" if done.get("outcome")
                                 and done["decision"] == "approved" else "")))
            return
        st.html(C.section("Your decision", "runs in a sandbox copy · never touches the official log"))
        mode = st.radio("Decision", ["Confirm it with the missing facts", "Dismiss: no action needed"], key=f"m_{k}",
                        horizontal=True, label_visibility="collapsed")
        if mode.startswith("Dismiss"):
            note = st.text_input("Why no action is needed", key=f"n_{k}")
            if st.button("Record dismissal", key=f"d_{k}", disabled=not reviewer):
                review.record(it, "dismissed", reviewer, note)
                st.rerun()
            return
        txt = st.text_area("Confirmed message: name the supplier or plant, the part, and the dates", key=f"t_{k}",
                           placeholder="e.g. Confirmed by <supplier>: the <part> due at <plant> on <date> will now arrive <date>.")
        if st.button("Preview what the agents would do", key=f"p_{k}", disabled=not txt.strip()):
            with st.spinner("Running the agents on a sandbox copy"):
                st.session_state[f"tr_{k}"] = review.preview(*sandbox_engine(DATA_DIR), sandbox_extractor(
                    DATA_DIR, st.session_state.get("rev_kind", "rules")), it, txt, data_dir=DATA_DIR)
                st.session_state[f"txt_{k}"] = txt
        tr = st.session_state.get(f"tr_{k}")
        if not tr:
            return
        o = review.outcome(tr)
        st.html(C.stats([(", ".join(C.TYPE_LABEL.get(x, x) for x in o["types"]), "read as", None),
                         (o["writes"], "changes proposed", None),
                         (o["blocked"], "blocked by checks", "bad" if o["blocked"] else None),
                         (o["failed"], "failed", "bad" if o["failed"] else None)]))
        if o["escalated_again"]:
            st.html(C.callout("warn", "<b>The agents still would not act.</b> " + pt(" ".join(tr["escalations"]))
                              + " Add the missing fact and preview again."))
        else:
            ws = review.writes(tr)
            st.html(C.callout("ok", pt(tr["summary"]))
                    + C.table([("#", "num"), ("Action", "nowrap"), ("Details", "wrap"), ("Rule", "nowrap")],
                              [[esc(r["seq"]), f"<b>{esc(L.tool_label(r['tool']))}</b>", esc(L.describe(r["tool"], r["args"])),
                                esc((r.get("rule") or "").split(":")[0])] for r in ws], max_height=320))
            why_picker(tr, ws, key=f"why_rev_{k}", where="sandbox copy of the organizer system")
        note = st.text_input("Note (optional)", key=f"rn_{k}")
        a, b, _ = st.columns([1, 1, 3])
        if a.button("Approve these actions", key=f"a_{k}", type="primary",
                    disabled=not reviewer or o["escalated_again"] or not o["writes"]):
            review.record(it, "approved", reviewer, note, st.session_state[f"txt_{k}"], tr)
            st.rerun()
        if b.button("Reject", key=f"r_{k}", disabled=not reviewer):
            review.record(it, "rejected", reviewer, note, st.session_state[f"txt_{k}"], tr)
            st.rerun()
        if not reviewer:
            st.html('<div class="rp-note">Enter your name at the top of this page to record a decision.</div>')


def decision_log(decisions):
    st.html(C.section("Decision log", "saved to runs/reviews/decisions.jsonl"))
    if not decisions:
        st.html('<div class="rp-note">No decisions yet.</div>')
        return
    st.html(C.table([("Time", "nowrap"), ("Reviewer", "nowrap"), ("Message", "nowrap"), ("Decision", "nowrap"),
                     ("Changes", "num"), ("Note", "wrap")],
                    [[esc(d["at"].replace("T", " ")), esc(d["reviewer"]), esc(L.plain(d["event_id"])),
                      C.tone_pill(P, d["decision"], "ok" if d["decision"] != "rejected" else "warn"),
                      esc((d.get("outcome") or {}).get("writes", 0) if d["decision"] == "approved" else 0), esc(d["note"])]
                     for d in reversed(decisions)]))


def page_audit():
    with st.container(key="page_audit"):
        st.html(title("Audit trail"))
        if not log_exists:
            st.html(C.callout("bad", f"<b>Official log missing.</b> No action_log.jsonl in {esc(args.run)}."))
        elif log and calls and not SAME:  # only speak up when something is wrong
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
            pick = [r for r in rows if r["kind"] != "read" and r["event_id"] in by_id][:2000]
            eid_of = {r["seq"]: r["event_id"] for r in pick}
            with st.container(key="card_why_audit"):
                st.html(C.section("Why this action?", "rule · evidence · graph links · checks"))
                seq = st.selectbox("Pick an action", [None] + list(eid_of), key="why_audit", label_visibility="collapsed",
                                   format_func=lambda s: "Pick an action to see why it was taken" if s is None else
                                   f"#{s} · {L.plain(eid_of[s])} · " + next(
                                       f"{L.tool_label(r['tool'])} · {L.describe(r['tool'], r['args'])}" for r in pick if r["seq"] == s))
                if seq is not None:
                    st.html(why_html(by_id[eid_of[seq]], seq, DATA_DIR))
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
            with st.container(key="card_kinds"):
                st.html(C.section("Actions taken", "hover a bar"))
                st.altair_chart(CH.actions_by_kind(tc.most_common()), theme=None, width="stretch")
            with st.container(key="card_load"):
                st.html(C.section("Actions so far, through the morning", "hover the line"))
                total, pts = 0, []
                for t in traces:
                    total += len(t["execution"])
                    pts.append({"received_at": t["received_at"], "label": L.plain(t["event_id"]),
                                "added": len(t["execution"]), "total": total})
                st.altair_chart(CH.workload_area(pts), theme=None, width="stretch")
        forecasts()


@st.cache_data
def _token_rows(tok):
    return FC.token_savings(list(tok), [100, 1000, 2500, 5000, 7500, 10000])


@st.cache_data
def _time_dist(acts, secs, n, lo, mode, hi):
    return FC.time_savings(list(acts), list(secs), n, lo, mode, hi)


def forecasts():
    """Two forward-looking probability charts, clearly labelled as estimates."""
    tok = tuple((t.get("understanding") or {}).get("tokens", {}).get("totalTokenCount") or 0 for t in traces)
    acts = tuple(len(t["execution"]) for t in traces)
    secs = tuple((t.get("duration_ms") or 0) / 1000 for t in traces)
    st.html('<div style="height:6px"></div>' + title("Forecasts", C.tone_pill(P, "Estimate, not measured", "warn")))
    c1, c2 = st.columns(2, gap="medium")
    with c1, st.container(key="card_fc_tokens"):
        rows = _token_rows(tok)
        k = next(r for r in rows if r["n"] == 1000)
        st.html(C.section("AI tokens saved by the rules-first mode (thousands)", "hover a point")
                + f'<div class="rp-note">At 1,000 messages: <b>{k["p50"]:,.0f}</b> tokens saved (median), '
                  f'90% likely between {k["p5"]:,.0f} and {k["p95"]:,.0f}, about {k["share"]:.0%} of what the AI would '
                  f'otherwise use. Dark band: 50% likely, light band: 90% likely.</div>')
        st.altair_chart(CH.token_forecast(rows), theme=None, width="stretch")
        st.html('<div class="rp-note">Based on: tokens per message in this run (341 to 581), and how often the '
                'rules-first mode still needed the AI in testing (5 of 30 messages, DESIGN_CARD.md).</div>')
    with c2, st.container(key="card_fc_time"):
        a, b = st.columns(2)
        n = a.select_slider("Messages to project", [15, 50, 100, 250, 500, 1000], value=100, key="fc_n")
        mode = b.select_slider("Minutes a person needs per action", [0.5, 1.0, 1.5, 2.0, 3.0, 5.0], value=1.5,
                               key="fc_min")
        hist, q, app_h = _time_dist(acts, secs, n, mode / 3, mode, mode * 2.5)
        st.html(C.section("Staff time saved handling disruptions (probability)", "hover a bar")
                + f'<div class="rp-note">For {n:,} messages: <b>{q["p50"]:,.0f} hours</b> of manual work saved '
                  f'(median), 90% likely between {q["p5"]:,.0f} and {q["p95"]:,.0f} hours. Ripple itself needs about '
                  f'{app_h * 60:,.0f} minutes.</div>')
        st.altair_chart(CH.time_forecast(hist, q), theme=None, width="stretch")
        st.html('<div class="rp-note">Based on: actions per message and Ripple\'s handling time in this run. The '
                f'minutes per action is an assumption (range {mode / 3:.1f} to {mode * 2.5:.1f} min); change it above.</div>')


{"Event feed": page_feed, "Human review": page_review, "Audit trail": page_audit,
 "Knowledge graph": page_graph, "Run summary": page_summary}[view]()
