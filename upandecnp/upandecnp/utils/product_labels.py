"""Show fertilizer products by name, not by item code.

Item codes on this site are bare numbers - "1010100032" is CAN,
"10070010005" is potassium sulphate. Nobody reading a report knows that, and
several near-identical Items exist per product, so a code is not even a
reliable hint. Reports therefore lead with the Item name.

The code is kept, in its own narrower column: store paperwork, Bin balances
and Material Requests are all keyed by it, so anyone cross-checking a report
against the store still needs it visible. Dropping it would trade one kind
of illegibility for another.
"""

import frappe


def label_products(columns, rows):
    """Put a readable name column in front of every Item-code column.

    Generic on purpose: reports key the product as "product" or
    "fertilizer_product" depending on where their data comes from, so this
    keys off the column's options rather than its fieldname, and every
    report gets the same treatment from one place.
    """
    code_fields = [
        col["fieldname"] for col in columns
        if isinstance(col, dict)
        and col.get("options") == "Item"
        and col.get("fieldname")
    ]
    if not code_fields:
        return columns, rows

    codes = {
        row.get(f) for row in rows for f in code_fields if row.get(f)
    }
    names = _names_for(codes)

    new_columns = []
    for col in columns:
        if isinstance(col, dict) and col.get("fieldname") in code_fields:
            new_columns.append({
                "label": col.get("label") or "Product",
                "fieldname": col["fieldname"] + "_name",
                "fieldtype": "Data",
                "width": col.get("width") or 150,
            })
            # The code stays, narrower and plainly labelled, still linking
            # through to the Item.
            new_columns.append({**col, "label": "Code", "width": 110})
        else:
            new_columns.append(col)

    for row in rows:
        for f in code_fields:
            code = row.get(f)
            if code:
                row[f + "_name"] = names.get(code) or code

    return new_columns, rows


def _names_for(codes):
    codes = [c for c in codes if c]
    if not codes:
        return {}
    return {
        row.name: row.item_name
        for row in frappe.get_all(
            "Item", filters={"name": ["in", codes]}, fields=["name", "item_name"]
        )
    }
