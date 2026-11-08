"""Human review of escalations, run in a sandbox.

An escalation means the agents refused to act (rumor, unresolved or contradictory facts). A reviewer can:
  - dismiss it: confirm no action is needed (recorded with a note), or
  - confirm it with the missing facts: the confirmed message is re-run through the full pipeline (extract,
    resolve, graph, policy checks, every write validated) on a fresh in-process copy of the organizer's
    Enterprise. The reviewer sees the proposed actions, then approves or rejects them.

Nothing here talks to a server or touches the official action_log.jsonl. Decisions go to
runs/reviews/decisions.jsonl, one JSON line each, with reviewer, time and what was approved.
"""
from __future__ import annotations

import datetime as dt
import json
import os

from .client import ToolClient
from .coordinator import Coordinator

LOG = os.path.join("runs", "reviews", "decisions.jsonl")


def pending(traces: list, decisions: list | None = None) -> list:
    """One item per escalated incident, with the original message and why it was escalated."""
    done = {d["incident_id"] for d in (decisions or [])}
    out = []
    for t in traces:
        for e in t["incidents"]:
            if e.get("decision") == "escalate":
                inc = e["incident"]
                out.append({"event_id": t["event_id"], "incident_id": inc["incident_id"], "received_at": t["received_at"],
                            "source": t["source"], "type": inc["type"], "evidence": inc.get("evidence_span", ""),
                            "reason": e.get("reason", ""), "policy": e.get("policy", []),
                            "reviewed": inc["incident_id"] in done})
    return out


def preview(world, kg, extractor, item: dict, confirmed_text: str, data_dir: str = "data") -> dict:
    """Re-run the confirmed message through the agents on a fresh sandbox Enterprise. Returns the trace."""
    client = ToolClient(None, data_dir=data_dir)
    coord = Coordinator(world, kg, extractor, client)
    event = {"event_id": f"{item['event_id']}-REVIEW", "received_at": item["received_at"],
             "source": "human review (confirmed)", "text": confirmed_text}
    return coord.handle(event)


def writes(trace: dict) -> list:
    return [r for r in trace["execution"] if r["kind"] == "write" and r["status"] == "confirmed"]


def outcome(trace: dict) -> dict:
    w = writes(trace)
    kinds = {}
    for r in w:
        kinds[r["tool"]] = kinds.get(r["tool"], 0) + 1
    return {"writes": len(w), "by_tool": kinds, "escalated_again": bool(trace["escalations"]),
            "blocked": len(trace["blocked"]), "failed": sum(1 for r in trace["execution"] if r["status"] != "confirmed"),
            "types": [i["incident"]["type"] for i in trace["incidents"]]}


def load(path: str = LOG) -> list:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def record(item: dict, decision: str, reviewer: str, note: str = "", confirmed_text: str | None = None,
           trace: dict | None = None, path: str = LOG) -> dict:
    """decision: 'dismissed' (no action needed), 'approved' (sandbox actions accepted), 'rejected' (sandbox actions refused)."""
    if decision not in ("dismissed", "approved", "rejected"):
        raise ValueError(decision)
    if not reviewer.strip():
        raise ValueError("reviewer name is required")
    rec = {"at": dt.datetime.now().isoformat(timespec="seconds"), "reviewer": reviewer.strip(), "decision": decision,
           "event_id": item["event_id"], "incident_id": item["incident_id"], "note": note.strip(),
           "confirmed_text": confirmed_text, "sandbox": True}
    if trace is not None:
        rec["outcome"] = outcome(trace)
        rec["actions"] = [{"tool": r["tool"], "args": r["args"], "rule": r.get("rule")} for r in writes(trace)]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")
    return rec


def undo(incident_id: str, path: str = LOG) -> int:
    """Remove the decisions for one incident (so it goes back to the queue). Returns how many were removed."""
    keep = [d for d in load(path) if d["incident_id"] != incident_id]
    removed = len(load(path)) - len(keep)
    if removed:
        with open(path, "w", encoding="utf-8") as f:
            for d in keep:
                f.write(json.dumps(d) + "\n")
    return removed
