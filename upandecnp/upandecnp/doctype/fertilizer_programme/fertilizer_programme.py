import frappe
from frappe.model.document import Document
from frappe.utils import flt


class FertilizerProgramme(Document):

    def validate(self):
        self.calculate_total_area()

    def calculate_total_area(self):
        total = sum(
            flt(row.area_ha)
            for row in self.get("block_yield_data", [])
        )
        self.total_area_ha = round(total, 3)