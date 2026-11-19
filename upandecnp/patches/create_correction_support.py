"""Corrections: the Material Request fields that tag a replaced request, and
the role (held by Bramuel) that decides correction requests."""

import frappe


def execute():
	if not frappe.db.exists("DocType", "Correction Request"):
		frappe.reload_doc("upandecnp", "doctype", "correction_request")
	from upandecnp.upandecnp.install import create_correction_support

	create_correction_support()
