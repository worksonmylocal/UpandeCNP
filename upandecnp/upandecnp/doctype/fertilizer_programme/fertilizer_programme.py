import frappe
from frappe.model.document import Document
from upandecnp.upandecnp.utils.calculation_engine import calculate_programme_lines


class FertilizerProgramme(Document):

    def validate(self):
        self.calculate_total_area()

    def calculate_total_area(self):
        total = sum(
            flt(row.area_ha)
            for row in self.get("block_yield_data", [])
        )
        self.total_area_ha = round(total, 3)


@frappe.whitelist()
def run_calculation(programme_name):
    programme = frappe.get_doc("Fertilizer Programme", programme_name)

    if programme.docstatus == 1:
        frappe.throw("Cannot recalculate a submitted programme.")

    blocks = [
        {
            "block":           row.block,
            "yield_t_ha":      row.actual_yield_t_ha,
            "leaf_analysis":   row.leaf_analysis,
            "area_ha":         row.area_ha,
            "big_tree_count":  row.big_tree_count,
            "small_tree_count": row.small_tree_count,
        }
        for row in programme.get("block_yield_data", [])
    ]

    lines = calculate_programme_lines(
        blocks, crop=programme.crop or "Hass Avocado"
    )

    programme.set("programme_lines", [])
    for line in lines:
        programme.append("programme_lines", line)

    programme.save()
    return len(lines)