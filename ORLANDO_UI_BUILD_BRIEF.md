# Ripple Control · UI build brief for Orlando

> **For Orlando's coding agent:** read this whole file first. Then start with the **design interview in section 5**,
> and ask Orlando every question there. Wait for his answers before you change how anything looks. Every frontend
> choice belongs to Orlando. When this brief doesn't settle something about the frontend, ask him; don't decide for
> him. Backend logic is out of scope (section 2).

## 1. Project in two sentences
**Ripple Control** is our entry for the Hitachi **"Hack the Highway"** track at TAMU Datathon 2026. It is a control
tower for a just-in-time automaker that reads 15 messy operational messages (supplier delays, plant outages, quality
holds, noise, rumors). It works out everything each one touches through a knowledge graph, and acts through the
company's tools under a policy handbook. The UI has to make one thing obvious to an operations manager or a judge:
**for every event, what we understood, what it affected (graph path), what we did and why (policy), and what we
deliberately did not do.**

## 2. Your assignment
**You (Orlando) own:** the look, feel and usability of the existing Streamlit control tower, `app.py`. You are
polishing it, not rewriting it in another framework. You also own the new **"Similar past incidents"** panel (section 4).

**Malakai owns:** everything that produces data. That covers `ripple/`, `run.py`, `tests/`, `integrations/`,
`make_submission.py` and the files in `submission/`. MongoDB, and the real `similar_incidents.json`, are his too.
**Don't edit those**, and don't change what any decision or number means. If the UI needs a field that doesn't exist,
ask Malakai (section 6).

**In the MVP:** the event feed and event detail with its three tabs, the human review queue, the audit trail, the
similar-incidents panel (fixture first), and a consistent visual design.
**Polish, if time allows:** the knowledge graph page, the run summary charts, motion and transitions.
**Skip:** a new framework, authentication, editing data, and anything that calls the tools server. The UI is
**read-only**.

**Repo and setup** (verified 2026-11-07):
```bash
git clone https://github.com/malki-aal/ripple-control.git
cd ripple-control
git checkout -b ui            # your branch; Malakai reviews and merges into main
pip install -r requirements.txt
streamlit run app.py -- --run submission --events data/events.json
```
- It opens at http://localhost:8501. No API keys, `.env` or servers are needed. The UI only reads files that are
  already in the repo (`submission/`, `data/events.json`).
- **Demo device:** a laptop in Chrome, full screen. Phone layout is not needed.
- A file-only Streamlit app has no hidden backend, and there's nothing to deploy.

## 3. Judge demo (about 2 minutes, click by click)
1. **Open the app on Event feed.** This shows all 15 events with type icons, write counts and an "escalated" marker, so
   the judge sees the whole run at a glance.
2. **Click E-01 (daily digest). Open tab 1, Event understanding.** One message is split into **2 incidents** (a plant
   outage and a supplier delay). Show the resolved names and dates, for example "next Friday" → 2027-03-19. This
   proves the LLM understanding.
3. **Tab 2, Impact and policy.** Show one graph path per incident, the slot decisions table (why each order moved where
   it did) and the loaner allocation (priority, and who missed out because a pool was empty). This proves the
   knowledge graph and the policy reasoning.
4. **Tab 3, Execution and outcome.** Show the tool calls with status ✅ and zero failures. This proves execution and
   guardrails.
5. **Click E-03 (quality bulletin), tab 2.** Show the path from the defective lot to production orders to vehicles,
   and the split between sold and unsold vehicles. Open **Similar past incidents** to show E-15 as a precedent.
6. **Click E-05 (noise).** Zero tool calls, with the reason shown. This proves restraint.
7. **Human review page.** Show E-02 and E-13 escalated with what a human has to verify, and zero writes. This proves
   human-in-the-loop.
8. **Audit trail page.** Show 900 logged calls, 0 failed, and "client record matches the organizer log row for row".
   This is the audit-ready story.

**The actual graded submission is separate from the UI.** Judges replay `submission/action_log.jsonl`, and the design
card and traces are in `submission/`. The UI's job is to present that work clearly and earn the 10% "user experience
and explainability" score.

## 4. Screens and interactions

### Required
| Screen | Purpose | Data shown | Main action | States to handle |
|---|---|---|---|---|
| **Event feed + detail** (`Event feed` view) | Pick an event and understand it fully | Feed: `event_id`, `received_at`, `source`, incident types, confirmed write count, escalated flag. Detail: event text, `summary`, 4 headline numbers, 3 tabs | Select an event; switch tabs | Filter shows nothing ("No events match"). Event with 0 calls (noise): explain why. Incident with `impact: null`. `unresolved` list not empty |
| **Tab 1 · Event understanding** | Show what the model read and how code resolved it | Per incident: `type`, `confirmed`, `evidence_span`, `entity_evidence` (phrase → id, how it was matched), `dates` (phrase → date, rule), `unresolved`; plus `understanding.extractor`, `cross_check`, `tokens` | None (read) | `fallback` not null means the LLM failed and rules were used, so show a notice. Dates with `value: null` |
| **Tab 2 · Impact and policy** | Show what was affected and why | `impact.path` edges (graph), `impact.evidence`, `impact.policy`, `plan` moves, `loaners`, `dealer_plan.standard_no_loaner` | Choose the graph focus (one production order, or all with leaves grouped) | Quality holds have no moves. Noise and rumors have no impact block. Large graphs (E-03 has 260 vehicles) are grouped by default |
| **Tab 3 · Execution and outcome** | Show every tool call and its result | `execution[]`: `seq`, `tool`, `kind`, `status`, `agent`, `purpose`, `args`, `body`/`error`, `ms`; `blocked`, `escalations` | Show or hide read calls | 0 calls. `status` other than `confirmed`. `blocked` not empty |
| **Similar past incidents** (new, inside the detail view) | Help a reviewer by showing what we did last time | From `similar_incidents.json`: for this `incident_id`, up to 3 neighbours with `event_id`, `type`, `score`, `decision`, `outcome`, `why_similar`; clicking one opens that event | Click a neighbour to jump to it | File missing: hide the panel or show "Precedent search not available". Empty list: "No similar past incidents". Mock data: visible **MOCK** badge |
| **Human review** | Queue of escalations | Events with `escalations` not empty: text, reasons, operational writes = 0 | Jump to the event | No escalations: show a success state |
| **Audit trail** | Proof that the official log matches | `action_log.jsonl` counts, `client_calls.jsonl` table, filters by event and tool, the match check | Filter | Log missing. Mismatch warning |

### Polish
| Screen | Purpose |
|---|---|
| **Knowledge graph** | Ontology diagram with counts (`graph/ontology.json` + `run_manifest.json.graph`) |
| **Run summary** | Totals, per-event table, calls per tool |

## 5. Design direction: interview Orlando first
Malakai has **no design requirements**; the look is entirely Orlando's call. Agent, ask Orlando these questions in
one short numbered list, and **wait for his answers before you change any visuals:**

1. **References.** Are there two or three apps or dashboards whose look you like, such as an ops or monitoring tool,
   Linear, or Vercel? What exactly do you want to borrow from each, and what do you want to avoid?
2. **Mood.** Should it feel like a calm enterprise tool, a dark "mission control" screen, or something bright and
   friendly? Light theme, dark theme, or both?
3. **Color.** Do you have a primary or accent color? How should statuses look: success, failed, escalated, noise,
   mock? Should each incident type (delay, outage, quality, noise, rumor) get its own color?
4. **Typography.** Which font? Should IDs such as `PO-0316` use a monospace font? How dense should the text be?
5. **Layout.** Keep the sidebar navigation, or move to top tabs? Should the event feed stay as a left column? What
   should be on screen first for a judge: the summary, the graph, or the numbers?
6. **Graph style.** Keep Graphviz (`st.graphviz_chart`), or try an interactive graph, for example
   `streamlit-agraph` or pyvis in an HTML component? Should nodes be colored by type? Should derived edges be dashed?
7. **Tables and numbers.** Use plain tables, styled tables, or cards? Use metric cards for the headline numbers? Which
   columns are essential on a laptop screen?
8. **Motion.** Do you want any (transitions, toasts) or none? Remember that Streamlit reruns the page on every click.
9. **Icons and branding.** Keep the emoji icons or replace them? Add a logo or wordmark for "Ripple Control"?
10. **Tools.** Are you happy with a custom theme in `.streamlit/config.toml` and some custom CSS through
    `st.markdown(..., unsafe_allow_html=True)`? Are you OK adding one or two Streamlit component packages? Each one
    must be added to `requirements.txt`.

Rules that apply whatever he chooses:
- The app must stay read-only and run from repo files only.
- Text must stay readable on a projector: good contrast, and nothing under about 13px.
- Mock data must always be visibly labelled.

## 6. Backend contract and fixtures
**Interface:** files, no HTTP. The app takes `--run <folder>` and `--events <file>`, and the default demo is
`--run submission`. All paths below are relative to the run folder.

| File | Shape | Status | Owner |
|---|---|---|---|
| `event_traces.jsonl` | one JSON object per line, one per event (15) | **ready** | Malakai |
| `client_calls.jsonl` | one object per tool call (900) | **ready** | Malakai |
| `action_log.jsonl` | official organizer log: `{event_id, tool, args, ok}` | **ready** | Malakai (do not modify) |
| `run_manifest.json` | run id, mode, extractor (model), snapshot, graph counts, call totals | **ready** | Malakai |
| `graph/ontology.json`, `graph/graph_nodes.jsonl`, `graph/graph_edges.jsonl` | ontology plus full graph | **ready** | Malakai |
| `data/events.json` (repo root) | the 15 raw events `{event_id, received_at, source, text}` | **ready** | organizer |
| `similar_incidents.json` | see below | **mockable** now with `ui_fixtures/similar_incidents.mock.json`; real file **blocked** on Malakai's MongoDB step | Malakai |

**`event_traces.jsonl`: one event (fields the UI uses):**
```jsonc
{
  "event_id": "E-12", "received_at": "2027-03-08T10:24:00", "source": "supplier email", "run_id": "…",
  "summary": "E-12#1 supplier delay: CAM-360 delay at P_IN …",       // one-paragraph explanation, generated from facts
  "duration_ms": 5321.4,                                                // milliseconds to handle the event
  "understanding": {"extractor": "gemini:gemini-3.1-flash-lite", "fallback": null, "extract_ms": 4588.0,
                    "tokens": {"totalTokenCount": 549}, "cross_check": {"llm": ["supplier_delay"], "rules": ["supplier_delay"], "agree": true}},
  "incidents": [{
    "agent": "Supply Chain Planner",                       // or "Dealer Network", "Customer Care & Quality", "Coordinator"
    "decision": "act on 3 affected production orders",     // "no action" (noise), "escalate", "escalate (unresolved)", "hold LOT-…"
    "incident": {
      "incident_id": "E-12#1", "type": "supplier_delay",   // supplier_delay | plant_outage | quality_hold | noise | unconfirmed
      "confirmed": true, "evidence_span": "Our shipment SH-0182 …", "extractor_reason": "…",
      "entities": {"supplier": "SUP-11", "part": "CAM-360", "plant": "P_IN", "shipment": "SH-0182"},   // may be {}
      "entity_evidence": [{"type": "part", "phrase": "CAM-360", "id": "CAM-360", "matched": "cam-360", "source": "aliases.csv"}],
      "dates": {"original_eta": {"phrase": "2027-03-15", "value": "2027-03-15", "rule": "iso", "ambiguous": false}},  // value may be null
      "unresolved": []                                      // strings a human must check; not empty means caution
    },
    "impact": {                                             // null for noise and unconfirmed (then "reason" is present instead)
      "status": "actionable",                               // or "unresolved"
      "affected_pos": ["PO-0316", "PO-0319", "PO-0322"],
      "path": [{"edge_id": "SHIPMENT_OF_PART|Shipment:SH-0182|Part:CAM-360", "etype": "SHIPMENT_OF_PART",
                "src": "Shipment:SH-0182", "dst": "Part:CAM-360", "source_table": "inbound_shipments.csv",
                "source_key": "SH-0182", "derived": false}],   // derived=true only for Lot→ProductionOrder
      "policy": ["Rule 1 Supplier delay: …"],
      "evidence": {"window": "[2027-03-15, 2027-03-18)", "recovery_date": "2027-03-18"},  // free-form dict, different per type
      "disruption": {"label": "CAM-360 delay at P_IN: …"}     // quality holds have "lot", "stop_sale", "owners", "vehicles" instead
    }
  }],
  "plan": [{"tool": "mes.reschedule", "production_order_id": "PO-0316", "from": ["P_IN", "2027-03-15"],
            "to": ["P_IN", "2027-03-18"], "rationale": "earliest same-plant day …", "incidents": ["E-12#1"]}],
  "loaners": [{"dealer_id": "D08", "rank": 1, "customer_order_id": "CO-…", "tier": "Gold",
               "promised_date": "2027-03-19", "assigned": true, "why": "rank 1 of 3 eligible; 3 in pool"}],
  "dealer_plan": {"path": [...], "standard_no_loaner": ["CO-…"]},   // dealer and customer edges; Standard-tier orders
  "execution": [{"seq": 1, "tool": "mes.get_schedule", "kind": "read",  // read | write | escalation
                 "status": "confirmed",                                // confirmed | rejected | unknown (timeout) ; "blocked" never sent
                 "agent": "Supply Chain Planner", "purpose": "confirm free slot for PO-0316",
                 "args": {...}, "body": {...}, "error": null, "ms": 4.1, "rule": "Rule 3 …", "incidents": ["E-12#1"]}],
  "blocked": [],        // writes stopped by validation before sending
  "escalations": []     // reason strings; not empty means the event appears in Human review
}
```
Everything above was checked against `submission/event_traces.jsonl`. Units: dates are ISO `YYYY-MM-DD`, times are
local (no timezone), and `ms` / `duration_ms` are milliseconds. Customer names don't appear in traces, only IDs. The
data is the organizer's synthetic dataset, so it's fine for the demo, but don't post screenshots publicly.

**`similar_incidents.json` (new; agreed contract):**
```json
{
  "schema_version": "ripple-similar/1.0",
  "source": "mongodb-atlas-vector-search",
  "run_id": "20261107T192611-0adc50",
  "generated_at": "2026-11-07T21:00:00",
  "top_k": 3,
  "by_incident": {
    "E-12#1": [
      {"incident_id": "E-09#1", "event_id": "E-09", "type": "supplier_delay", "score": 0.91,
       "decision": "act on 6 affected production orders",
       "outcome": "4 rescheduled, 2 transferred, 26 dealers notified, 10 loaners",
       "why_similar": "same part CAM-360 from the same supplier; 3-day delay window"}
    ],
    "E-05#1": []
  }
}
```
- `score` is similarity from 0 to 1, where higher means more similar. Lists are sorted by score, highest first, and
  never include the incident itself.
- An incident that's missing from `by_incident`, or has an empty list, means "no similar past incidents".
- `source == "MOCK"` means fixture data, and you must show a **MOCK** badge.

**Switching from fixture to live data (build it like this):**
1. The app looks for `<run>/similar_incidents.json`.
2. If it's missing, it falls back to `ui_fixtures/similar_incidents.mock.json` and shows the MOCK badge. This can be
   triggered by an argument such as `--similar <path>` or automatically; Orlando decides.
3. When Malakai commits the real `submission/similar_incidents.json`, the panel picks it up with no code change, and
   the badge disappears because `source` is no longer `"MOCK"`.

## 7. Build order and integration checkpoint
1. **Design interview** (section 5), and agree on the look.
2. **One complete demo path** in the new design: event feed → E-01 → all 3 tabs, plus the similar-incidents panel on
   the **mock** fixture. **Checkpoint 1:** push branch `ui` and send Malakai a screenshot. He confirms the data is
   right and nothing was misread.
3. **The rest of the required screens:** E-03 graph, a noise event, human review, audit trail, and every empty or
   error state in section 4.
4. **Real data:** when Malakai sends `similar_incidents.json`, check that the panel renders it and the MOCK badge goes
   away. **Checkpoint 2:** ask Malakai for an integration review of the `ui` branch.
5. **Polish:** graph page, run summary, motion, and whatever else Orlando picked.

## 8. Definition of done (Orlando checks this himself)
- [ ] `streamlit run app.py -- --run submission --events data/events.json` starts on the demo laptop in Chrome with
      no exceptions or deprecation warnings in the terminal. The current code uses `use_container_width`; Streamlit
      now wants `width=`.
- [ ] The whole judge demo (section 3) can be clicked through in about 2 minutes at full screen.
- [ ] Every headline number still matches the data: 15 events, 900 calls, 0 failed, 2 escalations, 3 noise events
      with 0 calls.
- [ ] At least one failure or empty state checked: rename the similar-incidents file and confirm the panel degrades
      gracefully, and select a noise event.
- [ ] MOCK data is visibly labelled. Once Malakai's real file exists, it renders and the badge is gone.
- [ ] No files outside the UI were changed. Run `git diff --stat main..ui`, which should only touch `app.py`, new UI
      helper files, `.streamlit/`, assets and `requirements.txt` if needed.

**Send Malakai:** the `ui` branch name, the run command, a 30–60 second screen recording or 4–5 screenshots, and a
list of anything still mocked or blocked.
