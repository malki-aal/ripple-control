"""Small HTML builders. Every value that comes from data goes through esc() before it reaches the page."""
import html
import json

TYPE_LABEL = {"supplier_delay": "Supplier delay", "plant_outage": "Plant outage", "quality_hold": "Quality hold",
              "noise": "Noise", "unconfirmed": "Unconfirmed"}
STATUS = {"confirmed": ("✓", "ok"), "rejected": ("✕", "bad"), "unknown": ("?", "warn"), "blocked": ("!", "bad")}


def esc(x):
    return html.escape("" if x is None else str(x))


def pill(text, fg, bg, dashed=False, title=None):
    t = f' title="{esc(title)}"' if title else ""
    return (f'<span class="rp-pill{" dashed" if dashed else ""}"{t} '
            f'style="color:{fg};background:{bg};border-color:{fg if dashed else bg}">{esc(text)}</span>')


def tone_pill(P, text, tone, dashed=False):
    return pill(text, P[tone], P[tone + "_soft"], dashed)


def type_pill(P, t):
    fg, bg = P["types"].get(t, (P["muted"], P["raised"]))
    return pill(TYPE_LABEL.get(t, t), fg, bg, dashed=(t == "unconfirmed"))


def status_pill(P, status):
    glyph, tone = STATUS.get(status, ("?", "warn"))
    return tone_pill(P, f"{glyph} {status}", tone)


def mock_badge(text="MOCK"):
    return f'<span class="rp-mock" title="Fixture data, not a real result">{esc(text)}</span>'


def stats(items, n=None, hero=False):
    """items: (value, label, tone or None)."""
    cells = "".join(f'<div class="rp-stat{" hero" if hero else ""}{" " + tone if tone else ""}">'
                    f'<div class="v">{esc(v)}</div><div class="l">{esc(l)}</div></div>' for v, l, tone in items)
    return f'<div class="rp-stats" style="--n:{n or len(items)}">{cells}</div>'


def facts(items):
    """items: (label, value_html). Values are trusted HTML; escape before passing."""
    cells = "".join(f'<div class="rp-fact"><div class="k">{esc(k)}</div><div class="v">{v}</div></div>'
                    for k, v in items if v not in (None, ""))
    return f'<div class="rp-facts">{cells}</div>' if cells else ""


def table(cols, rows, max_height=None, row_class=None):
    """cols: list of (label, cell_class). rows: list of lists of trusted HTML cells."""
    head = "".join(f"<th>{esc(c)}</th>" for c, _ in cols)
    body = []
    for i, r in enumerate(rows):
        rc = row_class(i) if row_class else ""
        tds = "".join(f'<td class="{cls}">{cell}</td>' for (_, cls), cell in zip(cols, r))
        body.append(f'<tr class="{rc}">{tds}</tr>')
    style = f' style="max-height:{max_height}px"' if max_height else ""
    return (f'<div class="rp-tablewrap"{style}><table class="rp-table"><thead><tr>{head}</tr></thead>'
            f'<tbody>{"".join(body)}</tbody></table></div>')


def section(title, right=""):
    return f'<div class="rp-section"><div class="t">{esc(title)}</div><div class="r">{right}</div></div>'


def policy_lines(lines):
    out = []
    for p in lines or []:
        head, _, rest = str(p).partition(":")
        if rest:
            out.append(f'<div class="rp-policy"><span>{esc(head)}</span><span>{esc(rest.strip())}</span></div>')
        else:
            out.append(f'<div class="rp-policy"><span>Policy</span><span>{esc(p)}</span></div>')
    return "".join(out)


def callout(kind, html_inner):
    return f'<div class="rp-callout {kind}">{html_inner}</div>'


def short_json(x, n):
    s = json.dumps(x, default=str)
    return s if len(s) <= n else s[: n - 1] + "…"


def pre_json(x):
    return f'<pre class="rp-pre">{esc(json.dumps(x, indent=2, default=str))}</pre>'


def bars(items):
    """Horizontal bars, items: (label, count). One color, direct labels."""
    if not items:
        return ""
    top = max(c for _, c in items) or 1
    cells = "".join(f'<div class="n">{esc(l)}</div><div><div class="b" style="width:{max(2, 100 * c / top):.1f}%"></div></div>'
                    f'<div class="c">{c}</div>' for l, c in items)
    return f'<div class="rp-bars">{cells}</div>'
