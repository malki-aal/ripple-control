"""'Why this action' panel in the app's own style. The facts come from ripple/explain.py (read from the trace only)."""
import functools
import os

from ripple.explain import explain, handbook_rules

from . import components as C
from . import labels as L
from .components import esc
from .theme import P

HOW = {"aliases.csv": "known name variants (aliases.csv)", "suppliers.csv": "supplier list", "parts.csv": "parts list",
       "plants.csv": "plant list", "iso": "written as a date", "explicit month-day": "month and day as written"}


@functools.lru_cache(maxsize=4)
def _rules(path):
    return handbook_rules(path)


def why_html(trace, seq, data_dir="data", where="organizer system"):
    x = explain(trace, seq, _rules(os.path.join(data_dir, "policy_handbook.md")), where)
    out = ['<div class="rp-stack">',
           f'<div class="rp-h2">{esc(L.tool_label(x["tool"]))} '
           f'<span class="rp-note">· action #{x["seq"]} · {esc(x["agent"] or "Coordinator")}</span></div>',
           f'<div class="rp-body">{esc(L.describe(x["tool"], x["args"]))}. {esc(L.plain_text(x["purpose"] or ""))}</div>']

    out.append(C.section("1 · The rule it follows"))
    if x["rule_text"]:
        out.append(f'<div class="rp-quote"><b>Handbook rule {x["rule_number"]}.</b> '
                   f'{esc(x["rule_text"].replace("**", "").replace("`", ""))}</div>')
    else:
        out.append('<div class="rp-note">A look-up. The handbook says reads are free and never penalized.</div>')

    out.append(C.section("2 · What the message said"))
    if not x["evidence"]:
        out.append('<div class="rp-note">No incident attached to this action.</div>')
    for e in x["evidence"]:
        rows = [[f'"{esc(n["phrase"])}"', f'<b>{esc(L.plain(n["id"]))}</b>', esc(HOW.get(n["source"], L.data_file(n["source"])))] for n in e["names"]]
        rows += [[f'"{esc(d["phrase"])}"', f'<b>{esc(L.plain_date(d["value"]))}</b>', esc(HOW.get(d["rule"], d["rule"]))] for d in e["dates"]]
        out.append((f'<div class="rp-quote">{esc(e["quote"])}</div>' if e["quote"] else "")
                   + (C.table([("Written as", ""), ("Understood as", ""), ("How", "wrap")], rows) if rows else ""))

    out.append(C.section("3 · How the knowledge graph connects it", "each link cites the data row behind it"))
    c = x["chain"]
    if not c["paths"]:
        out.append('<div class="rp-note">No graph links for this action.</div>')
    for i, p in enumerate(c["paths"]):
        rows = [[esc(L.link_sentence(e["etype"], e["src"].split(":", 1)[1], e["dst"].split(":", 1)[1])),
                 esc(L.data_file(e["source_table"])) + f' <span class="rp-note">row {esc(e["source_key"])}</span>',
                 C.tone_pill(P, "derived", "warn", True) if e["derived"] else ""] for e in p]
        label = ("Why this plant" if i == 0 else "Why this part") if len(c["paths"]) == 2 and \
            any(e["etype"] == "PART_IN_MODEL" for e in c["paths"][1]) else (f"Route {i + 1}" if len(c["paths"]) > 1 else "")
        out.append((f'<div class="rp-note"><b>{label}</b></div>' if label else "")
                   + C.table([("Link", "wrap"), ("Source", "nowrap"), ("", "nowrap")], rows))
    if c["more_targets"]:
        out.append(f'<div class="rp-note">Shown for the first item. This action covers {c["more_targets"]} more, linked the same way.</div>')
    if any(e["derived"] for p in c["paths"] for e in p):
        out.append('<div class="rp-note">Derived link: same plant, build date inside the batch\'s window, and the '
                   'model\'s bill of materials uses the part.</div>')

    out.append(C.section("4 · Checks it passed before it was sent"))
    items = [C.callout("ok", esc(ch)) for ch in x["checks"]] + [C.callout("ok", esc(L.plain_text(o))) for o in x["observed"]]
    items.append(C.callout("ok" if x["server"].startswith(where) else "bad", esc(x["server"])))
    out.append("".join(items))
    out.append("</div>")
    return "".join(out)
