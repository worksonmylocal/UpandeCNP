import frappe


def get_context(context):
    """The agronomist's central desk.

    Gated on the module role rather than left open: this page carries the
    actions that build a programme, not just a view of one. Farm scoping is
    still done per-request in the API, so a farm agronomist sees their own
    farm here exactly as they do everywhere else.
    """
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/agronomist"
        raise frappe.Redirect

    roles = frappe.get_roles(frappe.session.user)
    if not ({"CNP Agronomist", "System Manager"} & set(roles)):
        frappe.throw(
            "This desk is for CNP agronomists. Ask for the CNP Agronomist role "
            "if you should have access.",
            frappe.PermissionError,
        )

    context.no_cache = 1
    context.show_sidebar = False
    return context
