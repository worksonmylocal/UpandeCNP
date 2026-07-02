"""
Daily scheduled alerts for the Crop Nutrition Planning module.
Run via the Frappe scheduler (daily).
"""

import frappe
from frappe.utils import today, getdate, date_diff, flt

MONTHS = ["January", "February", "March", "April", "May", "June",
          "July", "August", "September", "October", "November", "December"]


def get_settings():
    try:
        return frappe.get_doc("Crop Nutrition Planning Settings")
    except Exception:
        return None


def month_to_next_date(month_name, ref_date):
    """Return the next occurrence (as date) of the 1st of the given month."""
    if month_name not in MONTHS:
        return None
    month_idx = MONTHS.index(month_name) + 1
    year = ref_date.year if month_idx >= ref_date.month else ref_date.year + 1
    return getdate(f"{year}-{month_idx:02d}-01")


# ---------------------------------------------------------------------------
# 1. Upcoming application alerts
# ---------------------------------------------------------------------------
def check_upcoming_applications():
    settings = get_settings()
    if not settings or not settings.farm_manager_email:
        return

    days_threshold = int(settings.upcoming_alert_days or 14)
    today_date = getdate(today())

    plans = frappe.get_all(
        "Block Fertilizer Plan",
        filters={"status": "Planned", "docstatus": 1},
        fields=["name", "block", "fertilizer_product", "application_month", "total_kg_required"],
    )

    upcoming = []
    for plan in plans:
        target = month_to_next_date(plan.application_month, today_date)
        if not target:
            continue
        days_until = date_diff(target, today_date)
        if 0 <= days_until <= days_threshold:
            upcoming.append(plan)

    if not upcoming:
        return

    rows = "".join(
        f"<tr><td>{p.block}</td><td>{p.fertilizer_product}</td>"
        f"<td>{p.application_month}</td><td>{flt(p.total_kg_required):.1f}</td></tr>"
        for p in upcoming
    )
    frappe.sendmail(
        recipients=[settings.farm_manager_email],
        subject=f"Upcoming Fertilizer Applications - {len(upcoming)} due within {days_threshold} days",
        message=f"""
        <p>The following fertilizer applications are due within {days_threshold} days:</p>
        <table border="1" cellpadding="6" cellspacing="0">
          <tr><th>Block</th><th>Product</th><th>Month</th><th>Qty (Kg)</th></tr>
          {rows}
        </table>
        """,
    )


# ---------------------------------------------------------------------------
# 2. Low stock alerts
# ---------------------------------------------------------------------------
def check_low_stock():
    settings = get_settings()
    if not settings or not settings.farm_manager_email:
        return

    warehouse = settings.fertilizer_warehouse

    programmes = frappe.get_all(
        "Fertilizer Programme",
        filters={"docstatus": 1},
        fields=["name"],
        order_by="creation desc",
        limit=1,
    )
    if not programmes:
        return

    programme = frappe.get_doc("Fertilizer Programme", programmes[0].name)

    # Sum requirement per product
    required = {}
    for line in programme.get("programme_lines", []):
        required[line.fertilizer_product] = required.get(line.fertilizer_product, 0) + flt(line.total_kg)

    low = []
    for product, need in required.items():
        stock = get_stock(product, warehouse)
        if stock < need:
            low.append({"product": product, "stock": stock, "need": need})

    if not low:
        return

    rows = "".join(
        f"<tr><td>{i['product']}</td><td>{i['stock']:.1f}</td><td>{i['need']:.1f}</td></tr>"
        for i in low
    )
    frappe.sendmail(
        recipients=[settings.farm_manager_email],
        subject=f"Low Fertilizer Stock - {len(low)} products below requirement",
        message=f"""
        <p>The following products have insufficient stock for the active programme:</p>
        <table border="1" cellpadding="6" cellspacing="0">
          <tr><th>Product</th><th>Stock (Kg)</th><th>Required (Kg)</th></tr>
          {rows}
        </table>
        """,
    )


# ---------------------------------------------------------------------------
# 3. Missed application alerts
# ---------------------------------------------------------------------------
def check_missed_applications():
    settings = get_settings()
    if not settings or not settings.farm_manager_email:
        return

    today_date = getdate(today())

    plans = frappe.get_all(
        "Block Fertilizer Plan",
        filters={"status": "Planned", "docstatus": 1},
        fields=["name", "block", "fertilizer_product", "application_month"],
    )

    missed = []
    for plan in plans:
        if plan.application_month not in MONTHS:
            continue
        month_idx = MONTHS.index(plan.application_month) + 1
        # If the month is earlier in this calendar year, it has passed
        year = today_date.year if month_idx <= today_date.month else today_date.year - 1
        month_end = getdate(f"{year}-{month_idx:02d}-28")
        if today_date > month_end:
            missed.append(plan)

    if not missed:
        return

    rows = "".join(
        f"<tr><td>{p.block}</td><td>{p.fertilizer_product}</td><td>{p.application_month}</td></tr>"
        for p in missed
    )
    frappe.sendmail(
        recipients=[settings.farm_manager_email],
        subject=f"Missed Fertilizer Applications - {len(missed)} overdue",
        message=f"""
        <p>The following planned applications are past their month with no application recorded:</p>
        <table border="1" cellpadding="6" cellspacing="0">
          <tr><th>Block</th><th>Product</th><th>Month</th></tr>
          {rows}
        </table>
        <p>Please verify whether these were applied and record them.</p>
        """,
    )


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------
def get_stock(item_code, warehouse=None):
    filters = {"item_code": item_code}
    if warehouse:
        filters["warehouse"] = warehouse
    return flt(frappe.db.get_value("Bin", filters, "actual_qty"))