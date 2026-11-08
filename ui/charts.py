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
           alt.Tooltip("to_txt:N", title="Now"), alt.Tooltip("why:N", title="Why")]
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
