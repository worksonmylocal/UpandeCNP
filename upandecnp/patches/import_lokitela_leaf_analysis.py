"""Create Lokitela's per-block leaf analyses from the lab sheet
(fixtures/lokitela_leaf_analysis.json, from LeafAnalysis.ods).

One submitted Leaf Analysis per block for the sheet's season. A block that
already has one for that season is left alone, so this is safe to re-run and
never overwrites a result someone has since amended. Heavy-metal columns that
the lab reported below detection ("<0.02") are not stored.
"""

import json
import os

import frappe


def execute():
	if not frappe.db.exists("DocType", "Leaf Analysis"):
		return
	path = os.path.join(os.path.dirname(__file__), "fixtures", "lokitela_leaf_analysis.json")
	with open(path) as f:
		data = json.load(f)

	season = data["season"]
	created = skipped = 0
	for block, results in data["blocks"].items():
		if not frappe.db.exists("Farm Block", block):
			frappe.log_error(title="Leaf import: unknown block", message=block)
			continue
		if frappe.db.exists("Leaf Analysis", {"block": block, "season": season, "docstatus": ["<", 2]}):
			skipped += 1
			continue
		frappe.get_doc({
			"doctype": "Leaf Analysis",
			"block": block,
			"season": season,
			"sampling_date": data["sampling_date"],
			"laboratory": data["laboratory"],
			"nutrient_results": [
				{"nutrient": n, "result_value": v["value"], "unit": v["unit"]} for n, v in results.items()
			],
		}).insert(ignore_permissions=True).submit()
		created += 1
	frappe.db.commit()
	print(f"Leaf analysis import: {created} created, {skipped} already there.")
