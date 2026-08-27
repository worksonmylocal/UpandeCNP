# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class FieldAttendance(Document):
	def validate(self):
		duplicate = frappe.db.exists("Field Attendance", {
			"employee": self.employee,
			"attendance_date": self.attendance_date,
			"name": ["!=", self.name],
		})
		if duplicate:
			frappe.throw(f"Attendance for {self.employee} on {self.attendance_date} is already recorded ({duplicate}).")
