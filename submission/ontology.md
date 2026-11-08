# Ripple Control ontology

Schema `ripple-graph/1.0` · snapshot `9b1551f5b55378ef` · 17,029 nodes · 28,201 edges

```mermaid
flowchart LR
  Plant["Plant<br/>6"]
  Model["Model<br/>6"]
  Part["Part<br/>20"]
  Supplier["Supplier<br/>18"]
  Dealer["Dealer<br/>50"]
  LoanerPool["LoanerPool<br/>50"]
  Customer["Customer<br/>7,000"]
  Shipment["Shipment<br/>364"]
  ProductionOrder["ProductionOrder<br/>540"]
  CustomerOrder["CustomerOrder<br/>3,263"]
  Vehicle["Vehicle<br/>5,348"]
  Lot["Lot<br/>364"]
  Supplier -->|"supplies_shipment (364)"| Shipment
  Shipment -->|"shipment_of_part (364)"| Part
  Shipment -->|"shipment_to_plant (364)"| Plant
  Part -->|"part_in_model (47)"| Model
  Plant -->|"plant_builds_model (18)"| Model
  Plant -->|"plant_schedules_order (540)"| ProductionOrder
  ProductionOrder -->|"order_of_model (540)"| Model
  ProductionOrder -->|"order_fulfills_co (3,263)"| CustomerOrder
  CustomerOrder -->|"co_at_dealer (3,263)"| Dealer
  CustomerOrder -->|"co_for_customer (3,263)"| Customer
  Supplier -->|"supplies_lot (364)"| Lot
  Lot -->|"lot_of_part (364)"| Part
  Lot -->|"lot_at_plant (364)"| Plant
  Lot -.->|"lot_used_in_order (1,410)"| ProductionOrder
  ProductionOrder -->|"order_produced_vehicle (5,348)"| Vehicle
  Vehicle -->|"vehicle_at_dealer (5,348)"| Dealer
  Vehicle -->|"vehicle_owned_by (2,927)"| Customer
  Dealer -->|"dealer_has_loaner_pool (50)"| LoanerPool
```

Dashed edge = derived (same plant, build date in the lot's inclusive window, model BOM contains the part).

| Edge type | From | To | Meaning | Count |
|---|---|---|---|---|
| `SUPPLIES_SHIPMENT` | Supplier | Shipment | supplier sends an inbound shipment | 364 |
| `SHIPMENT_OF_PART` | Shipment | Part | shipment carries a part | 364 |
| `SHIPMENT_TO_PLANT` | Shipment | Plant | shipment is received at a plant | 364 |
| `PART_IN_MODEL` | Part | Model | bill of materials: model requires part | 47 |
| `PLANT_BUILDS_MODEL` | Plant | Model | plant is able to build the model | 18 |
| `PLANT_SCHEDULES_ORDER` | Plant | ProductionOrder | order is built at the plant | 540 |
| `ORDER_OF_MODEL` | ProductionOrder | Model | order builds this model | 540 |
| `ORDER_FULFILLS_CO` | ProductionOrder | CustomerOrder | customer order is filled by the build | 3,263 |
| `CO_AT_DEALER` | CustomerOrder | Dealer | customer order placed through dealer | 3,263 |
| `CO_FOR_CUSTOMER` | CustomerOrder | Customer | customer order belongs to customer | 3,263 |
| `SUPPLIES_LOT` | Supplier | Lot | supplier produced the part lot | 364 |
| `LOT_OF_PART` | Lot | Part | lot is a lot of this part | 364 |
| `LOT_AT_PLANT` | Lot | Plant | lot was installed at the plant | 364 |
| `LOT_USED_IN_ORDER` | Lot | ProductionOrder | DERIVED: same plant, build date in lot window, model BOM has part | 1,410 |
| `ORDER_PRODUCED_VEHICLE` | ProductionOrder | Vehicle | finished vehicle came from the build | 5,348 |
| `VEHICLE_AT_DEALER` | Vehicle | Dealer | vehicle is allocated to dealer | 5,348 |
| `VEHICLE_OWNED_BY` | Vehicle | Customer | sold vehicle owner | 2,927 |
| `DEALER_HAS_LOANER_POOL` | Dealer | LoanerPool | dealer's loaner pool | 50 |

Every edge stores `source_table` and `source_key` (the CSV row that justifies it). Keys: node `Type:id`, edge `TYPE|src|dst`.
