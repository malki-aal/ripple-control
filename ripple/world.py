"""Company data: CSV loading, indexes, calendar and alias lookup.

Read-only view of the organizer's tables. Everything the agents reason over comes from here,
and the knowledge graph (graph.py) is built from the same objects.
"""
from __future__ import annotations

import csv
import hashlib
import os
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta

TODAY = date(2027, 3, 8)          # simulation date, working-day index 0
FIRST_IDX, LAST_IDX = -10, 19     # history and planning window (Mon-Fri)
PLAN_START, PLAN_END = 0, LAST_IDX
TIER_RANK = {"Platinum": 0, "Gold": 1, "Standard": 2}
LOANER_TIERS = ("Platinum", "Gold")

CSV_FILES = [
    "aliases.csv", "bom.csv", "calendar.csv", "customer_orders.csv", "customers.csv", "dealers.csv",
    "finished_vehicles.csv", "inbound_shipments.csv", "loaners.csv", "models.csv", "part_lots.csv",
    "parts.csv", "plant_models.csv", "plants.csv", "production_orders.csv", "suppliers.csv",
]


def idx_to_date(i: int) -> date:
    return TODAY + timedelta(days=7 * (i // 5) + i % 5)


def date_to_idx(d: date) -> int:
    days = (d - TODAY).days
    if days % 7 > 4:
        raise ValueError(f"{d} is a weekend")
    return 5 * (days // 7) + days % 7


def is_workday(d: date) -> bool:
    return d.weekday() < 5


def next_workday_on_or_after(d: date) -> date:
    while not is_workday(d):
        d += timedelta(days=1)
    return d


def read_csv(path: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


@dataclass
class World:
    data_dir: str
    tables: dict[str, list[dict]] = field(default_factory=dict)

    @classmethod
    def load(cls, data_dir: str) -> "World":
        w = cls(data_dir)
        for name in CSV_FILES:
            w.tables[name[:-4]] = read_csv(os.path.join(data_dir, name))
        w._index()
        return w

    # ------------------------------------------------------------------ indexes
    def _index(self) -> None:
        t = self.tables
        self.plants = {r["plant_id"]: r for r in t["plants"]}
        self.plant_order = [r["plant_id"] for r in t["plants"]]          # stable tie-break order
        self.slots = {p: int(r["slots_per_day"]) for p, r in self.plants.items()}
        self.plant_models = defaultdict(set)
        for r in t["plant_models"]:
            self.plant_models[r["plant_id"]].add(r["model"])
        self.models = {r["model"]: r for r in t["models"]}
        self.parts = {r["part_id"]: r for r in t["parts"]}
        self.suppliers = {r["supplier_id"]: r for r in t["suppliers"]}
        self.dealers = {r["dealer_id"]: r for r in t["dealers"]}
        self.customers = {r["customer_id"]: r for r in t["customers"]}
        self.bom = defaultdict(set)                                        # model -> parts
        self.part_models = defaultdict(set)                                # part -> models
        for r in t["bom"]:
            self.bom[r["model"]].add(r["part_id"])
            self.part_models[r["part_id"]].add(r["model"])
        self.orders = {r["production_order_id"]: r for r in t["production_orders"]}
        self.orders_by_plant_day = defaultdict(list)
        for r in t["production_orders"]:
            self.orders_by_plant_day[(r["plant_id"], r["build_date"])].append(r["production_order_id"])
        self.cos = {r["customer_order_id"]: r for r in t["customer_orders"]}
        self.cos_by_po = defaultdict(list)
        for r in t["customer_orders"]:
            self.cos_by_po[r["production_order_id"]].append(r["customer_order_id"])
        self.vehicles = {r["vin"]: r for r in t["finished_vehicles"]}
        self.vehicles_by_po = defaultdict(list)
        for r in t["finished_vehicles"]:
            self.vehicles_by_po[r["production_order_id"]].append(r["vin"])
        self.shipments = {r["shipment_id"]: r for r in t["inbound_shipments"]}
        self.lots = {r["lot_id"]: r for r in t["part_lots"]}
        self.loaners = {r["dealer_id"]: int(r["loaners_available"]) for r in t["loaners"]}
        self.calendar = {r["date"]: int(r["day_index"]) for r in t["calendar"]}
        self.aliases = defaultdict(list)                                    # lower alias -> [(type, id)]
        for r in t["aliases"]:
            self.aliases[r["alias"].lower()].append((r["entity_type"], r["entity_id"]))
        self.dealer_city = {r["city"].lower(): r["dealer_id"] for r in t["dealers"]}

    # ------------------------------------------------------------------ lookups
    def name_index(self) -> list[tuple[str, str, str, str]]:
        """Every surface form we can match in text: (phrase_lower, entity_type, entity_id, source)."""
        out = []
        for a, ents in self.aliases.items():
            for et, eid in ents:
                out.append((a, et, eid, "aliases.csv"))
        for pid, r in self.plants.items():
            out += [(pid.lower(), "plant", pid, "plants.csv"), (r["name"].lower(), "plant", pid, "plants.csv")]
        for pid, r in self.parts.items():
            out += [(pid.lower(), "part", pid, "parts.csv"), (r["name"].lower(), "part", pid, "parts.csv")]
        for sid, r in self.suppliers.items():
            out += [(sid.lower(), "supplier", sid, "suppliers.csv"), (r["name"].lower(), "supplier", sid, "suppliers.csv")]
        # de-duplicate
        seen, uniq = set(), []
        for row in out:
            if row[:3] not in seen:
                seen.add(row[:3])
                uniq.append(row)
        return uniq

    def snapshot_id(self) -> str:
        h = hashlib.sha256()
        for name in CSV_FILES:
            with open(os.path.join(self.data_dir, name), "rb") as f:
                h.update(name.encode() + b"\0" + f.read())
        return h.hexdigest()[:16]

    def builds(self, plant: str, model: str) -> bool:
        return model in self.plant_models[plant]

    def tier_of_co(self, co: str) -> str:
        return self.customers[self.cos[co]["customer_id"]]["tier"]
