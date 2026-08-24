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


def get_farm_warehouse(farm):
    return frappe.db.get_value("Farm", farm, "warehouse") if farm else None


def get_business_unit_for_farm(farm_doc):
    """Business Unit isn't linked to Farm in the schema - match on the farm
    name appearing in the business unit label, scoped to the same company.
    Returns None (left for the approver to fill in) when nothing matches
    rather than guessing."""
    return frappe.db.get_value(
        "Business Unit",
        {"company": farm_doc.company, "business_unit": ["like", f"%{farm_doc.name}%"]},
        "name",
    )


def create_material_issue_request(block_fertilizer_plan, quantity, employee=None):
    """
    Create a Material Request (type Material Issue) for fertilizer pulled from
    a farm's store, in the same shape used for every other store-issue category
    on this site (Fuel Issuing, Chemical Issuing, etc.) - so it goes through the
    same farm-manager approval workflow instead of a bespoke one.
    """
    plan = frappe.get_doc("Block Fertilizer Plan", block_fertilizer_plan)
    farm_doc = frappe.get_doc("Farm", plan.farm)

    if not farm_doc.warehouse:
        frappe.throw(
            f"Farm {farm_doc.name} has no Fertilizer Store warehouse configured "
            f"(Farm.warehouse) - set it before issuing fertilizer from store."
        )

    item_name = frappe.db.get_value("Item", plan.fertilizer_product, "item_name") or plan.fertilizer_product
    cost_center = frappe.db.get_value("Farm Block", plan.block, "cost_center") if plan.block else None

    mr = frappe.get_doc({
        "doctype": "Material Request",
        "material_request_type": "Material Issue",
        "title": f"Material Issue Request for {item_name}",
        "transaction_date": today(),
        "schedule_date": today(),
        "company": farm_doc.company,
        "set_warehouse": farm_doc.warehouse,
        "custom_farm": farm_doc.name,
        "custom_business_unit": get_business_unit_for_farm(farm_doc),
        "custom_request_type": "Fertiliser Issuing",
        "custom_fertilizer_programme": plan.fertilizer_programme,
        "custom_block_fertilizer_plan": plan.name,
        "custom_employee": employee,
        "custom_employee_name": frappe.db.get_value("Employee", employee, "employee_name") if employee else None,
        "items": [{
            "item_code": plan.fertilizer_product,
            "qty": flt(quantity),
            "uom": "Kg",
            "warehouse": farm_doc.warehouse,
            "schedule_date": today(),
            "custom_purpose": f"Fertilizer issued for application - {plan.block} ({plan.application_month})",
            "cost_center": cost_center,
        }],
    })
    mr.insert(ignore_permissions=True)
    return mr


def calculate_shortfalls(programme):
    """
    Aggregate programme requirement per product, net off live stock,
    return a dict of products with a shortfall.
    """
    warehouse = get_farm_warehouse(programme.farm)

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

    warehouse = get_farm_warehouse(programme.farm)
    farm_doc = frappe.get_doc("Farm", programme.farm) if programme.farm else None
    items = []
    for product, data in shortfalls.items():
        items.append({
            "item_code": product,
            "qty": round(data["shortfall_kg"], 2),
            "uom": "Kg",
            "schedule_date": month_to_date(data["first_month"]),
            "warehouse": warehouse,
            "custom_purpose": f"Fertilizer shortfall purchase for {programme_name}",
        })

    mr = frappe.get_doc({
        "doctype": "Material Request",
        "material_request_type": "Purchase",
        "transaction_date": today(),
        "schedule_date": min(i["schedule_date"] for i in items),
        "company": farm_doc.company if farm_doc else None,
        "custom_farm": farm_doc.name if farm_doc else None,
        "custom_business_unit": get_business_unit_for_farm(farm_doc) if farm_doc else None,
        "custom_request_type": "Fertiliser Issuing",
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
    Resolves the receiving warehouse back to a Farm, then updates the actuals
    on that farm's most recent submitted Fertilizer Budget - a receipt for
    one farm's warehouse must never update another farm's budget.
    """
    fertilizer_items = [item for item in doc.get("items", []) if is_fertilizer(item.item_code)]
    if not fertilizer_items:
        return

    warehouses = {item.warehouse for item in fertilizer_items if item.warehouse}
    farm = frappe.db.get_value("Farm", {"warehouse": ["in", list(warehouses)]}, "name") if warehouses else None
    if not farm:
        return

    budgets = frappe.get_all(
        "Fertilizer Budget",
        filters={"docstatus": 1, "farm": farm},
        fields=["name"],
        order_by="creation desc",
        limit=1,
    )
    if not budgets:
        return

    budget = frappe.get_doc("Fertilizer Budget", budgets[0].name)

    for item in fertilizer_items:
        budget.update_actuals_from_receipt(
            item_code=item.item_code,
            received_qty=flt(item.qty),
            received_rate=flt(item.rate),
        )

    frappe.msgprint(
        f"Fertilizer Budget {budget.name} updated with received quantities.",
        alert=True,
    )