"""
Whitelisted API methods for the mobile field page.
These reuse the existing DocType logic so the workflow stays consistent.
"""

import frappe
from frappe.utils import flt


@frappe.whitelist()
def get_blocks_with_pending_work():
    """Return blocks that have at least one Planned or Issued Block Fertilizer Plan."""
    plans = frappe.get_all(
        "Block Fertilizer Plan",
        filters={"docstatus": 1, "status": ["in", ["Planned", "Issued"]]},
        fields=["block"],
        distinct=True,
    )
    blocks = sorted(set(p.block for p in plans))
    return blocks


@frappe.whitelist()
def get_pending_plans_for_block(block):
    """Return the pending fertilizer plans for a block, with any linked request status."""
    plans = frappe.get_all(
        "Block Fertilizer Plan",
        filters={"docstatus": 1, "block": block, "status": ["in", ["Planned", "Issued"]]},
        fields=["name", "fertilizer_product", "application_month",
                "total_kg_required", "status"],
        order_by="application_month",
    )

    for p in plans:
        # Find the most recent store request for this plan
        requests = frappe.get_all(
            "Fertilizer Store Request",
            filters={"block_fertilizer_plan": p["name"]},
            fields=["name", "status"],
            order_by="creation desc",
            limit=1,
        )
        if requests:
            p["request_name"] = requests[0].name
            p["request_status"] = requests[0].status
        else:
            p["request_name"] = None
            p["request_status"] = None

    return plans


@frappe.whitelist()
def create_store_request(block_fertilizer_plan, quantity, employee=None):
    """Create a Fertilizer Store Request from the field page."""
    plan = frappe.get_doc("Block Fertilizer Plan", block_fertilizer_plan)

    if not employee:
        employee = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")

    doc = frappe.get_doc({
        "doctype": "Fertilizer Store Request",
        "block_fertilizer_plan": block_fertilizer_plan,
        "block": plan.block,
        "fertilizer_product": plan.fertilizer_product,
        "application_month": plan.application_month,
        "quantity_requested_kg": flt(quantity),
        "requested_by": employee,
        "request_date": frappe.utils.today(),
        "status": "Requested",
    })
    doc.insert(ignore_permissions=True)
    return {"name": doc.name, "status": "Requested"}


@frappe.whitelist()
def record_application(block_fertilizer_plan, actual_quantity, applied_in_full,
                       partial_reason=None, employee=None, store_request=None):
    """Create a Fertilizer Application from the field page."""
    plan = frappe.get_doc("Block Fertilizer Plan", block_fertilizer_plan)

    if not employee:
        employee = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")

    in_full = 1 if str(applied_in_full) in ("1", "true", "True", "yes") else 0

    if not in_full and not partial_reason:
        frappe.throw("A reason is required when the application is not done in full.")

    doc = frappe.get_doc({
        "doctype": "Fertilizer Application",
        "block_fertilizer_plan": block_fertilizer_plan,
        "store_request": store_request,
        "block": plan.block,
        "fertilizer_product": plan.fertilizer_product,
        "application_date": frappe.utils.today(),
        "planned_quantity_kg": flt(plan.total_kg_required),
        "actual_quantity_applied_kg": flt(actual_quantity),
        "applied_in_full": in_full,
        "partial_reason": partial_reason,
        "applied_by": employee,
    })
    doc.insert(ignore_permissions=True)
    doc.submit()
    return {"name": doc.name, "status": "Applied"}


@frappe.whitelist()
def get_issued_request_for_plan(block_fertilizer_plan):
    """Find an issued store request for this plan, so the app can link to it."""
    sr = frappe.get_all(
        "Fertilizer Store Request",
        filters={"block_fertilizer_plan": block_fertilizer_plan, "status": "Issued"},
        fields=["name"],
        limit=1,
    )
    return sr[0].name if sr else None

@frappe.whitelist(allow_guest=False)
def get_token():
    return frappe.sessions.get_csrf_token()


# ---------------------------------------------------------------------------
# Dashboard API
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_seasons():
    """Return the list of seasons that have programmes, plus 'All'."""
    seasons = frappe.get_all("Fertilizer Programme", filters={"docstatus": 1},
                             fields=["season"], distinct=True)
    return ["All Seasons"] + sorted(set(s.season for s in seasons))


@frappe.whitelist()
def get_farms():
    """Return active farms, for the dashboard's farm selector."""
    return frappe.get_all("Farm", filters={"is_active": 1}, fields=["name"], order_by="name")


@frappe.whitelist()
def get_dashboard_summary(season=None, farm=None):
    """Return headline numbers for the dashboard."""
    plan_filter = {"docstatus": 1}
    if season and season != "All Seasons":
        plan_filter["season"] = season
    if farm:
        plan_filter["farm"] = farm

    plans = frappe.get_all("Block Fertilizer Plan", filters=plan_filter,
                           fields=["name", "status", "total_kg_required", "block"])

    total_plans = len(plans)
    applied = sum(1 for p in plans if p.status == "Applied")
    issued = sum(1 for p in plans if p.status == "Issued")
    planned = sum(1 for p in plans if p.status == "Planned")
    total_kg = sum(flt(p.total_kg_required) for p in plans)

    blocks = len(set(p.block for p in plans))

    # Pending store requests
    request_filter = {"status": "Requested"}
    if farm:
        request_filter["farm"] = farm
    pending_requests = frappe.db.count("Fertilizer Store Request", request_filter)

    pct_applied = round(applied / total_plans * 100, 1) if total_plans else 0

    return {
        "total_plans": total_plans,
        "applied": applied,
        "issued": issued,
        "planned": planned,
        "total_kg": round(total_kg, 0),
        "blocks": blocks,
        "pending_requests": pending_requests,
        "pct_applied": pct_applied,
    }


@frappe.whitelist()
def get_monthly_breakdown(season=None, farm=None):
    """Return quantity and cost per month across the programme."""
    prog_filter = {"docstatus": 1}
    if season and season != "All Seasons":
        prog_filter["season"] = season
    if farm:
        prog_filter["farm"] = farm

    programmes = frappe.get_all("Fertilizer Programme", filters=prog_filter, fields=["name"])

    month_order = ["January","February","March","April","May","June",
                   "July","August","September","October","November","December"]
    monthly = {m: {"qty": 0, "cost": 0} for m in month_order}

    price_cache = {}
    def price(prod):
        if prod not in price_cache:
            price_cache[prod] = flt(frappe.db.get_value("Item Price",
                {"item_code": prod, "buying": 1}, "price_list_rate"))
        return price_cache[prod]

    for prog in programmes:
        doc = frappe.get_doc("Fertilizer Programme", prog.name)
        for line in doc.get("programme_lines", []):
            m = line.application_month
            if m in monthly:
                monthly[m]["qty"] += flt(line.total_kg)
                monthly[m]["cost"] += flt(line.total_kg) * price(line.fertilizer_product)

    return [
        {"month": m[:3], "qty": round(monthly[m]["qty"], 0), "cost": round(monthly[m]["cost"], 0)}
        for m in month_order if monthly[m]["qty"] > 0
    ]


@frappe.whitelist()
def get_product_breakdown(season=None, farm=None):
    """Return total quantity per product."""
    prog_filter = {"docstatus": 1}
    if season and season != "All Seasons":
        prog_filter["season"] = season
    if farm:
        prog_filter["farm"] = farm

    programmes = frappe.get_all("Fertilizer Programme", filters=prog_filter, fields=["name"])
    products = {}
    for prog in programmes:
        doc = frappe.get_doc("Fertilizer Programme", prog.name)
        for line in doc.get("programme_lines", []):
            products[line.fertilizer_product] = products.get(line.fertilizer_product, 0) + flt(line.total_kg)

    return [{"product": p, "qty": round(q, 0)} for p, q in
            sorted(products.items(), key=lambda x: x[1], reverse=True)]


@frappe.whitelist()
def get_recent_activity(farm=None):
    """Return the last 8 fertilizer applications."""
    filters = {"docstatus": 1}
    if farm:
        filters["farm"] = farm
    apps = frappe.get_all("Fertilizer Application", filters=filters,
        fields=["block", "fertilizer_product", "actual_quantity_applied_kg",
                "application_date", "applied_by", "applied_in_full"],
        order_by="creation desc", limit=8)
    return apps


@frappe.whitelist()
def get_stock_levels(farm=None):
    """Return current stock for each fertilizer item."""
    warehouse = frappe.db.get_value("Farm", farm, "warehouse") if farm else None
    items = ["CAN", "MOP", "K2SO4", "TSP", "Gypsum", "Ag Lime", "Zinc Sulphate", "Borax"]
    result = []
    for item in items:
        filters = {"item_code": item}
        if warehouse:
            filters["warehouse"] = warehouse
        qty = flt(frappe.db.get_value("Bin", filters, "actual_qty"))
        result.append({"product": item, "qty": round(qty, 0)})
    return result

# ---------------------------------------------------------------------------
# Dashboard - extended panels
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_budget_summary(season=None, farm=None):
    """Budget vs actual spend and cost per hectare."""
    filters = {"docstatus": 1}
    if season and season != "All Seasons":
        filters["season"] = season
    if farm:
        filters["farm"] = farm

    budgets = frappe.get_all("Fertilizer Budget", filters=filters,
        fields=["name", "total_budget_ksh", "total_actual",
                "cost_per_ha_budget", "cost_per_ha_actual"])

    total_budget = sum(flt(b.total_budget_ksh) for b in budgets)
    total_actual = sum(flt(b.total_actual) for b in budgets)
    # Average cost/ha across budgets (simple mean where set)
    cph_budget = [flt(b.cost_per_ha_budget) for b in budgets if b.cost_per_ha_budget]
    cph_actual = [flt(b.cost_per_ha_actual) for b in budgets if b.cost_per_ha_actual]

    return {
        "total_budget": round(total_budget, 0),
        "total_actual": round(total_actual, 0),
        "variance": round(total_actual - total_budget, 0),
        "pct_spent": round(total_actual / total_budget * 100, 1) if total_budget else 0,
        "cost_per_ha_budget": round(sum(cph_budget)/len(cph_budget), 0) if cph_budget else 0,
        "cost_per_ha_actual": round(sum(cph_actual)/len(cph_actual), 0) if cph_actual else 0,
    }


@frappe.whitelist()
def get_upcoming_and_overdue(farm=None):
    """Plans due in the next 30 days, and overdue plans (month passed, not applied)."""
    from frappe.utils import today, getdate, date_diff

    months = ["January","February","March","April","May","June",
              "July","August","September","October","November","December"]
    today_date = getdate(today())

    plan_filter = {"docstatus": 1, "status": ["in", ["Planned", "Issued"]]}
    if farm:
        plan_filter["farm"] = farm

    plans = frappe.get_all("Block Fertilizer Plan",
        filters=plan_filter,
        fields=["block", "fertilizer_product", "application_month", "total_kg_required", "status"])

    upcoming, overdue = [], []
    for p in plans:
        if p.application_month not in months:
            continue
        idx = months.index(p.application_month) + 1
        # Next occurrence
        year = today_date.year if idx >= today_date.month else today_date.year + 1
        due = getdate(f"{year}-{idx:02d}-01")
        days = date_diff(due, today_date)
        if 0 <= days <= 30:
            upcoming.append({**p, "days": days})
        # Overdue: month earlier this year, still pending
        past_year = today_date.year if idx < today_date.month else today_date.year - 1
        past_end = getdate(f"{past_year}-{idx:02d}-28")
        if today_date > past_end and days > 60:  # its window has clearly passed
            overdue.append(p)

    upcoming.sort(key=lambda x: x["days"])
    return {"upcoming": upcoming[:10], "overdue": overdue[:10]}


@frappe.whitelist()
def get_leaf_deficiency_grid(season=None, farm=None):
    """Grid of section/tier groups x nutrients showing status (Deficient/
    Adequate/Excess). Leaf Analysis is keyed by (Section, Yield Tier), not
    by block - see leaf_analysis.json."""
    filters = {"docstatus": 1}
    if season and season != "All Seasons":
        filters["season"] = season
    if farm:
        filters["farm"] = farm

    analyses = frappe.get_all("Leaf Analysis", filters=filters, fields=["name", "section", "yield_tier"])

    nutrients = ["N", "P", "K", "Ca", "Mg", "S", "Zn", "B"]
    grid = []
    for a in analyses:
        doc = frappe.get_doc("Leaf Analysis", a.name)
        row = {"section": a.section, "yield_tier": a.yield_tier, "cells": {}}
        for r in doc.get("nutrient_results", []):
            if r.nutrient in nutrients:
                row["cells"][r.nutrient] = r.status or "—"
        grid.append(row)

    grid.sort(key=lambda r: (r["section"] or "", r["yield_tier"] or ""))
    return {"nutrients": nutrients, "grid": grid}


@frappe.whitelist()
def get_stock_coverage(season=None, farm=None):
    """Stock on hand vs remaining requirement per product."""
    prog_filter = {"docstatus": 1}
    if season and season != "All Seasons":
        prog_filter["season"] = season
    if farm:
        prog_filter["farm"] = farm

    programmes = frappe.get_all("Fertilizer Programme", filters=prog_filter, fields=["name"])
    required = {}
    for prog in programmes:
        doc = frappe.get_doc("Fertilizer Programme", prog.name)
        for line in doc.get("programme_lines", []):
            required[line.fertilizer_product] = required.get(line.fertilizer_product, 0) + flt(line.total_kg)

    warehouse = frappe.db.get_value("Farm", farm, "warehouse") if farm else None
    result = []
    for product, need in required.items():
        filters = {"item_code": product}
        if warehouse:
            filters["warehouse"] = warehouse
        stock = flt(frappe.db.get_value("Bin", filters, "actual_qty"))
        result.append({
            "product": product,
            "need": round(need, 0),
            "stock": round(stock, 0),
            "covered": stock >= need,
            "shortfall": round(max(need - stock, 0), 0),
        })
    return sorted(result, key=lambda x: x["shortfall"], reverse=True)

# ---------------------------------------------------------------------------
# Managerial dashboard
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_manager_kpis(season=None, farm=None):
    """Headline KPIs for the managerial dashboard."""
    plan_filter = {"docstatus": 1}
    if season and season != "All Seasons":
        plan_filter["season"] = season
    if farm:
        plan_filter["farm"] = farm

    plans = frappe.get_all("Block Fertilizer Plan", filters=plan_filter,
                           fields=["status", "block", "total_kg_required"])
    total = len(plans)
    applied = sum(1 for p in plans if p.status == "Applied")
    pct_complete = round(applied / total * 100, 1) if total else 0

    # Budget
    bfilter = {"docstatus": 1}
    if season and season != "All Seasons":
        bfilter["season"] = season
    if farm:
        bfilter["farm"] = farm
    budgets = frappe.get_all("Fertilizer Budget", filters=bfilter,
        fields=["total_budget_ksh", "total_actual", "cost_per_ha_actual", "cost_per_ha_budget"])
    total_budget = sum(flt(b.total_budget_ksh) for b in budgets)
    total_actual = sum(flt(b.total_actual) for b in budgets)
    cph = [flt(b.cost_per_ha_actual) for b in budgets if b.cost_per_ha_actual]
    cph_b = [flt(b.cost_per_ha_budget) for b in budgets if b.cost_per_ha_budget]

    # Overdue count (reuse logic)
    overdue = len(get_upcoming_and_overdue(farm=farm).get("overdue", []))

    # Pending requests
    request_filter = {"status": "Requested"}
    if farm:
        request_filter["farm"] = farm
    pending = frappe.db.count("Fertilizer Store Request", request_filter)

    return {
        "total_budget": round(total_budget, 0),
        "total_actual": round(total_actual, 0),
        "variance": round(total_actual - total_budget, 0),
        "variance_pct": round((total_actual - total_budget) / total_budget * 100, 1) if total_budget else 0,
        "cost_per_ha": round(sum(cph)/len(cph), 0) if cph else 0,
        "cost_per_ha_budget": round(sum(cph_b)/len(cph_b), 0) if cph_b else 0,
        "pct_complete": pct_complete,
        "blocks": len(set(p.block for p in plans)),
        "overdue": overdue,
        "pending_requests": pending,
    }


@frappe.whitelist()
def get_yield_tier_distribution(season=None, farm=None):
    """How many blocks fall in each yield tier."""
    from upandecnp.upandecnp.utils.calculation_engine import get_yield_tier

    prog_filter = {"docstatus": 1}
    if season and season != "All Seasons":
        prog_filter["season"] = season
    if farm:
        prog_filter["farm"] = farm
    programmes = frappe.get_all("Fertilizer Programme", filters=prog_filter, fields=["name", "crop"])

    crop_cache = {}
    tiers = {}
    order = []
    for prog in programmes:
        if prog.crop not in crop_cache:
            crop_cache[prog.crop] = frappe.get_doc("Crop", prog.crop)
        crop_doc = crop_cache[prog.crop]

        doc = frappe.get_doc("Fertilizer Programme", prog.name)
        for row in doc.get("block_yield_data", []):
            tier_label, _ = get_yield_tier(crop_doc, row.yield_kg_ha)
            if tier_label not in tiers:
                tiers[tier_label] = 0
                order.append(tier_label)
            tiers[tier_label] += 1

    return [{"tier": t, "count": tiers[t]} for t in order]


@frappe.whitelist()
def get_application_pace(season=None, farm=None):
    """Month-by-month: planned applications vs actually applied."""
    months = ["January","February","March","April","May","June",
              "July","August","September","October","November","December"]

    plan_filter = {"docstatus": 1}
    if season and season != "All Seasons":
        plan_filter["season"] = season
    if farm:
        plan_filter["farm"] = farm

    plans = frappe.get_all("Block Fertilizer Plan", filters=plan_filter,
                           fields=["application_month", "status"])

    planned = {m: 0 for m in months}
    applied = {m: 0 for m in months}
    for p in plans:
        if p.application_month in planned:
            planned[p.application_month] += 1
            if p.status == "Applied":
                applied[p.application_month] += 1

    return [
        {"month": m[:3], "planned": planned[m], "applied": applied[m]}
        for m in months if planned[m] > 0
    ]


@frappe.whitelist()
def get_leaf_deficiency_summary(season=None, farm=None):
    """Count of blocks deficient per nutrient."""
    filters = {"docstatus": 1}
    if season and season != "All Seasons":
        filters["season"] = season
    if farm:
        filters["farm"] = farm
    analyses = frappe.get_all("Leaf Analysis", filters=filters, fields=["name"])

    nutrients = ["N", "P", "K", "Ca", "Mg", "S", "Zn", "B"]
    deficient = {n: 0 for n in nutrients}
    for a in analyses:
        doc = frappe.get_doc("Leaf Analysis", a.name)
        for r in doc.get("nutrient_results", []):
            if r.nutrient in deficient and r.status == "Deficient":
                deficient[r.nutrient] += 1

    return [{"nutrient": n, "count": deficient[n]} for n in nutrients if deficient[n] > 0]

# ---------------------------------------------------------------------------
# Kaitet integration - sync Farm Blocks from Warehouse
# ---------------------------------------------------------------------------

import json
import re


def _get_tree_count(warehouse_name):
    """Extract tree_count from a warehouse's geojson properties."""
    raw = frappe.db.get_value("Warehouse", warehouse_name, "custom_raw_geojson")
    if not raw:
        return None
    try:
        data = json.loads(raw)
        for feature in data.get("features", []):
            props = feature.get("properties", {})
            if props.get("block") == warehouse_name and "tree_count" in props:
                return props["tree_count"]
        for feature in data.get("features", []):
            props = feature.get("properties", {})
            if "tree_count" in props:
                return props["tree_count"]
    except Exception:
        return None
    return None


@frappe.whitelist()
def sync_blocks_from_warehouse(farm=None):
    """
    Sync Farm Block records from Kaitet's Warehouse master.
    If `farm` is given, only syncs blocks under that custom_farm value.
    Otherwise syncs all farms.
    Always overwrites area_ha and tree_count from the warehouse.

    Kaitet has no concept of Section or Crop, so newly-created blocks land
    without them (ignore_mandatory) - an agronomist assigns those manually
    afterwards on the same Farm Block record. Farm itself is derived from
    Section, so it's also blank until then.
    """
    filters = {"warehouse_type": "Block", "is_group": 0}
    if farm:
        filters["custom_farm"] = farm

    warehouses = frappe.get_all("Warehouse", filters=filters,
        fields=["name", "warehouse_name", "custom_area_ha", "custom_farm"],
        order_by="name")

    created, updated, errors = 0, 0, []

    for w in warehouses:
        try:
            area = w.custom_area_ha or 0
            trees = _get_tree_count(w.name) or 0
            match = re.search(r"BLK\s+(\d+)", w.warehouse_name)
            block_number = match.group(1) if match else "0"

            existing = frappe.db.exists("Farm Block", {"block_name": w.warehouse_name})

            if existing:
                doc = frappe.get_doc("Farm Block", existing)
                doc.area_ha = area
                doc.tree_count = trees
                doc.save(ignore_permissions=True)
                updated += 1
            else:
                doc = frappe.get_doc({
                    "doctype": "Farm Block",
                    "block_name": w.warehouse_name,
                    "block_number": block_number,
                    "area_ha": area,
                    "tree_count": trees,
                    "variety": "Hass",
                })
                doc.insert(ignore_permissions=True, ignore_mandatory=True)
                created += 1
        except Exception as e:
            errors.append(f"{w.name}: {str(e)}")

    frappe.db.commit()
    return {
        "created": created,
        "updated": updated,
        "errors": errors,
        "total_processed": len(warehouses),
    }


# ---------------------------------------------------------------------------
# Agronomist / Manager Dashboard v2 - progress, planned-vs-actual, alerts
# ---------------------------------------------------------------------------

DASHBOARD_MONTHS = ["January", "February", "March", "April", "May", "June",
                    "July", "August", "September", "October", "November", "December"]


def _is_month_passed(month_name, today_date):
    if month_name not in DASHBOARD_MONTHS:
        return False
    month_idx = DASHBOARD_MONTHS.index(month_name) + 1
    year = today_date.year if month_idx <= today_date.month else today_date.year - 1
    month_end = frappe.utils.getdate(f"{year}-{month_idx:02d}-28")
    return today_date > month_end


@frappe.whitelist()
def get_block_progress(farm=None, season=None):
    """Section -> block list with a derived status (Completed/In Progress/
    Behind Schedule/Pending), for progress views and farm->section->block
    drill-down. A block can have several plan lines (product x month); the
    least-advanced status wins so a block isn't "Completed" until all of
    its lines are."""
    filters = {"docstatus": 1}
    if farm:
        filters["farm"] = farm
    if season:
        filters["season"] = season

    plans = frappe.get_all("Block Fertilizer Plan", filters=filters,
        fields=["block", "section", "application_month", "status"])

    today_date = frappe.utils.getdate(frappe.utils.today())
    priority = {"Behind Schedule": 0, "Pending": 1, "In Progress": 2, "Completed": 3}
    sections = {}

    for p in plans:
        if p.status in ("Applied", "Verified"):
            derived = "Completed"
        elif p.status == "Issued":
            derived = "In Progress"
        elif _is_month_passed(p.application_month, today_date):
            derived = "Behind Schedule"
        else:
            derived = "Pending"

        sec = sections.setdefault(p.section or "Unassigned", {})
        existing = sec.get(p.block)
        if not existing or priority[derived] < priority[existing]:
            sec[p.block] = derived

    result = []
    for section, blocks in sections.items():
        counts = {"Completed": 0, "In Progress": 0, "Pending": 0, "Behind Schedule": 0}
        for status in blocks.values():
            counts[status] += 1
        total = sum(counts.values())
        result.append({
            "section": section,
            "counts": counts,
            "total_blocks": total,
            "pct_complete": round(counts["Completed"] / total * 100, 1) if total else 0,
            "blocks": sorted(
                [{"block": b, "status": s} for b, s in blocks.items()],
                key=lambda r: r["block"],
            ),
        })

    return sorted(result, key=lambda r: r["section"])


@frappe.whitelist()
def get_farm_progress_overview(farm=None, season=None):
    """Farm-wide rollup of section/block progress, for headline KPIs."""
    sections = get_block_progress(farm=farm, season=season)

    counts = {"Completed": 0, "In Progress": 0, "Pending": 0, "Behind Schedule": 0}
    total_blocks = 0
    for s in sections:
        for k in counts:
            counts[k] += s["counts"][k]
        total_blocks += s["total_blocks"]

    return {
        "total_sections": len(sections),
        "total_blocks": total_blocks,
        "counts": counts,
        "pct_complete": round(counts["Completed"] / total_blocks * 100, 1) if total_blocks else 0,
    }


@frappe.whitelist()
def get_qty_planned_vs_actual(farm=None, season=None):
    """Total planned kg (submitted programme lines) vs total actual kg
    (submitted applications), for the whole farm/season."""
    prog_filter = {"docstatus": 1}
    if farm:
        prog_filter["farm"] = farm
    if season:
        prog_filter["season"] = season
    programmes = frappe.get_all("Fertilizer Programme", filters=prog_filter, fields=["name"])

    planned = 0
    for prog in programmes:
        doc = frappe.get_doc("Fertilizer Programme", prog.name)
        planned += sum(flt(l.total_kg) for l in doc.get("programme_lines", []))

    plan_filter = {"docstatus": 1}
    if farm:
        plan_filter["farm"] = farm
    if season:
        plan_filter["season"] = season
    plan_names = frappe.get_all("Block Fertilizer Plan", filters=plan_filter, pluck="name")

    actual = 0
    if plan_names:
        actual = flt(frappe.db.sql("""
            SELECT SUM(actual_quantity_applied_kg) FROM `tabFertilizer Application`
            WHERE docstatus = 1 AND block_fertilizer_plan IN %(plans)s
        """, {"plans": plan_names})[0][0] or 0)

    remaining = max(planned - actual, 0)
    variance = actual - planned

    return {
        "planned_kg": round(planned, 1),
        "actual_kg": round(actual, 1),
        "remaining_kg": round(remaining, 1),
        "variance_kg": round(variance, 1),
        "variance_pct": round(variance / planned * 100, 1) if planned else 0,
    }


@frappe.whitelist()
def get_section_usage_breakdown(farm=None, season=None):
    """Planned vs actual kg per section."""
    prog_filter = {"docstatus": 1}
    if farm:
        prog_filter["farm"] = farm
    if season:
        prog_filter["season"] = season
    programmes = frappe.get_all("Fertilizer Programme", filters=prog_filter, fields=["name"])

    planned = {}
    for prog in programmes:
        doc = frappe.get_doc("Fertilizer Programme", prog.name)
        for line in doc.get("programme_lines", []):
            planned[line.section] = planned.get(line.section, 0) + flt(line.total_kg)

    conditions = ["fa.docstatus = 1", "bfp.docstatus = 1"]
    values = {}
    if farm:
        conditions.append("bfp.farm = %(farm)s")
        values["farm"] = farm
    if season:
        conditions.append("bfp.season = %(season)s")
        values["season"] = season

    rows = frappe.db.sql(f"""
        SELECT bfp.section AS section, SUM(fa.actual_quantity_applied_kg) AS actual_kg
        FROM `tabFertilizer Application` fa
        JOIN `tabBlock Fertilizer Plan` bfp ON bfp.name = fa.block_fertilizer_plan
        WHERE {" AND ".join(conditions)}
        GROUP BY bfp.section
    """, values, as_dict=True)
    actual = {r.section: flt(r.actual_kg) for r in rows}

    sections = sorted(set(list(planned.keys()) + list(actual.keys())))
    return [
        {
            "section": s,
            "planned_kg": round(planned.get(s, 0), 1),
            "actual_kg": round(actual.get(s, 0), 1),
        }
        for s in sections
    ]


@frappe.whitelist()
def get_partial_applications(farm=None, season=None):
    """Applications not done in full - the closest real signal to a field
    exception, using applied_in_full/partial_reason (there's no typed
    exception log yet)."""
    filters = {"docstatus": 1, "applied_in_full": 0}
    if farm:
        filters["farm"] = farm

    apps = frappe.get_all("Fertilizer Application", filters=filters,
        fields=["name", "block", "fertilizer_product", "application_date",
                "planned_quantity_kg", "actual_quantity_applied_kg",
                "partial_reason", "block_fertilizer_plan"],
        order_by="application_date desc")

    if season:
        plan_names = set(frappe.get_all("Block Fertilizer Plan", filters={"season": season}, pluck="name"))
        apps = [a for a in apps if a.block_fertilizer_plan in plan_names]

    return apps


@frappe.whitelist()
def get_operator_activity(farm=None, season=None):
    """Applications count and total kg per applied_by Employee - the
    closest real signal to applicator productivity (only one operator is
    recorded per application, not a crew)."""
    filters = {"docstatus": 1}
    if farm:
        filters["farm"] = farm
    apps = frappe.get_all("Fertilizer Application", filters=filters,
        fields=["applied_by", "actual_quantity_applied_kg", "block_fertilizer_plan"])

    if season:
        plan_names = set(frappe.get_all("Block Fertilizer Plan", filters={"season": season}, pluck="name"))
        apps = [a for a in apps if a.block_fertilizer_plan in plan_names]

    stats = {}
    for a in apps:
        key = a.applied_by or "Unassigned"
        s = stats.setdefault(key, {"applications": 0, "total_kg": 0})
        s["applications"] += 1
        s["total_kg"] += flt(a.actual_quantity_applied_kg)

    return sorted(
        [{"applied_by": k, "applications": v["applications"], "total_kg": round(v["total_kg"], 1)}
         for k, v in stats.items()],
        key=lambda x: x["applications"], reverse=True,
    )


@frappe.whitelist()
def get_variance_alerts(farm=None, season=None):
    """Applications whose actual-vs-planned variance exceeds the configured
    threshold (same threshold Fertilizer Application's own variance email
    alert uses)."""
    settings = frappe.get_cached_doc("Crop Nutrition Planning Settings")
    threshold = flt(settings.variance_threshold_pct or 15)

    filters = {"docstatus": 1}
    if farm:
        filters["farm"] = farm
    apps = frappe.get_all("Fertilizer Application", filters=filters,
        fields=["name", "block", "fertilizer_product", "application_date",
                "planned_quantity_kg", "actual_quantity_applied_kg", "variance_kg",
                "block_fertilizer_plan"])

    if season:
        plan_names = set(frappe.get_all("Block Fertilizer Plan", filters={"season": season}, pluck="name"))
        apps = [a for a in apps if a.block_fertilizer_plan in plan_names]

    alerts = []
    for a in apps:
        if not a.planned_quantity_kg:
            continue
        pct = abs(flt(a.variance_kg)) / flt(a.planned_quantity_kg) * 100
        if pct > threshold:
            alerts.append({**a, "variance_pct": round(pct, 1)})

    return sorted(alerts, key=lambda x: x["variance_pct"], reverse=True)


@frappe.whitelist()
def get_computed_budget(farm=None, season=None):
    """Estimated fertilizer cost = season requirement (from submitted
    Programme Lines) x Item buying price. Available immediately, without
    needing a manually created + submitted Fertilizer Budget document
    (that doctype is still used for tracking *actual* spend against
    Purchase Receipts - this is the always-on estimate)."""
    prog_filter = {"docstatus": 1}
    if farm:
        prog_filter["farm"] = farm
    if season:
        prog_filter["season"] = season
    programmes = frappe.get_all("Fertilizer Programme", filters=prog_filter, fields=["name"])

    required = {}
    for prog in programmes:
        doc = frappe.get_doc("Fertilizer Programme", prog.name)
        for line in doc.get("programme_lines", []):
            required[line.fertilizer_product] = required.get(line.fertilizer_product, 0) + flt(line.total_kg)

    price_cache = {}
    def price(product):
        if product not in price_cache:
            price_cache[product] = flt(frappe.db.get_value(
                "Item Price", {"item_code": product, "buying": 1}, "price_list_rate"))
        return price_cache[product]

    lines = []
    total = 0
    for product, qty in required.items():
        rate = price(product)
        cost = qty * rate
        total += cost
        lines.append({"product": product, "qty_kg": round(qty, 1), "unit_price": rate, "cost": round(cost, 0)})

    return {"total_cost": round(total, 0), "lines": sorted(lines, key=lambda x: x["cost"], reverse=True)}


@frappe.whitelist()
def get_available_farms():
    """Return the list of distinct custom_farm values on Block warehouses, for the sync dialog."""
    farms = frappe.db.sql("""
        SELECT DISTINCT custom_farm FROM `tabWarehouse`
        WHERE warehouse_type = 'Block' AND custom_farm IS NOT NULL AND custom_farm != ''
        ORDER BY custom_farm
    """, as_dict=True)
    return [f.custom_farm for f in farms]