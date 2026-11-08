# Databricks notebook source
# MAGIC %md
# MAGIC # Ripple Control · graph data preparation and validation
# MAGIC Builds Delta tables for normalized entity keys, graph nodes and graph edges (with source provenance) from the
# MAGIC approved company extracts, using **the same schema mapping and graph rules as the local builder**
# MAGIC (`ripple/graph.py`), including the derived Lot → ProductionOrder edge. Then validates keys, edge endpoints,
# MAGIC orphaned BOM links and shipment/lot links, runs a reproducible impact-path check, and compares canonical node
# MAGIC and edge keys with the local export for the same snapshot.
# MAGIC
# MAGIC Operational writes never happen here. This notebook only reads extracts and writes analytics tables.
# MAGIC
# MAGIC Runs unchanged on a laptop too: `python integrations/databricks/ripple_graph_build.py --source data --local-export runs/run1/export`
# MAGIC (local Spark, Parquet instead of Delta).

# COMMAND ----------

import json
import os
import sys

from pyspark.sql import SparkSession, functions as F

ON_DATABRICKS = "DATABRICKS_RUNTIME_VERSION" in os.environ


def param(name, default):
    if ON_DATABRICKS:
        dbutils.widgets.text(name, default)  # noqa: F821  (provided by Databricks)
        return dbutils.widgets.get(name)     # noqa: F821
    if f"--{name.replace('_', '-')}" in sys.argv:
        return sys.argv[sys.argv.index(f"--{name.replace('_', '-')}") + 1]
    return default


SOURCE = param("source", "/Volumes/workspace/ripple/files/extracts" if ON_DATABRICKS else "data")
TARGET = param("target", "workspace.ripple_graph" if ON_DATABRICKS else "runs/databricks_local")
LOCAL_EXPORT = param("local_export", "/Volumes/workspace/ripple/files/exports/run2" if ON_DATABRICKS else "runs/run2/export")
CHECK_SHIPMENT = param("check_shipment", "SH-0182")
CHECK_NEW_ETA = param("check_new_eta", "2027-03-18")
CHECK_LOT = param("check_lot", "LOT-0191")

if ON_DATABRICKS:
    spark = spark  # noqa: F821,PLW0127
else:
    spark = (SparkSession.builder.master("local[2]").appName("ripple-graph")
             .config("spark.sql.shuffle.partitions", "4").config("spark.ui.enabled", "false").getOrCreate())
    spark.sparkContext.setLogLevel("ERROR")

# COMMAND ----------
# MAGIC %md ## 1 · Ingest extracts (all columns as strings, exactly like `csv.DictReader` locally)

# COMMAND ----------

FILES = ["aliases", "bom", "calendar", "customer_orders", "customers", "dealers", "finished_vehicles", "inbound_shipments",
         "loaners", "models", "part_lots", "parts", "plant_models", "plants", "production_orders", "suppliers"]
T = {f: spark.read.option("header", True).option("inferSchema", False).option("multiLine", False)
     .option("quote", '"').option("escape", '"').csv(f"{SOURCE}/{f}.csv") for f in FILES}
for f, df in T.items():
    df.createOrReplaceTempView(f"src_{f}")
SNAPSHOT_ID = None
try:
    SNAPSHOT_ID = json.load(open(os.path.join(LOCAL_EXPORT, "manifest.json")))["snapshot_id"]
except Exception:
    pass
SNAPSHOT_ID = param("snapshot_id", SNAPSHOT_ID or "unversioned")
print({f: df.count() for f, df in T.items()}, "snapshot", SNAPSHOT_ID)

# COMMAND ----------
# MAGIC %md ## 2 · Normalized entity keys

# COMMAND ----------

ENTITY_KEYS = {"Plant": ("plants", "plant_id"), "Model": ("models", "model"), "Part": ("parts", "part_id"),
               "Supplier": ("suppliers", "supplier_id"), "Dealer": ("dealers", "dealer_id"),
               "LoanerPool": ("loaners", "dealer_id"), "Customer": ("customers", "customer_id"),
               "Shipment": ("inbound_shipments", "shipment_id"), "ProductionOrder": ("production_orders", "production_order_id"),
               "CustomerOrder": ("customer_orders", "customer_order_id"), "Vehicle": ("finished_vehicles", "vin"),
               "Lot": ("part_lots", "lot_id")}
entity_keys = None
for ntype, (tbl, col) in ENTITY_KEYS.items():
    d = T[tbl].select(F.lit(ntype).alias("ntype"), F.col(col).alias("sid"), F.lit(f"{tbl}.csv").alias("source_table"))
    entity_keys = d if entity_keys is None else entity_keys.unionByName(d)
entity_keys = entity_keys.withColumn("snapshot_id", F.lit(SNAPSHOT_ID))
nodes = (entity_keys.select("snapshot_id", F.concat_ws(":", "ntype", "sid").alias("node_key"), "ntype", "sid").distinct())

# COMMAND ----------
# MAGIC %md ## 3 · Graph edges with provenance (mirrors `ripple/graph.py`)

# COMMAND ----------

EDGE_SQL = """
SELECT 'DEALER_HAS_LOANER_POOL' etype, concat('Dealer:', dealer_id) src, concat('LoanerPool:', dealer_id) dst, 'loaners.csv' source_table, dealer_id source_key, false derived FROM src_loaners
UNION ALL SELECT 'PART_IN_MODEL', concat('Part:', part_id), concat('Model:', model), 'bom.csv', concat(model, '/', part_id), false FROM src_bom
UNION ALL SELECT 'PLANT_BUILDS_MODEL', concat('Plant:', plant_id), concat('Model:', model), 'plant_models.csv', concat(plant_id, '/', model), false FROM src_plant_models
UNION ALL SELECT 'SUPPLIES_SHIPMENT', concat('Supplier:', supplier_id), concat('Shipment:', shipment_id), 'inbound_shipments.csv', shipment_id, false FROM src_inbound_shipments
UNION ALL SELECT 'SHIPMENT_OF_PART', concat('Shipment:', shipment_id), concat('Part:', part_id), 'inbound_shipments.csv', shipment_id, false FROM src_inbound_shipments
UNION ALL SELECT 'SHIPMENT_TO_PLANT', concat('Shipment:', shipment_id), concat('Plant:', plant_id), 'inbound_shipments.csv', shipment_id, false FROM src_inbound_shipments
UNION ALL SELECT 'PLANT_SCHEDULES_ORDER', concat('Plant:', plant_id), concat('ProductionOrder:', production_order_id), 'production_orders.csv', production_order_id, false FROM src_production_orders
UNION ALL SELECT 'ORDER_OF_MODEL', concat('ProductionOrder:', production_order_id), concat('Model:', model), 'production_orders.csv', production_order_id, false FROM src_production_orders
UNION ALL SELECT 'ORDER_FULFILLS_CO', concat('ProductionOrder:', production_order_id), concat('CustomerOrder:', customer_order_id), 'customer_orders.csv', customer_order_id, false FROM src_customer_orders
UNION ALL SELECT 'CO_AT_DEALER', concat('CustomerOrder:', customer_order_id), concat('Dealer:', dealer_id), 'customer_orders.csv', customer_order_id, false FROM src_customer_orders
UNION ALL SELECT 'CO_FOR_CUSTOMER', concat('CustomerOrder:', customer_order_id), concat('Customer:', customer_id), 'customer_orders.csv', customer_order_id, false FROM src_customer_orders
UNION ALL SELECT 'ORDER_PRODUCED_VEHICLE', concat('ProductionOrder:', production_order_id), concat('Vehicle:', vin), 'finished_vehicles.csv', vin, false FROM src_finished_vehicles
UNION ALL SELECT 'VEHICLE_AT_DEALER', concat('Vehicle:', vin), concat('Dealer:', dealer_id), 'finished_vehicles.csv', vin, false FROM src_finished_vehicles
UNION ALL SELECT 'VEHICLE_OWNED_BY', concat('Vehicle:', vin), concat('Customer:', customer_id), 'finished_vehicles.csv', vin, false FROM src_finished_vehicles WHERE customer_id IS NOT NULL AND customer_id <> ''
UNION ALL SELECT 'SUPPLIES_LOT', concat('Supplier:', supplier_id), concat('Lot:', lot_id), 'part_lots.csv', lot_id, false FROM src_part_lots
UNION ALL SELECT 'LOT_OF_PART', concat('Lot:', lot_id), concat('Part:', part_id), 'part_lots.csv', lot_id, false FROM src_part_lots
UNION ALL SELECT 'LOT_AT_PLANT', concat('Lot:', lot_id), concat('Plant:', plant_id), 'part_lots.csv', lot_id, false FROM src_part_lots
-- DERIVED: no direct lot->order field. Same plant, build date inside the inclusive lot window, model BOM contains the part.
UNION ALL SELECT 'LOT_USED_IN_ORDER', concat('Lot:', l.lot_id), concat('ProductionOrder:', o.production_order_id), 'derived',
                 concat(l.lot_id, '/', o.production_order_id), true
          FROM src_part_lots l
          JOIN src_production_orders o ON o.plant_id = l.plant_id AND o.build_date BETWEEN l.first_build_date AND l.last_build_date
          JOIN src_bom b ON b.model = o.model AND b.part_id = l.part_id
"""
edges = (spark.sql(EDGE_SQL)
         .withColumn("edge_key", F.concat_ws("|", "etype", "src", "dst"))
         .withColumn("snapshot_id", F.lit(SNAPSHOT_ID))
         .dropDuplicates(["edge_key"])
         .select("snapshot_id", "edge_key", "etype", "src", "dst", "source_table", "source_key", "derived"))
if not ON_DATABRICKS:
    edges.cache()        # serverless compute (Free Edition) does not allow cache()/persist()
edge_counts = {r["etype"]: r["n"] for r in edges.groupBy("etype").agg(F.count("*").alias("n")).collect()}
print(json.dumps(edge_counts, indent=1, sort_keys=True))

# COMMAND ----------
# MAGIC %md ## 4 · Validation: unique keys, edge endpoints, orphaned BOM and shipment/lot links

# COMMAND ----------

checks = {}
for ntype, (tbl, col) in ENTITY_KEYS.items():
    if ntype == "LoanerPool":
        continue
    dup = T[tbl].groupBy(col).count().filter("count > 1").count()
    nulls = T[tbl].filter(F.col(col).isNull() | (F.col(col) == "")).count()
    checks[f"unique_key:{tbl}.{col}"] = {"duplicates": dup, "nulls": nulls, "ok": dup == 0 and nulls == 0}

node_keys = nodes.select(F.col("node_key").alias("k"))
for end in ("src", "dst"):
    missing = edges.join(node_keys, edges[end] == node_keys.k, "left_anti")
    checks[f"edge_endpoint_exists:{end}"] = {"missing": missing.count(),
                                             "examples": [r["edge_key"] for r in missing.limit(5).collect()]}
    checks[f"edge_endpoint_exists:{end}"]["ok"] = checks[f"edge_endpoint_exists:{end}"]["missing"] == 0

ORPHANS = {
    "bom.model -> models": "SELECT b.* FROM src_bom b LEFT ANTI JOIN src_models m ON m.model = b.model",
    "bom.part_id -> parts": "SELECT b.* FROM src_bom b LEFT ANTI JOIN src_parts p ON p.part_id = b.part_id",
    "plant_models -> plants/models": "SELECT x.* FROM src_plant_models x LEFT ANTI JOIN src_plants p ON p.plant_id = x.plant_id",
    "shipment.supplier_id": "SELECT s.* FROM src_inbound_shipments s LEFT ANTI JOIN src_suppliers x ON x.supplier_id = s.supplier_id",
    "shipment.part_id": "SELECT s.* FROM src_inbound_shipments s LEFT ANTI JOIN src_parts x ON x.part_id = s.part_id",
    "shipment.plant_id": "SELECT s.* FROM src_inbound_shipments s LEFT ANTI JOIN src_plants x ON x.plant_id = s.plant_id",
    "shipment part not in any model built at plant": """SELECT s.* FROM src_inbound_shipments s LEFT ANTI JOIN
         (SELECT pm.plant_id, b.part_id FROM src_plant_models pm JOIN src_bom b ON b.model = pm.model) u
         ON u.plant_id = s.plant_id AND u.part_id = s.part_id""",
    "lot.supplier/part/plant": """SELECT l.* FROM src_part_lots l LEFT ANTI JOIN src_suppliers s ON s.supplier_id = l.supplier_id
         UNION ALL SELECT l.* FROM src_part_lots l LEFT ANTI JOIN src_parts p ON p.part_id = l.part_id
         UNION ALL SELECT l.* FROM src_part_lots l LEFT ANTI JOIN src_plants p ON p.plant_id = l.plant_id""",
    "lot with no derived order": """SELECT l.* FROM src_part_lots l LEFT ANTI JOIN
         (SELECT DISTINCT regexp_extract(src, 'Lot:(.*)', 1) lot_id FROM ripple_edges WHERE etype = 'LOT_USED_IN_ORDER') d
         ON d.lot_id = l.lot_id""",
    "customer_order.production_order_id": "SELECT c.* FROM src_customer_orders c LEFT ANTI JOIN src_production_orders o ON o.production_order_id = c.production_order_id",
    "vehicle.production_order_id": "SELECT v.* FROM src_finished_vehicles v LEFT ANTI JOIN src_production_orders o ON o.production_order_id = v.production_order_id",
    "sold vehicle without customer": "SELECT * FROM src_finished_vehicles WHERE status = 'sold' AND (customer_id IS NULL OR customer_id = '')",
}
edges.createOrReplaceTempView("ripple_edges")
for name, sql in ORPHANS.items():
    n = spark.sql(sql).count()
    # a lot without derived orders is informational (e.g. a lot whose build window has no orders for models using it)
    checks[f"orphan:{name}"] = {"rows": n, "ok": n == 0 or name == "lot with no derived order"}
print(json.dumps({k: v["ok"] for k, v in checks.items()}, indent=1))

# COMMAND ----------
# MAGIC %md ## 5 · Reproducible impact-path checks (one supplier delay, one quality hold)

# COMMAND ----------

delay_path = spark.sql(f"""
SELECT s.shipment_id, s.part_id, s.plant_id, s.eta_date original_eta, '{CHECK_NEW_ETA}' new_eta, o.production_order_id, o.model,
       o.build_date, count(c.customer_order_id) customer_orders, count(DISTINCT c.dealer_id) dealers
FROM src_inbound_shipments s
JOIN src_bom b ON b.part_id = s.part_id
JOIN src_production_orders o ON o.plant_id = s.plant_id AND o.model = b.model
     AND o.build_date >= s.eta_date AND o.build_date < '{CHECK_NEW_ETA}'
     AND dayofweek(to_date(o.build_date)) BETWEEN 2 AND 6
LEFT JOIN src_customer_orders c ON c.production_order_id = o.production_order_id
WHERE s.shipment_id = '{CHECK_SHIPMENT}'
GROUP BY ALL ORDER BY o.build_date, o.production_order_id""")
lot_path = spark.sql(f"""
SELECT e.src lot, e.dst production_order, v.status, count(*) vehicles, count(DISTINCT v.dealer_id) dealers
FROM ripple_edges e JOIN src_finished_vehicles v ON concat('ProductionOrder:', v.production_order_id) = e.dst
WHERE e.etype = 'LOT_USED_IN_ORDER' AND e.src = 'Lot:{CHECK_LOT}'
GROUP BY ALL ORDER BY production_order, status""")
delay_rows = [r.asDict() for r in delay_path.collect()]
lot_rows = [r.asDict() for r in lot_path.collect()]
impact = {"delay": {"shipment": CHECK_SHIPMENT, "new_eta": CHECK_NEW_ETA,
                    "affected_orders": sorted({r["production_order_id"] for r in delay_rows}),
                    "customer_orders": sum(r["customer_orders"] for r in delay_rows)},
          "quality": {"lot": CHECK_LOT, "orders": sorted({r["production_order"] for r in lot_rows}),
                      "in_stock": sum(r["vehicles"] for r in lot_rows if r["status"] == "in_stock"),
                      "sold": sum(r["vehicles"] for r in lot_rows if r["status"] == "sold")}}
print(json.dumps(impact, indent=1))
if ON_DATABRICKS:
    display(delay_path)  # noqa: F821
    display(lot_path)    # noqa: F821

# COMMAND ----------
# MAGIC %md ## 6 · Parity with the local graph export (canonical node and edge keys, same snapshot)

# COMMAND ----------

parity = {"status": "skipped: no local export found"}
le_path, ln_path = f"{LOCAL_EXPORT}/graph_edges.csv", f"{LOCAL_EXPORT}/graph_nodes.csv"
try:
    local_edges = spark.read.option("header", True).csv(le_path)
    local_nodes = spark.read.option("header", True).csv(ln_path)
    le, de = local_edges.select("edge_key"), edges.select("edge_key")
    ln, dn = local_nodes.select("node_key"), nodes.select("node_key")
    prov_l = local_edges.select("edge_key", "source_table", "source_key")
    prov_mismatch = (edges.select("edge_key", "source_table", "source_key").join(prov_l, "edge_key")
                     .filter((edges.source_table != prov_l.source_table) | (edges.source_key != prov_l.source_key)).count())
    parity = {
        "snapshot_local": local_edges.select("snapshot_id").first()["snapshot_id"], "snapshot_databricks": SNAPSHOT_ID,
        "nodes": {"local": ln.count(), "databricks": dn.count(), "only_local": ln.subtract(dn).count(), "only_databricks": dn.subtract(ln).count()},
        "edges": {"local": le.count(), "databricks": de.count(), "only_local": le.subtract(de).count(), "only_databricks": de.subtract(le).count()},
        "provenance_mismatches": prov_mismatch,
        "edge_counts_by_type": {k: {"databricks": v, "local": local_edges.filter(F.col("etype") == k).count()} for k, v in sorted(edge_counts.items())},
        "examples_only_local": [r["edge_key"] for r in le.subtract(de).limit(5).collect()],
        "examples_only_databricks": [r["edge_key"] for r in de.subtract(le).limit(5).collect()],
    }
    parity["status"] = "MATCH" if (parity["nodes"]["only_local"] == parity["nodes"]["only_databricks"] == 0 and
                                   parity["edges"]["only_local"] == parity["edges"]["only_databricks"] == 0 and
                                   prov_mismatch == 0 and parity["snapshot_local"] == SNAPSHOT_ID) else "DIFFERENT"
except Exception as e:  # noqa: BLE001
    parity["error"] = f"{type(e).__name__}: {str(e)[:200]}"
print(json.dumps({k: v for k, v in parity.items() if k != "edge_counts_by_type"}, indent=1))

# COMMAND ----------
# MAGIC %md ## 7 · Publish Delta tables (MERGE on snapshot + key, so re-runs do not duplicate)

# COMMAND ----------


def publish(df, name, keys):
    if ON_DATABRICKS:
        from delta.tables import DeltaTable
        full = f"{TARGET}.{name}"
        spark.sql(f"CREATE SCHEMA IF NOT EXISTS {TARGET}")  # Unity Catalog: <catalog>.<schema>
        if not spark.catalog.tableExists(full):
            df.limit(0).write.format("delta").saveAsTable(full)
        cond = " AND ".join(f"t.{k} = s.{k}" for k in keys)
        DeltaTable.forName(spark, full).alias("t").merge(df.alias("s"), cond).whenMatchedUpdateAll().whenNotMatchedInsertAll().execute()
        return spark.table(full).filter(F.col("snapshot_id") == SNAPSHOT_ID).count()
    # laptop stand-in for Delta (Spark file writes need winutils on Windows): one CSV per table, overwritten per snapshot
    os.makedirs(TARGET, exist_ok=True)
    pdf = df.toPandas().drop_duplicates(subset=keys)
    pdf.to_csv(os.path.join(TARGET, f"{name}.csv"), index=False)
    return len(pdf)


report = {"snapshot_id": SNAPSHOT_ID, "on_databricks": ON_DATABRICKS, "edge_counts": edge_counts,
          "node_counts": {r["ntype"]: r["n"] for r in nodes.groupBy("ntype").agg(F.count("*").alias("n")).collect()},
          "validation": checks, "validation_ok": all(v["ok"] for v in checks.values()), "impact_checks": impact, "parity": parity}
report["published_rows"] = {
    "entity_keys": publish(entity_keys, "entity_keys", ["snapshot_id", "ntype", "sid"]),
    "graph_nodes": publish(nodes, "graph_nodes", ["snapshot_id", "node_key"]),
    "graph_edges": publish(edges, "graph_edges", ["snapshot_id", "edge_key"]),
}
out = os.path.join(LOCAL_EXPORT, "databricks_parity_report.json")   # on Databricks: next to the export in the Volume
json.dump(report, open(out, "w"), indent=2, default=str)
print("validation_ok", report["validation_ok"], "| parity", parity["status"], "| report", out)
