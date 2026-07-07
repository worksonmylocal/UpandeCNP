import frappe

# API methods that the mobile field page calls (same-origin, login-protected)
FIELD_API_METHODS = {
    "upandecnp.upandecnp.api.create_store_request",
    "upandecnp.upandecnp.api.record_application",
    "upandecnp.upandecnp.api.get_blocks_with_pending_work",
    "upandecnp.upandecnp.api.get_pending_plans_for_block",
    "upandecnp.upandecnp.api.get_issued_request_for_plan",
}


def bypass_csrf_for_field_api():
    """Skip CSRF for the field-page API methods. Safe because they require login."""
    path = frappe.local.request.path if frappe.local.request else ""
    for method in FIELD_API_METHODS:
        if method in path:
            frappe.flags.ignore_csrf = True
            break