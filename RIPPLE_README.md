# Ripple Control — run notes

```
python enterprise_server.py --data data --events data/events.json --out runs/run1 --port 8000
python run.py --server http://127.0.0.1:8000 --out runs/run1        # judged run
python tests/verify_log.py --log runs/run1/action_log.jsonl --traces runs/run1/event_traces.jsonl
python run.py --dry-run --out runs/dry                                # no server, in-process Enterprise
python run.py --extractor gemini --server http://127.0.0.1:8001 --out runs/run2   # Gemini (GEMINI_API_KEY in .env)
python tests/benchmark_extractors.py --model gemini-3.1-flash-lite     # Gemini vs rules, no tool calls
python tests/stress_test.py [--extractor gemini]                        # edge cases + failure injection, no server
```

| Module | Role |
|---|---|
| `ripple/world.py` | CSV load, indexes, calendar, aliases |
| `ripple/graph.py` | NetworkX MultiDiGraph, 12 node types / 18 edge types, provenance per edge, derived Lot→ProductionOrder edges, export |
| `ripple/extract.py` | Incident proposals: Ollama (JSON-schema output) or deterministic rule extractor (fallback) |
| `ripple/resolve.py` | Phrases → ids and dates in code (documented relative-date rule) |
| `ripple/agents.py` | Supply Chain Planner, Dealer Network, Customer Care & Quality (deterministic) |
| `ripple/coordinator.py` | Routing, shared event ledger, validation before every write, live schedule reads, reconcile on timeout, escalation, trace + summary |
| `ripple/client.py` | Single tool client (HTTP or in-process); separates rejected (400) vs unknown (timeout) |

## Interpretations (handbook is silent)
- `next <weekday>` = that weekday in the following Mon–Sun week; `last <weekday>` = previous week.
- Transfers: earliest day in the window first (from today), then plants in `plants.csv` order.
- Compound events: incidents processed in message order, then original build date, then PO id; one ledger, one notice per dealer (union), one loaner allocation.
- Quality: the lot's own build window governs affected vehicles, even if the message window differs.
