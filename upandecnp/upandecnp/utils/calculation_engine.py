import frappe
from frappe.utils import flt, cint

YIELD_TIERS = [
    (22.0, "24T"),
    (19.0, "20T"),
    (16.0, "18T"),
    (0.0,  "15T"),
]

PRODUCT_NUTRIENT_CONTENT = {
    "CAN":           {"N":  0.26},
    "TSP":           {"P":  0.20},
    "MOP":           {"K":  0.50},
    "K2SO4":         {"K":  0.45},
    "Gypsum":        {"Ca": 0.23, "S": 0.18},
    "Ag Lime":       {"Ca": 0.32},
    "Zinc Sulphate": {"Zn": 0.36},
    "Borax":         {"B":  0.11},
}

APPLICATION_SCHEDULE = {
    "N": [
        ("November", 0.20),
        ("January",  0.40),
        ("March",    0.40),
    ],
    "K_MOP": [
        ("November", 0.20),
        ("March",    0.40),
    ],
    "K_K2SO4": [
        ("January",  0.40),
    ],
    "P": [
        ("March", 1.00),
    ],
    "B": [
        ("August",   0.25),
        ("November", 0.25),
        ("March",    0.25),
        ("June",     0.25),
    ],
    "Zn": [
        ("November", 0.50),
        ("March",    0.50),
    ],
    "Gypsum": [
        ("December", 1.00),
    ],
    "Lime": [
        ("April", 1.00),
    ],
}

ROUNDING_BASE = {
    "CAN":            25,
    "TSP":            25,
    "MOP":            25,
    "K2SO4":          25,
    "Gypsum":        100,
    "Ag Lime":       100,
    "Zinc Sulphate":   5,
    "Borax":           5,
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


def get_removal_factors(crop="Hass Avocado"):
    rows = frappe.get_all(
        "Nutrient Removal Factor",
        filters={"crop": crop},
        fields=["nutrient", "removal_per_tonne"],
    )
    return {r.nutrient: flt(r.removal_per_tonne) for r in rows}


def get_buildup_factors(leaf_analysis_name):
    if not leaf_analysis_name:
        return {}
    doc = frappe.get_doc("Leaf Analysis", leaf_analysis_name)
    return {
        row.nutrient: flt(row.build_up_factor or 1.0)
        for row in doc.nutrient_results
    }


def calculate_programme_lines(blocks, crop="Hass Avocado"):
    removal_factors = get_removal_factors(crop)
    lines = []

    for block in blocks:
        block_name   = block["block"]
        yield_t_ha   = flt(block.get("yield_t_ha", 0))
        la_name      = block.get("leaf_analysis")
        area_ha      = flt(block.get("area_ha", 0))
        big_trees    = cint(block.get("big_tree_count", 0))
        small_trees  = cint(block.get("small_tree_count", 0))
        total_trees  = big_trees + small_trees
        big_pct      = big_trees / total_trees if total_trees else 0.8
        buildup      = get_buildup_factors(la_name)
        tier         = get_yield_tier(yield_t_ha)

        def nutrient_kg_ha(nutrient):
            removal = removal_factors.get(nutrient, 0)
            factor  = buildup.get(nutrient, 1.0)
            return yield_t_ha * removal * factor

        def make_line(product, month, kg_ha):
            rounded   = round_to_base(kg_ha, ROUNDING_BASE.get(product, 25))
            total_kg  = rounded * area_ha
            big_kg    = total_kg * big_pct
            small_kg  = total_kg * (1 - big_pct)
            return {
                "block":                block_name,
                "fertilizer_product":   product,
                "application_month":    month,
                "yield_tier":           tier,
                "kg_per_ha_rate":       round(rounded, 2),
                "total_kg":             round(total_kg, 2),
                "total_kg_big_trees":   round(big_kg, 2),
                "total_kg_small_trees": round(small_kg, 2),
                "g_per_big_tree":       round((big_kg / big_trees * 1000), 1) if big_trees else 0,
                "g_per_small_tree":     round((small_kg / small_trees * 1000), 1) if small_trees else 0,
            }

        # Nitrogen - CAN
        n_kg_ha = nutrient_kg_ha("N") / 0.26
        for month, fraction in APPLICATION_SCHEDULE["N"]:
            lines.append(make_line("CAN", month, n_kg_ha * fraction))

        # Potassium - MOP
        k_kg_ha = nutrient_kg_ha("K")
        for month, fraction in APPLICATION_SCHEDULE["K_MOP"]:
            lines.append(make_line("MOP", month, (k_kg_ha * fraction) / 0.50))

        # Potassium - K2SO4
        for month, fraction in APPLICATION_SCHEDULE["K_K2SO4"]:
            lines.append(make_line("K2SO4", month, (k_kg_ha * fraction) / 0.45))

        # Phosphorus - TSP
        p_kg_ha = nutrient_kg_ha("P") / 0.20
        for month, fraction in APPLICATION_SCHEDULE["P"]:
            lines.append(make_line("TSP", month, p_kg_ha * fraction))

        # Boron - Borax
        b_kg_ha = nutrient_kg_ha("B") / 0.11
        for month, fraction in APPLICATION_SCHEDULE["B"]:
            lines.append(make_line("Borax", month, b_kg_ha * fraction))

        # Zinc - Zinc Sulphate
        zn_kg_ha = nutrient_kg_ha("Zn") / 0.36
        for month, fraction in APPLICATION_SCHEDULE["Zn"]:
            lines.append(make_line("Zinc Sulphate", month, zn_kg_ha * fraction))

        # Gypsum
        for month, fraction in APPLICATION_SCHEDULE["Gypsum"]:
            lines.append(make_line("Gypsum", month, 600.0))

        # Ag Lime
        for month, fraction in APPLICATION_SCHEDULE["Lime"]:
            lines.append(make_line("Ag Lime", month, 1000.0))

    return lines