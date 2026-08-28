"""
Shared helper to keep the `farm` field in sync on doctypes that scope through
Farm Block (Block → Section → Farm is a two-hop chain that plain `fetch_from`
can't reliably follow across all save paths).
"""

import frappe


def set_farm_from_block(doc, method=None):
	"""doc_events target for doctypes carrying a `block` link (Fertilizer Store
	Request, Fertilizer Application, Block Fertilizer Plan). Also sets `section`
	where the doctype has that field (e.g. Block Fertilizer Plan, for job-sheet
	grouping) - harmless no-op on doctypes without it."""
	if doc.get("block"):
		info = frappe.db.get_value("Farm Block", doc.block, ["farm", "section"], as_dict=True)
		doc.farm = info.farm
		doc.section = info.section


def set_farm_from_programme(doc, method=None):
	"""doc_events target for doctypes carrying a `fertilizer_programme` link
	(Fertilizer Budget)."""
	if doc.get("fertilizer_programme"):
		doc.farm = frappe.db.get_value("Fertilizer Programme", doc.fertilizer_programme, "farm")


def set_company_from_farm(doc, method=None):
	"""doc_events target for any doctype carrying both a `farm` link and a
	`company` field. Run after whichever hook (if any) resolves `farm` on that
	doctype, so the company always reflects the farm's parent Company for
	per-company accounting/reporting. CNP Farm has no company field of its
	own - warehouse is the only reliable source, same as everywhere else in
	the app that needs a farm's company."""
	if doc.get("farm"):
		warehouse = frappe.db.get_value("CNP Farm", doc.farm, "warehouse")
		doc.company = frappe.db.get_value("Warehouse", warehouse, "company") if warehouse else None
