import frappe


def after_install():
    create_roles()
    create_material_request_custom_field()
    set_site_config()
    seed_crop_data()
    frappe.db.commit()
    print("UpandeCNP: post-install setup complete.")


def seed_crop_data():
    """Patches don't run on a fresh `bench install-app` (only on `bench
    migrate` for sites that already had the app) - call the same seed
    function directly so it also runs on a brand new site."""
    from upandecnp.patches.seed_lokitela_crop_data import execute as seed_crop
    seed_crop()


def create_roles():
    """Create the Field Worker, Storekeeper and per-farm Agronomist roles if
    missing. A role named "<Farm> Agronomist" restricts whoever holds it to
    that Farm's data only (see utils/farm_permissions.py) - onboarding a new
    farm's agronomist just needs a matching Role, no code change."""
    roles = ["Field Worker", "Storekeeper", "Lokitela Agronomist", "Endebess Agronomist"]
    for role_name in roles:
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

    block_plan_fieldname = "custom_block_fertilizer_plan"
    if not frappe.db.exists("Custom Field", f"Material Request-{block_plan_fieldname}"):
        frappe.get_doc({
            "doctype": "Custom Field",
            "dt": "Material Request",
            "fieldname": block_plan_fieldname,
            "label": "Block Fertilizer Plan",
            "fieldtype": "Link",
            "options": "Block Fertilizer Plan",
            "insert_after": "custom_fertilizer_programme",
            "read_only": 1,
        }).insert(ignore_permissions=True)
        print("UpandeCNP: created Material Request custom_block_fertilizer_plan field")


def set_site_config():
    """Allow the field page and dashboard API calls (same-origin, login-protected)."""
    from frappe.installer import update_site_config
    update_site_config("ignore_csrf", 1)
    print("UpandeCNP: set ignore_csrf")