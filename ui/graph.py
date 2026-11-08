"""Graphviz DOT for impact paths and the ontology.

Same traversal and grouping as before; only the drawing changed. Edges carry no text labels, so nothing sits on
top of a line: the edge type is in the hover tooltip and in the "Traversed edges" list under the graph. Node
labels stay inside their boxes. Derived edges (lot to order) are dashed.
"""
from collections import defaultdict

from .theme import FONT_STACK

LEAF = {"CustomerOrder", "Customer", "Dealer", "Vehicle"}
NICE = {"ProductionOrder": "Production order", "CustomerOrder": "Customer order", "LoanerPool": "Loaner pool"}


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


def _q(s):
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _label(t, main, sub=None):
    """Plain multi-line label: every line is drawn centered on the box (HTML-like labels drift off center
    because Graphviz measures text with different font metrics than the browser)."""
    lines = [NICE.get(t, t).upper(), str(main)] + ([str(sub)] if sub else [])
    clean = [x.replace("\\", "/").replace('"', "'") for x in lines]
    return '"' + "\\n".join(clean) + '"'


def _header(P, rankdir="LR", fontsize=16, nodesep=0.25, ranksep=0.55):
    font = FONT_STACK.split(",")[0].strip('"')
    return [
        "digraph G {",
        f'graph [rankdir={rankdir}, bgcolor="transparent", nodesep={nodesep}, ranksep={ranksep}, pad=0.2, '
        f'fontname="{font}"];',
        f'node [shape=box, style="rounded,filled", penwidth=2, margin="0.2,0.09", fontname="{font}", '
        f'fontsize={fontsize}, fontcolor="{P["ink"]}"];',
        f'edge [color="{P["edge"]}", penwidth=1.6, arrowsize=0.8];',
    ]


def _node(P, key, t, label, tall=False, w=2.4, h=0.75):
    """Every box has the same fixed size so labels and numbers sit centered in a tidy grid."""
    color = P["nodes"].get(t, P["muted"])
    size = f'width={w}, height={h + 0.25 if tall else h}, fixedsize=true'
    return (f'{_q(key)} [label={label}, color="{color}", fillcolor="{color}", fontcolor="#FFFFFF", {size}, '
            f'tooltip={_q(NICE.get(t, t))}];')


def dot_graph(P, edges, focus_po=None, meanings=None, vehicle_status=None):
    """Head entities are drawn one by one; bulky leaf types are grouped per parent unless a single production
    order is in focus, in which case its full subtree is drawn."""
    meanings = meanings or {}
    vehicle_status = vehicle_status or {}
    if focus_po:
        root = f"ProductionOrder:{focus_po}"
        keep, frontier = {root}, [root]
        while frontier:
            n = frontier.pop()
            for e in edges:
                if e["src"] == n and ntype(e["dst"]) in LEAF and e["dst"] not in keep:
                    keep.add(e["dst"])
                    frontier.append(e["dst"])
        edges = [e for e in edges if (ntype(e["dst"]) != "ProductionOrder" or e["dst"] == root)
                 and (ntype(e["src"]) not in LEAF | {"ProductionOrder"} or e["src"] in keep)]
    nodes, lines, seen, groups = {}, [], set(), defaultdict(set)
    for e in edges:
        s, d = e["src"], e["dst"]
        if not focus_po and ntype(s) in LEAF:
            continue
        if not focus_po and ntype(d) in LEAF:
            groups[(s, ntype(d))].add(d)
            continue
        nodes[s] = (ntype(s), _label(ntype(s), nid(s)))
        nodes[d] = (ntype(d), _label(ntype(d), nid(d)))
        if (s, d, e["etype"]) not in seen:
            seen.add((s, d, e["etype"]))
            tip = e["etype"].lower().replace("_", " ") + (": " + meanings[e["etype"]] if e["etype"] in meanings else "")
            style = f', style=dashed, color="{P["nodes"]["Lot"]}", penwidth=1.8' if e.get("derived") else ""
            lines.append(f"{_q(s)} -> {_q(d)} [tooltip={_q(tip)}{style}];")
    tall = False
    for (parent, t), members in groups.items():
        g = f"{t}@{parent}"
        word = NICE.get(t, t).lower() + ("s" if len(members) != 1 else "")
        sub = None
        if t == "Vehicle" and vehicle_status:
            sold = sum(1 for m in members if vehicle_status.get(nid(m)) == "sold")
            sub = f"{sold} sold · {len(members) - sold} in stock"
        elif len(members) <= 3:
            sub = ", ".join(sorted(nid(m) for m in members))
        nodes[g] = (t, _label(t, f"{len(members)} {word}", sub))
        tall = tall or bool(sub)
        lines.append(f"{_q(parent)} -> {_q(g)} [tooltip={_q('grouped ' + word)}];")
    out = _header(P, nodesep=0.2, ranksep=0.4) + [_node(P, n, t, lab, tall, w=2.0, h=0.7)
                                                    for n, (t, lab) in nodes.items()]
    return "\n".join(out + lines + ["}"])


def ontology_dot(P, onto, counts):
    nodes_c, edges_c = counts.get("nodes", {}), counts.get("edges", {})
    types = sorted({v["src"] for v in onto["edge_types"].values()} | {v["dst"] for v in onto["edge_types"].values()})
    # top-to-bottom so the diagram stays narrow and is drawn at full size (big, readable text)
    out = _header(P, rankdir="TB", fontsize=22, nodesep=0.3, ranksep=0.4)
    out[1] = out[1].replace("pad=0.2", "pad=0.05")
    for t in types:
        c = nodes_c.get(t)
        out.append(_node(P, t, t, _label(t, f"{c:,}" if isinstance(c, int) else "–"), w=2.8, h=0.8))
    for k, v in onto["edge_types"].items():
        tip = f"{k.lower().replace('_', ' ')}: {v.get('meaning', '')} ({edges_c.get(k, '?')})"
        style = f', style=dashed, color="{P["nodes"]["Lot"]}", penwidth=1.8' if k == "LOT_USED_IN_ORDER" else ""
        out.append(f"{_q(v['src'])} -> {_q(v['dst'])} [tooltip={_q(tip)}{style}];")
    return "\n".join(out + ["}"])


def legend(P, types, derived=False):
    items = "".join(f'<span><i style="background:{P["nodes"].get(t, P["muted"])}"></i>{NICE.get(t, t)}</span>'
                    for t in types)
    if derived:
        items += '<span><i class="dash"></i>derived link</span>'
    return f'<div class="rp-legend">{items}</div>'
