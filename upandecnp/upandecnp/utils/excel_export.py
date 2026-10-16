"""Builds the downloadable Excel workbook for a Fertilizer Programme.

Follows the agronomist's own template: one flat table, Section and Block as
the first columns, then every product's own rounds side by side - the
column header is the actual month that round falls in (not "Round 1"), the
cell under it is that round's share of the product's annual total (e.g.
"20%" under "November"), and the next column over is the per-tree gram
dose for that same round.
"""

import re
from io import BytesIO

from frappe.utils import cint, flt
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from upandecnp.upandecnp.utils.rounding import round_half_up

HEADER_FILL = PatternFill("solid", fgColor="E5E7EB")


def build_programme_workbook(doc):
	"""doc: a Fertilizer Programme Document. Returns the .xlsx bytes."""
	blocks = {
		b.block: {"section": b.section, "area_ha": flt(b.area_ha), "tree_count": cint(b.tree_count)}
		for b in doc.get("block_yield_data", [])
	}

	products = {}          # code -> display name
	yield_tier = {}        # block -> yield tier label
	# (block, product) -> [(month, total_kg, dose_per_tree_g), ...], in the
	# order the rounds actually run - the order programme_lines was written
	# in, which already follows the Production Calendar's own row order.
	rounds = {}
	product_months = {}    # product -> months in first-seen (= round) order

	for line in doc.get("programme_lines", []):
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

	product_list = sorted(products.items(), key=lambda p: p[1])

	sections = {}
	for block, info in blocks.items():
		sections.setdefault(info["section"] or "(No section)", []).append(block)

	wb = Workbook()
	ws = wb.active
	safe_name = re.sub(r"[\\/*?:\[\]]", "-", doc.name or "Programme")
	ws.title = safe_name[:31]

	fixed_cols = 5  # Section, Block, Area, No of Trees, Tier
	col_span = {code: 2 * len(product_months.get(code, [])) for code, _ in product_list}
	n_cols = fixed_cols + sum(col_span.values())

	product_row, month_row = 1, 2
	for col, label in enumerate(("Section", "Block", "Area", "No of Trees", "Tier"), start=1):
		cell = ws.cell(row=product_row, column=col, value=label)
		cell.font = Font(bold=True)
		cell.fill = HEADER_FILL
		ws.merge_cells(start_row=product_row, start_column=col, end_row=month_row, end_column=col)

	col = fixed_cols + 1
	for code, name in product_list:
		span = col_span[code]
		if not span:
			continue
		cell = ws.cell(row=product_row, column=col, value=name)
		cell.font = Font(bold=True)
		cell.fill = HEADER_FILL
		cell.alignment = Alignment(horizontal="center")
		ws.merge_cells(start_row=product_row, start_column=col, end_row=product_row, end_column=col + span - 1)
		for month in product_months[code]:
			month_cell = ws.cell(row=month_row, column=col, value=month)
			gtree_cell = ws.cell(row=month_row, column=col + 1, value="G/Tree")
			for c in (month_cell, gtree_cell):
				c.font = Font(bold=True)
				c.fill = HEADER_FILL
				c.alignment = Alignment(horizontal="center")
			col += 2

	row = month_row + 1
	for section_name in sorted(sections):
		section_blocks = sorted(sections[section_name])
		section_start_row = row
		for block in section_blocks:
			info = blocks[block]
			ws.cell(row=row, column=2, value=block)
			ws.cell(row=row, column=3, value=info["area_ha"])
			ws.cell(row=row, column=4, value=info["tree_count"])
			ws.cell(row=row, column=5, value=yield_tier.get(block) or "—")

			col = fixed_cols + 1
			for code, _ in product_list:
				months = product_months.get(code, [])
				if not months:
					continue
				by_month = {m: (total_kg, dose) for m, total_kg, dose in rounds.get((block, code), [])}
				annual_total = sum(total_kg for total_kg, _ in by_month.values())
				for month in months:
					total_kg, dose = by_month.get(month, (0, 0))
					pct = int(round_half_up(total_kg / annual_total * 100)) if annual_total else 0
					# The month itself is the column header above - this cell is
					# that round's share of the product's annual total, e.g.
					# "20%" under the "November" header.
					ws.cell(row=row, column=col, value=f"{pct}%")
					ws.cell(row=row, column=col + 1, value=round(dose, 1))
					col += 2
			row += 1

		ws.cell(row=section_start_row, column=1, value=section_name)
		if row - 1 > section_start_row:
			ws.merge_cells(start_row=section_start_row, start_column=1, end_row=row - 1, end_column=1)
		ws.cell(row=section_start_row, column=1).alignment = Alignment(vertical="top")

	ws.column_dimensions["A"].width = 24
	ws.column_dimensions["B"].width = 16
	ws.column_dimensions["C"].width = 10
	ws.column_dimensions["D"].width = 12
	ws.column_dimensions["E"].width = 10
	col = fixed_cols + 1
	for code, _ in product_list:
		for _ in product_months.get(code, []):
			ws.column_dimensions[get_column_letter(col)].width = 16
			ws.column_dimensions[get_column_letter(col + 1)].width = 10
			col += 2

	buf = BytesIO()
	wb.save(buf)
	return buf.getvalue()
