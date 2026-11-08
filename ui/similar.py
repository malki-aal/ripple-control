"""Precedent search results (similar_incidents.json), with a clearly labelled fixture fallback.

Lookup order: --similar <path> if given, else <run>/similar_incidents.json, else the MOCK fixture in
ui_fixtures/. When Malakai's real file lands in the run folder it wins automatically, and because its
"source" is not "MOCK" the badge disappears.
"""
import json
import os

FIXTURE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ui_fixtures",
                       "similar_incidents.mock.json")


def load_similar(run_dir, override=None):
    """Returns dict(status, data, path, mock). status is 'ok', 'missing' or 'error: ...'."""
    candidates = [override] if override else [os.path.join(run_dir, "similar_incidents.json"), FIXTURE]
    for p in candidates:
        if p and os.path.exists(p):
            try:
                with open(p, encoding="utf-8-sig") as f:  # tolerate a BOM from Windows editors
                    data = json.load(f)
            except (OSError, ValueError) as e:
                return {"status": f"error: {e}", "data": None, "path": p, "mock": False}
            if not isinstance(data.get("by_incident"), dict):
                return {"status": "error: no by_incident map", "data": None, "path": p, "mock": False}
            return {"status": "ok", "data": data, "path": p, "mock": str(data.get("source", "")).upper() == "MOCK"}
    return {"status": "missing", "data": None, "path": None, "mock": False}


def neighbours(sim, incident_id):
    if sim["status"] != "ok":
        return None
    rows = sim["data"]["by_incident"].get(incident_id) or []
    rows = [r for r in rows if r.get("incident_id") != incident_id]
    return sorted(rows, key=lambda r: -(r.get("score") or 0))[: int(sim["data"].get("top_k") or 3)]
