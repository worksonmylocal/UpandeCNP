import frappe


def after_install():
    create_roles()
    create_material_request_custom_field()
    set_site_config()
    frappe.db.commit()
    print("UpandeCNP: post-install setup complete.")


def create_roles():
    """Create the Field Worker and Storekeeper roles if missing."""
    for role_name in ["Field Worker", "Storekeeper"]:
        if not frappe.db.exists("Role", role_name):
            frappe.get_doc({
                "doctype": "Role",
                "role_name": role_name,
                "desk_access": 1,
            }).insert(ignore_permissions=True)
            print(f"UpandeCNP: created role {role_name}")


def create_material_request_custom_field():
    """Add the programme link field to Material Request for traceability."""
    fieldname = "custom_fertilizer_programme"
    if not frappe.db.exists("Custom Field", f"Material Request-{fieldname}"):
        frappe.get_doc({
            "doctype": "Custom Field",
            "dt": "Material Request",
            "fieldname": fieldname,
            "label": "Fertilizer Programme",
            "fieldtype": "Link",
            "options": "Fertilizer Programme",
            "insert_after": "material_request_type",
            "read_only": 1,
        }).insert(ignore_permissions=True)
        print("UpandeCNP: created Material Request custom field")


def set_site_config():
    """Allow the field page and dashboard API calls (same-origin, login-protected)."""
    from frappe.installer import update_site_config
    update_site_config("ignore_csrf", 1)
    print("UpandeCNP: set ignore_csrf")