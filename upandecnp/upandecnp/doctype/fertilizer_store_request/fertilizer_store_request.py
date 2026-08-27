import frappe
from frappe.model.document import Document
from frappe.utils import flt


class FertilizerStoreRequest(Document):

    def validate(self):
        self.fetch_plan_details()

    def on_update(self):
        # Fire when the workflow moves status to Issued or Rejected
        if self.status == "Issued" and not self.stock_entry:
            self.issue_stock()
        elif self.status == "Rejected" and not self.rejection_reason:
            frappe.throw("Please provide a rejection reason before rejecting.")

    def fetch_plan_details(self):
        if self.block_fertilizer_plan:
            plan = frappe.db.get_value(
                "Block Fertilizer Plan",
                self.block_fertilizer_plan,
                ["block", "fertilizer_product", "application_month", "total_kg_required"],
                as_dict=True,
            )
            if plan:
                self.block = plan.block
                self.fertilizer_product = plan.fertilizer_product
                self.application_month = plan.application_month
                if not self.quantity_requested_kg:
                    self.quantity_requested_kg = flt(plan.total_kg_required)

    def issue_stock(self):
        warehouse = frappe.db.get_value("CNP Farm", self.farm, "warehouse") if self.farm else None

        se = frappe.get_doc({
            "doctype": "Stock Entry",
            "stock_entry_type": "Material Issue",
            "purpose": "Material Issue",
            "remarks": f"Fertilizer Store Request: {self.name} | Block: {self.block}",
            "items": [{
                "item_code": self.fertilizer_product,
                "qty": self.quantity_requested_kg,
                "uom": "Kg",
                "s_warehouse": warehouse,
            }],
        })
        se.insert(ignore_permissions=True)
        se.submit()

        self.db_set("stock_entry", se.name)
        self.db_set("storekeeper", frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name"))

        if self.block_fertilizer_plan:
            frappe.db.set_value("Block Fertilizer Plan", self.block_fertilizer_plan, "status", "Issued")