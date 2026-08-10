# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class LeafAnalysisNorm(Document):

	def validate(self):
		self.validate_unique_crop_nutrient()
		self.set_default_midpoint()

	def validate_unique_crop_nutrient(self):
		existing = frappe.db.exists(
			"Leaf Analysis Norm",
			{"crop": self.crop, "nutrient": self.nutrient, "name": ["!=", self.name]},
		)
		if existing:
			frappe.throw(f"A norm for {self.nutrient} already exists for crop {self.crop}.")

	def set_default_midpoint(self):
		if not self.midpoint:
			self.midpoint = (self.low + self.high) / 2
