# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class FarmBlock(Document):

	def validate(self):
		self.set_farm_from_section()

	def set_farm_from_section(self):
		if self.section:
			self.farm = frappe.db.get_value("Section", self.section, "farm")
