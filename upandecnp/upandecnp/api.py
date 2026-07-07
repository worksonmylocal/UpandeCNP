"""
Whitelisted API methods for the mobile field page.
These reuse the existing DocType logic so the workflow stays consistent.
"""

import frappe
from frappe.utils import flt


@frappe.whitelist()
def get_blocks_with_pending_work():
    """Return blocks that have at least one Planned or Issued Block Fertilizer Plan."""
    plans = frappe.get_all(
        "Block Fertilizer Plan",
        filters={"docstatus": 1, "status": ["in", ["Planned", "Issued"]]},
        fields=["block"],
        distinct=True,
    )
    blocks = sorted(set(p.block for p in plans))
    return blocks


@frappe.whitelist()
def get_pending_plans_for_block(block):
    """Return the pending fertilizer plans for a block, with any linked request status."""
    plans = frappe.get_all(
        "Block Fertilizer Plan",
        filters={"docstatus": 1, "block": block, "status": ["in", ["Planned", "Issued"]]},
        fields=["name", "fertilizer_product", "application_month",
                "total_kg_required", "status"],
        order_by="application_month",
    )

    for p in plans:
        # Find the most recent store request for this plan
        requests = frappe.get_all(
            "Fertilizer Store Request",
            filters={"block_fertilizer_plan": p["name"]},
            fields=["name", "status"],
            order_by="creation desc",
            limit=1,
        )
        if requests:
            p["request_name"] = requests[0].name
            p["request_status"] = requests[0].status
        else:
            p["request_name"] = None
            p["request_status"] = None

    return plans


@frappe.whitelist()
def create_store_request(block_fertilizer_plan, quantity, employee=None):
    """Create a Fertilizer Store Request from the field page."""
    plan = frappe.get_doc("Block Fertilizer Plan", block_fertilizer_plan)

    if not employee:
        employee = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")

    doc = frappe.get_doc({
        "doctype": "Fertilizer Store Request",
        "block_fertilizer_plan": block_fertilizer_plan,
        "block": plan.block,
        "fertilizer_product": plan.fertilizer_product,
        "application_month": plan.application_month,
        "quantity_requested_kg": flt(quantity),
        "requested_by": employee,
        "request_date": frappe.utils.today(),
        "status": "Requested",
    })
    doc.insert(ignore_permissions=True)
    return {"name": doc.name, "status": "Requested"}


@frappe.whitelist()
def record_application(block_fertilizer_plan, actual_quantity, applied_in_full,
                       partial_reason=None, employee=None, store_request=None):
    """Create a Fertilizer Application from the field page."""
    plan = frappe.get_doc("Block Fertilizer Plan", block_fertilizer_plan)

    if not employee:
        employee = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")

    in_full = 1 if str(applied_in_full) in ("1", "true", "True", "yes") else 0

    if not in_full and not partial_reason:
        frappe.throw("A reason is required when the application is not done in full.")

    doc = frappe.get_doc({
        "doctype": "Fertilizer Application",
        "block_fertilizer_plan": block_fertilizer_plan,
        "store_request": store_request,
        "block": plan.block,
        "fertilizer_product": plan.fertilizer_product,
        "application_date": frappe.utils.today(),
        "planned_quantity_kg": flt(plan.total_kg_required),
        "actual_quantity_applied_kg": flt(actual_quantity),
        "applied_in_full": in_full,
        "partial_reason": partial_reason,
        "applied_by": employee,
    })
    doc.insert(ignore_permissions=True)
    doc.submit()
    return {"name": doc.name, "status": "Applied"}


@frappe.whitelist()
def get_issued_request_for_plan(block_fertilizer_plan):
    """Find an issued store request for this plan, so the app can link to it."""
    sr = frappe.get_all(
        "Fertilizer Store Request",
        filters={"block_fertilizer_plan": block_fertilizer_plan, "status": "Issued"},
        fields=["name"],
        limit=1,
    )
    return sr[0].name if sr else None

@frappe.whitelist(allow_guest=False)
def get_token():
    return frappe.sessions.get_csrf_token()