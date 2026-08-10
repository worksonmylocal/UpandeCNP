# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class Crop(Document):

	def validate(self):
		self.validate_unique_tier_labels()
		self.validate_unique_nutrient_source_groups()

	def validate_unique_tier_labels(self):
		seen = set()
		for row in self.get("yield_tiers", []):
			if row.tier_label in seen:
				frappe.throw(f"Duplicate yield tier label: {row.tier_label}")
			seen.add(row.tier_label)

	def validate_unique_nutrient_source_groups(self):
		# A given nutrient_source_group should only ever supply one nutrient.
		group_nutrient = {}
		for row in self.get("nutrient_rules", []):
			if not row.nutrient_source_group:
				continue
			existing = group_nutrient.get(row.nutrient_source_group)
			if existing and existing != row.nutrient:
				frappe.throw(
					f"Nutrient Source Group '{row.nutrient_source_group}' is used for both "
					f"{existing} and {row.nutrient} — a source group must supply one nutrient."
				)
			group_nutrient[row.nutrient_source_group] = row.nutrient
