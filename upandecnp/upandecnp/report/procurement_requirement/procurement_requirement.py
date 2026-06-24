import frappe
from frappe.utils import flt
import math


def execute(filters=None):
    filters = filters or {}
    return get_columns(), get_data(filters)


def get_columns():
    return [
        {"label": "Fertilizer Product", "fieldname": "product",      "fieldtype": "Link", "options": "Item", "width": 160},
        {"label": "Season Total (Kg)",  "fieldname": "total_kg",     "fieldtype": "Float", "width": 150},
        {"label": "Stock On Hand (Kg)", "fieldname": "stock_kg",     "fieldtype": "Float", "width": 150},
        {"label": "Shortfall (Kg)",     "fieldname": "shortfall_kg", "fieldtype": "Float", "width": 140},
        {"label": "Order Qty (Rounded)","fieldname": "order_qty",    "fieldtype": "Float", "width": 150},
        {"label": "First Required",     "fieldname": "first_month",  "fieldtype": "Data",  "width": 130},
    ]


def get_data(filters):
    programme_name = filters.get("fertilizer_programme")
    if not programme_name:
        frappe.throw("Please select a Fertilizer Programme")

    programme = frappe.get_doc("Fertilizer Programme", programme_name)

    # Aggregate requirements per product
    requirements = {}
    for line in programme.get("programme_lines", []):
        product = line.fertilizer_product
        if product not in requirements:
            requirements[product] = {"total_kg": 0, "first_month": line.application_month}
        requirements[product]["total_kg"] += flt(line.total_kg)

    rows = []
    for product, req in requirements.items():
        stock = get_stock_qty(product)
        shortfall = max(req["total_kg"] - stock, 0)
        order_qty = round_order_qty(shortfall, product)

        rows.append({
            "product":      product,
            "total_kg":     round(req["total_kg"], 1),
            "stock_kg":     round(stock, 1),
            "shortfall_kg": round(shortfall, 1),
            "order_qty":    order_qty,
            "first_month":  req["first_month"],
        })

    return sorted(rows, key=lambda r: r["shortfall_kg"], reverse=True)


def get_stock_qty(item_code):
    result = frappe.db.get_value("Bin", {"item_code": item_code}, "actual_qty")
    return flt(result)


def round_order_qty(shortfall, product):
    if shortfall <= 0:
        return 0
    bag_sizes = {
        "CAN": 50, "TSP": 50, "MOP": 50, "K2SO4": 50,
        "Gypsum": 1000, "Ag Lime": 1000,
        "Zinc Sulphate": 25, "Borax": 25,
    }
    bag = bag_sizes.get(product, 50)
    return math.ceil(shortfall / bag) * bag