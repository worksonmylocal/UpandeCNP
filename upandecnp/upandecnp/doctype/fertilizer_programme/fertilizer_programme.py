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

    def on_submit(self):
        self.create_block_fertilizer_plans()
        self.create_material_requests()

    def on_cancel(self):
        self.cancel_block_fertilizer_plans()

    def create_block_fertilizer_plans(self):
        created = 0
        for line in self.get("programme_lines", []):
            # Skip if plan already exists
            if frappe.db.exists("Block Fertilizer Plan", {
                "fertilizer_programme": self.name,
                "block": line.block,
                "fertilizer_product": line.fertilizer_product,
                "application_month": line.application_month,
            }):
                continue

            plan = frappe.get_doc({
                "doctype": "Block Fertilizer Plan",
                "fertilizer_programme": self.name,
                "season": self.season,
                "block": line.block,
                "fertilizer_product": line.fertilizer_product,
                "application_month": line.application_month,
                "yield_tier": line.yield_tier,
                "application_rate_kg_ha": line.kg_per_ha_rate,
                "big_tree_dose_g": line.g_per_big_tree,
                "small_tree_dose_g": line.g_per_small_tree,
                "big_tree_count": self.get_tree_count(line.block, "big"),
                "small_tree_count": self.get_tree_count(line.block, "small"),
                "total_kg_required": line.total_kg,
                "status": "Planned",
            })
            plan.insert(ignore_permissions=True)
            plan.submit()
            created += 1

        frappe.msgprint(f"{created} Block Fertilizer Plans created.", alert=True)

    def create_material_requests(self):
        from upandecnp.upandecnp.utils.integration import create_material_requests_for_programme
        create_material_requests_for_programme(self.name)

    def get_tree_count(self, block_name, size):
        field = "big_tree_count" if size == "big" else "small_tree_count"
        return frappe.db.get_value("Farm Block", block_name, field) or 0

    def cancel_block_fertilizer_plans(self):
        plans = frappe.get_all(
            "Block Fertilizer Plan",
            filters={
                "fertilizer_programme": self.name,
                "docstatus": 1,
            },
            fields=["name"],
        )
        for p in plans:
            doc = frappe.get_doc("Block Fertilizer Plan", p.name)
            doc.cancel()