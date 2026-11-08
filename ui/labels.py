"""Plain-English names for the company tools and their arguments, so non-technical viewers can read the screens.
The raw tool name is still available (audit trail) for anyone who wants to check it against the official log."""
import csv
import datetime
import os
import re

# ---------------------------------------------------------------- plain names for coded IDs
_N = {"plant": {}, "supplier": {}, "part": {}, "dealer": {}}


def load_reference_names(data_dir):
    """Read display names from the organizer's reference CSVs (read-only)."""
    spec = {"plant": ("plants.csv", "plant_id"), "supplier": ("suppliers.csv", "supplier_id"),
            "part": ("parts.csv", "part_id"), "dealer": ("dealers.csv", "dealer_id")}
    for kind, (fname, key) in spec.items():
        p = os.path.join(data_dir, fname)
        if not os.path.exists(p):
            continue
        with open(p, encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                nm = row.get("name", "") or row[key]
                if kind == "plant":
                    nm = nm.replace("Wacky Wheels ", "") + " plant"
                _N[kind][row[key]] = nm


def _num(s):
    return str(int(s)) if s.isdigit() else s


def plain(x):
    """Turn a coded ID into words: P_TX -> 'San Antonio plant', PO-0058 -> 'Build 58', E-01#2 -> 'Message 1, problem 2'."""
    if x is None:
        return ""
    s = str(x)
    for kind in ("plant", "supplier", "part", "dealer"):
        if s in _N[kind]:
            return _N[kind][s]
    m = re.fullmatch(r"E-(\d+)#(\d+)", s)
    if m:
        return f"Message {_num(m[1])}, problem {_num(m[2])}"
    for pat, word in ((r"E-(\d+)", "Message"), (r"PO-(\d+)", "Build"), (r"CO-(\d+)", "Order"),
                      (r"LOT-(\d+)", "Batch"), (r"SH-(\d+)", "Shipment"), (r"C(\d{4})", "Customer"),
                      (r"D(\d{2})", "Dealer"), (r"SUP-(\d+)", "Supplier")):
        m = re.fullmatch(pat, s)
        if m:
            return f"{word} {_num(m[1])}"
    if re.fullmatch(r"[A-Z]{3,}", s):  # model names like NOVA
        return s.title()
    return s


_TOKEN = re.compile(r"E-\d+#\d+|E-\d{2}\b|PO-\d+|CO-\d+|LOT-\d+|SH-\d+|SUP-\d+|\bP_[A-Z]{2}\b|\bC\d{4}\b|\bD\d{2}\b|"
                    r"\b[A-Z]+-[A-Z0-9]+\b")


def plain_text(text):
    """Replace coded IDs inside a sentence with plain names."""
    if not text:
        return text or ""
    out = _TOKEN.sub(lambda m: plain(m.group(0)), str(text))
    return re.sub(r"\b2\d{3}-\d{2}-\d{2}\b", lambda m: _d(m.group(0)), out)


def plain_date(s):
    return _d(s)


# ---------------------------------------------------------------- knowledge-graph links in words
LINK_VERB = {
    "SUPPLIES_SHIPMENT": "sends", "SHIPMENT_OF_PART": "carries", "SHIPMENT_TO_PLANT": "is delivered to",
    "PART_IN_MODEL": "is needed to build", "PLANT_BUILDS_MODEL": "can build", "PLANT_SCHEDULES_ORDER": "has scheduled",
    "ORDER_OF_MODEL": "is a build of", "ORDER_FULFILLS_CO": "fills", "CO_AT_DEALER": "was placed at",
    "CO_FOR_CUSTOMER": "belongs to", "SUPPLIES_LOT": "made", "LOT_OF_PART": "is a batch of",
    "LOT_AT_PLANT": "was installed at", "LOT_USED_IN_ORDER": "went into", "ORDER_PRODUCED_VEHICLE": "produced",
    "VEHICLE_AT_DEALER": "is at", "VEHICLE_OWNED_BY": "is owned by", "DEALER_HAS_LOANER_POOL": "has",
}
DATA_FILE = {
    "inbound_shipments.csv": "Inbound shipments", "part_lots.csv": "Parts batches", "bom.csv": "Bill of materials",
    "production_orders.csv": "Production schedule", "customer_orders.csv": "Customer orders",
    "finished_vehicles.csv": "Finished vehicles", "plant_models.csv": "Plant capabilities", "loaners.csv": "Loaner pools",
}


def link_sentence(etype, src, dst):
    """'Shipment 182 carries surround-view camera kit'."""
    return f"{plain(src)} {LINK_VERB.get(etype, etype.lower().replace('_', ' '))} {plain(dst)}"


def data_file(name):
    return DATA_FILE.get(name, name or "")


def move_reason(text):
    """Plain wording for the planner's reasons (falls back to ID/date clean-up for anything unexpected)."""
    s = str(text or "")
    m = re.fullmatch(r"earliest same-plant day on/after recovery (\S+) with a free slot \((\d+) of (\d+) free\)", s)
    if m:
        return (f"First day at the same plant, on or after the restart ({_d(m[1])}), that still had an open slot "
                f"({m[2]} of {m[3]} slots free).")
    m = re.fullmatch(r"no free same-plant slot at (\S+) from (\S+) to (\S+); earliest free day at a plant that builds "
                     r"(\S+) \(day first, then plants\.csv order\)", s)
    if m:
        return (f"{plain(m[1])} had no open slot from {_d(m[2])} to {_d(m[3])}, so it moved to the earliest open day "
                f"at another plant that builds the {plain(m[4])}.")
    return plain_text(s)


def loaner_reason(text):
    s = str(text or "")
    m = re.fullmatch(r"rank (\d+) of (\d+) eligible; (\d+) in pool", s)
    if m:
        return f"#{m[1]} in line of {m[2]} eligible customers; the dealer had {m[3]} loaner car{'s' if m[3] != '1' else ''}."
    m = re.fullmatch(r"pool exhausted \((\d+) available at (\S+)\)", s)
    if m:
        return f"No loaner left: {plain(m[2])} had only {m[1]}, and they went to customers higher in line."
    return plain_text(s)


def graph_caption(types):
    """'How to read' line for an impact graph, built from the kinds of boxes it contains."""
    t = set(types)
    if "Lot" in t:
        return ("Read left to right: the supplier made a faulty parts batch, the batch went into these car builds, "
                "and each build produced finished cars (shown sold vs. still in stock).")
    if "Shipment" in t:
        return ("Read left to right: the supplier's late shipment carries a part, that part is needed to build these "
                "car models, so the car builds of those models at that plant are hit, and each build fills customer orders.")
    if "Plant" in t:
        return ("Read left to right: the plant that is down has these car builds scheduled during the outage, and each "
                "build fills customer orders.")
    return "Read left to right: each arrow means the box on the left directly affects the box on the right."

TOOL_LABEL = {
    "mes.get_schedule": "Check plant schedule",
    "mes.reschedule": "Move build to a later day",
    "mes.transfer": "Move build to another plant",
    "dealer.notify": "Notify dealer",
    "dealer.stop_sale": "Stop sale of cars",
    "crm.loaner_availability": "Check loaner cars",
    "crm.assign_loaner": "Give customer a loaner",
    "crm.notify_customer": "Message customer",
    "quality.hold_lot": "Hold faulty parts batch",
    "escalate": "Send to a person",
}

SOURCE_HELP = {
    "daily digest": "A daily email that bundles several updates into one message.",
    "ops chat": "The operations team's group chat. Informal, sometimes rumors.",
    "quality bulletin": "An official notice from the quality team about faulty parts.",
    "news wire": "General incoming messages, here dealers asking about brochures.",
    "plant alert": "An automatic alert sent by a factory's own systems.",
    "supplier email": "An email from a company that supplies parts.",
}

STATUS_LABEL ={"confirmed": "Done", "rejected": "Failed", "unknown": "No reply", "blocked": "Blocked"}


def tool_label(tool):
    return TOOL_LABEL.get(tool, tool)


def _d(s):
    try:
        d = datetime.date.fromisoformat(str(s)[:10])
        return f"{d:%b} {d.day}"
    except ValueError:
        return str(s)


def describe(tool, args):
    """One short sentence saying what a call did, e.g. 'Move PO-0058 to Mar 23'."""
    a = args or {}
    p = lambda k: plain(a.get(k))  # noqa: E731
    if tool == "mes.get_schedule":
        return f"Look at {p('plant_id')} on {_d(a.get('date'))}"
    if tool == "mes.reschedule":
        return f"Move {p('production_order_id')} to {_d(a.get('new_date'))}"
    if tool == "mes.transfer":
        return f"Move {p('production_order_id')} to {p('to_plant_id')}, {_d(a.get('new_date'))}"
    if tool == "dealer.notify":
        n = len(a.get("customer_order_ids") or [])
        return f"Tell {p('dealer_id')} about {n} customer order{'s' if n != 1 else ''}"
    if tool == "dealer.stop_sale":
        n = len(a.get("vins") or [])
        return f"Stop sale of {n} car{'s' if n != 1 else ''} at {p('dealer_id')}"
    if tool == "crm.loaner_availability":
        return f"How many loaners {p('dealer_id')} has"
    if tool == "crm.assign_loaner":
        return f"Loaner for {p('customer_order_id')}"
    if tool == "crm.notify_customer":
        return f"Message {p('customer_id')}"
    if tool == "quality.hold_lot":
        return f"Hold {p('lot_id')}"
    if tool == "escalate":
        return "Ask a person to check this report"
    return ", ".join(f"{k}: {v}" for k, v in a.items() if k != "message")


def outcome(tool, body, status):
    """Short plain result of a call."""
    if status != "confirmed":
        return STATUS_LABEL.get(status, status)
    b = body or {}
    if tool == "mes.get_schedule":
        free = b.get("free_slots")
        return f"{free} free slot{'s' if free != 1 else ''}" if free is not None else "Done"
    if tool == "crm.loaner_availability":
        n = b.get("available")
        return f"{n} available" if n is not None else "Done"
    return "Done"
