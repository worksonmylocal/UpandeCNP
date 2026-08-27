import frappe


def after_install():
    create_roles()
    create_material_request_custom_field()
    create_employee_custom_fields()
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


def create_employee_custom_fields():
    """Add upandecnp's own field-team fields to Employee. Deliberately kept
    separate from the HR reports_to field - custom_field_supervisor is
    "who manages this person for field-application purposes", set/cleared
    by supervisors themselves through the field app, and must never be
    confused with the real org-chart reporting line."""
    fieldname = "custom_field_supervisor"
    if not frappe.db.exists("Custom Field", f"Employee-{fieldname}"):
        frappe.get_doc({
            "doctype": "Custom Field",
            "dt": "Employee",
            "fieldname": fieldname,
            "label": "Field Supervisor (UpandeCNP)",
            "fieldtype": "Link",
            "options": "Employee",
            "insert_after": "reports_to",
            "description": "Who manages this employee for fertilizer field-application purposes - set via the field app's Manage Team, separate from the HR reporting line above.",
        }).insert(ignore_permissions=True)
        print("UpandeCNP: created Employee custom_field_supervisor field")

    block_fieldname = "custom_assigned_block"
    if not frappe.db.exists("Custom Field", f"Employee-{block_fieldname}"):
        frappe.get_doc({
            "doctype": "Custom Field",
            "dt": "Employee",
            "fieldname": block_fieldname,
            "label": "Assigned Block (UpandeCNP)",
            "fieldtype": "Link",
            "options": "Farm Block",
            "insert_after": "custom_field_supervisor",
        }).insert(ignore_permissions=True)
        print("UpandeCNP: created Employee custom_assigned_block field")


def set_site_config():
    """Allow the field page and dashboard API calls (same-origin, login-protected)."""
    from frappe.installer import update_site_config
    update_site_config("ignore_csrf", 1)
    print("UpandeCNP: set ignore_csrf")