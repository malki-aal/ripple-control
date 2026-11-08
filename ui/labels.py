"""Plain-English names for the company tools and their arguments, so non-technical viewers can read the screens.
The raw tool name is still available (audit trail) for anyone who wants to check it against the official log."""
import datetime

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

STATUS_LABEL = {"confirmed": "Done", "rejected": "Failed", "unknown": "No reply", "blocked": "Blocked"}


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
    if tool == "mes.get_schedule":
        return f"Look at {a.get('plant_id')} on {_d(a.get('date'))}"
    if tool == "mes.reschedule":
        return f"Move {a.get('production_order_id')} to {_d(a.get('new_date'))}"
    if tool == "mes.transfer":
        return f"Build {a.get('production_order_id')} at {a.get('to_plant_id')} on {_d(a.get('new_date'))}"
    if tool == "dealer.notify":
        n = len(a.get("customer_order_ids") or [])
        return f"Tell {a.get('dealer_id')} about {n} customer order{'s' if n != 1 else ''}"
    if tool == "dealer.stop_sale":
        n = len(a.get("vins") or [])
        return f"Stop sale of {n} car{'s' if n != 1 else ''} at {a.get('dealer_id')}"
    if tool == "crm.loaner_availability":
        return f"How many loaners {a.get('dealer_id')} has"
    if tool == "crm.assign_loaner":
        return f"Loaner for order {a.get('customer_order_id')}"
    if tool == "crm.notify_customer":
        return f"Message customer {a.get('customer_id')}"
    if tool == "quality.hold_lot":
        return f"Hold {a.get('lot_id')}"
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
