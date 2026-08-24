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


def get_agronomist_farms(user):
	"""Farms this user is restricted to, derived from their roles. Empty list
	means no restriction applies (not "no farms allowed")."""
	farms = []
	for role in frappe.get_roles(user):
		if role.endswith(ROLE_SUFFIX):
			farm = role[: -len(ROLE_SUFFIX)]
			if frappe.db.exists("Farm", farm):
				farms.append(farm)
	return farms


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
	return doc.get(fieldname) in farms


def material_request_query(user):
	return _condition("Material Request", "custom_farm", user)


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
