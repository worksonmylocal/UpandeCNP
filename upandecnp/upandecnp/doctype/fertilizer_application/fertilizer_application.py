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
        self.check_variance_alert()

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

    def get_fertilizer_warehouse(self):
        # Prefer the module settings, fall back to Stock Settings default
        warehouse = frappe.db.get_single_value(
            "Crop Nutrition Planning Settings", "fertilizer_warehouse"
        )
        if not warehouse:
            warehouse = frappe.db.get_single_value("Stock Settings", "default_warehouse")
        return warehouse

    def create_stock_entry(self):
        if self.stock_entry:
            return

        warehouse = self.get_fertilizer_warehouse()

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

    def check_variance_alert(self):
        if not self.planned_quantity_kg:
            return

        settings = frappe.get_doc("Crop Nutrition Planning Settings")
        if not settings.farm_manager_email:
            return

        threshold = flt(settings.variance_threshold_pct or 15)
        variance_ratio = abs(flt(self.variance_kg)) / flt(self.planned_quantity_kg) * 100

        if variance_ratio > threshold:
            frappe.sendmail(
                recipients=[settings.farm_manager_email],
                subject=f"Fertilizer Application Variance Alert - {self.block}",
                message=f"""
                <p>Application <b>{self.name}</b> shows a variance above the {threshold}% threshold:</p>
                <ul>
                    <li>Block: {self.block}</li>
                    <li>Product: {self.fertilizer_product}</li>
                    <li>Date: {self.application_date}</li>
                    <li>Planned: {flt(self.planned_quantity_kg):.1f} Kg</li>
                    <li>Actual: {flt(self.actual_quantity_applied_kg):.1f} Kg</li>
                    <li>Variance: {flt(self.variance_kg):.1f} Kg ({variance_ratio:.1f}%)</li>
                </ul>
                """,
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