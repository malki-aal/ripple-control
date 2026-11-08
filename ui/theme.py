"""Ripple look and feel: soft-UI palette and the page CSS.

Cool blue-gray page, white rounded cards with soft shadows, a blue gradient for the active tab and buttons,
and Montserrat throughout (13 to 40px).
"""

FONT_URL = "https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500;600;700;800&display=swap"
FONT_STACK = '"Montserrat", ui-sans-serif, system-ui, "Segoe UI", sans-serif'
MONO_STACK = 'ui-monospace, "Cascadia Mono", Consolas, Menlo, monospace'

# chart colors (validated with the dataviz palette checker on a white surface): what we did with a message
CHART = {"acted": "#2a78d6", "person": "#eb6834", "ignored": "#898781",
         "change": "#2a78d6", "lookup": "#1baf7a", "handoff": "#eb6834",
         "grid": "#e6eaf1", "axis": "#8a91a0", "ink": "#2b2f3a", "muted": "#5b6272"}

P = {
    # cool neutral base with solid blue accents; every pill color passes 4.5:1 with white text
    "bg": "#E9EDF3", "paper": "#FFFFFF", "raised": "#F2F4F8", "group": "#D9DFE8", "rule": "#E3E8EF",
    "ink": "#2B2F3A", "muted": "#5B6272",
    "hero": "#FFFFFF", "hero_ink": "#2B2F3A", "hero_muted": "#5B6272", "hero_hover": "#F2F4F8",
    "primary": "#2E5BEA",
    "grad": "linear-gradient(135deg, #4C8DF6 0%, #2E4FE0 100%)",
    "shadow": "0 10px 28px rgba(140, 155, 185, 0.22), 0 2px 6px rgba(140, 155, 185, 0.12)",
    "ok": "#15803D", "bad": "#B91C1C", "warn": "#B45309",
    "edge": "#6B7280",
    # incident types: one bold solid color each (white text on top)
    "types": {
        "supplier_delay": "#A21CAF", "plant_outage": "#1D4ED8", "quality_hold": "#0F766E",
        "noise": "#4B5563", "unconfirmed": "#BE123C",
    },
    # graph node types: solid fill with white text
    "nodes": {
        "Supplier": "#6D28D9", "Shipment": "#1D4ED8", "Part": "#0369A1", "Model": "#15803D", "Plant": "#0F766E",
        "ProductionOrder": "#B91C1C", "CustomerOrder": "#4338CA", "Customer": "#BE185D", "Dealer": "#0E7490",
        "Lot": "#A21CAF", "Vehicle": "#4B5563", "LoanerPool": "#374151",
    },
}


def css():
    v = "".join(f"--{k}:{P[k]};" for k in P if isinstance(P[k], str))
    return f"""<style>
@import url('{FONT_URL}');
:root {{ {v} --font:{FONT_STACK}; --mono:{MONO_STACK}; }}
html, body, .stApp, .stApp *:not([data-testid="stIconMaterial"]) {{ font-family: var(--font); }}
[data-testid="stIconMaterial"] {{ font-family: "Material Symbols Rounded" !important; }}
.stApp code, .stApp pre {{ font-family: var(--mono) !important; }}
.stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"] {{ background: var(--bg) !important; color: var(--ink); }}
[data-testid="stHeader"] {{ background: transparent !important; height: 0; }}
[data-testid="stToolbar"], [data-testid="stDecoration"], [data-testid="stSidebar"], [data-testid="stStatusWidget"],
[data-testid="stSidebarCollapsedControl"], [data-testid="collapsedControl"] {{ display: none !important; }}
[data-testid="stMainBlockContainer"], .block-container {{ padding-top: 1rem !important; padding-bottom: 3rem !important;
  max-width: 1500px; }}
/* no see-through boxes: keep content solid while the app reruns */
.stApp [data-stale="true"], .stApp [data-stale] {{ opacity: 1 !important; transition: none !important; }}
.stApp p, .stApp li, .stApp label, [data-testid="stMarkdownContainer"], [data-testid="stWidgetLabel"] p {{
  color: var(--ink); font-size: 15px; line-height: 1.45; }}
[data-testid="stVerticalBlock"] {{ gap: 14px; }}

/* ---------- header band: name + top tabs */
.st-key-hero {{ background: var(--hero); border-radius: 24px; padding: 14px 22px; margin-bottom: 8px;
  box-shadow: var(--shadow); }}
.rp-word {{ font-weight: 800; font-size: 26px; letter-spacing: .2em; line-height: 1; color: var(--primary); }}
.st-key-topnav [role="radiogroup"] {{ gap: 6px !important; justify-content: flex-end; flex-wrap: wrap; }}
.st-key-topnav label[data-testid="stRadioOption"] {{ margin: 0 !important; padding: 9px 16px; border-radius: 12px;
  background: transparent; cursor: pointer; display: flex; align-items: center; justify-content: center; }}
.st-key-topnav label[data-testid="stRadioOption"] > div > div:first-child:not([data-testid]) {{ display: none !important; }}
.st-key-topnav label[data-testid="stRadioOption"] p {{ font-size: 16px !important; font-weight: 600;
  color: var(--hero_muted) !important; margin: 0; }}
.st-key-topnav label[data-testid="stRadioOption"]:hover {{ background: var(--hero_hover); }}
.st-key-topnav label[data-testid="stRadioOption"]:has(input:checked) {{ background: var(--grad);
  box-shadow: 0 6px 16px rgba(46, 79, 224, 0.35); }}
.st-key-topnav label[data-testid="stRadioOption"]:has(input:checked) p {{ color: #FFFFFF !important; }}
.st-key-topnav [data-testid="stWidgetLabel"] {{ display: none; }}

/* ---------- cards */
[class*="st-key-card_"], .rp-card {{ background: var(--paper); border: 1px solid #EEF1F6; border-radius: 24px;
  padding: 22px; box-sizing: border-box; box-shadow: var(--shadow); }}
.rp-h1 {{ font-size: 26px; font-weight: 700; line-height: 1.2; color: var(--ink); margin: 0; }}
.rp-h2 {{ font-size: 18px; font-weight: 600; line-height: 1.3; color: var(--ink); margin: 0; }}
.rp-h3 {{ font-size: 17px; font-weight: 600; line-height: 1.3; color: var(--ink); margin: 0; }}
.rp-sub {{ font-size: 14px; color: var(--muted); line-height: 1.4; }}
.rp-body {{ font-size: 16px; color: var(--ink); line-height: 1.5; margin: 0; }}
.rp-quote {{ font-size: 16px; line-height: 1.5; color: var(--ink); background: var(--raised); border-radius: 14px;
  padding: 14px 16px; border-left: 4px solid var(--primary); white-space: pre-wrap; }}
.rp-head {{ display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; }}
.rp-row {{ display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }}
.rp-stack {{ display: flex; flex-direction: column; gap: 14px; }}
.rp-note {{ font-size: 14px; color: var(--muted); line-height: 1.45; }}
.rp-policy {{ display: flex; gap: 10px; align-items: baseline; font-size: 14px; color: var(--muted); line-height: 1.45; }}
.rp-policy span:first-child {{ font-weight: 700; color: var(--primary); white-space: nowrap; }}
.rp-callout {{ border-radius: 14px; padding: 12px 16px; font-size: 15px; line-height: 1.45; border: 1px solid; }}
.rp-callout {{ background: var(--paper); border-width: 2px; border-left-width: 8px; }}
.rp-callout.warn {{ border-color: var(--warn); color: var(--ink); }}
.rp-callout.bad {{ border-color: var(--bad); color: var(--ink); }}
.rp-callout.ok {{ border-color: var(--ok); color: var(--ink); }}
.rp-callout.warn b {{ color: var(--warn); }} .rp-callout.bad b {{ color: var(--bad); }} .rp-callout.ok b {{ color: var(--ok); }}

/* ---------- plain-language event summary */
.rp-sum {{ display: flex; flex-direction: column; gap: 6px; }}
.rp-sum .t {{ font-size: 17px; font-weight: 700; color: var(--ink); margin-top: 6px; }}
.rp-sum ul {{ margin: 0; padding-left: 20px; }}
.rp-sum li, .rp-sum p {{ font-size: 16px !important; line-height: 1.5 !important; color: var(--ink); margin: 3px 0; }}

/* ---------- pills */
.rp-pill {{ display: inline-flex; align-items: center; justify-content: center; border-radius: 999px; padding: 3px 11px;
  font-size: 13px; font-weight: 600; line-height: 1.35; white-space: nowrap; border: 1px solid transparent; }}
.rp-pill.dashed {{ border-style: dashed; }}
.rp-mock {{ display: inline-flex; align-items: center; border-radius: 8px; padding: 3px 10px; font-size: 13px;
  font-weight: 800; letter-spacing: .14em; color: #3B2600; border: 2px dashed #3B2600; background: #FFD36B; }}

/* ---------- stats */
.rp-stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 160px), 1fr)); gap: 12px; }}
.rp-stat {{ background: var(--paper); border: 1px solid #EEF1F6; border-radius: 20px; padding: 16px 12px; box-shadow: var(--shadow);
  min-width: 0; min-height: 100px; box-sizing: border-box;
  display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; gap: 6px; }}
.rp-stat .v {{ font-size: 32px; font-weight: 800; line-height: 1.1; font-variant-numeric: tabular-nums; color: var(--ink); }}
.rp-stat.hero .v {{ font-size: 40px; }}
.rp-stat .l {{ font-size: 14px; color: var(--muted); line-height: 1.35; max-width: 20ch; }}
.rp-stat.ok .v {{ color: var(--ok); }} .rp-stat.bad .v {{ color: var(--bad); }}
.rp-stat.warn .v {{ color: var(--warn); }} .rp-stat.accent .v {{ color: var(--primary); }}

/* ---------- facts grid */
.rp-facts {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 210px), 1fr)); gap: 10px; }}
.rp-fact {{ background: var(--raised); border-radius: 12px; padding: 12px 14px; min-width: 0; box-sizing: border-box;
  display: flex; flex-direction: column; justify-content: center; gap: 4px; }}
.rp-fact .k {{ font-size: 13px; color: var(--muted); line-height: 1.3; }}
.rp-fact .v {{ font-size: 16px; font-weight: 600; color: var(--ink); overflow-wrap: break-word; line-height: 1.35; }}

/* ---------- tables */
.rp-tablewrap {{ border: 1px solid #EEF1F6; border-radius: 18px; overflow: auto; background: var(--paper); }}
.rp-table {{ width: 100%; border-collapse: separate; border-spacing: 0; font-size: 14px; color: var(--ink); }}
.rp-table th {{ position: sticky; top: 0; z-index: 1; background: var(--raised); color: var(--muted); font-weight: 600;
  font-size: 13px; text-align: left; padding: 10px 12px; border-bottom: 1px solid var(--rule); white-space: nowrap; }}
.rp-table td {{ padding: 10px 12px; border-bottom: 1px solid var(--rule); vertical-align: middle; line-height: 1.4; }}
.rp-table tr:last-child td {{ border-bottom: 0; }}
.rp-table tr.miss td:first-child {{ box-shadow: inset 5px 0 0 var(--warn); }}
.rp-table td.num {{ text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }}
.rp-table td.id {{ font-weight: 600; white-space: nowrap; font-variant-numeric: tabular-nums; }}
.rp-table td.wrap {{ min-width: 200px; }}
.rp-table td.nowrap {{ white-space: nowrap; }}
.rp-table td.small {{ font-size: 13px; color: var(--muted); font-family: var(--mono); overflow-wrap: anywhere; min-width: 180px; }}
.rp-section {{ display: flex; justify-content: space-between; align-items: center; gap: 12px; }}
.rp-section .t {{ font-size: 17px; font-weight: 600; color: var(--ink); }}
.rp-section .r {{ font-size: 13px; color: var(--muted); font-weight: 600; }}
.rp-bars {{ display: grid; grid-template-columns: minmax(0, max-content) 1fr max-content; gap: 10px 12px; align-items: center; }}
.rp-bars .n {{ font-size: 14px; color: var(--ink); overflow-wrap: anywhere; }}
.rp-bars .b {{ height: 14px; border-radius: 7px; background: var(--grad); }}
.rp-bars .c {{ font-size: 14px; font-weight: 700; font-variant-numeric: tabular-nums; color: var(--ink); text-align: right; }}
.rp-legend {{ display: flex; flex-wrap: wrap; gap: 8px 16px; font-size: 13px; color: var(--muted); }}
.rp-legend span {{ display: inline-flex; align-items: center; gap: 6px; }}
.rp-legend i {{ display: inline-block; width: 12px; height: 12px; border-radius: 4px; }}
.rp-legend .dash {{ width: 22px; height: 0; border-top: 2px dashed var(--muted); border-radius: 0; }}
.rp-pre {{ font-family: var(--mono); font-size: 13px; color: var(--ink); background: var(--raised); border-radius: 12px;
  padding: 12px 14px; white-space: pre-wrap; overflow-wrap: anywhere; max-height: 360px; overflow: auto; margin: 0; }}

/* ---------- stacked list rows (run summary) */
.rp-list {{ background: var(--paper); border: 1px solid #EEF1F6; border-radius: 22px; overflow: hidden; box-shadow: var(--shadow); }}
.rp-li {{ display: flex; flex-wrap: wrap; gap: 8px 14px; align-items: center;
  padding: 12px 16px; border-bottom: 1px solid var(--rule); }}
.rp-li:last-child {{ border-bottom: 0; }}
.rp-li .id {{ font-size: 16px; font-weight: 700; width: 110px; flex: none; }}
.rp-li .rp-row {{ flex: 1 1 160px; min-width: 0; }}
.rp-li .nums {{ display: flex; gap: 14px; font-size: 14px; color: var(--muted); font-variant-numeric: tabular-nums;
  white-space: nowrap; margin-left: auto; }}
.rp-li .nums b {{ color: var(--ink); }}
.rp-li .nums span {{ min-width: 82px; text-align: right; }}

/* ---------- event feed */
.st-key-feed {{ position: sticky; top: 12px; max-height: calc(100vh - 140px); overflow-y: auto; padding: 2px 6px 8px 2px; }}
[class*="st-key-feeditem_"] {{ position: relative; gap: 0 !important; }}
/* the whole white card is clickable: an invisible button covers it (the source name sits above it for its hover) */
[class*="st-key-feeditem_"] [data-testid="stElementContainer"]:has(.stButton) {{ position: absolute !important;
  inset: 0; z-index: 3; width: auto !important; height: auto !important; margin: 0 !important; }}
[class*="st-key-feeditem_"] .stButton {{ position: absolute !important; inset: 0; margin: 0 !important; }}
[class*="st-key-feeditem_"] .stButton button {{ width: 100%; height: 100%; opacity: 0; cursor: pointer; }}
.rp-feed .id {{ line-height: 1.2; }}
.rp-feed {{ background: var(--paper); border: 1px solid #EEF1F6; border-radius: 20px; padding: 12px 14px; box-shadow: var(--shadow); }}
[class*="st-key-feeditem_"]:has(button:hover) .rp-feed {{ border-color: var(--primary); }}
[class*="st-key-feeditem_"]:has(button:focus-visible) .rp-feed {{ outline: 3px solid var(--primary); outline-offset: 2px; }}
.rp-feed.sel {{ border: 2px solid var(--primary); padding: 11px 13px; box-shadow: 0 8px 22px rgba(46, 79, 224, 0.25); }}
.rp-feed .top {{ display: flex; justify-content: space-between; gap: 8px; align-items: center; }}
.rp-feed .id {{ font-size: 17px; font-weight: 700; color: var(--ink); }}
.rp-feed .meta {{ font-size: 13px; color: var(--muted); }}
.rp-feed .types {{ margin: 8px 0; display: flex; gap: 6px; flex-wrap: wrap; }}
.rp-feed .foot {{ font-size: 13px; color: var(--muted); display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }}

/* ---------- hover explanation for where a message came from (sits above the card's click area) */
.rp-src {{ position: relative; z-index: 4; cursor: help; text-decoration: underline solid var(--ink);
  text-decoration-thickness: 1.5px; text-underline-offset: 3px; }}
.rp-src:hover::after, .rp-src:focus::after {{ content: attr(data-tip); position: absolute; right: 0; top: calc(100% + 6px);
  width: max-content; max-width: 240px; white-space: normal; text-align: left; background: var(--hero); color: #FFFFFF;
  font-size: 13px; font-weight: 500; line-height: 1.4; padding: 8px 10px; border-radius: 8px; z-index: 20; }}
.st-key-feed, [class*="st-key-feeditem_"], .rp-feed {{ overflow: visible; }}
.st-key-feed {{ overflow-y: auto; overflow-x: visible; }}
.rp-sub .rp-src:hover::after, .rp-sub .rp-src:focus::after {{ left: 0; right: auto; }}

/* the plain "← All events" link-style button stays a text link, not a gradient button */
.stButton button[data-testid="stBaseButton-tertiary"] {{ background: transparent !important; box-shadow: none !important;
  border: 0 !important; filter: none !important; }}
.stButton button[data-testid="stBaseButton-tertiary"] p {{ color: var(--primary) !important; font-weight: 700; }}

/* interactive charts sit on white soft cards */
[data-testid="stVegaLiteChart"] {{ background: transparent; }}
[data-testid="stVegaLiteChart"] summary, [data-testid="stVegaLiteChart"] details {{ display: none; }}
.st-key-scrolltop {{ position: absolute !important; width: 0 !important; height: 0 !important; overflow: hidden; }}

/* ---------- streamlit widgets */
[data-testid="stTabs"] [role="tablist"] {{ gap: 6px; border-bottom: 1px solid var(--rule); flex-wrap: wrap;
  overflow: visible !important; }}
[data-testid="stTab"] {{ background: var(--raised); border-radius: 12px 12px 0 0; padding: 10px 18px !important;
  display: flex; align-items: center; justify-content: center; text-align: center; }}
[data-testid="stTab"] p {{ font-size: 16px !important; font-weight: 600; color: var(--muted) !important; margin: 0; }}
[data-testid="stTab"][aria-selected="true"] {{ background: var(--paper); }}
[data-testid="stTab"][aria-selected="true"] p {{ color: var(--primary) !important; }}
[data-testid="stTabs"] .react-aria-SelectionIndicator {{ background: var(--primary) !important; height: 3px !important; }}
[data-testid="stButtonGroup"] button[data-variant="pills"] {{ background: var(--paper) !important;
  border: 1px solid var(--rule) !important; color: var(--ink) !important; }}
[data-testid="stButtonGroup"] button[data-variant="pills"] p {{ font-size: 14px !important; font-weight: 600; color: var(--ink) !important; }}
[data-testid="stButtonGroup"] button[data-variant="pills"][aria-pressed="true"] {{ background: var(--primary) !important;
  border-color: var(--primary) !important; }}
[data-testid="stButtonGroup"] button[data-variant="pills"][aria-pressed="true"] p {{ color: #FFFFFF !important; }}
[data-testid="stExpander"] details {{ background: var(--paper); border: 1px solid var(--rule) !important; border-radius: 14px; }}
[data-testid="stExpander"] summary {{ color: var(--ink) !important; background: transparent !important; border-radius: 14px; }}
[data-testid="stExpander"] summary:hover {{ background: var(--raised) !important; }}
[data-testid="stExpander"] summary p {{ color: var(--ink) !important; font-size: 15px; font-weight: 600; }}
.stButton button {{ background: var(--grad); color: #FFFFFF; border: 0; border-radius: 14px; box-shadow: 0 6px 16px rgba(46, 79, 224, 0.30); }}
.stButton button p {{ color: #FFFFFF !important; }}
.stButton button:hover {{ filter: brightness(1.06); }}
.stButton button p {{ font-size: 15px; font-weight: 600; }}
[data-testid="stBaseButton-tertiary"] {{ background: transparent !important; border: 0 !important; color: var(--primary) !important; padding-left: 0; }}
[data-testid="stSelectbox"] [role="group"], [data-testid="stMultiSelect"] [role="group"] {{ background: var(--paper) !important;
  border-color: var(--rule) !important; border-radius: 12px !important; }}
[data-testid="stSelectbox"] input, [data-testid="stMultiSelect"] input {{ color: var(--ink) !important; font-size: 15px !important;
  -webkit-text-fill-color: var(--ink); background: transparent !important; }}
.react-aria-Popover, [role="listbox"] {{ background: var(--paper) !important; border-color: var(--rule) !important; box-shadow: none !important; }}
[role="listbox"] [role="option"] {{ color: var(--ink) !important; font-size: 15px; }}
[role="listbox"] [role="option"][data-focused], [role="listbox"] [role="option"][data-hovered] {{ background: var(--raised) !important; }}
[data-testid="stCheckbox"] label p {{ font-size: 15px; }}
[data-testid="stCheckbox"] label:has(input[role="switch"]) > div:not([data-testid]) {{ background: var(--group) !important; }}
[data-testid="stCheckbox"] label:has(input[role="switch"]:checked) > div:not([data-testid]) {{ background: var(--primary) !important; }}
[data-testid="stGraphVizChart"] svg {{ max-width: 100%; height: auto; }}
/* Streamlit shrinks graph text to ~9.6px; restore the sizes the graphs are laid out for (SVG user units) */
[data-testid="stGraphVizChart"] svg g.node text {{ font-size: 13px !important; font-weight: 700; }}
.st-key-page_graph [data-testid="stGraphVizChart"] svg g.node text {{ font-size: 17px !important; }}
/* knowledge graph: scale the whole diagram down so it fits on one screen without scrolling */
.st-key-card_onto {{ width: fit-content !important; max-width: 100%; margin: 0 auto; padding: 14px 18px !important;
  gap: 6px !important; align-items: center; }}
.st-key-card_onto .rp-legend {{ justify-content: center; width: 0; min-width: 100%; }}
.st-key-page_graph [data-testid="stGraphVizChart"] {{ display: flex; justify-content: center; width: auto !important; }}
.st-key-page_graph [data-testid="stGraphVizChart"] svg {{ display: block; margin: 0 auto; width: auto !important;
  height: auto !important; max-width: 100%; max-height: min(calc(100vh - 250px), 640px); }}
</style>"""
