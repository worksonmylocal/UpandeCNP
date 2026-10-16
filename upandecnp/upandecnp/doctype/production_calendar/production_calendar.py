# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import flt


class ProductionCalendar(Document):
	def validate(self):
		self.validate_fertilizer_schedule_percentages()
		self.validate_potassium_schedule_percentage()

	def validate_fertilizer_schedule_percentages(self):
		totals = {}
		for row in self.get("fertilizer_schedule", []):
			totals.setdefault(row.fertilizer_product, 0)
			totals[row.fertilizer_product] += flt(row.percentage)

		for product, total in totals.items():
			if total - 100 > 0.01:
				frappe.throw(
					f"Fertilizer Schedule: {product} application percentages add up to {total}%, "
					f"which is over 100%. Reduce one or more monthly percentages."
				)
			if 100 - total > 0.01:
				frappe.throw(
					f"Fertilizer Schedule: {product} application percentages add up to {total}%, "
					f"but must total exactly 100%."
				)

	def validate_potassium_schedule_percentage(self):
		"""Unlike Fertilizer Schedule, this one isn't checked per product: a row
		here is a percentage of whichever product it names, not of a shared
		pool, so the invariant is across the whole table - e.g. 40% MOP +
		20% K2SO4 + 40% MOP = 100%, covering the year between them."""
		rows = self.get("potassium_schedule", [])
		if not rows:
			return
		total = sum(flt(row.percentage) for row in rows)
		if total - 100 > 0.01:
			frappe.throw(
				f"Potassium Schedule: the percentages add up to {total}%, which is over 100%. "
				"Reduce one or more rounds."
			)
		if 100 - total > 0.01:
			frappe.throw(
				f"Potassium Schedule: the percentages add up to {total}%, but must total exactly 100%."
			)
