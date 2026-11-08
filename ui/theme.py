"""Ripple look and feel: two palettes and the page CSS.

Calm mode (tan and beige) is the default. Mission control mode (near-black with red) takes over whenever the
screen shows a live problem: a real disruption, an escalation, or a failed check. Both modes share one type
scale (13 to 40px, one geometric sans) so switching only changes color, never layout.
"""

import base64

FONT_URL ="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap"
FONT_STACK = '"Plus Jakarta Sans", ui-sans-serif, system-ui, "Segoe UI", sans-serif'
MONO_STACK = 'ui-monospace, "Cascadia Mono", Consolas, Menlo, monospace'

CALM = {
    "name": "calm",
    "bg": "#F4EDE3", "paper": "#FFFBF5", "raised": "#EFE5D6", "group": "#E6D9C6", "rule": "#DCCDB8",
    "ink": "#2A241D", "muted": "#6A5E50", "faint": "#8C7F70",
    "primary": "#8A6A45", "primary_ink": "#FFFFFF", "primary_soft": "#EFE2CF",
    "ok": "#3F7A55", "ok_soft": "#E3EEE4", "bad": "#A63A32", "bad_soft": "#F6E1DD",
    "warn": "#8F5B12", "warn_soft": "#F5E7CF",
    "shadow": "0 1px 2px rgba(60,40,20,.06), 0 2px 8px rgba(60,40,20,.05)",
    "edge": "#8C7F70",
    # incident types: (ink, soft fill)
    "types": {
        "supplier_delay": ("#8F5B12", "#F5E7CF"), "plant_outage": ("#4A6585", "#E1E8EF"),
        "quality_hold": ("#79558A", "#EDE3F0"), "noise": ("#6A645B", "#ECE7DF"),
        "unconfirmed": ("#6E6826", "#EFEBD2"),
    },
    # graph node types: border / accent color
    "nodes": {
        "Supplier": "#79558A", "Shipment": "#4A6585", "Part": "#8F5B12", "Model": "#4F7A5A", "Plant": "#8A6A45",
        "ProductionOrder": "#A04E36", "CustomerOrder": "#9A7B2E", "Customer": "#9A5470", "Dealer": "#4F6F7A",
        "Lot": "#7A4A12", "Vehicle": "#6A645B", "LoanerPool": "#7D776D",
    },
}

MISSION = {
    "name": "mission",
    "bg": "#0D0A0B", "paper": "#161012", "raised": "#1F1618", "group": "#2A1D20", "rule": "#3B2A2D",
    "ink": "#F5ECEA", "muted": "#C2ADA9", "faint": "#9C8783",
    "primary": "#E5383B", "primary_ink": "#FFFFFF", "primary_soft": "#3A1517",
    "ok": "#56C98D", "ok_soft": "#12291D", "bad": "#FF5A5F", "bad_soft": "#3A1517",
    "warn": "#F2B35A", "warn_soft": "#33240F",
    "shadow": "0 0 0 1px rgba(229,56,59,.10), 0 10px 28px rgba(0,0,0,.45)",
    "edge": "#9C8783",
    "types": {
        "supplier_delay": ("#F2B35A", "#33240F"), "plant_outage": ("#FF7A6E", "#3A1714"),
        "quality_hold": ("#F08DB8", "#3A1626"), "noise": ("#B3A8A5", "#251D1E"),
        "unconfirmed": ("#E8D27A", "#2E2912"),
    },
    "nodes": {
        "Supplier": "#C99BE0", "Shipment": "#8FB4E8", "Part": "#F2B35A", "Model": "#7FD19E", "Plant": "#FF7A6E",
        "ProductionOrder": "#FF5A5F", "CustomerOrder": "#E8D27A", "Customer": "#F08DB8", "Dealer": "#8FD0DB",
        "Lot": "#F59B4A", "Vehicle": "#B3A8A5", "LoanerPool": "#9C8783",
    },
}


def palette(mode):
    return MISSION if mode == "mission" else CALM


def css(P):
    """Full page CSS for palette P. Colors live in CSS variables so a mode switch animates."""
    v = "".join(f"--{k}:{P[k]};" for k in
                ("bg", "paper", "raised", "group", "rule", "ink", "muted", "faint", "primary", "primary_ink",
                 "primary_soft", "ok", "ok_soft", "bad", "bad_soft", "warn", "warn_soft", "shadow"))
    return f"""<style>
@import url('{FONT_URL}');
:root {{ {v} --font:{FONT_STACK}; --mono:{MONO_STACK}; }}
html, body, .stApp, .stApp *:not([data-testid="stIconMaterial"]) {{ font-family: var(--font); }}
[data-testid="stIconMaterial"] {{ font-family: "Material Symbols Rounded" !important; }}
.stApp code, .stApp pre, .rp-mono {{ font-family: var(--mono) !important; }}
.stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"] {{
  background: var(--bg) !important; color: var(--ink);
  transition: background-color .6s ease, color .6s ease; }}
[data-testid="stHeader"] {{ background: transparent !important; height: 0; }}
[data-testid="stToolbar"], [data-testid="stDecoration"], [data-testid="stSidebar"],
[data-testid="stSidebarCollapsedControl"], [data-testid="collapsedControl"] {{ display: none !important; }}
[data-testid="stMainBlockContainer"], .block-container {{ padding-top: 1.1rem !important; padding-bottom: 3rem !important;
  max-width: 1500px; }}
.stApp p, .stApp li, .stApp label, [data-testid="stMarkdownContainer"], [data-testid="stWidgetLabel"] p,
[data-testid="stCaptionContainer"] {{ color: var(--ink); font-size: 15px; line-height: 1.4; }}
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p {{ color: var(--muted) !important; font-size: 14px; }}

/* ---------- motion */
@keyframes rp-rise {{ from {{ opacity: 0; transform: translateY(8px); }} to {{ opacity: 1; transform: none; }} }}
@keyframes rp-sweep {{ from {{ transform: scaleX(0); }} to {{ transform: scaleX(1); }} }}
@keyframes rp-pulse {{ 0%,100% {{ opacity: 1; }} 50% {{ opacity: .35; }} }}
[class*="st-key-detail_"], [class*="st-key-page_"] {{ animation: rp-rise .38s ease both; }}
[class*="st-key-card_"], .rp-card, .rp-stat, .rp-feed, .rp-banner {{
  transition: background-color .6s ease, border-color .6s ease, color .6s ease, box-shadow .6s ease; }}

/* ---------- header and top tabs */
.rp-brand {{ display: flex; align-items: center; gap: 14px; color: var(--ink); }}
.rp-brand svg {{ display: block; }}
.rp-word {{ font-weight: 800; font-size: 26px; letter-spacing: .22em; line-height: 1; color: var(--ink); }}
.rp-tag {{ font-size: 13px; color: var(--muted); margin-top: 5px; letter-spacing: .02em; }}
.st-key-topnav [role="radiogroup"] {{ gap: 6px !important; justify-content: flex-end; flex-wrap: wrap; }}
.st-key-topnav label[data-testid="stRadioOption"] {{ margin: 0 !important; padding: 10px 16px; border-radius: 12px;
  background: transparent; border: 1px solid transparent; cursor: pointer; transition: background-color .2s, border-color .2s; }}
.st-key-topnav label[data-testid="stRadioOption"] > div:first-child {{ display: none !important; }}
.st-key-topnav label[data-testid="stRadioOption"] > div > div:first-child:not([data-testid]) {{ display: none !important; }}
.st-key-topnav label[data-testid="stRadioOption"] p {{ font-size: 16px !important; font-weight: 600; color: var(--muted) !important; }}
.st-key-topnav label[data-testid="stRadioOption"]:hover {{ background: var(--raised); }}
.st-key-topnav label[data-testid="stRadioOption"]:has(input:checked) {{ background: var(--paper); border-color: var(--rule);
  box-shadow: var(--shadow); }}
.st-key-topnav label[data-testid="stRadioOption"]:has(input:checked) p {{ color: var(--primary) !important; }}
.st-key-topnav [data-testid="stWidgetLabel"] {{ display: none; }}
.rp-rule {{ height: 1px; background: var(--rule); margin: 6px 0 14px; }}

.rp-banner {{ position: relative; overflow: hidden; display: flex; align-items: center; gap: 12px;
  border-radius: 14px; padding: 12px 18px; margin: 0 0 16px; background: var(--primary_soft);
  border: 1px solid var(--primary); color: var(--ink); font-size: 15px; }}
.rp-banner::after {{ content: ""; position: absolute; left: 0; bottom: 0; height: 3px; width: 100%;
  background: var(--primary); transform-origin: left; animation: rp-sweep .9s ease-out both; }}
.rp-banner b {{ letter-spacing: .14em; font-size: 13px; color: var(--primary); }}
.rp-dot {{ width: 10px; height: 10px; border-radius: 50%; background: var(--primary); flex: none;
  animation: rp-pulse 1.6s ease-in-out infinite; }}

/* ---------- cards */
[class*="st-key-card_"], .rp-card {{ background: var(--paper); border: 1px solid var(--rule); border-radius: 18px;
  padding: 18px 20px 20px; box-shadow: var(--shadow); }}
.rp-card + .rp-card {{ margin-top: 12px; }}
.rp-kicker {{ font-size: 13px; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; color: var(--muted); }}
.rp-h1 {{ font-size: 26px; font-weight: 700; line-height: 1.2; color: var(--ink); margin: 2px 0 4px; }}
.rp-h2 {{ font-size: 18px; font-weight: 600; line-height: 1.3; color: var(--ink); margin: 0 0 10px; }}
.rp-h3 {{ font-size: 17px; font-weight: 600; line-height: 1.3; color: var(--ink); margin: 0; }}
.rp-sub {{ font-size: 14px; color: var(--muted); line-height: 1.4; }}
.rp-body {{ font-size: 16px; color: var(--ink); line-height: 1.5; }}
.rp-quote {{ font-size: 16px; line-height: 1.5; color: var(--ink); background: var(--raised); border-radius: 14px;
  padding: 14px 16px; border-left: 4px solid var(--primary); white-space: pre-wrap; }}
.rp-head {{ display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; flex-wrap: wrap; }}
.rp-row {{ display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }}
.rp-gap {{ height: 12px; }}
.rp-note {{ font-size: 14px; color: var(--muted); margin-top: 8px; line-height: 1.45; }}
.rp-policy {{ display: flex; gap: 10px; align-items: flex-start; font-size: 14px; color: var(--muted); margin: 6px 0; }}
.rp-policy span:first-child {{ font-weight: 700; color: var(--primary); white-space: nowrap; }}
.rp-callout {{ border-radius: 14px; padding: 12px 16px; font-size: 15px; line-height: 1.45; margin: 10px 0 0;
  border: 1px solid; }}
.rp-callout.warn {{ background: var(--warn_soft); border-color: var(--warn); color: var(--ink); }}
.rp-callout.bad {{ background: var(--bad_soft); border-color: var(--bad); color: var(--ink); }}
.rp-callout.ok {{ background: var(--ok_soft); border-color: var(--ok); color: var(--ink); }}
.rp-callout b {{ color: var(--ink); }}

/* ---------- pills */
.rp-pill {{ display: inline-flex; align-items: center; gap: 6px; border-radius: 999px; padding: 3px 11px;
  font-size: 13px; font-weight: 600; line-height: 1.35; white-space: nowrap; border: 1px solid transparent; }}
.rp-pill.dashed {{ border-style: dashed; }}
.rp-mock {{ display: inline-flex; align-items: center; gap: 6px; border-radius: 8px; padding: 3px 10px; font-size: 13px;
  font-weight: 800; letter-spacing: .14em; color: #3B2600; border: 2px dashed #3B2600;
  background: repeating-linear-gradient(135deg, #FFD36B 0 10px, #FFC13B 10px 20px); }}

/* ---------- stats */
.rp-stats {{ display: grid; grid-template-columns: repeat(var(--n, 4), minmax(0, 1fr)); gap: 12px; }}
.rp-stat {{ background: var(--paper); border: 1px solid var(--rule); border-radius: 16px; padding: 14px 16px;
  box-shadow: var(--shadow); min-width: 0; }}
.rp-stat .v {{ font-size: 32px; font-weight: 800; line-height: 1.1; font-variant-numeric: tabular-nums; color: var(--ink); }}
.rp-stat.hero .v {{ font-size: 40px; }}
.rp-stat .l {{ font-size: 14px; color: var(--muted); margin-top: 4px; line-height: 1.3; }}
.rp-stat.ok .v {{ color: var(--ok); }} .rp-stat.bad .v {{ color: var(--bad); }}
.rp-stat.warn .v {{ color: var(--warn); }} .rp-stat.accent .v {{ color: var(--primary); }}

/* ---------- facts grid */
.rp-facts {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(210px, 1fr)); gap: 10px; margin-top: 12px; }}
.rp-fact {{ background: var(--raised); border-radius: 12px; padding: 10px 12px; min-width: 0; }}
.rp-fact .k {{ font-size: 13px; color: var(--muted); }}
.rp-fact .v {{ font-size: 16px; font-weight: 600; color: var(--ink); overflow-wrap: anywhere; line-height: 1.35; }}

/* ---------- tables */
.rp-tablewrap {{ border: 1px solid var(--rule); border-radius: 14px; overflow: auto; background: var(--paper); margin-top: 10px; }}
.rp-table {{ width: 100%; border-collapse: separate; border-spacing: 0; font-size: 14px; color: var(--ink); }}
.rp-table th {{ position: sticky; top: 0; z-index: 1; background: var(--raised); color: var(--muted); font-weight: 600;
  font-size: 13px; text-align: left; padding: 9px 12px; border-bottom: 1px solid var(--rule); white-space: nowrap; }}
.rp-table td {{ padding: 9px 12px; border-bottom: 1px solid var(--rule); vertical-align: top; line-height: 1.4; }}
.rp-table tr:last-child td {{ border-bottom: 0; }}
.rp-table tr.miss td {{ background: var(--warn_soft); }}
.rp-table td.num {{ text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }}
.rp-table td.id {{ font-weight: 600; white-space: nowrap; font-variant-numeric: tabular-nums; }}
.rp-table td.wrap {{ min-width: 220px; }}
.rp-table td.nowrap {{ white-space: nowrap; }}
.rp-table td.small {{ font-size: 13px; color: var(--muted); font-family: var(--mono); overflow-wrap: anywhere; min-width: 200px; }}
.rp-section {{ display: flex; justify-content: space-between; align-items: baseline; gap: 12px; margin-top: 18px; }}
.rp-section .t {{ font-size: 17px; font-weight: 600; color: var(--ink); }}
.rp-section .r {{ font-size: 13px; color: var(--muted); font-weight: 600; }}
.rp-bars {{ display: grid; grid-template-columns: max-content 1fr max-content; gap: 8px 12px; align-items: center; }}
.rp-bars .n {{ font-size: 14px; color: var(--ink); }}
.rp-bars .b {{ height: 14px; border-radius: 7px; background: var(--primary); }}
.rp-bars .c {{ font-size: 14px; font-weight: 700; font-variant-numeric: tabular-nums; color: var(--ink); }}
.rp-legend {{ display: flex; flex-wrap: wrap; gap: 8px 14px; font-size: 13px; color: var(--muted); margin: 6px 0 2px; }}
.rp-legend i {{ display: inline-block; width: 12px; height: 12px; border-radius: 4px; margin-right: 6px; vertical-align: -1px; }}
.rp-legend .dash {{ width: 22px; height: 0; border-top: 2px dashed var(--muted); border-radius: 0; vertical-align: 3px; }}
.rp-pre {{ font-family: var(--mono); font-size: 13px; color: var(--ink); background: var(--raised); border-radius: 12px;
  padding: 12px 14px; white-space: pre-wrap; overflow-wrap: anywhere; max-height: 360px; overflow: auto; margin: 0; }}

/* ---------- event feed */
.st-key-feed {{ position: sticky; top: 12px; max-height: calc(100vh - 150px); overflow-y: auto; padding: 2px 6px 8px 2px; }}
[class*="st-key-feeditem_"] {{ position: relative; gap: 0 !important; }}
[class*="st-key-feeditem_"] .stButton {{ position: absolute !important; inset: 0; z-index: 3; margin: 0 !important; }}
[class*="st-key-feeditem_"] .stButton button {{ width: 100%; height: 100%; opacity: 0; cursor: pointer; }}
.rp-feed {{ background: var(--paper); border: 1px solid var(--rule); border-radius: 16px; padding: 12px 14px;
  box-shadow: var(--shadow); transition: transform .15s ease, border-color .2s ease, background-color .6s ease; }}
[class*="st-key-feeditem_"]:has(button:hover) .rp-feed {{ transform: translateY(-1px); border-color: var(--primary); }}
[class*="st-key-feeditem_"]:has(button:focus-visible) .rp-feed {{ outline: 3px solid var(--primary); outline-offset: 2px; }}
.rp-feed.sel {{ border: 2px solid var(--primary); background: var(--primary_soft); padding: 11px 13px; }}
.rp-feed .top {{ display: flex; justify-content: space-between; gap: 8px; align-items: baseline; }}
.rp-feed .id {{ font-size: 17px; font-weight: 700; color: var(--ink); }}
.rp-feed .meta {{ font-size: 13px; color: var(--muted); }}
.rp-feed .types {{ margin: 7px 0 6px; display: flex; gap: 6px; flex-wrap: wrap; }}
.rp-feed .foot {{ font-size: 13px; color: var(--muted); display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }}

/* ---------- streamlit widgets, both modes */
[data-testid="stTabs"] [data-baseweb="tab-list"] {{ gap: 6px; background: transparent; }}
[data-testid="stTabs"] button[data-baseweb="tab"] {{ background: var(--raised); border-radius: 12px 12px 0 0;
  padding: 10px 18px; height: auto; }}
[data-testid="stTabs"] button[data-baseweb="tab"] p {{ font-size: 16px !important; font-weight: 600; color: var(--muted) !important; }}
[data-testid="stTabs"] button[data-baseweb="tab"][aria-selected="true"] {{ background: var(--paper); }}
[data-testid="stTabs"] button[data-baseweb="tab"][aria-selected="true"] p {{ color: var(--primary) !important; }}
[data-testid="stTabs"] [data-baseweb="tab-highlight"] {{ background: var(--primary) !important; height: 3px; }}
[data-testid="stTabs"] [data-baseweb="tab-border"] {{ background: var(--rule) !important; }}
[data-testid="stTabs"] [role="tablist"] {{ gap: 6px; border-bottom: 1px solid var(--rule); }}
[data-testid="stTab"] {{ background: var(--raised); border-radius: 12px 12px 0 0; padding: 10px 18px !important;
  transition: background-color .2s ease; }}
[data-testid="stTab"] p {{ font-size: 16px !important; font-weight: 600; color: var(--muted) !important; }}
[data-testid="stTab"][aria-selected="true"] {{ background: var(--paper); }}
[data-testid="stTab"][aria-selected="true"] p {{ color: var(--primary) !important; }}
[data-testid="stTabs"] .react-aria-SelectionIndicator {{ background: var(--primary) !important; height: 3px !important; }}
[data-testid="stButtonGroup"] button[data-variant="pills"] {{ background: var(--paper) !important;
  border: 1px solid var(--rule) !important; color: var(--ink) !important; }}
[data-testid="stButtonGroup"] button[data-variant="pills"] p {{ font-size: 14px !important; font-weight: 600; color: var(--ink) !important; }}
[data-testid="stButtonGroup"] button[data-variant="pills"][aria-pressed="true"] {{ background: var(--primary_soft) !important;
  border-color: var(--primary) !important; }}
[data-testid="stButtonGroup"] button[data-variant="pills"][aria-pressed="true"] p {{ color: var(--primary) !important; }}
[data-testid="stExpander"] details {{ background: var(--paper); border: 1px solid var(--rule) !important; border-radius: 14px; }}
[data-testid="stExpander"] summary {{ color: var(--ink) !important; background: transparent !important; border-radius: 14px; }}
[data-testid="stExpander"] summary:hover {{ background: var(--raised) !important; }}
[data-testid="stExpander"] summary p {{ color: var(--ink) !important; }}
[data-testid="stExpander"] summary p {{ font-size: 15px; font-weight: 600; }}
[data-testid="stExpander"] summary svg {{ color: var(--muted); fill: var(--muted); }}
.stButton button, [data-testid="stBaseButton-secondary"] {{ background: var(--paper); color: var(--ink);
  border: 1px solid var(--rule); border-radius: 12px; font-weight: 600; }}
.stButton button:hover {{ border-color: var(--primary); color: var(--primary); }}
.stButton button p {{ font-size: 15px; font-weight: 600; }}
[data-testid="stBaseButton-tertiary"] {{ background: transparent !important; border: 0 !important; color: var(--primary) !important; padding-left: 0; }}
[data-baseweb="select"] > div {{ background: var(--paper) !important; border-color: var(--rule) !important; color: var(--ink) !important; border-radius: 12px !important; }}
[data-baseweb="select"] svg {{ color: var(--muted); }}
[data-baseweb="popover"] ul, [data-baseweb="popover"] [role="listbox"], [data-baseweb="menu"] {{ background: var(--paper) !important; }}
[data-baseweb="popover"] li {{ color: var(--ink) !important; font-size: 15px; }}
[data-baseweb="popover"] li:hover, [data-baseweb="popover"] li[aria-selected="true"] {{ background: var(--raised) !important; }}
[data-testid="stSelectbox"] [role="group"], [data-testid="stMultiSelect"] [role="group"] {{ background: var(--paper) !important;
  border-color: var(--rule) !important; border-radius: 12px !important; }}
[data-testid="stSelectbox"] input, [data-testid="stMultiSelect"] input {{ color: var(--ink) !important; font-size: 15px !important;
  -webkit-text-fill-color: var(--ink); background: transparent !important; }}
[data-testid="stSelectbox"] button, [data-testid="stMultiSelect"] button {{ color: var(--muted) !important; }}
.react-aria-Popover, [role="listbox"] {{ background: var(--paper) !important; border-color: var(--rule) !important; }}
[role="listbox"] [role="option"] {{ color: var(--ink) !important; font-size: 15px; }}
[role="listbox"] [role="option"][data-focused], [role="listbox"] [role="option"][data-hovered] {{ background: var(--raised) !important; }}
[data-testid="stCheckbox"] label p {{ font-size: 15px; }}
[data-testid="stCheckbox"] label:has(input[role="switch"]) > div:not([data-testid]) {{ background: var(--group) !important;
  border: 1px solid var(--rule); }}
[data-testid="stCheckbox"] label:has(input[role="switch"]:checked) > div:not([data-testid]) {{ background: var(--primary) !important; }}
[data-testid="stBaseButton-pills"] {{ background: var(--paper) !important; border-color: var(--rule) !important; color: var(--ink) !important; }}
[data-testid="stBaseButton-pills"] p, [data-testid="stBaseButton-pillsActive"] p {{ font-size: 14px !important; font-weight: 600; }}
[data-testid="stBaseButton-pillsActive"] {{ background: var(--primary_soft) !important; border-color: var(--primary) !important; color: var(--primary) !important; }}
[data-testid="stMultiSelect"] [data-baseweb="tag"] {{ background: var(--primary_soft) !important; color: var(--ink) !important; }}
[data-testid="stMultiSelect"] [data-baseweb="tag"] span {{ font-size: 14px; }}
[data-testid="stGraphVizChart"] {{ background: transparent; }}
[data-testid="stGraphVizChart"] svg {{ max-width: 100%; height: auto; }}
</style>"""


def logo_svg(P, size=64):
    """Ripple emblem: an oval dealership-style badge holding three ripple waves (original artwork)."""
    svg = logo_svg_source(P)
    data = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f'<img src="data:image/svg+xml;base64,{data}" width="{size}" height="{round(size * 0.66)}" alt="Ripple logo">'


def logo_svg_source(P):
    ring, fill, wave = P["primary"], P["paper"], P["ink"]
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="66" viewBox="0 0 100 66">'
        f'<ellipse cx="50" cy="33" rx="47" ry="30" fill="{fill}" stroke="{ring}" stroke-width="4"/>'
        f'<ellipse cx="50" cy="33" rx="39.5" ry="23.5" fill="none" stroke="{ring}" stroke-width="1.4" opacity=".7"/>'
        f'<path d="M20 25 q7.5 -7 15 0 t15 0 t15 0 t15 0" fill="none" stroke="{wave}" stroke-width="2.4" stroke-linecap="round" opacity=".55"/>'
        f'<path d="M16 34 q8.5 -8 17 0 t17 0 t17 0 t17 0" fill="none" stroke="{ring}" stroke-width="4.2" stroke-linecap="round"/>'
        f'<path d="M20 43 q7.5 -7 15 0 t15 0 t15 0 t15 0" fill="none" stroke="{wave}" stroke-width="2.4" stroke-linecap="round" opacity=".55"/>'
        f"</svg>"
    )
