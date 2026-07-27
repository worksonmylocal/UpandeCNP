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
def get_dashboard_summary(season=None):
    """Return headline numbers for the dashboard."""
    plan_filter = {"docstatus": 1}
    if season and season != "All Seasons":
        plan_filter["season"] = season

    plans = frappe.get_all("Block Fertilizer Plan", filters=plan_filter,
                           fields=["name", "status", "total_kg_required", "block"])

    total_plans = len(plans)
    applied = sum(1 for p in plans if p.status == "Applied")
    issued = sum(1 for p in plans if p.status == "Issued")
    planned = sum(1 for p in plans if p.status == "Planned")
    total_kg = sum(flt(p.total_kg_required) for p in plans)

    blocks = len(set(p.block for p in plans))

    # Pending store requests
    pending_requests = frappe.db.count("Fertilizer Store Request", {"status": "Requested"})

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
def get_monthly_breakdown(season=None):
    """Return quantity and cost per month across the programme."""
    prog_filter = {"docstatus": 1}
    if season and season != "All Seasons":
        prog_filter["season"] = season

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
def get_product_breakdown(season=None):
    """Return total quantity per product."""
    prog_filter = {"docstatus": 1}
    if season and season != "All Seasons":
        prog_filter["season"] = season

    programmes = frappe.get_all("Fertilizer Programme", filters=prog_filter, fields=["name"])
    products = {}
    for prog in programmes:
        doc = frappe.get_doc("Fertilizer Programme", prog.name)
        for line in doc.get("programme_lines", []):
            products[line.fertilizer_product] = products.get(line.fertilizer_product, 0) + flt(line.total_kg)

    return [{"product": p, "qty": round(q, 0)} for p, q in
            sorted(products.items(), key=lambda x: x[1], reverse=True)]


@frappe.whitelist()
def get_recent_activity():
    """Return the last 8 fertilizer applications."""
    apps = frappe.get_all("Fertilizer Application", filters={"docstatus": 1},
        fields=["block", "fertilizer_product", "actual_quantity_applied_kg",
                "application_date", "applied_by", "applied_in_full"],
        order_by="creation desc", limit=8)
    return apps


@frappe.whitelist()
def get_stock_levels():
    """Return current stock for each fertilizer item."""
    warehouse = frappe.db.get_single_value("Crop Nutrition Planning Settings", "fertilizer_warehouse")
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
def get_budget_summary(season=None):
    """Budget vs actual spend and cost per hectare."""
    filters = {"docstatus": 1}
    if season and season != "All Seasons":
        filters["season"] = season

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
def get_upcoming_and_overdue():
    """Plans due in the next 30 days, and overdue plans (month passed, not applied)."""
    from frappe.utils import today, getdate, date_diff

    months = ["January","February","March","April","May","June",
              "July","August","September","October","November","December"]
    today_date = getdate(today())

    plans = frappe.get_all("Block Fertilizer Plan",
        filters={"docstatus": 1, "status": ["in", ["Planned", "Issued"]]},
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
def get_leaf_deficiency_grid(season=None):
    """Grid of blocks x nutrients showing status (Deficient/Adequate/Excess)."""
    filters = {"docstatus": 1}
    if season and season != "All Seasons":
        filters["season"] = season

    analyses = frappe.get_all("Leaf Analysis", filters=filters, fields=["name", "block"])

    nutrients = ["N", "P", "K", "Ca", "Mg", "S", "Zn", "B"]
    grid = []
    for a in analyses:
        doc = frappe.get_doc("Leaf Analysis", a.name)
        row = {"block": a.block, "cells": {}}
        for r in doc.get("nutrient_results", []):
            if r.nutrient in nutrients:
                row["cells"][r.nutrient] = r.status or "—"
        grid.append(row)

    return {"nutrients": nutrients, "grid": grid}


@frappe.whitelist()
def get_stock_coverage(season=None):
    """Stock on hand vs remaining requirement per product."""
    prog_filter = {"docstatus": 1}
    if season and season != "All Seasons":
        prog_filter["season"] = season

    programmes = frappe.get_all("Fertilizer Programme", filters=prog_filter, fields=["name"])
    required = {}
    for prog in programmes:
        doc = frappe.get_doc("Fertilizer Programme", prog.name)
        for line in doc.get("programme_lines", []):
            required[line.fertilizer_product] = required.get(line.fertilizer_product, 0) + flt(line.total_kg)

    warehouse = frappe.db.get_single_value("Crop Nutrition Planning Settings", "fertilizer_warehouse")
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
def get_manager_kpis(season=None):
    """Headline KPIs for the managerial dashboard."""
    plan_filter = {"docstatus": 1}
    if season and season != "All Seasons":
        plan_filter["season"] = season

    plans = frappe.get_all("Block Fertilizer Plan", filters=plan_filter,
                           fields=["status", "block", "total_kg_required"])
    total = len(plans)
    applied = sum(1 for p in plans if p.status == "Applied")
    pct_complete = round(applied / total * 100, 1) if total else 0

    # Budget
    bfilter = {"docstatus": 1}
    if season and season != "All Seasons":
        bfilter["season"] = season
    budgets = frappe.get_all("Fertilizer Budget", filters=bfilter,
        fields=["total_budget_ksh", "total_actual", "cost_per_ha_actual", "cost_per_ha_budget"])
    total_budget = sum(flt(b.total_budget_ksh) for b in budgets)
    total_actual = sum(flt(b.total_actual) for b in budgets)
    cph = [flt(b.cost_per_ha_actual) for b in budgets if b.cost_per_ha_actual]
    cph_b = [flt(b.cost_per_ha_budget) for b in budgets if b.cost_per_ha_budget]

    # Overdue count (reuse logic)
    overdue = len(get_upcoming_and_overdue().get("overdue", []))

    # Pending requests
    pending = frappe.db.count("Fertilizer Store Request", {"status": "Requested"})

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
def get_yield_tier_distribution(season=None):
    """How many blocks fall in each yield tier."""
    prog_filter = {"docstatus": 1}
    if season and season != "All Seasons":
        prog_filter["season"] = season
    programmes = frappe.get_all("Fertilizer Programme", filters=prog_filter, fields=["name"])

    tiers = {}
    for prog in programmes:
        doc = frappe.get_doc("Fertilizer Programme", prog.name)
        for row in doc.get("block_yield_data", []):
            # Recompute tier from yield
            y = flt(row.actual_yield_t_ha)
            if y >= 22: tier = "24T"
            elif y >= 18.5: tier = "20T"
            elif y >= 14: tier = "18T"
            else: tier = "15T"
            tiers[tier] = tiers.get(tier, 0) + 1

    order = ["15T", "18T", "20T", "24T"]
    return [{"tier": t, "count": tiers.get(t, 0)} for t in order]


@frappe.whitelist()
def get_application_pace(season=None):
    """Month-by-month: planned applications vs actually applied."""
    months = ["January","February","March","April","May","June",
              "July","August","September","October","November","December"]

    plan_filter = {"docstatus": 1}
    if season and season != "All Seasons":
        plan_filter["season"] = season

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
def get_leaf_deficiency_summary(season=None):
    """Count of blocks deficient per nutrient."""
    filters = {"docstatus": 1}
    if season and season != "All Seasons":
        filters["season"] = season
    analyses = frappe.get_all("Leaf Analysis", filters=filters, fields=["name"])

    nutrients = ["N", "P", "K", "Ca", "Mg", "S", "Zn", "B"]
    deficient = {n: 0 for n in nutrients}
    for a in analyses:
        doc = frappe.get_doc("Leaf Analysis", a.name)
        for r in doc.get("nutrient_results", []):
            if r.nutrient in deficient and r.status == "Deficient":
                deficient[r.nutrient] += 1

    return [{"nutrient": n, "count": deficient[n]} for n in nutrients if deficient[n] > 0]