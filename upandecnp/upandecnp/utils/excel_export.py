"""Builds the downloadable Excel workbook for a Fertilizer Programme.

Follows the agronomist's own template: one flat table, Section and Block as
the first columns, then every product's own figures side by side - a Kg/Ha
for the tier the block sits in and a Kg/Ha for the block itself (these match
once nobody has hand-rounded anything in Edit Programme, and diverge exactly
where they have), then one column pair per actual round, headed by the
month it falls in (not "Round 1"), with that round's share of the product's
annual total underneath the month (e.g. "20%" under "November") and the
per-tree gram dose next to it. A product with no real application anywhere
in the programme (nothing but 0% rounds) is left out entirely.
"""

import re
from collections import Counter
from io import BytesIO

from frappe.utils import cint, flt
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from upandecnp.upandecnp.utils.rounding import round_half_up

HEADER_FILL = PatternFill("solid", fgColor="E5E7EB")
CENTER = Alignment(horizontal="center", vertical="center")


def build_programme_workbook(doc, section=None):
	"""doc: a Fertilizer Programme Document. section: when given, only that
	section's blocks are included - everything else (which products get
	columns, each one's Tier Kg/Ha, the round months) is then worked out
	from just that subset, same as a full export would for the whole farm.
	Returns the .xlsx bytes."""
	blocks = {
		b.block: {"section": b.section, "area_ha": flt(b.area_ha), "tree_count": cint(b.tree_count)}
		for b in doc.get("block_yield_data", [])
		if not section or b.section == section
	}

	products = {}          # code -> display name
	yield_tier = {}        # block -> yield tier label
	# (block, product) -> [(month, total_kg, dose_per_tree_g), ...], in the
	# order the rounds actually run - the order programme_lines was written
	# in, which already follows the Production Calendar's own row order.
	rounds = {}
	product_months = {}    # product -> months in first-seen (= round) order

	for line in doc.get("programme_lines", []):
		if line.block not in blocks:
			continue
		code = line.fertilizer_product
		products[code] = line.fertilizer_product_name or code
		yield_tier.setdefault(line.block, line.yield_tier)

		key = (line.block, code)
		rounds.setdefault(key, []).append(
			(line.application_month, flt(line.total_kg), flt(line.dose_per_tree_g))
		)

		seen = product_months.setdefault(code, [])
		if line.application_month not in seen:
			seen.append(line.application_month)

	def block_total(block, code):
		return sum(total_kg for _, total_kg, _ in rounds.get((block, code), []))

	def block_kg_ha(block, code):
		area = blocks.get(block, {}).get("area_ha") or 0
		return round(block_total(block, code) / area, 2) if area else 0

	# A product with nothing but 0% rounds everywhere isn't actually being
	# applied this programme - no point giving it columns.
	product_list = [
		(code, name) for code, name in sorted(products.items(), key=lambda p: p[1])
		if sum(block_total(b, code) for b in blocks) > 0
	]

	# Tier Kg/Ha is the rate most of a tier's blocks actually carry - the
	# mode, not an average, so one hand-rounded outlier block doesn't drag
	# the "tier" figure away from what every other block in it still is. A
	# tier is a yield classification, not a per-section thing - 15T in one
	# section is the same tier as 15T in another - so this is farm-wide,
	# matching how Edit Programme's Round Tier applies.
	tier_kg_ha = {}
	for code, _ in product_list:
		by_tier = {}
		for block in blocks:
			tier = yield_tier.get(block)
			if not tier:
				continue
			by_tier.setdefault(tier, []).append(block_kg_ha(block, code))
		for tier, values in by_tier.items():
			tier_kg_ha[(tier, code)] = Counter(values).most_common(1)[0][0]

	sections = {}
	for block, info in blocks.items():
		sections.setdefault(info["section"] or "(No section)", []).append(block)

	wb = Workbook()
	ws = wb.active
	safe_name = re.sub(r"[\\/*?:\[\]]", "-", doc.name or "Programme")
	ws.title = safe_name[:31]

	fixed_cols = 5  # Section, Block, Area, No of Trees, Tier
	# 2 columns for Tier/Block Kg/Ha, then 2 per actual round.
	col_span = {code: 2 + 2 * len(product_months.get(code, [])) for code, _ in product_list}

	product_row, sub_row = 1, 2
	for col, label in enumerate(("Section", "Block", "Area", "No of Trees", "Tier"), start=1):
		cell = ws.cell(row=product_row, column=col, value=label)
		cell.font = Font(bold=True)
		cell.fill = HEADER_FILL
		cell.alignment = CENTER
		ws.merge_cells(start_row=product_row, start_column=col, end_row=sub_row, end_column=col)

	col = fixed_cols + 1
	for code, name in product_list:
		span = col_span[code]
		cell = ws.cell(row=product_row, column=col, value=name)
		cell.font = Font(bold=True)
		cell.fill = HEADER_FILL
		cell.alignment = CENTER
		ws.merge_cells(start_row=product_row, start_column=col, end_row=product_row, end_column=col + span - 1)

		for offset, label in enumerate(("Kg/Ha (Tier)", "Kg/Ha (Block)")):
			c = ws.cell(row=sub_row, column=col + offset, value=label)
			c.font = Font(bold=True)
			c.fill = HEADER_FILL
			c.alignment = CENTER
		col += 2

		for month in product_months[code]:
			month_cell = ws.cell(row=sub_row, column=col, value=month)
			gtree_cell = ws.cell(row=sub_row, column=col + 1, value="G/Tree")
			for c in (month_cell, gtree_cell):
				c.font = Font(bold=True)
				c.fill = HEADER_FILL
				c.alignment = CENTER
			col += 2

	row = sub_row + 1
	for section_name in sorted(sections):
		section_blocks = sorted(sections[section_name])
		section_start_row = row
		for block in section_blocks:
			info = blocks[block]
			tier = yield_tier.get(block)
			for c, value in ((2, block), (3, info["area_ha"]), (4, info["tree_count"]), (5, tier or "—")):
				cell = ws.cell(row=row, column=c, value=value)
				cell.alignment = CENTER

			col = fixed_cols + 1
			for code, _ in product_list:
				this_block_kg_ha = block_kg_ha(block, code)
				this_tier_kg_ha = tier_kg_ha.get((tier, code), this_block_kg_ha)
				for value in (this_tier_kg_ha, this_block_kg_ha):
					ws.cell(row=row, column=col, value=value).alignment = CENTER
					col += 1

				by_month = {m: (total_kg, dose) for m, total_kg, dose in rounds.get((block, code), [])}
				annual_total = sum(total_kg for total_kg, _ in by_month.values())
				for month in product_months[code]:
					total_kg, dose = by_month.get(month, (0, 0))
					pct = int(round_half_up(total_kg / annual_total * 100)) if annual_total else 0
					# The month itself is the column header above - this cell is
					# that round's share of the product's annual total, e.g.
					# "20%" under the "November" header.
					ws.cell(row=row, column=col, value=f"{pct}%").alignment = CENTER
					ws.cell(row=row, column=col + 1, value=round(dose, 1)).alignment = CENTER
					col += 2
			row += 1

		ws.cell(row=section_start_row, column=1, value=section_name).alignment = CENTER
		if row - 1 > section_start_row:
			ws.merge_cells(start_row=section_start_row, start_column=1, end_row=row - 1, end_column=1)

	ws.column_dimensions["A"].width = 24
	ws.column_dimensions["B"].width = 16
	ws.column_dimensions["C"].width = 10
	ws.column_dimensions["D"].width = 12
	ws.column_dimensions["E"].width = 10
	col = fixed_cols + 1
	for code, _ in product_list:
		ws.column_dimensions[get_column_letter(col)].width = 13
		ws.column_dimensions[get_column_letter(col + 1)].width = 13
		col += 2
		for _ in product_months.get(code, []):
			ws.column_dimensions[get_column_letter(col)].width = 16
			ws.column_dimensions[get_column_letter(col + 1)].width = 10
			col += 2

	buf = BytesIO()
	wb.save(buf)
	return buf.getvalue()
