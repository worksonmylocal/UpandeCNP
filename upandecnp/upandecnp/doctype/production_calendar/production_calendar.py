# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import flt


class ProductionCalendar(Document):
	def validate(self):
		self.validate_fertilizer_schedule_percentages()

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
