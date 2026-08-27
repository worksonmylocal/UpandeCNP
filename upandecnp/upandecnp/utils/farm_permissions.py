"""
Role-based farm data segregation.

A role named "<Farm> Agronomist" (e.g. "Lokitela Agronomist", "Endebess
Agronomist") restricts whoever holds it to records for that Farm only, on
every farm-scoped doctype below - no per-user setup needed. Assigning the
role is the whole configuration step; adding a new farm's agronomist role
(e.g. once Endebess is onboarded) needs no code change, only a new Role
named to match its Farm.

Users with System Manager, or with none of these roles at all, are
unrestricted - the restriction only ever kicks in for someone who actually
holds a "<Farm> Agronomist" role.
"""

import frappe

ROLE_SUFFIX = " Agronomist"
MANAGER_ROLE = "Farm Manager"
MANAGER_ROLE_PREFIX = "Farm Manager "


def get_agronomist_farms(user):
	"""Farms this user is restricted to, derived from their roles. Empty list
	means no restriction applies (not "no farms allowed")."""
	farms = []
	for role in frappe.get_roles(user):
		if role.endswith(ROLE_SUFFIX):
			farm = role[: -len(ROLE_SUFFIX)]
			if frappe.db.exists("CNP Farm", farm):
				farms.append(farm)
	return farms


def get_manager_farms(user):
	"""Farms this user is restricted to for the Manager dashboard, from the
	company's existing Farm Manager roles (not upandecnp's own - reused as-is
	so "who manages this farm" isn't a duplicated concept). Holding the bare
	"Farm Manager" role is the all-farm super role: empty list, same
	"unrestricted" convention as get_agronomist_farms. "Farm Manager <Farm>"
	(e.g. "Farm Manager Lokitela") restricts to that farm."""
	roles = frappe.get_roles(user)
	if MANAGER_ROLE in roles:
		return []

	farms = []
	for role in roles:
		if role.startswith(MANAGER_ROLE_PREFIX):
			farm = role[len(MANAGER_ROLE_PREFIX):]
			if frappe.db.exists("CNP Farm", farm):
				farms.append(farm)
	return farms


def is_farm_manager(user=None):
	"""Whether this user holds any Farm Manager role at all (super or
	farm-specific) - used to gate access to /manager itself, not just scope
	its data."""
	user = user or frappe.session.user
	roles = frappe.get_roles(user)
	if "System Manager" in roles or MANAGER_ROLE in roles:
		return True
	return any(role.startswith(MANAGER_ROLE_PREFIX) for role in roles)


def resolve_farm_scope(user, requested_farm):
	"""Reconcile a dashboard API call's requested farm against the caller's
	role-based restriction. Several api.py functions serve both /dashboard
	and /manager, so this combines both Agronomist and Farm Manager
	restrictions rather than assuming which page is calling - a user
	restricted by either (or both) only ever sees the farm(s) either role
	allows. Returns the farm to actually query with (None means "all
	farms" for an unrestricted caller), or raises frappe.PermissionError if
	the caller explicitly asked for a farm outside their allowed scope."""
	user = user or frappe.session.user
	if "System Manager" in frappe.get_roles(user):
		return requested_farm

	farms = list(dict.fromkeys(get_agronomist_farms(user) + get_manager_farms(user)))
	if not farms:
		return requested_farm

	if not requested_farm:
		return farms[0]

	if requested_farm not in farms:
		frappe.throw(f"You don't have access to {requested_farm}.", frappe.PermissionError)

	return requested_farm


def _condition(doctype, fieldname, user):
	user = user or frappe.session.user
	if "System Manager" in frappe.get_roles(user):
		return ""

	farms = get_agronomist_farms(user)
	if not farms:
		return ""

	values = ", ".join(frappe.db.escape(f) for f in farms)
	return f"`tab{doctype}`.`{fieldname}` in ({values})"


def has_farm_permission(doc, ptype=None, user=None):
	"""Generic has_permission hook, shared by every doctype registered below -
	doc.doctype tells it which fieldname to check."""
	user = user or frappe.session.user
	if "System Manager" in frappe.get_roles(user):
		return True

	farms = get_agronomist_farms(user)
	if not farms:
		return True

	fieldname = "custom_farm" if doc.doctype == "Material Request" else "farm"
	if doc.get(fieldname) not in farms:
		return False

	if doc.doctype == "Material Request" and doc.get("custom_request_type") != "Fertiliser Issuing":
		return False

	return True


def material_request_query(user):
	"""Material Request is shared across every department on the site (fuel,
	chemicals, other purchases) - farm-scoping alone isn't enough, an
	Agronomist should only see the two agronomy-generated categories
	(fertilizer purchase and field-application issue), both tagged
	custom_request_type="Fertiliser Issuing" by upandecnp's own
	integration.py, not every Material Request tagged to their farm."""
	base = _condition("Material Request", "custom_farm", user)
	if not base:
		return ""
	category = "`tabMaterial Request`.`custom_request_type` = 'Fertiliser Issuing'"
	return f"({base}) and {category}"


def fertilizer_programme_query(user):
	return _condition("Fertilizer Programme", "farm", user)


def block_fertilizer_plan_query(user):
	return _condition("Block Fertilizer Plan", "farm", user)


def fertilizer_budget_query(user):
	return _condition("Fertilizer Budget", "farm", user)


def fertilizer_application_query(user):
	return _condition("Fertilizer Application", "farm", user)


def production_calendar_query(user):
	return _condition("Production Calendar", "farm", user)


def leaf_analysis_query(user):
	return _condition("Leaf Analysis", "farm", user)


def farm_block_query(user):
	return _condition("Farm Block", "farm", user)


def section_query(user):
	return _condition("Section", "farm", user)
