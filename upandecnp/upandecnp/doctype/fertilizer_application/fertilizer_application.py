import frappe
from frappe.model.document import Document
from frappe.utils import flt


class FertilizerApplication(Document):

    def validate(self):
        self.calculate_variance()
        self.fetch_planned_quantity()

    def on_submit(self):
        self.create_stock_entry()
        self.update_block_plan_status()

    def on_cancel(self):
        self.cancel_stock_entry()
        self.revert_block_plan_status()

    def fetch_planned_quantity(self):
        if self.block_fertilizer_plan and not self.planned_quantity_kg:
            planned = frappe.db.get_value(
                "Block Fertilizer Plan",
                self.block_fertilizer_plan,
                "total_kg_required"
            )
            self.planned_quantity_kg = flt(planned)

    def calculate_variance(self):
        self.variance_kg = round(
            flt(self.actual_quantity_applied_kg) - flt(self.planned_quantity_kg), 2
        )

    def create_stock_entry(self):
        if self.stock_entry:
            return

        # Get default warehouse from settings or use a fallback
        warehouse = frappe.db.get_single_value(
            "Stock Settings", "default_warehouse"
        ) or "Stores - "

        se = frappe.get_doc({
            "doctype": "Stock Entry",
            "stock_entry_type": "Material Issue",
            "purpose": "Material Issue",
            "remarks": f"Fertilizer Application: {self.name} | Block: {self.block}",
            "items": [{
                "item_code": self.fertilizer_product,
                "qty": self.actual_quantity_applied_kg,
                "uom": "Kg",
                "s_warehouse": warehouse,
            }]
        })
        se.insert(ignore_permissions=True)
        se.submit()
        self.db_set("stock_entry", se.name)

    def update_block_plan_status(self):
        if self.block_fertilizer_plan:
            frappe.db.set_value(
                "Block Fertilizer Plan",
                self.block_fertilizer_plan,
                "status",
                "Applied"
            )

    def cancel_stock_entry(self):
        if self.stock_entry:
            se = frappe.get_doc("Stock Entry", self.stock_entry)
            if se.docstatus == 1:
                se.cancel()

    def revert_block_plan_status(self):
        if self.block_fertilizer_plan:
            frappe.db.set_value(
                "Block Fertilizer Plan",
                self.block_fertilizer_plan,
                "status",
                "Planned"
            )