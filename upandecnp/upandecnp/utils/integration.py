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
    return frappe.db.get_value("CNP Farm", farm, "warehouse") if farm else None


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
    farm_doc = frappe.get_doc("CNP Farm", plan.farm)

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
    advance_to_approval(mr)
    return mr


def advance_to_approval(mr):
    """Move a freshly-inserted Material Request out of Draft into the farm's
    real approval queue (e.g. "Farm Manager to Approve"), using the same
    Workflow ("Item Requisition") the desk approval screens already use for
    every other store-issue category on this site - otherwise it silently
    sits in Draft forever and the field app has no way to show real
    approval progress. The workflow's own transitions are gated by roles
    (Stock User) that field-app supervisors don't hold, so this writes the
    state directly instead of going through frappe.model.workflow.apply_workflow
    - the same "bypass the gate, rely on upandecnp's own scoping" pattern
    used by every other write in this app."""
    from frappe.model.workflow import get_workflow_name, is_transition_condition_satisfied

    workflow_name = get_workflow_name(mr.doctype)
    if not workflow_name:
        return
    workflow = frappe.get_cached_doc("Workflow", workflow_name)
    current_state = mr.get(workflow.workflow_state_field) or workflow.states[0].state

    for transition in workflow.transitions:
        if transition.state != current_state:
            continue
        if "submit" not in (transition.action or "").lower():
            continue
        if is_transition_condition_satisfied(transition, mr):
            frappe.db.set_value(mr.doctype, mr.name, workflow.workflow_state_field, transition.next_state)
            return


def categorize_request_status(state):
    """Collapse the shared, farm-specific "Item Requisition" workflow's many
    state names (e.g. "Request Approved by Lokitela Farm Manager", "Approved
    by Saboti Farm Manager") into the handful of buckets the field app's UI
    actually branches on."""
    if not state or state.lower().endswith("to approve"):
        return "Requested"
    if state.startswith("Rejected"):
        return "Rejected"
    if state.startswith("Approved") or state.startswith("Request Approved"):
        return "Approved"
    return "Requested"


def mark_plan_issued_from_stock_entry(doc, method=None):
    """Stock Entry on_submit hook. When a storekeeper issues stock against a
    Material Request that the field app created (custom_block_fertilizer_plan
    set), and that request has now been fully issued, flip the linked Block
    Fertilizer Plan to Issued - this is the missing link that used to exist
    only for the old Fertilizer Store Request doctype (its issue_stock()
    method set this directly) but was never carried over when store requests
    moved to the standard Material Request + Item Requisition workflow.
    Without this, a fully-approved-and-issued request would never show up as
    ready in the field app's Record Application flow."""
    mr_names = {item.material_request for item in doc.items if item.material_request}
    if not mr_names:
        return

    requests = frappe.get_all(
        "Material Request",
        filters={"name": ["in", list(mr_names)], "custom_block_fertilizer_plan": ["is", "set"]},
        fields=["name", "custom_block_fertilizer_plan"],
    )
    for mr in requests:
        # Stock Entry's own on_submit may run update_completed_qty() before
        # or after this hook depending on hook ordering - read per_ordered
        # fresh from the DB rather than trusting any in-memory value.
        per_ordered = flt(frappe.db.get_value("Material Request", mr.name, "per_ordered"))
        if per_ordered >= 100:
            frappe.db.set_value("Block Fertilizer Plan", mr.custom_block_fertilizer_plan, "status", "Issued")


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

    stock_by_product = {}
    if requirements:
        bin_filters = {"item_code": ["in", list(requirements.keys())]}
        if warehouse:
            bin_filters["warehouse"] = warehouse
        for row in frappe.get_all("Bin", filters=bin_filters, fields=["item_code", "sum(actual_qty) as actual_qty"], group_by="item_code"):
            stock_by_product[row.item_code] = flt(row.actual_qty)

    shortfalls = {}
    for product, req in requirements.items():
        stock = stock_by_product.get(product, 0)
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
    farm_doc = frappe.get_doc("CNP Farm", programme.farm) if programme.farm else None
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
    farm = frappe.db.get_value("CNP Farm", {"warehouse": ["in", list(warehouses)]}, "name") if warehouses else None
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