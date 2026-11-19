"""Micro-element programmes (Borax first).

A micro-element is planned the way the agronomist's own sheet does it: type
one rate in kg per hectare, and everything else follows from the standard
planting density.

    kg per tree   = rate / trees per ha              (20 / 250 = 0.080)
    block kg      = block's tree count x kg per tree (534 x 0.080 = 42.72 -> 42.7)

The tree count is the block's real one, not area x 250 - the sheet's "Big
Trees" column is the count on the Farm Block, which is why a 2.14 ha block
carries 534 trees rather than 535. Quantities are rounded to 1 decimal and
the per-tree figure to 3, exactly as the sheet shows them.

A micro programme is an ordinary Fertilizer Programme with
programme_type = "Micro", so submitting it creates the same Block Fertilizer
Plans, store requests and recorded applications as any other - which is what
puts it in front of the field app without a second pipeline to maintain.
"""

import frappe
from frappe.utils import cint, flt

from upandecnp.upandecnp.utils.rounding import round_half_up

DEFAULT_TREES_PER_HA = 250
MICRO_NUTRIENTS = ("B", "Mn", "Zn", "Mo")


def kg_per_tree(rate_kg_ha, trees_per_ha=DEFAULT_TREES_PER_HA):
	return round_half_up(flt(rate_kg_ha) / flt(trees_per_ha), 3) if flt(trees_per_ha) else 0


def block_kg(trees, rate_kg_ha, trees_per_ha=DEFAULT_TREES_PER_HA):
	"""Kilograms for one block, rounded the way the sheet rounds it."""
	if not flt(trees_per_ha):
		return 0
	return round_half_up(cint(trees) * flt(rate_kg_ha) / flt(trees_per_ha), 1)


def trees_for(row, trees_per_ha=DEFAULT_TREES_PER_HA):
	"""The block's own tree count; area x density only when none is recorded."""
	return cint(row.tree_count) or int(round(flt(row.area_ha) * flt(trees_per_ha)))


def calculate_micro_programme(programme):
	"""Fill programme_lines from the blocks already pulled onto the programme."""
	from upandecnp.upandecnp.utils.calculation_engine import update_product_requirements

	doc = programme if not isinstance(programme, str) else frappe.get_doc("Fertilizer Programme", programme)
	if doc.docstatus == 1:
		frappe.throw("Cannot recalculate a submitted programme.")
	if doc.get("programme_type") != "Micro":
		frappe.throw("This is not a micro-element programme.")

	if flt(doc.micro_rate_kg_ha) <= 0:
		frappe.throw("Enter the rate in kg/ha first.")
	tph = cint(doc.trees_per_ha) or DEFAULT_TREES_PER_HA
	if not doc.micro_month:
		frappe.throw("Choose the application month first.")
	if not doc.get("block_yield_data"):
		frappe.throw("Pull the blocks first - there is nothing to calculate yet.")

	selection = next((r for r in doc.get("product_selections", []) if r.product), None)
	if not selection:
		frappe.throw("Load the product first.")
	if not selection.fertilizer_item:
		frappe.throw(f"Choose an Item for <b>{selection.product}</b> before calculating.")

	dose_g = round_half_up(kg_per_tree(doc.micro_rate_kg_ha, tph) * 1000, 1)
	lines = []
	for row in doc.get("block_yield_data"):
		trees = trees_for(row, tph)
		kg = block_kg(trees, doc.micro_rate_kg_ha, tph)
		if kg <= 0:
			continue
		lines.append({
			"block": row.block,
			"section": row.section,
			"fertilizer_product": selection.fertilizer_item,
			"application_month": doc.micro_month,
			"kg_per_ha_rate": flt(doc.micro_rate_kg_ha),
			"dose_per_tree_g": dose_g,
			"total_kg": kg,
		})
	if not lines:
		frappe.throw("None of the blocks in scope have any trees, so there is nothing to apply.")

	doc.set("programme_lines", [])
	for line in lines:
		doc.append("programme_lines", line)
	update_product_requirements(doc, lines)
	doc.save()
	return len(lines)


def sheet_rows(doc):
	"""The programme as the sheet lays it out: one dict per block, plus totals."""
	tph = cint(doc.trees_per_ha) or DEFAULT_TREES_PER_HA
	rate = flt(doc.micro_rate_kg_ha)
	per_tree = kg_per_tree(rate, tph)
	kg_by_block = {}
	for l in doc.get("programme_lines", []):
		kg_by_block[l.block] = kg_by_block.get(l.block, 0) + flt(l.total_kg)

	rows = []
	for b in doc.get("block_yield_data", []):
		trees = trees_for(b, tph)
		rows.append({
			"section": b.section, "block": b.block, "area_ha": flt(b.area_ha),
			"rate_kg_ha": rate, "trees": trees, "kg_per_tree": per_tree,
			"kg": kg_by_block.get(b.block, block_kg(trees, rate, tph)),
		})
	rows.sort(key=lambda r: (r["section"] or "", r["block"] or ""))
	totals = {
		"area_ha": round_half_up(sum(r["area_ha"] for r in rows), 2),
		"trees": sum(r["trees"] for r in rows),
		"kg": round_half_up(sum(r["kg"] for r in rows), 1),
		# The sheet's header box is area x rate, which differs from the
		# table's tree-based total by a fraction of a kilogram.
		"kg_by_area": round_half_up(sum(r["area_ha"] for r in rows) * rate, 1),
	}
	return rows, totals
