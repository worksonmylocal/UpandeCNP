"""
Seeds the Hass Avocado crop's calculation constants and leaf-analysis norms for
Lokitela Orchards, as given by the agronomist: yield tiers, per-tonne nutrient
rates/bag composition for CAN/TSP/MOP/K2SO4, and N/P/K leaf norms.

Idempotent - does nothing if the Crop already exists, so re-running (or a second
farm growing the same crop) won't duplicate/overwrite hand-edited master data.
"""

import frappe

CROP_NAME = "Hass Avocado"

YIELD_TIERS = [
	# tier_label, min_yield_kg_ha, max_yield_kg_ha, tier_tonnage
	("15T", None, 15000, 15),
	("18T", 15000, 18000, 18),
	("20T", 18000, 20000, 20),
	("24T", 20000, None, 24),
]

NUTRIENT_RULES = [
	# fertilizer_product, nutrient, rate_per_tonne, bag_weight_kg, product_nutrient_pct,
	# apply_compost_netting, nutrient_source_group
	("CAN", "N", 7.5, 50, 26, 1, None),
	("TSP", "P", 2.5, 50, 20, 0, None),
	("MOP", "K", 10.2, 50, 42, 0, "K"),
	("K2SO4", "K", 10.2, 50, 46, 0, "K"),
]

LEAF_NORMS = [
	# nutrient, low, high
	("N", 2.0, 2.6),
	("P", 0.08, 0.30),
	("K", 0.74, 2.0),
]


def execute():
	"""Called both as a migration patch (existing sites picking up this
	update) and from install.py::after_install (fresh installs - patches
	are skipped entirely on a fresh `install-app`, so this must also be
	reachable outside the patch runner)."""
	if frappe.db.exists("Crop", CROP_NAME):
		return

	# Item records (CAN/TSP/MOP/K2SO4) are operational setup, not shipped with
	# the app - they may not exist yet on a fresh site. Use ignore_links so
	# the full Crop config (all 4 nutrient rules) is created regardless; the
	# Link fields resolve automatically once those Items are created with
	# matching codes.
	crop = frappe.get_doc({
		"doctype": "Crop",
		"crop_name": CROP_NAME,
		"compost_dose_kg": 25,
		"compost_n_pct": 2.5,
		"leaf_adjustment_pct": 10,
		"yield_tiers": [
			{
				"tier_label": label,
				"min_yield_kg_ha": min_y,
				"max_yield_kg_ha": max_y,
				"tier_tonnage": tonnage,
				"sort_order": i,
			}
			for i, (label, min_y, max_y, tonnage) in enumerate(YIELD_TIERS)
		],
		"nutrient_rules": [
			{
				"fertilizer_product": product,
				"nutrient": nutrient,
				"rate_per_tonne": rate,
				"bag_weight_kg": bag_weight,
				"product_nutrient_pct": pct,
				"apply_compost_netting": netting,
				"nutrient_source_group": group,
			}
			for product, nutrient, rate, bag_weight, pct, netting, group in NUTRIENT_RULES
		],
	})
	crop.insert(ignore_permissions=True, ignore_links=True)

	for nutrient, low, high in LEAF_NORMS:
		if frappe.db.exists("Leaf Analysis Norm", {"crop": CROP_NAME, "nutrient": nutrient}):
			continue
		frappe.get_doc({
			"doctype": "Leaf Analysis Norm",
			"crop": CROP_NAME,
			"nutrient": nutrient,
			"low": low,
			"high": high,
			"unit": "%",
		}).insert(ignore_permissions=True)

	frappe.db.commit()

	missing = [p for p in {r[0] for r in NUTRIENT_RULES} if not frappe.db.exists("Item", p)]
	if missing:
		print(
			f"UpandeCNP: Crop '{CROP_NAME}' seeded. Create Item records for {', '.join(sorted(missing))} "
			"(matching these exact codes) before building a Fertilizer Programme - the calculation "
			"engine's product links need them to exist."
		)
