# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import flt


class LeafAnalysis(Document):
	"""One lab analysis per block per season. A block's own result adjusts that
	block's rate in the programme calculation - there is no sharing between
	blocks, and the yield tier plays no part here (tiers belong to the yield
	calculation, not to what the lab found)."""

	def before_naming(self):
		# The name is built from block and season, so a second analysis for the
		# same pair would collide in the database before validate() ever ran.
		self.validate_one_per_block_per_season()

	def validate(self):
		self.set_from_block()
		self.validate_one_per_block_per_season()
		self.populate_norms_and_status()

	def on_submit(self):
		self.approved_by = frappe.session.user
		self.approval_date = frappe.utils.today()

	def set_from_block(self):
		block = frappe.db.get_value("Farm Block", self.block, ["section", "farm", "crop"], as_dict=True)
		if not block:
			frappe.throw(f"Block {self.block} was not found.")
		self.section = block.section
		self.farm = block.farm
		if not self.crop:
			self.crop = block.crop

	def validate_one_per_block_per_season(self):
		existing = frappe.db.get_value(
			"Leaf Analysis",
			{"block": self.block, "season": self.season, "docstatus": ["<", 2], "name": ["!=", self.name or ""]},
			"name",
		)
		if existing:
			frappe.throw(
				f"{self.block} already has a leaf analysis for {self.season} ({existing}). "
				"There is one per block per season - amend that one instead."
			)

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
