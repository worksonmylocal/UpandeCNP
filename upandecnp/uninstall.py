import frappe


def before_uninstall():
    """Remove everything after_install() created outside upandecnp's own
    doctypes - those are dropped automatically by Frappe's uninstall (every
    table/doctype owned by the app's module). What's NOT automatic is
    anything this app added onto doctypes it doesn't own: Custom Fields on
    Material Request, and the Roles it created. Site config (ignore_csrf) is
    deliberately left alone - it's a shared, site-wide setting other things
    may also depend on, not something safe to blindly unset on uninstall.
    """
    remove_material_request_custom_fields()
    remove_employee_custom_fields()
    remove_roles()
    frappe.db.commit()
    print("UpandeCNP: uninstall cleanup complete.")


def remove_material_request_custom_fields():
    for fieldname in ("custom_fertilizer_programme", "custom_block_fertilizer_plan"):
        name = f"Material Request-{fieldname}"
        if frappe.db.exists("Custom Field", name):
            frappe.delete_doc("Custom Field", name, ignore_permissions=True, force=True)
            print(f"UpandeCNP: removed Custom Field {name}")


def remove_employee_custom_fields():
    for fieldname in ("custom_field_supervisor", "custom_assigned_block"):
        name = f"Employee-{fieldname}"
        if frappe.db.exists("Custom Field", name):
            frappe.delete_doc("Custom Field", name, ignore_permissions=True, force=True)
            print(f"UpandeCNP: removed Custom Field {name}")


def remove_roles():
    """Field Worker, Storekeeper, and every "<Farm> Agronomist" role this
    app created (see utils/farm_permissions.py's ROLE_SUFFIX - matching
    that same suffix here catches roles added for farms onboarded after
    install, not just the ones seeded at install time)."""
    from upandecnp.upandecnp.utils.farm_permissions import ROLE_SUFFIX

    role_names = set(frappe.get_all("Role", filters={"role_name": ["like", f"%{ROLE_SUFFIX}"]}, pluck="name"))
    role_names.update(["Field Worker", "Storekeeper"])

    for role_name in role_names:
        if not frappe.db.exists("Role", role_name):
            continue
        # Drop the role from anyone still holding it first, so uninstalling
        # doesn't leave dangling Has Role rows pointing at a deleted Role -
        # the same class of orphaned-reference problem as a deleted DocType.
        frappe.db.delete("Has Role", {"role": role_name})
        frappe.delete_doc("Role", role_name, ignore_permissions=True, force=True)
        print(f"UpandeCNP: removed role {role_name}")
