import frappe
from frappe.model.document import Document
from frappe.utils import flt


class FertilizerBudget(Document):

    def get_programme_area(self):
        if not self.fertilizer_programme:
            return 0
        rows = frappe.get_all(
            "Programme Block Yield",
            filters={"parent": self.fertilizer_programme, "parenttype": "Fertilizer Programme"},
            fields=["area_ha"],
        )
        return sum(flt(r.area_ha) for r in rows)

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
        self.total_actual = round(
            sum(flt(l.actual_total_cost) for l in self.get("budget_lines", [])), 2
        )
        self.total_variance_ksh = round(
            self.total_actual - self.total_budget_ksh, 2
        )

        area = self.get_programme_area() or 1

        self.cost_per_ha_budget = round(self.total_budget_ksh / area, 2)
        self.cost_per_ha_actual = round(self.total_actual / area, 2)

    @frappe.whitelist()
    def fetch_from_programme(self):
        """Populate budget lines from the linked Fertilizer Programme."""
        if not self.fertilizer_programme:
            frappe.throw("Please set the Fertilizer Programme first.")

        programme = frappe.get_doc("Fertilizer Programme", self.fertilizer_programme)

        requirements = {}
        for line in programme.get("programme_lines", []):
            product = line.fertilizer_product
            requirements[product] = requirements.get(product, 0) + flt(line.total_kg)

        self.set("budget_lines", [])
        for product, qty in requirements.items():
            price = self.get_item_buying_price(product)
            self.append("budget_lines", {
                "fertilizer_product":  product,
                "planned_quantity_kg": round(qty, 2),
                "budgeted_unit_price": price,
            })

        self.save()
        frappe.msgprint(
            f"Loaded {len(requirements)} products from programme {self.fertilizer_programme}.",
            alert=True,
        )

    def get_item_buying_price(self, item_code):
        price = frappe.db.get_value(
            "Item Price",
            {"item_code": item_code, "buying": 1},
            "price_list_rate",
        )
        return flt(price)

    def update_actuals_from_receipt(self, item_code, received_qty, received_rate):
        """Update a budget line's actuals when fertilizer is received.
        Uses a weighted average price across multiple deliveries."""
        for line in self.get("budget_lines", []):
            if line.fertilizer_product == item_code:
                existing_qty  = flt(line.actual_quantity_kg)
                existing_cost = existing_qty * flt(line.actual_unit_price)
                new_cost      = flt(received_qty) * flt(received_rate)
                total_qty     = existing_qty + flt(received_qty)

                line.actual_quantity_kg = total_qty
                line.actual_unit_price  = (existing_cost + new_cost) / total_qty if total_qty else 0
                line.actual_total_cost  = round(total_qty * flt(line.actual_unit_price), 2)
                line.volume_variance_kg = round(total_qty - flt(line.planned_quantity_kg), 2)
                line.price_variance_ksh = round(flt(line.volume_variance_kg) * flt(line.budgeted_unit_price), 2)
                line.total_variance_ksh = round(flt(line.actual_total_cost) - flt(line.budgeted_total_cost), 2)
                break

        self.total_actual = round(
            sum(flt(l.actual_total_cost) for l in self.get("budget_lines", [])), 2
        )
        self.total_variance_ksh = round(self.total_actual - flt(self.total_budget_ksh), 2)
        area = self.get_programme_area() or 1
        self.cost_per_ha_actual = round(self.total_actual / area, 2)

        self.save(ignore_permissions=True)