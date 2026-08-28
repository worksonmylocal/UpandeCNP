"""
Restores the Lokitela demo/master data an app deploy has been observed to
wipe on this site: CNP Farm records, Sections, Farm Block linkage (section/
crop/variety/area/tree count/cost center/previous year yield), the Lokitela
Production Calendar (fertilizer schedule + calendar events), and Leaf
Analysis records.

Safe to re-run on every migrate - each piece only creates what's missing
(Production Calendar and Leaf Analysis are left alone if they already
exist, so hand edits made after a restore aren't clobbered by the next
one), except Farm Block field values, which are always re-applied for the
known Lokitela blocks since those are exactly the fields observed to get
silently zeroed out (e.g. by re-running sync_blocks_from_warehouse against
a Warehouse tree that has no GIS/area data of its own).
"""

import json
import os

import frappe


def execute():
    fixture_path = os.path.join(os.path.dirname(__file__), "fixtures", "lokitela_demo_data.json")
    with open(fixture_path) as f:
        data = json.load(f)

    _seed_farms(data["farms"])
    _seed_sections(data["sections"])
    _restore_blocks(data["blocks"])
    _seed_production_calendar(data["production_calendar"])
    _seed_leaf_analyses(data["leaf_analyses"])

    frappe.db.commit()


def _seed_farms(farms):
    for f in farms:
        if frappe.db.exists("CNP Farm", f["farm_name"]):
            continue
        if not frappe.db.exists("Warehouse", f["warehouse"]):
            # Farm-specific warehouse hierarchy isn't guaranteed to exist on
            # every environment this patch might run against.
            continue
        frappe.get_doc({
            "doctype": "CNP Farm",
            "farm_name": f["farm_name"],
            "is_active": 1,
            "warehouse": f["warehouse"],
            "default_crop": "Hass Avocado" if frappe.db.exists("Crop", "Hass Avocado") else None,
        }).insert(ignore_permissions=True)


def _seed_sections(sections):
    if not frappe.db.exists("CNP Farm", "Lokitela"):
        return
    for s in sections:
        name = f"Lokitela-{s['section_name']}"
        if frappe.db.exists("Section", name):
            continue
        frappe.get_doc({
            "doctype": "Section",
            "farm": "Lokitela",
            "section_name": s["section_name"],
        }).insert(ignore_permissions=True)


def _restore_blocks(blocks):
    for b in blocks:
        if not frappe.db.exists("Farm Block", b["name"]):
            # This patch links known blocks - it doesn't create Farm Block
            # records from scratch (that's sync_blocks_from_warehouse's job).
            continue
        frappe.db.set_value("Farm Block", b["name"], {
            "section": b["section"],
            "crop": b["crop"],
            "variety": b["variety"],
            "area_ha": b["area_ha"],
            "tree_count": b["tree_count"],
            "cost_center": b["cost_center"],
            "previous_year_yield_kg_ha": b["previous_year_yield_kg_ha"],
        }, update_modified=False)


def _seed_production_calendar(pc):
    name = f"PC-{pc['farm']}-{pc['season']}"
    if frappe.db.exists("Production Calendar", name) or not frappe.db.exists("CNP Farm", pc["farm"]):
        return
    schedule = [row for row in pc["fertilizer_schedule"] if frappe.db.exists("Item", row["fertilizer_product"])]
    frappe.get_doc({
        "doctype": "Production Calendar",
        "farm": pc["farm"],
        "season": pc["season"],
        "fertilizer_schedule": schedule,
        "calendar_events": pc["calendar_events"],
    }).insert(ignore_permissions=True)


def _seed_leaf_analyses(leaf_analyses):
    for la in leaf_analyses:
        if not (frappe.db.exists("Section", la["section"]) and frappe.db.exists("Crop", la["crop"])):
            continue
        if frappe.db.exists("Leaf Analysis", {
            "section": la["section"], "yield_tier": la["yield_tier"], "farm": la["farm"],
        }):
            continue
        frappe.get_doc({
            "doctype": "Leaf Analysis",
            "section": la["section"],
            "yield_tier": la["yield_tier"],
            "farm": la["farm"],
            "crop": la["crop"],
            "season": la["season"],
            "sampling_date": la["sampling_date"],
            "laboratory": "Simulated - placeholder pending real lab submission",
            "nutrient_results": la["nutrient_results"],
        }).insert(ignore_permissions=True)
