# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import flt


class LeafAnalysis(Document):

	def validate(self):
		self.set_farm()
		self.populate_norms_and_status()

	def on_submit(self):
		self.approved_by = frappe.session.user
		self.approval_date = frappe.utils.today()

	def set_farm(self):
		if self.section:
			self.farm = frappe.db.get_value("Section", self.section, "farm")
		elif self.block:
			# Section master data isn't populated yet on this site, so fall back
			# to the block -> farm chain the other Farm Block scoped doctypes use.
			self.farm = frappe.db.get_value("Farm Block", self.block, "farm")

	def populate_norms_and_status(self):
		norms = {
			n.nutrient: n
			for n in frappe.get_all(
				"Leaf Analysis Norm",
				filters={"crop": self.crop} if self.crop else {},
				fields=["nutrient", "low", "high"],
			)
		}

		for row in self.get("nutrient_results", []):
			norm = norms.get(row.nutrient)
			if not norm:
				continue

			# Fill normal ranges if blank
			if not row.normal_range_low:
				row.normal_range_low = norm.low
			if not row.normal_range_high:
				row.normal_range_high = norm.high

			if row.result_value is None:
				continue

			if flt(row.result_value) < flt(norm.low):
				row.status = "Deficient"
			elif flt(row.result_value) > flt(norm.high):
				row.status = "Excess"
			else:
				row.status = "Adequate"
