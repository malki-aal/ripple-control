# Event summaries

Generated from `event_traces.jsonl`. One section per event: what it was, what we did, and why.

## E-01 · daily digest · 2027-03-08T07:17:00

> Morning digest, two items. (1) San Antonio update: a software outage on the line. We're dark from next Friday through Monday Mar 22; the line restarts the following working day. (2) Quick heads up from Quanta: the infotainment chip run for Princeton can't make it next Monday. Carrier says next Friday now (severe weather on the route).

- **E-01#1 · plant_outage** · handled by Supply Chain Planner · decision: act on 6 affected production orders
  - resolved: plant=P_TX; start = 2027-03-19 ("next Friday"), end = 2027-03-22 ("Monday Mar 22")
  - graph path: PLANT_SCHEDULES_ORDER ×6
  - policy: Rule 2 Plant outage
- **E-01#2 · supplier_delay** · handled by Supply Chain Planner · decision: act on 8 affected production orders
  - resolved: supplier=SUP-12, part=CHIP-IVI, plant=P_IN; original_eta = 2027-03-15 ("next Monday"), new_eta = 2027-03-19 ("next Friday")
  - graph path: SUPPLIES_SHIPMENT ×1 → SHIPMENT_OF_PART ×1 → SHIPMENT_TO_PLANT ×1 → PART_IN_MODEL ×5 → PLANT_SCHEDULES_ORDER ×8 → ORDER_OF_MODEL ×8
  - policy: Rule 1 Supplier delay

**Outcome.** E-01#1 plant outage: outage at P_TX: 2027-03-19 .. 2027-03-22 inclusive; window [2027-03-19, 2027-03-22] inclusive; 6 production orders affected. E-01#2 supplier delay: CHIP-IVI delay at P_IN: 2027-03-15 -> 2027-03-19; window [2027-03-15, 2027-03-19); 8 production orders affected (models NOVA, PIONEER, SUMMIT, TERRA, VOYAGER). Moves: 14 rescheduled, 0 transferred. Dealers notified: 41. Loaners assigned: 26 (4 eligible customers left without one: pool exhausted).

Writes confirmed: 81 · action kinds: crm.assign_loaner, dealer.notify, mes.reschedule · failed calls: 0

## E-02 · ops chat · 2027-03-08T07:34:00

> Rumor from a supplier rep: something may be off with a seat material coming up. No dates, no details, nothing confirmed.

- **E-02#1 · unconfirmed** · handled by Coordinator · decision: escalate
  - policy: Rule 8 Unconfirmed or unclear
  - reason: Unconfirmed report (Vague report of potential issue with seat material without specific details or confirmation.); entities named: none. No operational action taken. Human should confirm the source, the affected part/plant/supplier, and concrete dates.

**Outcome.** E-02#1 unconfirmed: escalated to a human, no operational change. Unconfirmed report (Vague report of potential issue with seat material without specific details or confirmation.); entities named: none. No operational action taken. Human should confirm the source, the affected part/plant/supplier, and concrete dates.

Writes confirmed: 0 · action kinds: escalate · failed calls: 0 · escalated to a human

## E-03 · quality bulletin · 2027-03-08T07:51:00

> Quality alert: Kestrel says the infotainment chip sent to Jackson had a faulty weld. Anything built Thursday Feb 25 through last Monday is suspect.

- **E-03#1 · quality_hold** · handled by Customer Care & Quality · decision: hold LOT-0130, stop-sale 110 VINs, contact 150 owners
  - resolved: supplier=SUP-06, part=CHIP-IVI, plant=P_MS; build_from = 2027-02-25 ("Thursday Feb 25"), build_to = 2027-03-01 ("last Monday")
  - graph path: SUPPLIES_LOT ×1 → LOT_OF_PART ×1 → LOT_AT_PLANT ×1 → LOT_USED_IN_ORDER ×9 → ORDER_PRODUCED_VEHICLE ×260 → VEHICLE_AT_DEALER ×260 → VEHICLE_OWNED_BY ×150
  - policy: Rule 6 Quality hold

**Outcome.** E-03#1 quality hold: lot LOT-0130 (supplier + part + plant + exact build window), 260 vehicles traced via derived lot->order edges; 110 unsold VINs at 37 dealers stopped, 150 owners contacted.

Writes confirmed: 188 · action kinds: crm.notify_customer, dealer.stop_sale, quality.hold_lot · failed calls: 0

## E-04 · ops chat · 2027-03-08T08:08:00

> The Kentucky plant update: a software outage on the line. We're dark from next Tuesday through next Thursday; the line restarts the following working day.

- **E-04#1 · plant_outage** · handled by Supply Chain Planner · decision: act on 9 affected production orders
  - resolved: plant=P_KY; start = 2027-03-16 ("next Tuesday"), end = 2027-03-18 ("next Thursday")
  - graph path: PLANT_SCHEDULES_ORDER ×9
  - policy: Rule 2 Plant outage

**Outcome.** E-04#1 plant outage: outage at P_KY: 2027-03-16 .. 2027-03-18 inclusive; window [2027-03-16, 2027-03-18] inclusive; 9 production orders affected. Moves: 9 rescheduled, 0 transferred. Dealers notified: 32. Loaners assigned: 18 (4 eligible customers left without one: pool exhausted).

Writes confirmed: 59 · action kinds: crm.assign_loaner, dealer.notify, mes.reschedule · failed calls: 0

## E-05 · news wire · 2027-03-08T08:25:00

> Dealer Amarillo, TX asks where to find the new brochure PDF.

- **E-05#1 · noise** · handled by Coordinator · decision: no action
  - policy: Rule 7 Noise
  - reason: Not operational: The message is an inquiry about marketing materials and does not pertain to operational incidents.. No supplier, plant, part, shipment or lot incident language with a resolvable entity.

**Outcome.** E-05#1 noise: Not operational: The message is an inquiry about marketing materials and does not pertain to operational incidents.. No supplier, plant, part, shipment or lot incident language with a resolvable entity.

Writes confirmed: 0 · action kinds: none · failed calls: 0

## E-06 · news wire · 2027-03-08T08:42:00

> Dealer Little Rock, AR asks where to find the new brochure PDF.

- **E-06#1 · noise** · handled by Coordinator · decision: no action
  - policy: Rule 7 Noise
  - reason: Not operational: The message is an inquiry about marketing materials and does not pertain to operational incidents.. No supplier, plant, part, shipment or lot incident language with a resolvable entity.

**Outcome.** E-06#1 noise: Not operational: The message is an inquiry about marketing materials and does not pertain to operational incidents.. No supplier, plant, part, shipment or lot incident language with a resolvable entity.

Writes confirmed: 0 · action kinds: none · failed calls: 0

## E-07 · news wire · 2027-03-08T08:59:00

> Dealer Pensacola, FL asks where to find the new brochure PDF.

- **E-07#1 · noise** · handled by Coordinator · decision: no action
  - policy: Rule 7 Noise
  - reason: Not operational: The message is an inquiry about marketing materials and does not pertain to operational incidents.. No supplier, plant, part, shipment or lot incident language with a resolvable entity.

**Outcome.** E-07#1 noise: Not operational: The message is an inquiry about marketing materials and does not pertain to operational incidents.. No supplier, plant, part, shipment or lot incident language with a resolvable entity.

Writes confirmed: 0 · action kinds: none · failed calls: 0

## E-08 · plant alert · 2027-03-08T09:16:00

> Plant operations alert: Wacky Wheels Lexington (P_KY) lost production to a power failure. Production is stopped from 2027-03-24 through 2027-03-25 inclusive.

- **E-08#1 · plant_outage** · handled by Supply Chain Planner · decision: act on 6 affected production orders
  - resolved: plant=P_KY; start = 2027-03-24 ("2027-03-24"), end = 2027-03-25 ("2027-03-25")
  - graph path: PLANT_SCHEDULES_ORDER ×6
  - policy: Rule 2 Plant outage

**Outcome.** E-08#1 plant outage: outage at P_KY: 2027-03-24 .. 2027-03-25 inclusive; window [2027-03-24, 2027-03-25] inclusive; 6 production orders affected. Moves: 6 rescheduled, 0 transferred. Dealers notified: 25. Loaners assigned: 15.

Writes confirmed: 46 · action kinds: crm.assign_loaner, dealer.notify, mes.reschedule · failed calls: 0

## E-09 · supplier email · 2027-03-08T09:33:00

> Quick heads up from Orbit: the surround-view cameras run for Huntsville can't make it Monday Mar 29. Carrier says Thursday Apr 1 now (a customs inspection).

- **E-09#1 · supplier_delay** · handled by Supply Chain Planner · decision: act on 6 affected production orders
  - resolved: supplier=SUP-11, part=CAM-360, plant=P_AL; original_eta = 2027-03-29 ("Monday Mar 29"), new_eta = 2027-04-01 ("Thursday Apr 1")
  - graph path: SUPPLIES_SHIPMENT ×1 → SHIPMENT_OF_PART ×1 → SHIPMENT_TO_PLANT ×1 → PART_IN_MODEL ×2 → PLANT_SCHEDULES_ORDER ×6 → ORDER_OF_MODEL ×6
  - policy: Rule 1 Supplier delay

**Outcome.** E-09#1 supplier delay: CAM-360 delay at P_AL: 2027-03-29 -> 2027-04-01; window [2027-03-29, 2027-04-01); 6 production orders affected (models SUMMIT, VOYAGER). Moves: 4 rescheduled, 2 transferred. Dealers notified: 26. Loaners assigned: 10 (2 eligible customers left without one: pool exhausted).

Writes confirmed: 42 · action kinds: crm.assign_loaner, dealer.notify, mes.reschedule, mes.transfer · failed calls: 0

## E-10 · ops chat · 2027-03-08T09:50:00

> Huntsville line is waiting on 60 kWh battery packs from Lumen. Original drop was Monday Mar 29, new ETA is Thursday Apr 1 because of a truck breakdown.

- **E-10#1 · supplier_delay** · handled by Supply Chain Planner · decision: act on 3 affected production orders
  - resolved: supplier=SUP-18, part=BATT-60, plant=P_AL; original_eta = 2027-03-29 ("Monday Mar 29"), new_eta = 2027-04-01 ("Thursday Apr 1")
  - graph path: SUPPLIES_SHIPMENT ×1 → SHIPMENT_OF_PART ×1 → SHIPMENT_TO_PLANT ×1 → PART_IN_MODEL ×1 → PLANT_SCHEDULES_ORDER ×3 → ORDER_OF_MODEL ×3
  - policy: Rule 1 Supplier delay

**Outcome.** E-10#1 supplier delay: BATT-60 delay at P_AL: 2027-03-29 -> 2027-04-01; window [2027-03-29, 2027-04-01); 3 production orders affected (models NOVA). Moves: 3 rescheduled, 0 transferred. Dealers notified: 18. Loaners assigned: 7.

Writes confirmed: 28 · action kinds: crm.assign_loaner, dealer.notify, mes.reschedule · failed calls: 0

## E-11 · ops chat · 2027-03-08T10:07:00

> Jackson update: a power failure. We're dark from Friday Mar 26 through Tuesday Mar 30; the line restarts the following working day.

- **E-11#1 · plant_outage** · handled by Supply Chain Planner · decision: act on 9 affected production orders
  - resolved: plant=P_MS; start = 2027-03-26 ("Friday Mar 26"), end = 2027-03-30 ("Tuesday Mar 30")
  - graph path: PLANT_SCHEDULES_ORDER ×9
  - policy: Rule 2 Plant outage

**Outcome.** E-11#1 plant outage: outage at P_MS: 2027-03-26 .. 2027-03-30 inclusive; window [2027-03-26, 2027-03-30] inclusive; 9 production orders affected. Moves: 6 rescheduled, 3 transferred. Dealers notified: 36. Loaners assigned: 17 (1 eligible customers left without one: pool exhausted).

Writes confirmed: 62 · action kinds: crm.assign_loaner, dealer.notify, mes.reschedule, mes.transfer · failed calls: 0

## E-12 · supplier email · 2027-03-08T10:24:00

> Subject: Shipment SH-0182 delayed From: dispatch@orbit.example  Our shipment SH-0182 of CAM-360 (surround-view camera kit) for Wacky Wheels Princeton (P_IN) was due 2027-03-15 and will now arrive 2027-03-18. Reason: port congestion.

- **E-12#1 · supplier_delay** · handled by Supply Chain Planner · decision: act on 3 affected production orders
  - resolved: supplier=SUP-11, part=CAM-360, plant=P_IN, shipment=SH-0182; original_eta = 2027-03-15 ("2027-03-15"), new_eta = 2027-03-18 ("2027-03-18")
  - graph path: SUPPLIES_SHIPMENT ×1 → SHIPMENT_OF_PART ×1 → SHIPMENT_TO_PLANT ×1 → PART_IN_MODEL ×2 → PLANT_SCHEDULES_ORDER ×3 → ORDER_OF_MODEL ×3
  - policy: Rule 1 Supplier delay

**Outcome.** E-12#1 supplier delay: CAM-360 delay at P_IN: 2027-03-15 -> 2027-03-18; window [2027-03-15, 2027-03-18); 3 production orders affected (models SUMMIT, VOYAGER). Moves: 3 rescheduled, 0 transferred. Dealers notified: 14. Loaners assigned: 10.

Writes confirmed: 27 · action kinds: crm.assign_loaner, dealer.notify, mes.reschedule · failed calls: 0

## E-13 · ops chat · 2027-03-08T10:41:00

> Someone on the floor mentioned a possible shortage of something electronic sometime soon. Not confirmed by anyone.

- **E-13#1 · unconfirmed** · handled by Coordinator · decision: escalate
  - policy: Rule 8 Unconfirmed or unclear
  - reason: Unconfirmed report (Possible shortage of electronic parts mentioned as a rumor.); entities named: none. No operational action taken. Human should confirm the source, the affected part/plant/supplier, and concrete dates.

**Outcome.** E-13#1 unconfirmed: escalated to a human, no operational change. Unconfirmed report (Possible shortage of electronic parts mentioned as a rumor.); entities named: none. No operational action taken. Human should confirm the source, the affected part/plant/supplier, and concrete dates.

Writes confirmed: 0 · action kinds: escalate · failed calls: 0 · escalated to a human

## E-14 · ops chat · 2027-03-08T10:58:00

> Quality alert: Atlas says the heavy-duty wiring harness sent to the Texas plant had a moisture contamination. Anything built Monday Feb 22 through Wednesday Feb 24 is suspect.

- **E-14#1 · quality_hold** · handled by Customer Care & Quality · decision: hold LOT-0017, stop-sale 86 VINs, contact 94 owners
  - resolved: supplier=SUP-07, part=HARN-B, plant=P_TX; build_from = 2027-02-22 ("Monday Feb 22"), build_to = 2027-02-24 ("Wednesday Feb 24")
  - graph path: SUPPLIES_LOT ×1 → LOT_OF_PART ×1 → LOT_AT_PLANT ×1 → LOT_USED_IN_ORDER ×6 → ORDER_PRODUCED_VEHICLE ×180 → VEHICLE_AT_DEALER ×180 → VEHICLE_OWNED_BY ×94
  - policy: Rule 6 Quality hold

**Outcome.** E-14#1 quality hold: lot LOT-0017 (supplier + part + plant + exact build window), 180 vehicles traced via derived lot->order edges; 86 unsold VINs at 36 dealers stopped, 94 owners contacted.

Writes confirmed: 131 · action kinds: crm.notify_customer, dealer.stop_sale, quality.hold_lot · failed calls: 0

## E-15 · quality bulletin · 2027-03-08T11:15:00

> QUALITY BULLETIN QB-368: Lot LOT-0191 (CHIP-IVI, supplier SUP-12) installed at P_IN on vehicles built 2027-03-02 to 2027-03-03 has a faulty weld. Place the lot on hold, stop sale of unsold vehicles and contact owners.

- **E-15#1 · quality_hold** · handled by Customer Care & Quality · decision: hold LOT-0191, stop-sale 40 VINs, contact 76 owners
  - resolved: supplier=SUP-12, part=CHIP-IVI, plant=P_IN, lot=LOT-0191; build_from = 2027-03-02 ("2027-03-02"), build_to = 2027-03-03 ("2027-03-03")
  - graph path: SUPPLIES_LOT ×1 → LOT_OF_PART ×1 → LOT_AT_PLANT ×1 → LOT_USED_IN_ORDER ×4 → ORDER_PRODUCED_VEHICLE ×116 → VEHICLE_AT_DEALER ×116 → VEHICLE_OWNED_BY ×76
  - policy: Rule 6 Quality hold

**Outcome.** E-15#1 quality hold: lot LOT-0191 (explicit lot id), 116 vehicles traced via derived lot->order edges; 40 unsold VINs at 25 dealers stopped, 76 owners contacted.

Writes confirmed: 102 · action kinds: crm.notify_customer, dealer.stop_sale, quality.hold_lot · failed calls: 0

