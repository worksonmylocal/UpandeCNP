"""Builds the downloadable Excel workbook for a Fertilizer Programme.

One sheet, one table per section, one row per block - every product's
amount per tree, month(s) of application and total Kg/Ha side by side, so
the agronomist can hand the whole programme to someone who never opens the
desk.
"""

import re
from io import BytesIO

from frappe.utils import cint, flt
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

MONTH_ORDER = [
	"January", "February", "March", "April", "May", "June",
	"July", "August", "September", "October", "November", "December",
]

SECTION_FILL = PatternFill("solid", fgColor="1F2937")
HEADER_FILL = PatternFill("solid", fgColor="E5E7EB")


def build_programme_workbook(doc):
	"""doc: a Fertilizer Programme Document. Returns the .xlsx bytes."""
	blocks = {
		b.block: {"section": b.section, "area_ha": flt(b.area_ha), "tree_count": cint(b.tree_count)}
		for b in doc.get("block_yield_data", [])
	}

	products = {}
	totals = {}       # (block, product) -> total_kg
	months = {}        # (block, product) -> set of application_month
	dose = {}          # (block, product) -> total dose_per_tree_g
	for line in doc.get("programme_lines", []):
		products[line.fertilizer_product] = line.fertilizer_product_name or line.fertilizer_product
		key = (line.block, line.fertilizer_product)
		totals[key] = totals.get(key, 0) + flt(line.total_kg)
		dose[key] = dose.get(key, 0) + flt(line.dose_per_tree_g)
		months.setdefault(key, set()).add(line.application_month)

	product_list = sorted(products.items(), key=lambda p: p[1])

	sections = {}
	for block, info in blocks.items():
		sections.setdefault(info["section"] or "(No section)", []).append(block)

	wb = Workbook()
	ws = wb.active
	safe_name = re.sub(r"[\\/*?:\[\]]", "-", doc.name or "Programme")
	ws.title = safe_name[:31]

	n_cols = 3 + 3 * len(product_list)
	row = 1

	for section_name in sorted(sections):
		ws.cell(row=row, column=1, value=section_name)
		ws.cell(row=row, column=1).font = Font(bold=True, color="FFFFFF")
		ws.cell(row=row, column=1).fill = SECTION_FILL
		for col in range(2, n_cols + 1):
			ws.cell(row=row, column=col).fill = SECTION_FILL
		row += 1

		product_row, sub_row = row, row + 1
		for col, label in enumerate(("Block", "Area (ha)", "Tree Count"), start=1):
			cell = ws.cell(row=product_row, column=col, value=label)
			cell.font = Font(bold=True)
			cell.fill = HEADER_FILL
			ws.merge_cells(start_row=product_row, start_column=col, end_row=sub_row, end_column=col)

		col = 4
		for code, name in product_list:
			cell = ws.cell(row=product_row, column=col, value=name)
			cell.font = Font(bold=True)
			cell.fill = HEADER_FILL
			cell.alignment = Alignment(horizontal="center")
			ws.merge_cells(start_row=product_row, start_column=col, end_row=product_row, end_column=col + 2)
			for offset, sub_label in enumerate(("Amount/tree (g)", "Month of application", "Total Kg/Ha")):
				sub_cell = ws.cell(row=sub_row, column=col + offset, value=sub_label)
				sub_cell.font = Font(bold=True)
				sub_cell.fill = HEADER_FILL
				sub_cell.alignment = Alignment(wrap_text=True, horizontal="center")
			col += 3
		row = sub_row + 1

		for block in sorted(sections[section_name]):
			info = blocks[block]
			ws.cell(row=row, column=1, value=block)
			ws.cell(row=row, column=2, value=info["area_ha"])
			ws.cell(row=row, column=3, value=info["tree_count"])
			col = 4
			for code, name in product_list:
				key = (block, code)
				applied_months = sorted(months.get(key, []), key=lambda m: MONTH_ORDER.index(m) if m in MONTH_ORDER else 99)
				total_kg_ha = round(totals.get(key, 0) / info["area_ha"], 2) if info["area_ha"] else 0
				ws.cell(row=row, column=col, value=round(dose.get(key, 0), 1))
				ws.cell(row=row, column=col + 1, value=", ".join(applied_months) or "—")
				ws.cell(row=row, column=col + 2, value=total_kg_ha)
				col += 3
			row += 1

		row += 1  # blank row between section tables

	ws.column_dimensions["A"].width = 18
	ws.column_dimensions["B"].width = 10
	ws.column_dimensions["C"].width = 10
	for i in range(len(product_list)):
		base = 4 + i * 3
		ws.column_dimensions[ws.cell(row=1, column=base).column_letter].width = 16
		ws.column_dimensions[ws.cell(row=1, column=base + 1).column_letter].width = 20
		ws.column_dimensions[ws.cell(row=1, column=base + 2).column_letter].width = 14

	buf = BytesIO()
	wb.save(buf)
	return buf.getvalue()
