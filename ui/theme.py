"""Ripple look and feel: one fixed tan palette and the page CSS.

Flat, solid boxes (no transparency, no shadows), one geometric sans (13 to 40px), and a solid header band
with the name and the top tabs.
"""

FONT_URL = "https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap"
FONT_STACK = '"Plus Jakarta Sans", ui-sans-serif, system-ui, "Segoe UI", sans-serif'
MONO_STACK = 'ui-monospace, "Cascadia Mono", Consolas, Menlo, monospace'

P = {
    "bg": "#F4EDE3", "paper": "#FFFDF9", "raised": "#F1E8DA", "group": "#E6D9C6", "rule": "#DCCDB8",
    "ink": "#2A241D", "muted": "#6A5E50",
    "hero": "#4B3A28", "hero_ink": "#FFF8EE", "hero_muted": "#E3D3BC",
    "primary": "#8A6A45", "primary_soft": "#EFE2CF",
    "ok": "#3F7A55", "ok_soft": "#E3EEE4", "bad": "#A63A32", "bad_soft": "#F6E1DD",
    "warn": "#8F5B12", "warn_soft": "#F5E7CF",
    "edge": "#8C7F70",
    # incident types: (ink, solid light fill)
    "types": {
        "supplier_delay": ("#8F5B12", "#F5E7CF"), "plant_outage": ("#4A6585", "#E1E8EF"),
        "quality_hold": ("#79558A", "#EDE3F0"), "noise": ("#6A645B", "#ECE7DF"),
        "unconfirmed": ("#6E6826", "#EFEBD2"),
    },
    # graph node types: border color
    "nodes": {
        "Supplier": "#79558A", "Shipment": "#4A6585", "Part": "#8F5B12", "Model": "#4F7A5A", "Plant": "#8A6A45",
        "ProductionOrder": "#A04E36", "CustomerOrder": "#9A7B2E", "Customer": "#9A5470", "Dealer": "#4F6F7A",
        "Lot": "#7A4A12", "Vehicle": "#6A645B", "LoanerPool": "#7D776D",
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
.st-key-hero {{ background: var(--hero); border-radius: 20px; padding: 14px 22px; margin-bottom: 6px; }}
.rp-word {{ font-weight: 800; font-size: 26px; letter-spacing: .2em; line-height: 1; color: var(--hero_ink); }}
.st-key-topnav [role="radiogroup"] {{ gap: 6px !important; justify-content: flex-end; flex-wrap: wrap; }}
.st-key-topnav label[data-testid="stRadioOption"] {{ margin: 0 !important; padding: 9px 16px; border-radius: 12px;
  background: transparent; cursor: pointer; display: flex; align-items: center; justify-content: center; }}
.st-key-topnav label[data-testid="stRadioOption"] > div > div:first-child:not([data-testid]) {{ display: none !important; }}
.st-key-topnav label[data-testid="stRadioOption"] p {{ font-size: 16px !important; font-weight: 600;
  color: var(--hero_muted) !important; margin: 0; }}
.st-key-topnav label[data-testid="stRadioOption"]:hover {{ background: #5E4A35; }}
.st-key-topnav label[data-testid="stRadioOption"]:has(input:checked) {{ background: var(--paper); }}
.st-key-topnav label[data-testid="stRadioOption"]:has(input:checked) p {{ color: var(--hero) !important; }}
.st-key-topnav [data-testid="stWidgetLabel"] {{ display: none; }}

/* ---------- cards */
[class*="st-key-card_"], .rp-card {{ background: var(--paper); border: 1px solid var(--rule); border-radius: 18px;
  padding: 20px; box-sizing: border-box; }}
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
.rp-callout.warn {{ background: var(--warn_soft); border-color: var(--warn); color: var(--ink); }}
.rp-callout.bad {{ background: var(--bad_soft); border-color: var(--bad); color: var(--ink); }}
.rp-callout.ok {{ background: var(--ok_soft); border-color: var(--ok); color: var(--ink); }}

/* ---------- pills */
.rp-pill {{ display: inline-flex; align-items: center; justify-content: center; border-radius: 999px; padding: 3px 11px;
  font-size: 13px; font-weight: 600; line-height: 1.35; white-space: nowrap; border: 1px solid transparent; }}
.rp-pill.dashed {{ border-style: dashed; }}
.rp-mock {{ display: inline-flex; align-items: center; border-radius: 8px; padding: 3px 10px; font-size: 13px;
  font-weight: 800; letter-spacing: .14em; color: #3B2600; border: 2px dashed #3B2600; background: #FFD36B; }}

/* ---------- stats */
.rp-stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 160px), 1fr)); gap: 12px; }}
.rp-stat {{ background: var(--paper); border: 1px solid var(--rule); border-radius: 16px; padding: 16px 12px;
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
.rp-tablewrap {{ border: 1px solid var(--rule); border-radius: 14px; overflow: auto; background: var(--paper); }}
.rp-table {{ width: 100%; border-collapse: separate; border-spacing: 0; font-size: 14px; color: var(--ink); }}
.rp-table th {{ position: sticky; top: 0; z-index: 1; background: var(--raised); color: var(--muted); font-weight: 600;
  font-size: 13px; text-align: left; padding: 10px 12px; border-bottom: 1px solid var(--rule); white-space: nowrap; }}
.rp-table td {{ padding: 10px 12px; border-bottom: 1px solid var(--rule); vertical-align: middle; line-height: 1.4; }}
.rp-table tr:last-child td {{ border-bottom: 0; }}
.rp-table tr.miss td {{ background: var(--warn_soft); }}
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
.rp-bars .b {{ height: 14px; border-radius: 7px; background: var(--primary); }}
.rp-bars .c {{ font-size: 14px; font-weight: 700; font-variant-numeric: tabular-nums; color: var(--ink); text-align: right; }}
.rp-legend {{ display: flex; flex-wrap: wrap; gap: 8px 16px; font-size: 13px; color: var(--muted); }}
.rp-legend span {{ display: inline-flex; align-items: center; gap: 6px; }}
.rp-legend i {{ display: inline-block; width: 12px; height: 12px; border-radius: 4px; }}
.rp-legend .dash {{ width: 22px; height: 0; border-top: 2px dashed var(--muted); border-radius: 0; }}
.rp-pre {{ font-family: var(--mono); font-size: 13px; color: var(--ink); background: var(--raised); border-radius: 12px;
  padding: 12px 14px; white-space: pre-wrap; overflow-wrap: anywhere; max-height: 360px; overflow: auto; margin: 0; }}

/* ---------- stacked list rows (run summary) */
.rp-list {{ background: var(--paper); border: 1px solid var(--rule); border-radius: 18px; overflow: hidden; }}
.rp-li {{ display: flex; flex-wrap: wrap; gap: 8px 14px; align-items: center;
  padding: 12px 16px; border-bottom: 1px solid var(--rule); }}
.rp-li:last-child {{ border-bottom: 0; }}
.rp-li .id {{ font-size: 16px; font-weight: 700; width: 52px; flex: none; }}
.rp-li .rp-row {{ flex: 1 1 160px; min-width: 0; }}
.rp-li .nums {{ display: flex; gap: 14px; font-size: 14px; color: var(--muted); font-variant-numeric: tabular-nums;
  white-space: nowrap; margin-left: auto; }}
.rp-li .nums b {{ color: var(--ink); }}
.rp-li .nums span {{ min-width: 82px; text-align: right; }}

/* ---------- event feed */
.st-key-feed {{ position: sticky; top: 12px; max-height: calc(100vh - 140px); overflow-y: auto; padding: 2px 6px 8px 2px; }}
[class*="st-key-feeditem_"] {{ position: relative; gap: 0 !important; }}
[class*="st-key-feeditem_"] .stButton {{ position: absolute !important; inset: 0; z-index: 3; margin: 0 !important; }}
[class*="st-key-feeditem_"] .stButton button {{ width: 100%; height: 100%; opacity: 0; cursor: pointer; }}
.rp-feed {{ background: var(--paper); border: 1px solid var(--rule); border-radius: 16px; padding: 12px 14px; }}
[class*="st-key-feeditem_"]:has(button:hover) .rp-feed {{ border-color: var(--primary); }}
[class*="st-key-feeditem_"]:has(button:focus-visible) .rp-feed {{ outline: 3px solid var(--primary); outline-offset: 2px; }}
.rp-feed.sel {{ border: 2px solid var(--primary); background: var(--primary_soft); padding: 11px 13px; }}
.rp-feed .top {{ display: flex; justify-content: space-between; gap: 8px; align-items: center; }}
.rp-feed .id {{ font-size: 17px; font-weight: 700; color: var(--ink); }}
.rp-feed .meta {{ font-size: 13px; color: var(--muted); }}
.rp-feed .types {{ margin: 8px 0; display: flex; gap: 6px; flex-wrap: wrap; }}
.rp-feed .foot {{ font-size: 13px; color: var(--muted); display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }}

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
[data-testid="stButtonGroup"] button[data-variant="pills"][aria-pressed="true"] {{ background: var(--primary_soft) !important;
  border-color: var(--primary) !important; }}
[data-testid="stButtonGroup"] button[data-variant="pills"][aria-pressed="true"] p {{ color: var(--primary) !important; }}
[data-testid="stExpander"] details {{ background: var(--paper); border: 1px solid var(--rule) !important; border-radius: 14px; }}
[data-testid="stExpander"] summary {{ color: var(--ink) !important; background: transparent !important; border-radius: 14px; }}
[data-testid="stExpander"] summary:hover {{ background: var(--raised) !important; }}
[data-testid="stExpander"] summary p {{ color: var(--ink) !important; font-size: 15px; font-weight: 600; }}
.stButton button {{ background: var(--paper); color: var(--ink); border: 1px solid var(--rule); border-radius: 12px; }}
.stButton button:hover {{ border-color: var(--primary); color: var(--primary); }}
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
</style>"""
