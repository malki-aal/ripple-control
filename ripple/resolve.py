"""Resolve raw incident proposals (phrases) into typed incidents (ids + calendar dates), in code.

Relative date convention (documented, applied uniformly):
  * weeks start Monday. "this <wd>" = that weekday in the week of received_at.
  * "next <wd>"  = that weekday in the FOLLOWING calendar week (received Mon 2027-03-08 ->
                   "next Friday" = 2027-03-19, "next Monday" = 2027-03-15).
  * "last <wd>"  = that weekday in the PREVIOUS calendar week ("last Monday" = 2027-03-01).
  * bare "<wd>"  = the first such weekday strictly after received_at (flagged as an assumption).
  * "<wd> Mon DD" / "Mon DD" = explicit date in the year of received_at; a named weekday that
                   contradicts the date is flagged as ambiguous.
The E-01 digest ("dark from next Friday through Monday Mar 22") is only a contiguous range under
this convention, which is the cross-check that motivated it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timedelta

WD = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
MON = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
MON.update({"ene": 1, "abr": 4, "ago": 8, "dic": 12})   # Spanish abbreviations (marzo, mayo, ... already match)


@dataclass
class ResolvedDate:
    phrase: str
    value: str | None
    rule: str
    ambiguous: bool = False


@dataclass
class Incident:
    incident_id: str
    type: str
    confirmed: bool
    evidence_span: str
    extractor_reason: str
    mentions: dict = field(default_factory=dict)        # raw phrases from the extractor
    entities: dict = field(default_factory=dict)        # type -> resolved id
    entity_evidence: list = field(default_factory=list)
    dates: dict = field(default_factory=dict)           # role -> ResolvedDate
    unresolved: list = field(default_factory=list)      # what a human would need to verify

    def to_dict(self):
        d = asdict(self)
        return d


def resolve_date(phrase: str | None, received: date) -> ResolvedDate | None:
    if not phrase:
        return None
    p = re.sub(r"(\d)(?:st|nd|rd|th)\b", r"\1", phrase.strip().lower().rstrip(".").replace(",", ""))
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", p)
    if m:
        return ResolvedDate(phrase, date(*map(int, m.groups())).isoformat(), "iso")
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})(?:/(\d{2}|\d{4}))?", p)
    if m:   # US company: month/day
        try:
            y = int(m.group(3)) + (2000 if m.group(3) and len(m.group(3)) == 2 else 0) if m.group(3) else received.year
            return ResolvedDate(phrase, date(y, int(m.group(1)), int(m.group(2))).isoformat(), "US month/day")
        except ValueError:
            return ResolvedDate(phrase, None, "invalid month/day", True)
    m = re.fullmatch(rf"(?:({'|'.join(WD)})\s+)?(\d{{1,2}})\s+(?:of\s+|de\s+)?([a-z]{{3}})[a-z]*\.?(?:\s+(\d{{4}}))?", p)
    if m and m.group(3) in MON:   # day-month: "16 March", "25 de marzo"
        try:
            d = date(int(m.group(4) or received.year), MON[m.group(3)], int(m.group(2)))
        except ValueError:
            return ResolvedDate(phrase, None, "invalid day-month", True)
        amb = bool(m.group(1)) and WD.index(m.group(1)) != d.weekday()
        return ResolvedDate(phrase, d.isoformat(), "explicit day-month" + (" (weekday mismatch)" if amb else ""), amb)
    m = re.fullmatch(rf"(?:({'|'.join(WD)})\s+)?([a-z]{{3}})[a-z]*\.?\s+(\d{{1,2}})", p)
    if m and m.group(2) in MON:
        d = date(received.year, MON[m.group(2)], int(m.group(3)))
        amb = bool(m.group(1)) and WD.index(m.group(1)) != d.weekday()
        return ResolvedDate(phrase, d.isoformat(), "explicit month-day" + (" (weekday mismatch)" if amb else ""), amb)
    monday = received - timedelta(days=received.weekday())
    m = re.fullmatch(rf"(next|last|this|coming)\s+({'|'.join(WD)})", p)
    if m:
        off = {"next": 7, "last": -7, "this": 0, "coming": 7}[m.group(1)]
        d = monday + timedelta(days=off + WD.index(m.group(2)))
        return ResolvedDate(phrase, d.isoformat(), f"'{m.group(1)} <weekday>' = weekday in the "
                            + {"next": "following", "coming": "following", "last": "previous", "this": "current"}[m.group(1)]
                            + " Mon-Sun week of received_at")
    if p in WD:
        d = received + timedelta(days=1)
        while d.weekday() != WD.index(p):
            d += timedelta(days=1)
        return ResolvedDate(phrase, d.isoformat(), "bare weekday = next occurrence after received_at (assumption)", True)
    if p in ("today", "tomorrow", "yesterday"):
        d = received + timedelta(days={"today": 0, "tomorrow": 1, "yesterday": -1}[p])
        return ResolvedDate(phrase, d.isoformat(), p)
    return ResolvedDate(phrase, None, "unparsed", True)


class Resolver:
    def __init__(self, world):
        self.w = world
        self.names = sorted(world.name_index(), key=lambda r: -len(r[0]))

    def _entity(self, etype: str, phrase: str | None, lexical: list) -> tuple[str | None, dict | None]:
        """Resolve a phrase to an id of a given type, using exact ids, aliases and names."""
        cands = []
        if phrase:
            low = phrase.strip().lower()
            for ph, et, eid, src in self.names:
                if et == etype and (low == ph or re.search(r"(?<![\w-])" + re.escape(ph) + r"(?![\w-])", low)):
                    cands.append((eid, ph, src))
        if not cands and phrase and len(phrase.strip()) >= 4:
            # shortened name ("Kentucky" for "the Kentucky plant"): the phrase appears as whole words inside a known name
            low = phrase.strip().lower()
            cands = [(eid, ph, src + " (partial name)") for ph, et, eid, src in self.names
                     if et == etype and re.search(r"(?<![\w-])" + re.escape(low) + r"(?![\w-])", ph)]
        if not cands:   # fall back to lexical scan of the evidence span
            cands = [(m["id"], m["phrase"], m["source"]) for m in lexical if m["type"] == etype]
        ids = sorted({c[0] for c in cands})
        if len(ids) == 1:
            c = next(c for c in cands if c[0] == ids[0])
            return ids[0], {"type": etype, "phrase": phrase or c[1], "id": ids[0], "matched": c[1], "source": c[2]}
        if len(ids) > 1:
            return None, {"type": etype, "phrase": phrase, "ambiguous_ids": ids}
        return None, None

    def resolve(self, event: dict, raw: dict, n: int) -> Incident:
        received = datetime.fromisoformat(event["received_at"]).date()
        inc = Incident(incident_id=f"{event['event_id']}#{n}", type=raw["type"], confirmed=bool(raw.get("confirmed", True)),
                       evidence_span=raw.get("evidence_span", ""), extractor_reason=raw.get("reason", ""),
                       mentions={k: raw.get(k) for k in ("supplier", "part", "plant", "shipment_id", "lot_id", "date_from", "date_to")})
        lexical = raw.get("_mentions", [])
        for et in ("supplier", "part", "plant"):
            eid, ev = self._entity(et, raw.get(et), lexical)
            if eid:
                inc.entities[et] = eid
            if ev:
                inc.entity_evidence.append(ev)
                if "ambiguous_ids" in ev:
                    inc.unresolved.append(f"{et} '{ev['phrase']}' matches several ids {ev['ambiguous_ids']}")
        for key, et, table in (("shipment_id", "shipment", self.w.shipments), ("lot_id", "lot", self.w.lots)):
            v = (raw.get(key) or "").strip().upper()
            if v:
                if v in table:
                    inc.entities[et] = v
                    inc.entity_evidence.append({"type": et, "phrase": raw.get(key), "id": v, "source": f"{et} table"})
                else:
                    inc.unresolved.append(f"{et} id {v} not found in the tables")
        roles = {"supplier_delay": ("original_eta", "new_eta"), "plant_outage": ("start", "end"),
                 "quality_hold": ("build_from", "build_to")}.get(inc.type, ("date_from", "date_to"))
        phrases = {k: raw.get(k) for k in ("date_from", "date_to")}
        f, t = (phrases["date_from"] or "").strip(), (phrases["date_to"] or "").strip()
        if re.fullmatch(r"\d{1,2}", f) and t:      # "24 to 25 March": the bare day takes the other date's month
            other = resolve_date(t, received)
            if other and other.value:
                phrases["date_from"] = f"{date.fromisoformat(other.value):%b} {f}"
        for role, key in zip(roles, ("date_from", "date_to")):
            rd = resolve_date(phrases[key], received)
            if rd:
                inc.dates[role] = rd
                if rd.ambiguous:
                    inc.unresolved.append(f"date phrase '{rd.phrase}' is ambiguous ({rd.rule})")
        return inc
