"""Leaf Analysis moves from one-per-(section, yield tier) to one-per-block-per-season.

The old records describe a section and tier, not a block, so there is nothing to
convert them into: they are removed, and the per-block results are entered (or
imported) fresh. Yield tiers elsewhere are untouched - they drive the
yield-based calculation, not the lab results.
"""

import frappe


def execute():
	if not frappe.db.exists("DocType", "Leaf Analysis"):
		return
	for row in frappe.get_all("Leaf Analysis", fields=["name", "docstatus"]):
		doc = frappe.get_doc("Leaf Analysis", row.name)
		if doc.docstatus == 1:
			doc.flags.ignore_permissions = True
			doc.cancel()
	frappe.db.delete("Leaf Analysis Nutrient Result")
	frappe.db.delete("Leaf Analysis")
	if frappe.db.has_column("Leaf Analysis", "yield_tier"):
		frappe.db.sql_ddl("alter table `tabLeaf Analysis` drop column `yield_tier`")
