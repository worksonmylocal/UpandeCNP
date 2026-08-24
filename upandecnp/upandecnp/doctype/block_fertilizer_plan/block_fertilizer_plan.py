# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document

STATUS_PROGRESS = {
	"Planned": 25,
	"Issued": 50,
	"Applied": 75,
	"Verified": 100,
}


class BlockFertilizerPlan(Document):
	def validate(self):
		self.progress = STATUS_PROGRESS.get(self.status, 0)
