"""
Integration between Crop Nutrition Planning and ERPNext core modules.
Handles Material Request generation and stock netting.
"""

import frappe
from frappe.utils import flt, today, getdate

MONTHS = ["January", "February", "March", "April", "May", "June",
          "July", "August", "September", "October", "November", "December"]


def get_stock_qty(item_code, warehouse=None):
    filters = {"item_code": item_code}
    if warehouse:
        filters["warehouse"] = warehouse
    return flt(frappe.db.get_value("Bin", filters, "actual_qty"))


def month_to_date(month_name):
    """Return the next occurrence of the 1st of the given month as a date string."""
    today_date = getdate(today())
    if month_name not in MONTHS:
        return today()
    month_idx = MONTHS.index(month_name) + 1
    year = today_date.year if month_idx >= today_date.month else today_date.year + 1
    return f"{year}-{month_idx:02d}-01"


def calculate_shortfalls(programme):
    """
    Aggregate programme requirement per product, net off live stock,
    return a dict of products with a shortfall.
    """
    warehouse = frappe.db.get_single_value(
        "Crop Nutrition Planning Settings", "fertilizer_warehouse"
    )

    requirements = {}
    for line in programme.get("programme_lines", []):
        product = line.fertilizer_product
        if product not in requirements:
            requirements[product] = {"total_kg": 0, "first_month": line.application_month}
        requirements[product]["total_kg"] += flt(line.total_kg)

    shortfalls = {}
    for product, req in requirements.items():
        stock = get_stock_qty(product, warehouse)
        shortfall = req["total_kg"] - stock
        if shortfall > 0:
            shortfalls[product] = {
                "shortfall_kg": shortfall,
                "first_month": req["first_month"],
            }
    return shortfalls


def create_material_requests_for_programme(programme_name):
    """
    Called when a Fertilizer Programme is submitted.
    Creates one Material Request (Purchase) covering all shortfall products.
    """
    programme = frappe.get_doc("Fertilizer Programme", programme_name)
    shortfalls = calculate_shortfalls(programme)

    if not shortfalls:
        frappe.msgprint("Stock is sufficient — no Material Request needed.", alert=True)
        return None

    items = []
    for product, data in shortfalls.items():
        items.append({
            "item_code": product,
            "qty": round(data["shortfall_kg"], 2),
            "uom": "Kg",
            "schedule_date": month_to_date(data["first_month"]),
            "warehouse": frappe.db.get_single_value(
                "Crop Nutrition Planning Settings", "fertilizer_warehouse"
            ),
        })

    mr = frappe.get_doc({
        "doctype": "Material Request",
        "material_request_type": "Purchase",
        "transaction_date": today(),
        "schedule_date": min(i["schedule_date"] for i in items),
        "custom_fertilizer_programme": programme_name,
        "items": items,
    })
    mr.insert(ignore_permissions=True)

    frappe.msgprint(
        f"Material Request {mr.name} created for {len(items)} product(s) with shortfall.",
        alert=True,
    )
    return mr.name

def is_fertilizer(item_code):
    """Check whether an item is a fertilizer (by item group)."""
    group = frappe.db.get_value("Item", item_code, "item_group")
    return group in ("Fertilizer", "Crop Inputs", "Agrochemicals")


def update_budget_on_receipt(doc, method=None):
    """
    Hook: called when a Purchase Receipt is submitted.
    For each fertilizer line, update the actuals on the most recent
    submitted Fertilizer Budget.
    """
    budgets = frappe.get_all(
        "Fertilizer Budget",
        filters={"docstatus": 1},
        fields=["name"],
        order_by="creation desc",
        limit=1,
    )
    if not budgets:
        return

    budget = frappe.get_doc("Fertilizer Budget", budgets[0].name)

    updated = False
    for item in doc.get("items", []):
        if is_fertilizer(item.item_code):
            budget.update_actuals_from_receipt(
                item_code=item.item_code,
                received_qty=flt(item.qty),
                received_rate=flt(item.rate),
            )
            updated = True

    if updated:
        frappe.msgprint(
            f"Fertilizer Budget {budget.name} updated with received quantities.",
            alert=True,
        )