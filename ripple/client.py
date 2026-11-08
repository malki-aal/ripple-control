"""The single tool client. All tool calls go through here (server over HTTP, or the organizer's
Enterprise class in-process for dry runs). Captures response bodies, errors and timing, and
distinguishes a server rejection (HTTP 400, logged ok:false) from a client-side timeout (unknown outcome)."""
from __future__ import annotations

import importlib.util
import json
import os
import time
import urllib.error
import urllib.request

READ_TOOLS = {"mes.get_schedule", "crm.loaner_availability"}


class ToolClient:
    def __init__(self, base_url: str | None = None, data_dir: str | None = None, timeout: float = 15.0):
        self.base_url, self.timeout = (base_url.rstrip("/") if base_url else None), timeout
        self.local = None
        if not base_url:
            root = os.path.dirname(os.path.abspath(data_dir))
            spec = importlib.util.spec_from_file_location("enterprise", os.path.join(root, "enterprise.py"))
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            self.local, self._mod = mod.Enterprise(data_dir), mod
        self.seq = 0
        self.calls = []

    @property
    def mode(self):
        return "server" if self.base_url else "local-dry-run"

    def _get(self, path):
        with urllib.request.urlopen(self.base_url + path, timeout=self.timeout) as r:
            return json.load(r)

    def tools(self) -> dict:
        if self.base_url:
            return self._get("/tools")
        return self._mod.TOOLS

    def events(self) -> list:
        return self._get("/events")

    def call(self, event_id: str, tool: str, args: dict, purpose: str = "") -> dict:
        self.seq += 1
        rec = {"seq": self.seq, "event_id": event_id, "tool": tool, "args": args, "purpose": purpose,
               "kind": "read" if tool in READ_TOOLS else ("escalation" if tool == "escalate" else "write")}
        t0 = time.perf_counter()
        try:
            if self.base_url:
                body = json.dumps({"event_id": event_id, "tool": tool, "args": args}).encode()
                req = urllib.request.Request(self.base_url + "/act", body, {"Content-Type": "application/json"})
                try:
                    with urllib.request.urlopen(req, timeout=self.timeout) as r:
                        rec.update(http=r.status, body=json.load(r), status="confirmed")
                except urllib.error.HTTPError as e:
                    try:
                        payload = json.loads(e.read() or b"{}")
                    except ValueError:
                        payload = {}
                    rec.update(http=e.code, body=payload, error=payload.get("error", str(e)), status="rejected")
            else:
                try:
                    out = self.local.call(event_id, tool, args)
                    rec.update(http=200, body=out, status="confirmed")
                except self._mod.ToolError as e:
                    rec.update(http=400, body={"error": str(e)}, error=str(e), status="rejected")
        except (TimeoutError, urllib.error.URLError, ConnectionError, OSError) as e:
            rec.update(http=None, body=None, error=f"client-side failure, outcome unknown: {e}", status="unknown")
        rec["ms"] = round((time.perf_counter() - t0) * 1000, 2)
        self.calls.append(rec)
        return rec
