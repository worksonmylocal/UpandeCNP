import frappe
from frappe.utils import flt, cint

YIELD_TIERS = [
    (22.0, "24T"),
    (19.0, "20T"),
    (16.0, "18T"),
    (0.0,  "15T"),
]

APPLICATION_SCHEDULE = {
    "CAN":           [("November", 0.20), ("January", 0.40), ("March", 0.40)],
    "MOP":           [("November", 0.20), ("March", 0.40)],
    "K2SO4":         [("January", 0.40)],
    "TSP":           [("May", 1.00)],
    "Gypsum":        [("December", 1.00)],
    "Ag Lime":       [("April", 1.00)],
    "Zinc Sulphate": [("November", 0.50), ("March", 0.50)],
    "Borax":         [("November", 0.25), ("December", 0.25), ("March", 0.25), ("June", 0.25)],
}

ROUNDING_BASE = {
    "CAN":            25,
    "MOP":            25,
    "K2SO4":          25,
    "TSP":            25,
    "Gypsum":        100,
    "Ag Lime":       100,
    "Zinc Sulphate":   5,
    "Borax":           5,
}

# Fixed planting density used for g/tree calculation
PLANTS_PER_HA = 250

# Small tree dose is always 25% of big tree dose
SMALL_TREE_RATIO = 0.25

PRODUCT_NUTRIENT_MAP = {
    "CAN":           "N",
    "MOP":           "K",
    "K2SO4":         "K",
    "TSP":           "P",
    "Gypsum":        "Ca",
    "Ag Lime":       "Ca",
    "Zinc Sulphate": "Zn",
    "Borax":         "B",
}


def get_yield_tier(yield_t_ha):
    for threshold, tier in YIELD_TIERS:
        if flt(yield_t_ha) >= threshold:
            return tier
    return "15T"


def round_to_base(value, base):
    if not base:
        return value
    return round(value / base) * base


def get_fertilizer_rates(crop, season):
    rows = frappe.get_all(
        "Fertilizer Rate",
        filters={"crop": crop, "season": season},
        fields=["fertilizer_product", "yield_tier", "base_rate_kg_ha"],
    )
    rates = {}
    for r in rows:
        product = r.fertilizer_product
        if product not in rates:
            rates[product] = {}
        rates[product][r.yield_tier] = flt(r.base_rate_kg_ha)
    return rates


def get_buildup_factors(leaf_analysis_name):
    if not leaf_analysis_name:
        return {}
    doc = frappe.get_doc("Leaf Analysis", leaf_analysis_name)
    return {
        row.nutrient: flt(row.build_up_factor or 1.0)
        for row in doc.nutrient_results
    }


def calculate_programme_lines(blocks, crop="Hass Avocado", season="2025/2026"):
    rates = get_fertilizer_rates(crop, season)
    lines = []

    for block in blocks:
        block_name  = block["block"]
        yield_t_ha  = flt(block.get("yield_t_ha", 0))
        la_name     = block.get("leaf_analysis")
        area_ha     = flt(block.get("area_ha", 0))
        big_trees   = cint(block.get("big_tree_count", 0))
        small_trees = cint(block.get("small_tree_count", 0))
        total_trees = big_trees + small_trees
        big_pct     = big_trees / total_trees if total_trees else 0.8
        tier        = get_yield_tier(yield_t_ha)

        # Get build-up factors from leaf analysis
        nutrient_buildup = get_buildup_factors(la_name)

        for product, schedule in APPLICATION_SCHEDULE.items():
            product_rates = rates.get(product, {})

            # Get rate for this tier, fallback to "All" tier
            base_rate = product_rates.get(tier) or product_rates.get("All", 0)
            if not base_rate:
                continue

            # Apply build-up factor via nutrient map
            nutrient = PRODUCT_NUTRIENT_MAP.get(product)
            buildup  = nutrient_buildup.get(nutrient, 1.0) if nutrient else 1.0
            adjusted_rate = base_rate * buildup

            for month, fraction in schedule:
                monthly_rate = adjusted_rate * fraction
                rounded_rate = round_to_base(monthly_rate, ROUNDING_BASE.get(product, 25))
                total_kg     = rounded_rate * area_ha
                big_kg       = total_kg * big_pct
                small_kg     = total_kg * (1 - big_pct)

                # G/tree based on fixed planting density of 250 plants/Ha
                g_per_big   = round(rounded_rate / PLANTS_PER_HA, 3)
                g_per_small = round(g_per_big * SMALL_TREE_RATIO, 3)

                lines.append({
                    "block":                block_name,
                    "fertilizer_product":   product,
                    "application_month":    month,
                    "yield_tier":           tier,
                    "kg_per_ha_rate":       round(rounded_rate, 2),
                    "total_kg":             round(total_kg, 2),
                    "total_kg_big_trees":   round(big_kg, 2),
                    "total_kg_small_trees": round(small_kg, 2),
                    "g_per_big_tree":       g_per_big,
                    "g_per_small_tree":     g_per_small,
                })

    return lines


@frappe.whitelist()
def run_calculation(programme_name):
    programme = frappe.get_doc("Fertilizer Programme", programme_name)

    if programme.docstatus == 1:
        frappe.throw("Cannot recalculate a submitted programme.")

    blocks = [
        {
            "block":            row.block,
            "yield_t_ha":       row.actual_yield_t_ha,
            "leaf_analysis":    row.leaf_analysis,
            "area_ha":          row.area_ha,
            "big_tree_count":   row.big_tree_count,
            "small_tree_count": row.small_tree_count,
        }
        for row in programme.get("block_yield_data", [])
    ]

    lines = calculate_programme_lines(
        blocks,
        crop=programme.crop or "Hass Avocado",
        season=programme.season or "2025/2026"
    )

    programme.set("programme_lines", [])
    for line in lines:
        programme.append("programme_lines", line)

    programme.save()
    return len(lines)