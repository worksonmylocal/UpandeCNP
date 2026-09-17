"""
Role-based farm data segregation.

Access to this module is two roles, answering two different questions:

  "CNP Agronomist"    - may this person use the module at all? This is the
                        role the doctypes grant permissions to, so it is what
                        puts the workspace in someone's sidebar. Granting it
                        alone gives access to every farm.
  "<Farm> Agronomist" - which farm's rows may they see? That is this file.

A farm agronomist holds both. They are separate because the per-farm roles
are open-ended - one per farm, created as farms are onboarded - and a
doctype's permission list cannot name a role that does not exist yet.

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


def get_restricted_farms(user=None):
	"""Every farm restriction that applies to this user, from both role
	families combined. This is the single source of truth for "what is this
	person allowed to see" - the desk permission layer and the dashboard APIs
	both go through it, so the two can never drift apart and let someone see
	in a list view what the dashboard would refuse them.

	Empty list means unrestricted. Holding a farm-specific role of either
	family restricts to that farm, and holding several restricts to the union
	of them."""
	user = user or frappe.session.user
	return list(dict.fromkeys(get_agronomist_farms(user) + get_manager_farms(user)))


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

	farms = get_restricted_farms(user)
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

	farms = get_restricted_farms(user)
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

	farms = get_restricted_farms(user)
	if not farms:
		return True

	# CNP Farm has no farm field - it *is* the farm, keyed by its own name.
	if doc.doctype == "CNP Farm":
		return doc.name in farms

	# Material Request is no longer registered on this hook (see hooks.py), so
	# the special-casing it needed is gone with it.
	if doc.get("farm") not in farms:
		return False

	return True



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


def field_attendance_query(user):
	return _condition("Field Attendance", "farm", user)


def fertilizer_store_request_query(user):
	return _condition("Fertilizer Store Request", "farm", user)


def cnp_farm_query(user):
	"""CNP Farm is the one scoped doctype with no farm field - it is keyed by
	its own name. A restricted user shouldn't even see that the other farms
	exist, so scope on name rather than leaving the list wide open."""
	user = user or frappe.session.user
	if "System Manager" in frappe.get_roles(user):
		return ""
	farms = get_restricted_farms(user)
	if not farms:
		return ""
	values = ", ".join(frappe.db.escape(f) for f in farms)
	return f"`tabCNP Farm`.`name` in ({values})"
