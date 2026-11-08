"""Interactive charts (Altair / Vega-Lite, drawn by Streamlit). Read-only: they only visualise recorded run files.

Every chart answers a question the control tower is judged on:
  workload_area     - how the work built up through the morning
  actions_by_kind   - which tools did the work
  build_moves       - for one disruption, where each affected build moved from and to, and why
Colors come from theme.CHART (checked with the dataviz palette validator).
"""
import datetime

import altair as alt

from . import labels as L
from .theme import CHART, FONT_STACK

FONT = FONT_STACK.split(",")[0].strip('"')


def _style(ch, legend=True):
    ch = (ch.configure(font=FONT, background="transparent", padding={"left": 4, "right": 12, "top": 8, "bottom": 4})
          .configure_view(stroke=None)
          .configure_axis(labelColor=CHART["muted"], titleColor=CHART["muted"], labelFontSize=13, titleFontSize=13,
                          titleFontWeight=600, gridColor=CHART["grid"], domainColor=CHART["grid"],
                          tickColor=CHART["grid"], labelFont=FONT, titleFont=FONT, labelPadding=6)
          .configure_text(font=FONT))
    if legend:
        ch = ch.configure_legend(orient="top", direction="horizontal", labelFontSize=13, labelColor=CHART["ink"],
                                 labelFont=FONT, title=None, symbolType="circle", symbolSize=140, columnPadding=18)
    return ch


def _clock(ts):
    t = datetime.datetime.fromisoformat(ts)
    return datetime.datetime(2000, 1, 1, t.hour, t.minute)


def actions_per_message(rows):
    """rows: dicts with eid, num, kind, n, total, about, source. Stacked bar per message (changes / look-ups /
    sent to a person), in arrival order. Hover shows what the message was; click a bar to open it."""
    kinds = ["Changes made", "Look-ups", "Sent to a person"]
    src = alt.Data(values=[{**r, "label": f"Message {r['num']}", "order": kinds.index(r["kind"])} for r in rows])
    pick = alt.selection_point(name="pick", on="click", fields=["eid"], empty=False)
    hover = alt.selection_point(name="hv", on="pointerover", fields=["eid"], empty=False, clear="pointerout")
    x = alt.X("num:O", title="Message", axis=alt.Axis(labelAngle=0, ticks=False))
    bars = (alt.Chart(src).transform_filter(alt.datum.n > 0)
            .mark_bar(stroke="#FFFFFF", strokeWidth=1, cursor="pointer")
            .encode(x=x, y=alt.Y("n:Q", title=None, stack="zero", axis=alt.Axis(tickCount=4)),
                    color=alt.Color("kind:N", scale=alt.Scale(domain=kinds,
                                                             range=[CHART["change"], CHART["lookup"], CHART["handoff"]])),
                    order=alt.Order("order:Q"),
                    opacity=alt.condition(hover, alt.value(1), alt.value(0.85)),
                    tooltip=[alt.Tooltip("label:N", title="Message"), alt.Tooltip("about:N", title="What it was"),
                             alt.Tooltip("source:N", title="From"), alt.Tooltip("kind:N", title="Part"),
                             alt.Tooltip("n:Q", title="Count"), alt.Tooltip("total:Q", title="All actions")])
            .add_params(pick, hover))
    # messages with no actions still get a visible, clickable marker on the baseline
    zero = (alt.Chart(src).transform_filter((alt.datum.total == 0) & (alt.datum.order == 0))
            .mark_tick(thickness=3, size=18, color=CHART["ignored"], cursor="pointer")
            .encode(x=x, y=alt.datum(0),
                    tooltip=[alt.Tooltip("label:N", title="Message"), alt.Tooltip("about:N", title="What it was"),
                             alt.Tooltip("total:Q", title="All actions")]))
    return _style(alt.layer(bars, zero).properties(height=260))


def token_forecast(rows):
    """Fan chart: tokens saved vs number of future messages. Bands = 50% and 90% ranges, line = median."""
    data = [{**r, "k50": r["p50"] / 1000, "k5": r["p5"] / 1000, "k95": r["p95"] / 1000,
             "k25": r["p25"] / 1000, "k75": r["p75"] / 1000} for r in rows]
    src = alt.Data(values=data)
    x = alt.X("n:Q", title="Messages processed", axis=alt.Axis(format=",.0f", grid=False, tickCount=5))
    band90 = alt.Chart(src).mark_area(color="#cde2fb", interpolate="monotone").encode(
        x=x, y=alt.Y("k5:Q", title=None, axis=alt.Axis(format=",.0f", tickCount=5)), y2="k95:Q")
    band50 = alt.Chart(src).mark_area(color="#86b6ef", interpolate="monotone").encode(x=x, y="k25:Q", y2="k75:Q")
    line = alt.Chart(src).mark_line(color=CHART["acted"], strokeWidth=2, interpolate="monotone").encode(x=x, y="k50:Q")
    hover = alt.selection_point(name="tf", on="pointerover", fields=["n"], nearest=True, empty=False, clear="pointerout")
    pts = (alt.Chart(src).mark_circle(size=70, color=CHART["acted"], stroke="#FFFFFF", strokeWidth=2)
           .encode(x=x, y="k50:Q", size=alt.condition(hover, alt.value(160), alt.value(60)),
                   tooltip=[alt.Tooltip("n:Q", title="Messages", format=","),
                            alt.Tooltip("p50:Q", title="Tokens saved (median)", format=",.0f"),
                            alt.Tooltip("p5:Q", title="90% range from", format=",.0f"),
                            alt.Tooltip("p95:Q", title="90% range to", format=",.0f"),
                            alt.Tooltip("share:Q", title="Share of tokens saved", format=".0%")])
           .add_params(hover))
    return _style(alt.layer(band90, band50, line, pts).properties(height=260), legend=False)


def time_forecast(hist, q):
    """Distribution of staff hours saved: probability bars plus markers at the 5th, 50th and 95th percentiles."""
    src = alt.Data(values=hist)
    bars = alt.Chart(src).mark_bar(color=CHART["acted"], opacity=0.85, binSpacing=1).encode(
        x=alt.X("h0:Q", title="Staff hours saved", bin="binned", axis=alt.Axis(grid=False, tickCount=6, format=",.0f")),
        x2="h1:Q",
        y=alt.Y("share:Q", title=None, axis=alt.Axis(format="%", tickCount=4)),
        tooltip=[alt.Tooltip("h0:Q", title="From (hours)", format=",.0f"), alt.Tooltip("h1:Q", title="To (hours)", format=",.0f"),
                 alt.Tooltip("share:Q", title="Probability", format=".1%")])
    marks = alt.Data(values=[{"h": q["p5"], "t": f"5%: {q['p5']:,.0f} h"}, {"h": q["p50"], "t": f"median: {q['p50']:,.0f} h"},
                             {"h": q["p95"], "t": f"95%: {q['p95']:,.0f} h"}])
    rules = alt.Chart(marks).mark_rule(color=CHART["ink"], strokeDash=[4, 3], strokeWidth=1.5).encode(x="h:Q")
    text = alt.Chart(marks).mark_text(align="left", dx=4, dy=-6, fontSize=12, fontWeight=600, color=CHART["ink"]).encode(
        x="h:Q", y=alt.value(10), text="t:N")
    return _style(alt.layer(bars, rules, text).properties(height=260), legend=False)


def workload_area(points):
    """points: dicts with time (ISO), label, total (running actions). Smooth area with a hover crosshair."""
    data = [{**p, "t": _clock(p["received_at"]).isoformat()} for p in points]
    src = alt.Data(values=data)
    x = alt.X("t:T", title=None, axis=alt.Axis(format="%H:%M", tickCount=8, grid=False))
    y = alt.Y("total:Q", title=None, axis=alt.Axis(tickCount=4))
    area = alt.Chart(src).mark_area(
        interpolate="monotone", line={"color": CHART["acted"], "strokeWidth": 2},
        color="#dbe7f8").encode(x=x, y=y)
    hover = alt.selection_point(name="x", on="pointerover", fields=["t"], nearest=True, empty=False,
                                clear="pointerout")
    rule = (alt.Chart(src).mark_rule(color=CHART["axis"], strokeWidth=1)
            .encode(x=x, opacity=alt.condition(hover, alt.value(1), alt.value(0)),
                    tooltip=[alt.Tooltip("label:N", title="After"), alt.Tooltip("t:T", title="Time", format="%H:%M"),
                             alt.Tooltip("added:Q", title="Added"), alt.Tooltip("total:Q", title="Running total")])
            .add_params(hover))
    dot = alt.Chart(src).mark_circle(size=90, color=CHART["acted"], stroke="#FFFFFF", strokeWidth=2).encode(
        x=x, y=y, opacity=alt.condition(hover, alt.value(1), alt.value(0)))
    return _style(alt.layer(area, rule, dot).properties(height=240), legend=False)


def actions_by_kind(items):
    """items: list of (label, count). One series, so one hue and no legend; bars lift on hover."""
    data = [{"kind": k, "n": n} for k, n in items]
    src = alt.Data(values=data)
    hover = alt.selection_point(name="b", on="pointerover", fields=["kind"], empty=False, clear="pointerout")
    order = [d["kind"] for d in sorted(data, key=lambda d: -d["n"])]
    y = alt.Y("kind:N", sort=order, title=None, axis=alt.Axis(labelLimit=220))
    bars = (alt.Chart(src).mark_bar(cornerRadiusEnd=4, height=16, color=CHART["acted"])
            .encode(x=alt.X("n:Q", title=None, axis=alt.Axis(grid=True, tickCount=4),
                            scale=alt.Scale(domain=[0, max(d["n"] for d in data) * 1.15 if data else 1])), y=y,
                    opacity=alt.condition(hover, alt.value(1), alt.value(0.78)),
                    tooltip=[alt.Tooltip("kind:N", title="Action"), alt.Tooltip("n:Q", title="Done")])
            .add_params(hover))
    text = alt.Chart(src).mark_text(align="left", dx=6, fontSize=12, fontWeight=700, color=CHART["ink"]).encode(
        x="n:Q", y=y, text="n:Q")
    return _style(alt.layer(bars, text).properties(height=34 * len(data) + 10), legend=False)


def build_moves(moves):
    """moves: dicts with build, from_day, to_day, from_plant, to_plant, how, why (plain words).
    A dumbbell per build: gray = original day, color = new day (blue same plant, orange other plant)."""
    data = []
    for m in moves:
        data.append({**m, "when": m["from_day"], "end": "Was"})
        data.append({**m, "when": m["to_day"], "end": "Now"})
    src = alt.Data(values=data)
    order = sorted({m["build"] for m in moves}, key=lambda b: int("".join(c for c in b if c.isdigit()) or 0))
    y = alt.Y("build:N", sort=order, title=None)
    x = alt.X("when:T", title=None, axis=alt.Axis(format="%b %d", tickCount=6))
    tip = [alt.Tooltip("build:N", title="Build"), alt.Tooltip("from_txt:N", title="Was"),
           alt.Tooltip("to_txt:N", title="Now"), alt.Tooltip("shift:N", title="Shift"),
           alt.Tooltip("why:N", title="Why")]
    hover = alt.selection_point(name="m", on="pointerover", fields=["build"], empty=False, clear="pointerout")
    line = alt.Chart(src).mark_line(strokeWidth=3, color="#c9d2e0").encode(x=x, y=y, detail="build:N")
    was = (alt.Chart(src).transform_filter(alt.datum.end == "Was")
           .mark_circle(size=120, color=CHART["ignored"], stroke="#FFFFFF", strokeWidth=2).encode(x=x, y=y, tooltip=tip))
    now = (alt.Chart(src).transform_filter(alt.datum.end == "Now")
           .mark_circle(stroke="#FFFFFF", strokeWidth=2)
           .encode(x=x, y=y, tooltip=tip,
                   size=alt.condition(hover, alt.value(300), alt.value(150)),
                   color=alt.Color("how:N", scale=alt.Scale(domain=["Later day, same plant", "Another plant"],
                                                           range=[CHART["acted"], CHART["person"]])))
           .add_params(hover))
    return _style(alt.layer(line, was, now).properties(height=30 * len(order) + 40))
