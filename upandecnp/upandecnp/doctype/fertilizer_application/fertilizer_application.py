import frappe
from frappe.model.document import Document
from frappe.utils import flt


class FertilizerApplication(Document):

    def validate(self):
        self.calculate_variance()
        self.fetch_planned_quantity()
        self.validate_partial_reason()

    def on_submit(self):
        self.create_stock_entry()
        self.update_block_plan_status()
        self.check_variance_alert()

    def on_cancel(self):
        self.cancel_stock_entry()
        self.revert_block_plan_status()

    def validate_partial_reason(self):
        if not self.applied_in_full and not self.partial_reason:
            frappe.throw("Please give a reason why the application was not done in full.")

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
        warehouse = frappe.db.get_value("CNP Farm", self.farm, "warehouse") if self.farm else None
        if not warehouse:
            warehouse = frappe.db.get_single_value("Stock Settings", "default_warehouse")
        return warehouse

    def create_stock_entry(self):
        # If the store already issued stock via the Store Request, reuse it - don't double-issue
        if self.store_request:
            issued = frappe.db.get_value("Fertilizer Store Request", self.store_request, "stock_entry")
            if issued:
                self.db_set("stock_entry", issued)
                return

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

        farm_manager = frappe.db.get_value("CNP Farm", self.farm, "farm_manager") if self.farm else None
        if not farm_manager:
            return
        recipient = frappe.db.get_value("User", farm_manager, "email") or farm_manager

        settings = frappe.get_doc("Crop Nutrition Planning Settings")
        threshold = flt(settings.variance_threshold_pct or 15)
        variance_ratio = abs(flt(self.variance_kg)) / flt(self.planned_quantity_kg) * 100

        if variance_ratio > threshold:
            try:
                frappe.sendmail(
                    recipients=[recipient],
                    subject=f"Fertilizer Application Variance Alert - {self.block}",
                    message=f"""
                    <p>Application <b>{self.name}</b> shows a variance above the {threshold}% threshold:</p>
                    <ul>
                        <li>Block: {self.block}</li>
                        <li>Product: {self.fertilizer_product}</li>
                        <li>Date: {self.application_date}</li>
                        <li>Planned: {flt(self.planned_quantity_kg):.1f} Kg</li>
                        <li>Actual: {flt(self.actual_quantity_applied_kg):.1f} Kg</li>
                        <li>Applied in full: {"Yes" if self.applied_in_full else "No"}</li>
                        <li>Variance: {flt(self.variance_kg):.1f} Kg ({variance_ratio:.1f}%)</li>
                    </ul>
                    """,
                )
            except Exception:
                frappe.log_error(f"Variance alert email failed for {self.name}", "CNP Variance Alert")

    def cancel_stock_entry(self):
        # Only cancel if this application created its own stock entry (not the store request's)
        if self.stock_entry and not self.store_request:
            se = frappe.get_doc("Stock Entry", self.stock_entry)
            if se.docstatus == 1:
                se.cancel()

    def revert_block_plan_status(self):
        if self.block_fertilizer_plan:
            frappe.db.set_value(
                "Block Fertilizer Plan",
                self.block_fertilizer_plan,
                "status",
                "Issued"
            )