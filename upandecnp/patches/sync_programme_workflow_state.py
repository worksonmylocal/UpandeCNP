"""Backfill workflow_state on programmes submitted while approval was off.

Those were submitted by an inactive Workflow, which does not move the state,
so they carry docstatus 1 with a stored state of Draft (or nothing). The
controller now keeps the two in step on submit; this repairs the ones
already written.
"""

import frappe


def execute():
	if not frappe.db.has_column("Fertilizer Programme", "workflow_state"):
		return
	n = frappe.db.sql("""
		update `tabFertilizer Programme`
		set workflow_state = 'Approved'
		where docstatus = 1 and ifnull(workflow_state, '') in ('', 'Draft')
	""")
	frappe.db.commit()
	print("UpandeCNP: synced workflow_state on submitted programmes")
