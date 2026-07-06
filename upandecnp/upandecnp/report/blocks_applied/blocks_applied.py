import frappe
from frappe.utils import flt


def execute(filters=None):
    filters = filters or {}
    return get_columns(), get_data(filters)


def get_columns():
    return [
        {"label": "Date",         "fieldname": "application_date",           "fieldtype": "Date",  "width": 100},
        {"label": "Block",        "fieldname": "block",                      "fieldtype": "Link",  "options": "Farm Block", "width": 100},
        {"label": "Product",      "fieldname": "fertilizer_product",         "fieldtype": "Link",  "options": "Item",       "width": 130},
        {"label": "Month",        "fieldname": "application_month",          "fieldtype": "Data",  "width": 90},
        {"label": "Planned (Kg)", "fieldname": "planned_quantity_kg",        "fieldtype": "Float", "width": 100},
        {"label": "Applied (Kg)", "fieldname": "actual_quantity_applied_kg", "fieldtype": "Float", "width": 100},
        {"label": "Variance (Kg)","fieldname": "variance_kg",                "fieldtype": "Float", "width": 100},
        {"label": "In Full?",     "fieldname": "in_full",                    "fieldtype": "Data",  "width": 80},
        {"label": "Reason (if partial)", "fieldname": "partial_reason",      "fieldtype": "Data",  "width": 200},
        {"label": "Applied By",   "fieldname": "applied_by",                 "fieldtype": "Link",  "options": "Employee", "width": 130},
        {"label": "Store Request","fieldname": "store_request",              "fieldtype": "Link",  "options": "Fertilizer Store Request", "width": 130},
        {"label": "Record",       "fieldname": "name",                       "fieldtype": "Link",  "options": "Fertilizer Application", "width": 110},
    ]


def get_data(filters):
    conditions = {"docstatus": 1}

    if filters.get("from_date") and filters.get("to_date"):
        conditions["application_date"] = ["between", [filters["from_date"], filters["to_date"]]]
    if filters.get("block"):
        conditions["block"] = filters["block"]
    if filters.get("applied_by"):
        conditions["applied_by"] = filters["applied_by"]
    if filters.get("only_partial"):
        conditions["applied_in_full"] = 0

    records = frappe.get_all(
        "Fertilizer Application",
        filters=conditions,
        fields=[
            "name", "application_date", "block", "fertilizer_product",
            "planned_quantity_kg", "actual_quantity_applied_kg", "variance_kg",
            "applied_in_full", "partial_reason", "applied_by", "store_request",
        ],
        order_by="application_date desc, block asc",
    )

    # Pull application_month from the linked block plan where available
    for r in records:
        r["in_full"] = "Yes" if r.get("applied_in_full") else "No"
        r["application_month"] = ""

    return records