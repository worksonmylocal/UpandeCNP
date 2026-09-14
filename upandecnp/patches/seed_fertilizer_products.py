"""Seed the Fertilizer Product master data and point the crop's nutrient
rules at it.

The site keeps several Items for the same real-world product, spelled
inconsistently and with the stock sitting on only one of them - e.g.
"POTASIUM SULPHATE" holds 30t while "POTASSIUM SULPHATE" holds 7.5t, and
"MOP" holds 630kg while "MURATE OF POTASIUM (MOP)" holds 66kg. Which Item a
programme should draw from is therefore a per-season decision, not a fixed
property of the crop. This seeds the groups that decision is made within.

Search terms are matched against both item code and item name, so every
observed spelling variant is listed rather than one canonical one.
"""

import frappe

PRODUCTS = [
	{
		"product_code": "CAN",
		"product_name": "Calcium Ammonium Nitrate",
		"nutrient": "N",
		"search_terms": "CAN",
	},
	{
		"product_code": "MOP",
		"product_name": "Muriate of Potash",
		"nutrient": "K",
		"search_terms": "MOP\nMURATE\nMURIATE",
	},
	{
		"product_code": "K2SO4",
		"product_name": "Potassium Sulphate",
		"nutrient": "K",
		# Both spellings are live on this site and hold different stock.
		"search_terms": "K2SO4\nPOTASSIUM SULPHATE\nPOTASIUM SULPHATE",
	},
	{
		"product_code": "TSP",
		"product_name": "Triple Superphosphate",
		"nutrient": "P",
		"search_terms": "TSP\nSUPERPHOSPHATE",
	},
]

# Existing rules name an Item directly; map each to the product it belongs to
# so calculations keep working and the new selection UI has something to show.
ITEM_TO_PRODUCT = {
	"1010100032": "CAN",           # CAN
	"20100100014": "MOP",          # MOP
	"10070010004": "MOP",          # MURATE OF POTASIUM (MOP)
	"10070010005": "K2SO4",        # POTASIUM SULPHATE
	"1010100015": "K2SO4",         # POTASSIUM SULPHATE
	"10070010007": "TSP",          # TRIPPLE SUPERPHOSPHATE (TSP)
	"20100100017": "TSP",          # TSP
}


def execute():
	if not frappe.db.exists("DocType", "Fertilizer Product"):
		return

	for spec in PRODUCTS:
		if frappe.db.exists("Fertilizer Product", spec["product_code"]):
			continue
		doc = frappe.new_doc("Fertilizer Product")
		doc.update(spec)
		doc.item_group = "Fertilizer"
		doc.insert(ignore_permissions=True)
		print(f"UpandeCNP: created Fertilizer Product {spec['product_code']}")

	# Backfill the link on existing nutrient rules, leaving any already set.
	for row in frappe.get_all(
		"Crop Nutrient Rule", fields=["name", "fertilizer_product", "product"]
	):
		if row.product or not row.fertilizer_product:
			continue
		product = ITEM_TO_PRODUCT.get(row.fertilizer_product)
		if product and frappe.db.exists("Fertilizer Product", product):
			frappe.db.set_value("Crop Nutrient Rule", row.name, "product", product,
			                    update_modified=False)
			print(f"UpandeCNP: nutrient rule {row.name} -> {product}")

	backfill_application_year()

	frappe.db.commit()


def backfill_application_year():
	"""Plans created before this field existed carry 0. push_application()
	falls back to the season year when it sees that, so nothing breaks - but
	an untrustworthy column is worth fixing once rather than reasoning about
	at every read."""
	rows = frappe.get_all(
		"Block Fertilizer Plan", filters={"application_year": ["in", [0, None]]},
		fields=["name", "season"],
	)
	if not rows:
		return
	import re
	for row in rows:
		match = re.search(r"(\d{4})", row.season or "")
		if match:
			frappe.db.set_value("Block Fertilizer Plan", row.name, "application_year",
			                    int(match.group(1)), update_modified=False)
	print(f"UpandeCNP: backfilled application_year on {len(rows)} block plans")
