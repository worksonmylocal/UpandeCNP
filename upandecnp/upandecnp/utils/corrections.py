"""Corrections to submitted applications and store requests.

A supervisor cannot edit a submitted record, and should not be able to: the
Application has moved stock and the store request is in somebody's queue. What
they can do is ask. The request carries the new quantity and why; only a
person holding the "CNP Correction Approver" role (Bramuel) can decide it.

Approved, the original is cancelled and a replacement is created in its
place, tagged as corrected and linked back to the request - so the record of
what was first said survives, cancelled, next to what replaced it.

    Application   cancel (stock entry reversed) -> amended copy at the new
                  quantity, submitted (stock re-issued at the new quantity)
    Store request cancel -> a fresh request at the new quantity, which starts
                  its approval again. Only while the store has not issued it.
"""

import frappe
from frappe.utils import cint, flt, now_datetime

from upandecnp.upandecnp.utils.integration import categorize_request_status

APPROVER_ROLE = "CNP Correction Approver"
TYPES = ("Application", "Store Request")


def is_approver(user=None):
	user = user or frappe.session.user
	return user == "Administrator" or APPROVER_ROLE in frappe.get_roles(user)


# ------------------------------------------------------------------ eligibility

def _issued(mr_name):
	"""The store has moved stock against this request."""
	if flt(frappe.db.get_value("Material Request", mr_name, "per_ordered")) > 0:
		return True
	return bool(frappe.db.sql(
		"select 1 from `tabStock Entry Detail` where material_request = %s and docstatus = 1 limit 1",
		mr_name))


def pending_for(doctype, name):
	return frappe.db.get_value("Correction Request",
		{"reference_doctype": doctype, "reference": name, "status": "Pending"}, "name")


def store_request_problem(mr):
	"""Why this store request cannot be corrected, or None."""
	state = categorize_request_status(mr.get("workflow_state") or mr.status)
	if mr.docstatus == 2 or state in ("Cancelled", "Rejected"):
		return f"{mr.name} is {state.lower()}, so there is nothing to correct - raise a new request."
	if _issued(mr.name):
		return (f"The store has already issued {mr.name}. Fertilizer that has left the store can't be "
		        "changed here - ask the stores to adjust it.")
	return None


def application_problem(app):
	if app.docstatus != 1:
		return f"{app.name} is not a submitted application."
	return None


# --------------------------------------------------------------------- request

def create_request(request_type, reference, corrected_quantity, reason, requested_by, employee,
                   client_request_id=None):
	"""Record a supervisor's request. The caller has already checked the
	reference is theirs; this checks it can be corrected at all."""
	if request_type not in TYPES:
		frappe.throw("A correction is for an Application or a Store Request.")
	corrected_quantity = flt(corrected_quantity)
	reason = (reason or "").strip()
	if corrected_quantity <= 0:
		frappe.throw("Enter the correct quantity in kg.")
	if not reason:
		frappe.throw("Say why it needs correcting, so the approver can decide.")

	if request_type == "Application":
		doctype = "Fertilizer Application"
		doc = frappe.get_doc(doctype, reference)
		problem = application_problem(doc)
		original = flt(doc.actual_quantity_applied_kg)
		plan, block, product, farm = doc.block_fertilizer_plan, doc.block, doc.fertilizer_product, doc.farm
	else:
		doctype = "Material Request"
		doc = frappe.get_doc(doctype, reference)
		problem = store_request_problem(doc)
		item = doc.items[0] if doc.items else None
		original = flt(item.qty) if item else 0
		plan = doc.get("custom_block_fertilizer_plan")
		block = frappe.db.get_value("Block Fertilizer Plan", plan, "block") if plan else None
		product = item.item_code if item else None
		farm = doc.get("custom_farm")
	if problem:
		frappe.throw(problem)
	if abs(corrected_quantity - original) < 0.005:
		frappe.throw(f"That is the same as the {original:g} kg already recorded.")
	if pending_for(doctype, reference):
		frappe.throw("There is already a correction waiting on this record.")

	cr = frappe.get_doc({
		"doctype": "Correction Request", "request_type": request_type,
		"reference_doctype": doctype, "reference": reference, "block": block,
		"fertilizer_product": product, "block_fertilizer_plan": plan, "farm": farm,
		"original_quantity": original, "corrected_quantity": corrected_quantity, "reason": reason,
		"requested_by": requested_by,
		"requester_name": frappe.db.get_value("User", requested_by, "full_name") or requested_by,
		"employee": employee, "requested_on": now_datetime(), "status": "Pending",
		"client_request_id": client_request_id,
	})
	cr.insert(ignore_permissions=True)
	return cr


# -------------------------------------------------------------------- decision

def _stamp(cr, status, note):
	cr.status = status
	cr.reviewed_by = frappe.session.user
	cr.reviewed_on = now_datetime()
	cr.review_note = (note or "").strip() or None


def reject(name, note):
	if not (note or "").strip():
		frappe.throw("Give a reason for rejecting, so the supervisor knows why.")
	cr = _open_request(name)
	_stamp(cr, "Rejected", note)
	cr.save(ignore_permissions=True)
	return cr


def approve(name, note=None):
	"""Apply the correction. All or nothing: any failure part-way rolls the
	whole request back, leaving the original untouched and the request pending."""
	cr = _open_request(name)
	if cr.request_type == "Application":
		replacement = _replace_application(cr)
	else:
		replacement = _replace_store_request(cr)
	cr.replaced_by = replacement
	_stamp(cr, "Approved", note)
	cr.save(ignore_permissions=True)
	return cr


def _open_request(name):
	if not is_approver():
		frappe.throw("Only the correction approver can decide this.", frappe.PermissionError)
	cr = frappe.get_doc("Correction Request", name)
	if cr.status != "Pending":
		frappe.throw(f"{name} was already {cr.status.lower()}.")
	return cr


def _replace_application(cr):
	old = frappe.get_doc("Fertilizer Application", cr.reference)
	problem = application_problem(old)
	if problem:
		frappe.throw(problem)
	old.flags.ignore_permissions = True
	old.cancel()

	new = frappe.copy_doc(old)
	new.amended_from = old.name
	new.actual_quantity_applied_kg = flt(cr.corrected_quantity)
	new.stock_entry = None
	new.corrected = 1
	new.correction_request = cr.name
	new.notes = ((old.notes + "\n") if old.notes else "") + f"Corrected from {flt(cr.original_quantity):g} kg: {cr.reason}"
	planned = flt(new.planned_quantity_kg)
	if planned and flt(new.actual_quantity_applied_kg) < planned - max(planned * 0.01, 0.5) and not new.partial_reason:
		new.partial_reason = cr.reason     # a partial round needs a reason; the correction's is the reason
	new.insert(ignore_permissions=True)
	new.submit()
	# Keep it the supervisor's own record, not the approver's.
	frappe.db.set_value("Fertilizer Application", new.name, "owner", old.owner, update_modified=False)
	old.add_comment("Comment", f"Cancelled and replaced by {new.name} after correction {cr.name} "
	                           f"({flt(cr.original_quantity):g} -> {flt(cr.corrected_quantity):g} kg).")
	return new.name


def _replace_store_request(cr):
	old = frappe.get_doc("Material Request", cr.reference)
	problem = store_request_problem(old)
	if problem:
		frappe.throw(problem)
	plan = old.get("custom_block_fertilizer_plan")
	item = old.items[0]
	employee = item.get("employee") or cr.employee

	if old.docstatus == 1:
		old.flags.ignore_permissions = True
		old.cancel()
		frappe.db.set_value("Material Request", old.name, "workflow_state", "Cancelled", update_modified=False)
	else:
		# Still in the approval queue, so it has no submitted state to cancel:
		# mark it cancelled where everyone reads it.
		frappe.db.set_value("Material Request", old.name, {"workflow_state": _cancelled_state(old), "status": "Cancelled"},
		                    update_modified=False)

	from upandecnp.upandecnp.utils.integration import create_material_issue_request
	new = create_material_issue_request(plan, flt(cr.corrected_quantity), employee)
	frappe.db.set_value("Material Request", new.name, {
		"custom_corrected": 1, "custom_corrected_from": old.name, "custom_correction_request": cr.name,
		"owner": old.owner,
	}, update_modified=False)
	old.add_comment("Comment", f"Cancelled and replaced by {new.name} after correction {cr.name} "
	                           f"({flt(cr.original_quantity):g} -> {flt(cr.corrected_quantity):g} kg).")
	return new.name


def _cancelled_state(mr):
	return "Cancelled"
