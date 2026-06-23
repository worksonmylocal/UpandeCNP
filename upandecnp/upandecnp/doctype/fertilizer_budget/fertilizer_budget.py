import frappe
from frappe.model.document import Document
from frappe.utils import flt


class FertilizerBudget(Document):

    def validate(self):
        self.calculate_line_totals()
        self.calculate_grand_totals()

    def calculate_line_totals(self):
        for line in self.get("budget_lines", []):
            line.budgeted_total_cost = round(
                flt(line.planned_quantity_kg) * flt(line.budgeted_unit_price), 2
            )
            line.actual_total_cost = round(
                flt(line.actual_quantity_kg) * flt(line.actual_unit_price), 2
            )
            line.volume_variance_kg = round(
                flt(line.actual_quantity_kg) - flt(line.planned_quantity_kg), 2
            )
            line.price_variance_ksh = round(
                flt(line.volume_variance_kg) * flt(line.budgeted_unit_price), 2
            )
            line.total_variance_ksh = round(
                flt(line.actual_total_cost) - flt(line.budgeted_total_cost), 2
            )

    def calculate_grand_totals(self):
        self.total_budget_ksh = round(
            sum(flt(l.budgeted_total_cost) for l in self.get("budget_lines", [])), 2
        )
        self.total_actual_ksh = round(
            sum(flt(l.actual_total_cost) for l in self.get("budget_lines", [])), 2
        )
        self.total_variance_ksh = round(
            self.total_actual_ksh - self.total_budget_ksh, 2
        )

        # Get total area from linked programme
        area = frappe.db.get_value(
            "Fertilizer Programme",
            self.fertilizer_programme,
            "total_area_ha"
        ) or 1

        self.cost_per_ha_budget = round(self.total_budget_ksh / area, 2)
        self.cost_per_ha_actual = round(self.total_actual_ksh / area, 2)