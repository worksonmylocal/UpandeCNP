import frappe
from frappe.model.document import Document
from frappe.utils import flt

# Build-up factors based on deficiency severity.
# ratio = result / normal_low
#   >= 0.90 → marginal deficiency → 1.1x
#   >= 0.70 → moderate deficiency → 1.3x
#   <  0.70 → severe deficiency   → 1.6x
BUILD_UP_THRESHOLDS = [
    (0.90, 1.1),
    (0.70, 1.3),
    (0.0,  1.6),
]


class LeafAnalysis(Document):

    def validate(self):
        self.populate_norms_and_status()

    def on_submit(self):
        self.approved_by = frappe.session.user
        self.approval_date = frappe.utils.today()

    def populate_norms_and_status(self):
        # Load norms from master
        norms = {
            n.nutrient: n
            for n in frappe.get_all(
                "Leaf Analysis Norm",
                fields=["nutrient", "low", "high"]
            )
        }

        for row in self.get("nutrient_results", []):
            norm = norms.get(row.nutrient)
            if not norm:
                continue

            # Fill normal ranges if blank
            if not row.normal_range_low:
                row.normal_range_low = norm.low
            if not row.normal_range_high:
                row.normal_range_high = norm.high

            # Calculate status and build-up factor
            if row.result_value is None:
                continue

            if flt(row.result_value) < flt(norm.low):
                row.status = "Deficient"
                ratio = flt(row.result_value) / flt(norm.low) if norm.low else 0
                row.build_up_factor = self.get_buildup(ratio)
            elif flt(row.result_value) > flt(norm.high):
                row.status = "Excess"
                row.build_up_factor = 1.0
            else:
                row.status = "Adequate"
                row.build_up_factor = 1.0

    @staticmethod
    def get_buildup(ratio):
        for threshold, factor in BUILD_UP_THRESHOLDS:
            if ratio >= threshold:
                return factor
        return 1.6