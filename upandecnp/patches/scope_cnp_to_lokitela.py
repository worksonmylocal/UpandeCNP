"""Pin the module to Lokitela, the one farm with data and a working store.

Only sets it when nothing is set, so re-running never overrides a farm someone
chose on purpose - and a site where Lokitela does not exist is left alone
rather than pointed at a farm that is not there.
"""

import frappe


def execute():
	if not frappe.db.exists("CNP Farm", "Lokitela"):
		return
	current = frappe.db.get_single_value("Crop Nutrition Planning Settings", "scope_farm")
	if current:
		return
	frappe.db.set_single_value("Crop Nutrition Planning Settings", "scope_farm", "Lokitela")
	frappe.db.commit()
	print("UpandeCNP: module scoped to Lokitela")
