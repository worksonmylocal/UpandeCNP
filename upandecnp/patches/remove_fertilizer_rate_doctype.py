"""Fertilizer Rate is retired in favour of Crop Nutrient Rule (a child table on Crop) -
a single per-tonne rate multiplied by the tier's tonnage, rather than one hand-entered
row per product+tier+season."""

import frappe


def execute():
	if frappe.db.exists("DocType", "Fertilizer Rate"):
		frappe.delete_doc("DocType", "Fertilizer Rate", force=True, ignore_missing=True)
