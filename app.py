"""Ripple Control: control tower UI.

    streamlit run app.py -- --run runs/run1

Reads only recorded run artifacts (event_traces.jsonl, action_log.jsonl, client_calls.jsonl, graph/),
so it shows exactly what the agents did. No tool calls are made from the UI.
"""
import argparse
import json
import os
from collections import Counter, defaultdict

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Ripple Control", page_icon="🚗", layout="wide")

TYPE_LABEL = {"supplier_delay": "Supplier delay", "plant_outage": "Plant outage", "quality_hold": "Quality hold",
              "noise": "Noise", "unconfirmed": "Unconfirmed"}
TYPE_ICON = {"supplier_delay": "🚚", "plant_outage": "🏭", "quality_hold": "🧪", "noise": "🔇", "unconfirmed": "❓"}
NODE_COLOR = {"Supplier": "#8E7CC3", "Shipment": "#6FA8DC", "Part": "#76A5AF", "Model": "#93C47D", "Plant": "#F6B26B",
              "ProductionOrder": "#E06666", "CustomerOrder": "#FFD966", "Customer": "#C27BA0", "Dealer": "#A4C2F4",
              "Lot": "#B45F06", "Vehicle": "#999999", "LoanerPool": "#D9D9D9"}
STATUS_ICON = {"confirmed": "✅", "rejected": "❌", "unknown": "⚠️", "blocked": "⛔"}


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="runs/run1")
    ap.add_argument("--events", default="data/events.json")
    try:
        return ap.parse_args()
    except SystemExit:
        return ap.parse_args([])


@st.cache_data
def load(run_dir, events_path):
    rl = lambda p: [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()] if os.path.exists(p) else []
    traces = rl(os.path.join(run_dir, "event_traces.jsonl"))
    log = rl(os.path.join(run_dir, "action_log.jsonl"))
    calls = rl(os.path.join(run_dir, "client_calls.jsonl"))
    manifest = json.load(open(os.path.join(run_dir, "run_manifest.json"))) if os.path.exists(os.path.join(run_dir, "run_manifest.json")) else {}
    events = {e["event_id"]: e for e in json.load(open(events_path, encoding="utf-8"))} if os.path.exists(events_path) else {}
    return traces, log, calls, manifest, events


def ntype(k):
    return k.split(":", 1)[0]


def nid(k):
    return k.split(":", 1)[1]


def incident_edges(trace, entry):
    """Graph edges for one incident: its own impact path plus dealer edges for its affected orders."""
    imp = entry.get("impact") or {}
    edges = list(imp.get("path", []))
    pos = {f"ProductionOrder:{p}" for p in imp.get("affected_pos", [])}
    dp = (trace.get("dealer_plan") or {}).get("path", [])
    cos = {e["dst"] for e in dp if e["src"] in pos}
    edges += [e for e in dp if e["src"] in pos or e["src"] in cos]
    return edges


def dot_graph(edges, focus_po=None):
    """DOT for a path. Head entities are drawn individually; bulky leaf types are grouped per parent
    unless a single production order is in focus, in which case its full subtree is drawn."""
    leaf = {"CustomerOrder", "Customer", "Dealer", "Vehicle"}
    if focus_po:
        root = f"ProductionOrder:{focus_po}"
        keep, frontier = {root}, [root]
        while frontier:
            n = frontier.pop()
            for e in edges:
                if e["src"] == n and ntype(e["dst"]) in leaf and e["dst"] not in keep:
                    keep.add(e["dst"]); frontier.append(e["dst"])
        edges = [e for e in edges if (ntype(e["dst"]) != "ProductionOrder" or e["dst"] == root)
                 and (ntype(e["src"]) not in leaf | {"ProductionOrder"} or e["src"] in keep)]
    labels, lines, seen, groups = {}, [], set(), defaultdict(set)
    for e in edges:
        s, d = e["src"], e["dst"]
        if not focus_po and ntype(s) in leaf:
            continue
        if not focus_po and ntype(d) in leaf:
            groups[(s, ntype(d))].add(d)
            continue
        labels[s], labels[d] = s, d
        if (s, d, e["etype"]) not in seen:
            seen.add((s, d, e["etype"]))
            style = ', style=dashed, color="#B45F06"' if e.get("derived") else ""
            lines.append(f'"{s}" -> "{d}" [label="{e["etype"].lower()}", fontsize=8{style}];')
    nodes = {n: (ntype(n), n.replace(":", "\\n", 1)) for n in labels}
    for (parent, t), members in groups.items():
        g = f"{t}@{parent}"
        lab = f"{t} x{len(members)}" + ("\\n" + "\\n".join(sorted(nid(m) for m in members)) if len(members) <= 3 else "")
        nodes[g] = (t, lab)
        lines.append(f'"{parent}" -> "{g}" [fontsize=8];')
    out = ['digraph G { rankdir=LR; node [shape=box, style="rounded,filled", fontname="Helvetica", fontsize=10];']
    out += [f'"{n}" [label="{lab}", fillcolor="{NODE_COLOR.get(t, "#eee")}"];' for n, (t, lab) in nodes.items()]
    return "\n".join(out + lines + ["}"])


# ============================================================================ page
args = parse_args()
traces, log, calls, manifest, events = load(args.run, args.events)
if not traces:
    st.error(f"No event_traces.jsonl in {args.run}. Run `python run.py ...` first.")
    st.stop()
by_id = {t["event_id"]: t for t in traces}

st.sidebar.title("🚗 Ripple Control")
st.sidebar.caption("Wacky Wheels Co. event-driven control tower")
view = st.sidebar.radio("View", ["Event feed", "Human review", "Audit trail", "Knowledge graph", "Run summary"])
st.sidebar.divider()
st.sidebar.markdown(f"**Run** `{manifest.get('run_id', '?')}`  \n**Mode** {manifest.get('mode', '?')}  \n"
                    f"**Extractor** {manifest.get('extractor', '?')}  \n**Snapshot** `{manifest.get('snapshot_id', '?')}`")
st.sidebar.caption("Planning, graph traversal and policy checks are deterministic code. "
                   "The extractor only proposes incident facts.")


def kinds(t):
    return sorted({r["tool"] for r in t["execution"] if r["kind"] != "read" and r["status"] == "confirmed"})


# ---------------------------------------------------------------------------- Event feed
if view == "Event feed":
    left, right = st.columns([1, 2.4], gap="large")
    with left:
        st.subheader("Event feed")
        types_all = sorted({i["incident"]["type"] for t in traces for i in t["incidents"]})
        flt = st.multiselect("Filter by type", types_all, format_func=lambda x: TYPE_LABEL.get(x, x))
        rows = [t for t in traces if not flt or any(i["incident"]["type"] in flt for i in t["incidents"])]
        if "sel" not in st.session_state or st.session_state.sel not in by_id:
            st.session_state.sel = rows[0]["event_id"] if rows else traces[0]["event_id"]
        for t in rows:
            types = [i["incident"]["type"] for i in t["incidents"]]
            n_w = sum(1 for r in t["execution"] if r["kind"] == "write" and r["status"] == "confirmed")
            icon = " ".join(TYPE_ICON.get(x, "") for x in types)
            label = f"{icon} **{t['event_id']}** · {t['received_at'][11:16]} · {t['source']}  \n" \
                    f"{' + '.join(TYPE_LABEL.get(x, x) for x in types)} · {n_w} writes" + \
                    (" · escalated" if t["escalations"] else "")
            if st.button(label, key=f"b{t['event_id']}", use_container_width=True,
                         type="primary" if st.session_state.sel == t["event_id"] else "secondary"):
                st.session_state.sel = t["event_id"]
                st.rerun()
    t = by_id[st.session_state.sel]
    with right:
        ev = events.get(t["event_id"], {})
        st.subheader(f"{t['event_id']} · {t['source']}")
        st.caption(f"Received {t['received_at']} · handled in {t.get('duration_ms', '?')} ms")
        if ev:
            st.info(ev["text"])
        st.markdown(f"**Summary.** {t['summary']}")
        ex = t["execution"]
        c = st.columns(4)
        c[0].metric("Incidents", len(t["incidents"]))
        c[1].metric("Confirmed writes", sum(1 for r in ex if r["kind"] == "write" and r["status"] == "confirmed"))
        c[2].metric("Action kinds", len(kinds(t)))
        c[3].metric("Failed / blocked", sum(1 for r in ex if r["status"] != "confirmed") + len(t["blocked"]))

        tab_u, tab_i, tab_x = st.tabs(["1 · Event understanding", "2 · Impact and policy", "3 · Execution and outcome"])
        with tab_u:
            u = t.get("understanding", {})
            st.caption(f"Extractor: {u.get('extractor')} · {u.get('extract_ms')} ms"
                       + (f" · fell back to rules: {u['fallback']}" if u.get("fallback") else ""))
            for e in t["incidents"]:
                inc = e["incident"]
                with st.container(border=True):
                    st.markdown(f"#### {TYPE_ICON.get(inc['type'], '')} {inc['incident_id']} · {TYPE_LABEL.get(inc['type'])}"
                                f" · {'confirmed' if inc['confirmed'] else 'unconfirmed'}")
                    st.markdown(f"> {inc['evidence_span']}")
                    st.caption(f"Classifier reason: {inc['extractor_reason']}")
                    ents = pd.DataFrame([{"type": x["type"], "phrase in text": x.get("phrase"), "resolved id": x.get("id", "—"),
                                          "matched via": x.get("matched", ""), "source": x.get("source", "")}
                                         for x in inc["entity_evidence"]])
                    if len(ents):
                        st.markdown("**Resolved entities**")
                        st.dataframe(ents, hide_index=True, use_container_width=True)
                    if inc["dates"]:
                        st.markdown("**Resolved dates**")
                        st.dataframe(pd.DataFrame([{"role": k, "phrase": v["phrase"], "date": v["value"], "rule": v["rule"]}
                                                   for k, v in inc["dates"].items()]), hide_index=True, use_container_width=True)
                    if inc["unresolved"]:
                        st.warning("Unresolved: " + "; ".join(inc["unresolved"]))
        with tab_i:
            for e in t["incidents"]:
                inc, imp = e["incident"], e.get("impact")
                with st.container(border=True):
                    st.markdown(f"#### {inc['incident_id']} · {TYPE_LABEL.get(inc['type'])} → {e.get('agent') or 'Coordinator'}")
                    st.markdown(f"**Decision:** {e.get('decision')}")
                    for p in (imp or {}).get("policy", e.get("policy", [])):
                        st.caption(f"📘 {p}")
                    if not imp:
                        st.write(e.get("reason", ""))
                        continue
                    if imp.get("unresolved"):
                        st.warning("; ".join(imp["unresolved"]))
                    evd = imp.get("evidence", {})
                    if imp.get("status") == "actionable":
                        edges = incident_edges(t, e)
                        pos = imp.get("affected_pos") or sorted({nid(x["dst"]) for x in edges if x["etype"] == "LOT_USED_IN_ORDER"})
                        focus = st.selectbox("Graph focus", ["(all, leaves grouped)"] + pos, key=f"f{inc['incident_id']}")
                        st.graphviz_chart(dot_graph(edges, None if focus.startswith("(") else focus), use_container_width=True)
                        st.caption("Dashed orange edges are derived (lot → order via plant + build window + BOM).")
                        cnt = Counter(x["etype"] for x in edges)
                        st.markdown("**Traversed edges:** " + ", ".join(f"`{k}` ×{v}" for k, v in cnt.items()))
                        with st.expander("Edge evidence (source table and record key)"):
                            st.dataframe(pd.DataFrame(edges)[["etype", "src", "dst", "source_table", "source_key", "derived"]],
                                         hide_index=True, use_container_width=True)
                    show = {k: v for k, v in evd.items() if k not in ("shipment_candidates",)}
                    if show:
                        with st.expander("Window, eligibility and record evidence", expanded=True):
                            st.json(show, expanded=1)
            moves = [p for p in t["plan"] if "production_order_id" in p]
            if moves:
                st.markdown("#### Slot decisions (rule 3)")
                st.dataframe(pd.DataFrame([{"order": p["production_order_id"], "tool": p["tool"], "from": " ".join(p["from"]),
                                            "to": " ".join(p["to"]), "why": p["rationale"], "incidents": ", ".join(p["incidents"])}
                                           for p in moves]), hide_index=True, use_container_width=True)
            if t.get("loaners"):
                st.markdown("#### Loaner allocation (rule 5)")
                st.dataframe(pd.DataFrame(t["loaners"])[["dealer_id", "rank", "customer_order_id", "tier", "promised_date",
                                                         "assigned", "why"]], hide_index=True, use_container_width=True)
                std = (t.get("dealer_plan") or {}).get("standard_no_loaner", [])
                st.caption(f"{len(std)} Standard-tier customer orders were included in dealer notices and received no loaner.")
        with tab_x:
            if not ex:
                st.success("No tool calls. " + (t["incidents"][0].get("reason", "") if t["incidents"] else ""))
            else:
                df = pd.DataFrame([{"#": r["seq"], "": STATUS_ICON.get(r["status"], ""), "tool": r["tool"], "kind": r["kind"],
                                    "agent": r.get("agent"), "purpose": r.get("purpose"),
                                    "args": json.dumps({k: v for k, v in r["args"].items() if k != "message"})[:160],
                                    "result": json.dumps(r.get("body"))[:120] if r["status"] == "confirmed" else r.get("error"),
                                    "ms": r.get("ms")} for r in ex])
                show_reads = st.toggle("Show read calls", value=False, key=f"rd{t['event_id']}")
                st.dataframe(df if show_reads else df[df.kind != "read"], hide_index=True, use_container_width=True, height=420)
            if t["blocked"]:
                st.error("Blocked by validation before sending:")
                st.json(t["blocked"])
            for r in t["escalations"]:
                st.warning(f"🧑‍💼 Escalated to human: {r}")

# ---------------------------------------------------------------------------- Human review
elif view == "Human review":
    st.subheader("🧑‍💼 Human review queue")
    st.caption("Every `escalate` call, with the reason and what a human needs to verify. No operational changes were made for these.")
    esc = [t for t in traces if t["escalations"]]
    if not esc:
        st.success("Nothing escalated in this run.")
    for t in esc:
        with st.container(border=True):
            st.markdown(f"**{t['event_id']}** · {t['source']} · {t['received_at']}")
            if t["event_id"] in events:
                st.info(events[t["event_id"]]["text"])
            for r in t["escalations"]:
                st.warning(r)
            writes = [r for r in t["execution"] if r["kind"] == "write"]
            st.caption(f"Operational writes for this event: {len(writes)}")

# ---------------------------------------------------------------------------- Audit trail
elif view == "Audit trail":
    st.subheader("📜 Audit trail")
    st.caption("Official organizer log (`action_log.jsonl`) next to the client's own record of the same calls.")
    c = st.columns(4)
    c[0].metric("Logged calls", len(log))
    c[1].metric("Failed (ok:false)", sum(1 for r in log if not r["ok"]))
    c[2].metric("Writes", sum(1 for r in calls if r["kind"] == "write"))
    c[3].metric("Client timeouts", sum(1 for r in calls if r["status"] == "unknown"))
    ev_f = st.multiselect("Events", sorted(by_id), default=[])
    tool_f = st.multiselect("Tools", sorted({r["tool"] for r in calls}), default=[])
    df = pd.DataFrame([{"seq": r["seq"], "event": r["event_id"], "status": STATUS_ICON.get(r["status"], "") + " " + r["status"],
                        "tool": r["tool"], "agent": r.get("agent"), "rule": (r.get("rule") or "")[:40],
                        "incidents": ", ".join(r.get("incidents") or []), "args": json.dumps(r["args"])[:200],
                        "ms": r.get("ms")} for r in calls])
    if len(df):
        if ev_f:
            df = df[df.event.isin(ev_f)]
        if tool_f:
            df = df[df.tool.isin(tool_f)]
        st.dataframe(df, hide_index=True, use_container_width=True, height=520)
    if log and calls:
        same = [(r["event_id"], r["tool"]) for r in log] == [(r["event_id"], r["tool"]) for r in calls]
        (st.success if same else st.warning)(
            "Client record matches the organizer log row for row." if same else
            "Client record and organizer log differ (e.g. client-only timeouts or requests that never reached the server).")

# ---------------------------------------------------------------------------- Knowledge graph
elif view == "Knowledge graph":
    st.subheader("🕸️ Ontology and knowledge graph")
    g = manifest.get("graph", {})
    onto_p = os.path.join(args.run, "graph", "ontology.json")
    if os.path.exists(onto_p):
        onto = json.load(open(onto_p))
        lines = ['digraph O { rankdir=LR; node [shape=box, style="rounded,filled", fontname="Helvetica"];']
        types = {v["src"] for v in onto["edge_types"].values()} | {v["dst"] for v in onto["edge_types"].values()}
        for tname in types:
            lines.append(f'"{tname}" [label="{tname}\\n{g.get("nodes", {}).get(tname, "")}", fillcolor="{NODE_COLOR.get(tname, "#eee")}"];')
        for k, v in onto["edge_types"].items():
            style = ', style=dashed, color="#B45F06"' if k == "LOT_USED_IN_ORDER" else ""
            lines.append(f'"{v["src"]}" -> "{v["dst"]}" [label="{k.lower()}\\n{g.get("edges", {}).get(k, "")}", fontsize=8{style}];')
        st.graphviz_chart("\n".join(lines + ["}"]), use_container_width=True)
        st.caption(f"Schema {onto['schema_version']} · snapshot {g.get('snapshot_id')} · counts shown on nodes and edges")
        st.dataframe(pd.DataFrame([{"edge type": k, "from": v["src"], "to": v["dst"], "meaning": v["meaning"],
                                    "count": g.get("edges", {}).get(k)} for k, v in onto["edge_types"].items()]),
                     hide_index=True, use_container_width=True)
    else:
        st.warning("No graph export in this run folder.")

# ---------------------------------------------------------------------------- Run summary
else:
    st.subheader("📊 Run summary")
    rows = []
    for t in traces:
        ex = t["execution"]
        rows.append({"event": t["event_id"], "type": " + ".join(TYPE_LABEL.get(i["incident"]["type"], "") for i in t["incidents"]),
                     "writes": sum(1 for r in ex if r["kind"] == "write" and r["status"] == "confirmed"),
                     "reads": sum(1 for r in ex if r["kind"] == "read"),
                     "failed": sum(1 for r in ex if r["status"] != "confirmed"),
                     "action kinds": ", ".join(kinds(t)), "escalated": bool(t["escalations"]),
                     "ms": t.get("duration_ms")})
    df = pd.DataFrame(rows)
    c = st.columns(5)
    c[0].metric("Events", len(df))
    c[1].metric("Confirmed writes", int(df.writes.sum()))
    c[2].metric("Failed calls", int(df.failed.sum()))
    c[3].metric("Escalations", int(df.escalated.sum()))
    c[4].metric("Noise events with 0 calls",
                sum(1 for t in traces if all(i["incident"]["type"] == "noise" for i in t["incidents"]) and not t["execution"]))
    st.dataframe(df, hide_index=True, use_container_width=True)
    tc = Counter(r["tool"] for r in calls if r["status"] == "confirmed")
    st.bar_chart(pd.Series(tc, name="confirmed calls").sort_values(ascending=False))
