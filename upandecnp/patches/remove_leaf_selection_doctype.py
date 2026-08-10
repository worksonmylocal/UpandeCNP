"""Fertilizer Programme Leaf Selection is retired - Leaf Analysis is now keyed
directly by (Section, Yield Tier), so the engine looks it up automatically
instead of the agronomist manually picking a representative sample."""

import frappe


def execute():
	if frappe.db.exists("DocType", "Fertilizer Programme Leaf Selection"):
		frappe.delete_doc("DocType", "Fertilizer Programme Leaf Selection", force=True, ignore_missing=True)
