"""Seed the micro-element Fertilizer Products (Borax first).

The site has several Items that mention boron - BORAX, "Boron", and
compound products like "Microsol with Boron" and "Lithovit Boron" - so the
search terms pick out the plain borates and leave the blends to be excluded.
"""

import frappe

MICRO_PRODUCTS = [
	{
		"product_code": "BORAX",
		"product_name": "Borax",
		"nutrient": "B",
		"search_terms": "BORAX\nBORON",
		"exclude_terms": "MICROSOL\nLITHOVIT",
	},
]


def execute():
	if not frappe.db.exists("DocType", "Fertilizer Product"):
		return
	for p in MICRO_PRODUCTS:
		if frappe.db.exists("Fertilizer Product", p["product_code"]):
			continue
		frappe.get_doc({"doctype": "Fertilizer Product", "item_group": "Fertilizer", **p}).insert(
			ignore_permissions=True
		)
