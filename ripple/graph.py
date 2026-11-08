"""Typed knowledge graph over the company tables.

Node key  = "<Type>:<source id>"  (e.g. "ProductionOrder:PO-0031").
Edge key  = "<EDGE_TYPE>|<src key>|<dst key>"  (stable across runs for the same snapshot).
Every edge keeps the source table and source record key that justify it. Lot -> ProductionOrder
edges have no direct field in the data; they are derived from plant + inclusive build window + BOM
membership and are flagged derived=True with the evidence rows.
"""
from __future__ import annotations

import json
import os
from collections import Counter

import networkx as nx

from .world import World

SCHEMA_VERSION = "ripple-graph/1.0"

# edge type -> (src node type, dst node type, description)
ONTOLOGY = {
    "SUPPLIES_SHIPMENT": ("Supplier", "Shipment", "supplier sends an inbound shipment"),
    "SHIPMENT_OF_PART": ("Shipment", "Part", "shipment carries a part"),
    "SHIPMENT_TO_PLANT": ("Shipment", "Plant", "shipment is received at a plant"),
    "PART_IN_MODEL": ("Part", "Model", "bill of materials: model requires part"),
    "PLANT_BUILDS_MODEL": ("Plant", "Model", "plant is able to build the model"),
    "PLANT_SCHEDULES_ORDER": ("Plant", "ProductionOrder", "order is built at the plant"),
    "ORDER_OF_MODEL": ("ProductionOrder", "Model", "order builds this model"),
    "ORDER_FULFILLS_CO": ("ProductionOrder", "CustomerOrder", "customer order is filled by the build"),
    "CO_AT_DEALER": ("CustomerOrder", "Dealer", "customer order placed through dealer"),
    "CO_FOR_CUSTOMER": ("CustomerOrder", "Customer", "customer order belongs to customer"),
    "SUPPLIES_LOT": ("Supplier", "Lot", "supplier produced the part lot"),
    "LOT_OF_PART": ("Lot", "Part", "lot is a lot of this part"),
    "LOT_AT_PLANT": ("Lot", "Plant", "lot was installed at the plant"),
    "LOT_USED_IN_ORDER": ("Lot", "ProductionOrder", "DERIVED: same plant, build date in lot window, model BOM has part"),
    "ORDER_PRODUCED_VEHICLE": ("ProductionOrder", "Vehicle", "finished vehicle came from the build"),
    "VEHICLE_AT_DEALER": ("Vehicle", "Dealer", "vehicle is allocated to dealer"),
    "VEHICLE_OWNED_BY": ("Vehicle", "Customer", "sold vehicle owner"),
    "DEALER_HAS_LOANER_POOL": ("Dealer", "LoanerPool", "dealer's loaner pool"),
}


def nk(ntype: str, sid: str) -> str:
    return f"{ntype}:{sid}"


class KnowledgeGraph:
    def __init__(self, world: World):
        self.world = world
        self.g = nx.MultiDiGraph()
        self._build()

    # ------------------------------------------------------------------ build
    def _node(self, ntype, sid, **attrs):
        k = nk(ntype, sid)
        if k not in self.g:
            self.g.add_node(k, ntype=ntype, sid=sid, **attrs)
        return k

    def _edge(self, etype, src, dst, table, key, derived=False, evidence=None):
        s_t, d_t, _ = ONTOLOGY[etype]
        assert src.startswith(s_t + ":") and dst.startswith(d_t + ":"), (etype, src, dst)
        ek = f"{etype}|{src}|{dst}"
        self.g.add_edge(src, dst, key=ek, etype=etype, source_table=table, source_key=key,
                        derived=derived, evidence=evidence or [])

    def _build(self):
        w = self.world
        for pid, r in w.plants.items():
            self._node("Plant", pid, name=r["name"], slots_per_day=int(r["slots_per_day"]))
        for m in w.models:
            self._node("Model", m, segment=w.models[m]["segment"])
        for pid, r in w.parts.items():
            self._node("Part", pid, name=r["name"], category=r["category"])
        for sid, r in w.suppliers.items():
            self._node("Supplier", sid, name=r["name"])
        for did, r in w.dealers.items():
            self._node("Dealer", did, name=r["name"], city=r["city"])
            if did in w.loaners:
                self._node("LoanerPool", did, available=w.loaners[did])
                self._edge("DEALER_HAS_LOANER_POOL", nk("Dealer", did), nk("LoanerPool", did), "loaners.csv", did)
        for cid, r in w.customers.items():
            self._node("Customer", cid, tier=r["tier"])
        for r in w.tables["bom"]:
            self._edge("PART_IN_MODEL", nk("Part", r["part_id"]), nk("Model", r["model"]), "bom.csv",
                       f"{r['model']}/{r['part_id']}")
        for r in w.tables["plant_models"]:
            self._edge("PLANT_BUILDS_MODEL", nk("Plant", r["plant_id"]), nk("Model", r["model"]),
                       "plant_models.csv", f"{r['plant_id']}/{r['model']}")
        for r in w.tables["inbound_shipments"]:
            s = self._node("Shipment", r["shipment_id"], eta_date=r["eta_date"], covers_days=r["covers_days"])
            self._edge("SUPPLIES_SHIPMENT", nk("Supplier", r["supplier_id"]), s, "inbound_shipments.csv", r["shipment_id"])
            self._edge("SHIPMENT_OF_PART", s, nk("Part", r["part_id"]), "inbound_shipments.csv", r["shipment_id"])
            self._edge("SHIPMENT_TO_PLANT", s, nk("Plant", r["plant_id"]), "inbound_shipments.csv", r["shipment_id"])
        for r in w.tables["production_orders"]:
            po = self._node("ProductionOrder", r["production_order_id"], build_date=r["build_date"],
                            model=r["model"], plant_id=r["plant_id"], units=int(r["units"]))
            self._edge("PLANT_SCHEDULES_ORDER", nk("Plant", r["plant_id"]), po, "production_orders.csv", r["production_order_id"])
            self._edge("ORDER_OF_MODEL", po, nk("Model", r["model"]), "production_orders.csv", r["production_order_id"])
        for r in w.tables["customer_orders"]:
            co = self._node("CustomerOrder", r["customer_order_id"], promised_date=r["promised_date"], model=r["model"])
            self._edge("ORDER_FULFILLS_CO", nk("ProductionOrder", r["production_order_id"]), co, "customer_orders.csv", r["customer_order_id"])
            self._edge("CO_AT_DEALER", co, nk("Dealer", r["dealer_id"]), "customer_orders.csv", r["customer_order_id"])
            self._edge("CO_FOR_CUSTOMER", co, nk("Customer", r["customer_id"]), "customer_orders.csv", r["customer_order_id"])
        for r in w.tables["finished_vehicles"]:
            v = self._node("Vehicle", r["vin"], status=r["status"], build_date=r["build_date"], model=r["model"])
            self._edge("ORDER_PRODUCED_VEHICLE", nk("ProductionOrder", r["production_order_id"]), v, "finished_vehicles.csv", r["vin"])
            self._edge("VEHICLE_AT_DEALER", v, nk("Dealer", r["dealer_id"]), "finished_vehicles.csv", r["vin"])
            if r["customer_id"]:
                self._edge("VEHICLE_OWNED_BY", v, nk("Customer", r["customer_id"]), "finished_vehicles.csv", r["vin"])
        for r in w.tables["part_lots"]:
            lot = self._node("Lot", r["lot_id"], first_build_date=r["first_build_date"], last_build_date=r["last_build_date"])
            self._edge("SUPPLIES_LOT", nk("Supplier", r["supplier_id"]), lot, "part_lots.csv", r["lot_id"])
            self._edge("LOT_OF_PART", lot, nk("Part", r["part_id"]), "part_lots.csv", r["lot_id"])
            self._edge("LOT_AT_PLANT", lot, nk("Plant", r["plant_id"]), "part_lots.csv", r["lot_id"])
            models = w.part_models[r["part_id"]]
            for o in w.tables["production_orders"]:
                if (o["plant_id"] == r["plant_id"] and r["first_build_date"] <= o["build_date"] <= r["last_build_date"]
                        and o["model"] in models):
                    self._edge("LOT_USED_IN_ORDER", lot, nk("ProductionOrder", o["production_order_id"]), "derived",
                               f"{r['lot_id']}/{o['production_order_id']}", derived=True,
                               evidence=[f"part_lots.csv:{r['lot_id']}", f"bom.csv:{o['model']}/{r['part_id']}",
                                         f"production_orders.csv:{o['production_order_id']}"])

    # ------------------------------------------------------------------ traversal
    def out(self, node: str, etype: str) -> list[tuple[str, dict]]:
        res = []
        for _, dst, k, d in self.g.out_edges(node, keys=True, data=True):
            if d["etype"] == etype:
                res.append((dst, {"edge_id": k, **d}))
        return sorted(res)

    def inn(self, node: str, etype: str) -> list[tuple[str, dict]]:
        res = []
        for src, _, k, d in self.g.in_edges(node, keys=True, data=True):
            if d["etype"] == etype:
                res.append((src, {"edge_id": k, **d}))
        return sorted(res)

    def edge(self, src: str, dst: str, etype: str) -> dict:
        k = f"{etype}|{src}|{dst}"
        d = self.g.get_edge_data(src, dst, key=k)
        if d is None:
            raise KeyError(f"missing edge {k}")
        return {"edge_id": k, "etype": etype, "src": src, "dst": dst, "source_table": d["source_table"],
                "source_key": d["source_key"], "derived": d["derived"]}

    # ------------------------------------------------------------------ export
    def stats(self) -> dict:
        return {"nodes": dict(Counter(d["ntype"] for _, d in self.g.nodes(data=True))),
                "edges": dict(Counter(d["etype"] for _, _, d in self.g.edges(data=True)))}

    def export(self, out_dir: str, snapshot_id: str) -> dict:
        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(out_dir, "graph_nodes.jsonl"), "w", encoding="utf-8") as f:
            for k, d in sorted(self.g.nodes(data=True)):
                f.write(json.dumps({"snapshot_id": snapshot_id, "node_key": k, **d}, default=str) + "\n")
        with open(os.path.join(out_dir, "graph_edges.jsonl"), "w", encoding="utf-8") as f:
            for s, t, k, d in sorted(self.g.edges(keys=True, data=True), key=lambda e: e[2]):
                f.write(json.dumps({"snapshot_id": snapshot_id, "edge_key": k, "src": s, "dst": t, **d}) + "\n")
        with open(os.path.join(out_dir, "ontology.json"), "w", encoding="utf-8") as f:
            json.dump({"schema_version": SCHEMA_VERSION,
                       "edge_types": {k: {"src": a, "dst": b, "meaning": c} for k, (a, b, c) in ONTOLOGY.items()}},
                      f, indent=2)
        st = self.stats()
        st["schema_version"] = SCHEMA_VERSION
        st["snapshot_id"] = snapshot_id
        return st
