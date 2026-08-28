"""
Whitelisted API methods for the mobile field page.
These reuse the existing DocType logic so the workflow stays consistent.
"""

import frappe
from frappe.utils import flt, today
from upandecnp.upandecnp.utils.farm_permissions import resolve_farm_scope
from upandecnp.upandecnp.utils.integration import get_grouped_sum


def _current_employee():
    return frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")


def _section_scope_guard(section):
    """frappe.get_all() bypasses permission_query_conditions, so every
    endpoint that takes a raw section/block name (not already routed through
    resolve_farm_scope's own farm param) needs to check the caller is
    allowed to see that section's farm explicitly."""
    farm = frappe.db.get_value("Section", section, "farm")
    resolve_farm_scope(frappe.session.user, farm)


def _block_scope_guard(block):
    farm = frappe.db.get_value("Farm Block", block, "farm")
    resolve_farm_scope(frappe.session.user, farm)


@frappe.whitelist(allow_guest=True)
def mobile_login(usr, pwd):
    """Token login for the bundled mobile app. Session cookies don't survive
    the app's cross-origin calls to the server - browsers only send
    SameSite=Lax cookies (Frappe's default) on top-level navigation, never
    on cross-site fetch/XHR - so the app authenticates once here and uses
    the returned api_key/api_secret as an Authorization header on every
    later call instead of relying on a cookie."""
    from frappe.core.doctype.user.user import User

    result = User.find_by_credentials(usr, pwd)
    if not result or not result.get("is_authenticated") or not result.get("enabled"):
        frappe.throw("Incorrect user or password.", frappe.AuthenticationError)

    user_doc = frappe.get_doc("User", result["name"])
    if not user_doc.api_key:
        user_doc.api_key = frappe.generate_hash(length=15)
    api_secret = frappe.generate_hash(length=15)
    user_doc.api_secret = api_secret
    user_doc.save(ignore_permissions=True)
    # api_secret is a Password field - it's masked on user_doc in-memory as
    # soon as save() runs, so the plaintext above (not user_doc.api_secret)
    # is the only copy left to return.

    return {
        "api_key": user_doc.api_key,
        "api_secret": api_secret,
        "full_name": user_doc.full_name,
        "user": user_doc.name,
    }


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
    from upandecnp.upandecnp.utils.integration import categorize_request_status

    _block_scope_guard(block)
    plans = frappe.get_all(
        "Block Fertilizer Plan",
        filters={"docstatus": 1, "block": block, "status": ["in", ["Planned", "Issued"]]},
        fields=["name", "fertilizer_product", "application_month",
                "total_kg_required", "status"],
        order_by="application_month",
    )

    for p in plans:
        # Find the most recent store request (Material Request) for this plan
        requests = frappe.get_all(
            "Material Request",
            filters={"custom_block_fertilizer_plan": p["name"]},
            fields=["name", "status", "workflow_state"],
            order_by="creation desc",
            limit=1,
        )
        if requests:
            p["request_name"] = requests[0].name
            p["request_status"] = categorize_request_status(requests[0].workflow_state or requests[0].status)
        else:
            p["request_name"] = None
            p["request_status"] = None

    return plans


@frappe.whitelist()
def get_sections_with_pending_work(farm=None):
    """Sections that have at least one Planned or Issued Block Fertilizer
    Plan, with a pending-plan count - the entry point for the field app's
    Upcoming Applications flow (Sections first, then plans within one)."""
    farm = resolve_farm_scope(frappe.session.user, farm)
    filters = {"docstatus": 1, "status": ["in", ["Planned", "Issued"]]}
    if farm:
        filters["farm"] = farm

    plans = frappe.get_all("Block Fertilizer Plan", filters=filters, fields=["section"])
    counts = {}
    for p in plans:
        if p.section:
            counts[p.section] = counts.get(p.section, 0) + 1

    return sorted(
        [{"section": section, "pending_count": count} for section, count in counts.items()],
        key=lambda x: x["section"],
    )


@frappe.whitelist()
def get_pending_plans_for_section(section):
    """Same shape as get_pending_plans_for_block, scoped to every block in
    a Section instead of a single block."""
    from upandecnp.upandecnp.utils.integration import categorize_request_status

    _section_scope_guard(section)
    plans = frappe.get_all(
        "Block Fertilizer Plan",
        filters={"docstatus": 1, "section": section, "status": ["in", ["Planned", "Issued"]]},
        fields=["name", "block", "fertilizer_product", "application_month",
                "total_kg_required", "status"],
        order_by="block, application_month",
    )

    for p in plans:
        requests = frappe.get_all(
            "Material Request",
            filters={"custom_block_fertilizer_plan": p["name"]},
            fields=["name", "status", "workflow_state"],
            order_by="creation desc",
            limit=1,
        )
        if requests:
            p["request_name"] = requests[0].name
            p["request_status"] = categorize_request_status(requests[0].workflow_state or requests[0].status)
        else:
            p["request_name"] = None
            p["request_status"] = None

    return plans


@frappe.whitelist()
def get_sections_with_issued_work(farm=None):
    """Same shape as get_sections_with_pending_work, but only counts blocks
    that have already been issued fertilizer from store - the entry point
    for Record Application, which should only ever offer blocks that are
    actually ready to record against."""
    farm = resolve_farm_scope(frappe.session.user, farm)
    filters = {"docstatus": 1, "status": "Issued"}
    if farm:
        filters["farm"] = farm

    plans = frappe.get_all("Block Fertilizer Plan", filters=filters, fields=["section"])
    counts = {}
    for p in plans:
        if p.section:
            counts[p.section] = counts.get(p.section, 0) + 1

    return sorted(
        [{"section": section, "pending_count": count} for section, count in counts.items()],
        key=lambda x: x["section"],
    )


@frappe.whitelist()
def get_issued_blocks_in_section(section):
    """Blocks within a section that have at least one Issued Block
    Fertilizer Plan - used by Record Application's block picker so a
    supervisor can only select blocks actually ready to record against."""
    _section_scope_guard(section)
    plans = frappe.get_all(
        "Block Fertilizer Plan",
        filters={"docstatus": 1, "section": section, "status": "Issued"},
        fields=["block"],
    )
    counts = {}
    for p in plans:
        counts[p.block] = counts.get(p.block, 0) + 1
    return sorted(
        [{"block": block, "issued_count": count} for block, count in counts.items()],
        key=lambda x: x["block"],
    )


@frappe.whitelist()
def get_all_sections(farm=None):
    """Every active Section for the caller's farm scope - used by the
    add-applicator and reassign-block pickers, which need to reach any
    block regardless of whether it currently has pending fertilizer work."""
    farm = resolve_farm_scope(frappe.session.user, farm)
    filters = {"is_active": 1}
    if farm:
        filters["farm"] = farm
    return frappe.get_all("Section", filters=filters, fields=["name", "section_name"], order_by="section_name")


@frappe.whitelist()
def get_blocks_in_section(section):
    """Every Farm Block in a section, regardless of fertilizer-plan status -
    the pick list backing the add-applicator and reassign-block flows."""
    _section_scope_guard(section)
    return frappe.get_all("Farm Block", filters={"section": section}, fields=["name"], order_by="name")


@frappe.whitelist()
def get_applications_today(farm=None):
    """Count of Fertilizer Applications recorded today - the field app's
    home-screen headline stat."""
    farm = resolve_farm_scope(frappe.session.user, farm)
    filters = {"docstatus": 1, "application_date": frappe.utils.today()}
    if farm:
        filters["farm"] = farm
    return frappe.db.count("Fertilizer Application", filters)


@frappe.whitelist()
def create_store_request(block_fertilizer_plan, quantity, employee=None):
    """Create a Material Request (Material Issue) from the field page, in the
    same format used for every other store-issue category on this site."""
    from upandecnp.upandecnp.utils.integration import create_material_issue_request, categorize_request_status

    if not employee:
        employee = _current_employee()

    mr = create_material_issue_request(block_fertilizer_plan, quantity, employee)
    return {"name": mr.name, "status": categorize_request_status(mr.workflow_state or mr.status)}


@frappe.whitelist()
def get_store_requests(farm=None):
    """All Fertiliser Issuing Material Requests for the caller's farm scope,
    with a colour-coded status - the field app's "status of requests"
    view."""
    from upandecnp.upandecnp.utils.integration import categorize_request_status

    farm = resolve_farm_scope(frappe.session.user, farm)
    filters = {"custom_request_type": "Fertiliser Issuing"}
    if farm:
        filters["custom_farm"] = farm

    requests = frappe.get_all(
        "Material Request",
        filters=filters,
        fields=["name", "custom_block_fertilizer_plan", "workflow_state", "status",
                "per_ordered", "transaction_date", "docstatus"],
        order_by="creation desc",
        limit_page_length=100,
    )
    plan_names = list({r.custom_block_fertilizer_plan for r in requests if r.custom_block_fertilizer_plan})
    plans = {
        p.name: p for p in frappe.get_all(
            "Block Fertilizer Plan",
            filters={"name": ["in", plan_names]},
            fields=["name", "block", "fertilizer_product"],
        )
    } if plan_names else {}

    result = []
    for r in requests:
        plan = plans.get(r.custom_block_fertilizer_plan)
        if r.docstatus == 1 and flt(r.per_ordered) >= 100:
            category = "Issued"
        else:
            category = categorize_request_status(r.workflow_state or r.status)
        result.append({
            "name": r.name,
            "block": plan.block if plan else None,
            "fertilizer_product": plan.fertilizer_product if plan else None,
            "date": r.transaction_date,
            "status": category,
        })
    return result


@frappe.whitelist()
def record_application(block_fertilizer_plan, actual_quantity, applied_in_full,
                       partial_reason=None, employee=None, store_request=None, operators=None):
    """Create a Fertilizer Application from the field page. `employee` is the
    supervisor recording the entry (defaults to the logged-in user's
    Employee); `operators` is the list of applicators who actually did the
    work (a block is too big for one person), picked from the supervisor's
    team roster (see get_my_applicators)."""
    plan = frappe.get_doc("Block Fertilizer Plan", block_fertilizer_plan)

    if not employee:
        employee = _current_employee()

    if operators and isinstance(operators, str):
        operators = frappe.parse_json(operators)
    operators = operators or []

    for op in operators:
        if not _is_my_applicator(op, employee):
            frappe.throw(f"{op} is not on your team.", frappe.PermissionError)

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
        "supervisor": employee,
        "applicators": [{"employee": op} for op in operators],
    })
    doc.insert(ignore_permissions=True)
    doc.submit()
    return {"name": doc.name, "status": "Applied"}


@frappe.whitelist()
def get_issued_request_for_plan(block_fertilizer_plan):
    """Find a fully-issued Material Request for this plan, so the app can link
    to it. `per_ordered` is ERPNext's own tracking of how much of the
    requested qty has actually moved out via Stock Entry - 100% means issued
    in full, regardless of which workflow state it's sitting in."""
    mr = frappe.get_all(
        "Material Request",
        filters={
            "custom_block_fertilizer_plan": block_fertilizer_plan,
            "docstatus": 1,
            "per_ordered": [">=", 100],
        },
        fields=["name"],
        limit=1,
    )
    return mr[0].name if mr else None


def _is_my_applicator(employee, supervisor):
    """Guards every team-scoped action (attendance, block assignment,
    recording an application) - a supervisor may only act on Employees on
    their own field team. Uses custom_field_supervisor (upandecnp's own
    field-team assignment), not the HR reports_to line - deliberately kept
    separate so this app never rewrites the real org chart."""
    return bool(employee) and bool(supervisor) and frappe.db.exists(
        "Employee", {"name": employee, "custom_field_supervisor": supervisor, "status": "Active"}
    )


@frappe.whitelist()
def get_my_applicators():
    """The current supervisor's field team - Employees whose
    custom_field_supervisor is the logged-in user's own Employee record -
    with today's attendance status. Empty list means no one has been added
    to this supervisor's team yet (see add_applicator), not that nothing
    is wrong."""
    supervisor = _current_employee()
    if not supervisor:
        return []

    applicators = frappe.get_all(
        "Employee",
        filters={"custom_field_supervisor": supervisor, "status": "Active"},
        fields=["name", "employee_name", "custom_assigned_block"],
        order_by="employee_name",
    )
    if not applicators:
        return []

    today_attendance = {
        a.employee: a.status
        for a in frappe.get_all(
            "Field Attendance",
            filters={
                "employee": ["in", [a.name for a in applicators]],
                "attendance_date": today(),
            },
            fields=["employee", "status"],
        )
    }
    for a in applicators:
        a["attendance_status"] = today_attendance.get(a.name)
    return applicators


@frappe.whitelist()
def get_applicators_for_block(block):
    """Applicators on the current supervisor's team who are specifically
    assigned to this block - Record Application only offers people actually
    assigned there (not the whole team), since who worked a given block is
    what the entry needs to reflect."""
    supervisor = _current_employee()
    if not supervisor:
        return []
    return frappe.get_all(
        "Employee",
        filters={"custom_field_supervisor": supervisor, "custom_assigned_block": block, "status": "Active"},
        fields=["name", "employee_name"],
        order_by="employee_name",
    )


@frappe.whitelist()
def get_my_applicators_by_section():
    """The current supervisor's field team, grouped by Section and then by
    the specific Block each applicator is assigned to (an "Unassigned"
    section/block bucket for anyone without a block yet) - backs the Manage
    Team overview, the reassign flow, and the per-block quick-add shortcut."""
    applicators = get_my_applicators()
    if not applicators:
        return []

    blocks = {a.custom_assigned_block for a in applicators if a.custom_assigned_block}
    block_section = {}
    if blocks:
        block_section = {
            b.name: b.section
            for b in frappe.get_all("Farm Block", filters={"name": ["in", list(blocks)]}, fields=["name", "section"])
        }

    sections = {}
    for a in applicators:
        block = a.custom_assigned_block
        section = block_section.get(block) or "Unassigned"
        block_label = block or "No block assigned"
        sections.setdefault(section, {}).setdefault(block_label, []).append(a)

    result = []
    for section, block_map in sections.items():
        block_list = sorted(
            [{"block": block, "applicators": apps} for block, apps in block_map.items()],
            key=lambda x: (x["block"] == "No block assigned", x["block"]),
        )
        result.append({"section": section, "blocks": block_list})

    return sorted(result, key=lambda x: (x["section"] == "Unassigned", x["section"]))


@frappe.whitelist()
def get_available_employees_for_team():
    """Active, unassigned Employees in the caller's own company - the pick
    list for Manage Team's "Add Applicator" screen. Scoped to company
    because this site's Employee list spans unrelated businesses (e.g.
    Karen Roses) that share the same Frappe instance as upandecnp's own
    company; without this a supervisor would have to search thousands of
    irrelevant names. Someone already on a team doesn't show up here;
    they're removed from their current team first if they need to move."""
    supervisor = _current_employee()
    filters = {"status": "Active", "custom_field_supervisor": ["is", "not set"]}
    company = frappe.db.get_value("Employee", supervisor, "company") if supervisor else None
    if company:
        filters["company"] = company
    return frappe.get_all(
        "Employee",
        filters=filters,
        fields=["name", "employee_name"],
        order_by="employee_name",
    )


@frappe.whitelist()
def add_applicator(employee):
    """Add an Employee to the current supervisor's field team. Any active
    Employee not already on someone else's team can be added - this only
    ever touches custom_field_supervisor, never the HR reports_to line."""
    supervisor = _current_employee()
    if not supervisor:
        frappe.throw("You don't have an Employee record linked to your account.")

    if not frappe.db.exists("Employee", {"name": employee, "status": "Active"}):
        frappe.throw("That employee doesn't exist or isn't active.")

    current_supervisor = frappe.db.get_value("Employee", employee, "custom_field_supervisor")
    if current_supervisor and current_supervisor != supervisor:
        frappe.throw("That employee is already on another supervisor's team.")

    frappe.db.set_value("Employee", employee, "custom_field_supervisor", supervisor)
    return {"employee": employee, "status": "added"}


@frappe.whitelist()
def remove_applicator(employee):
    """Remove an Employee from the current supervisor's field team - a
    supervisor may only remove their own team members."""
    supervisor = _current_employee()
    if not _is_my_applicator(employee, supervisor):
        frappe.throw("This employee is not on your team.", frappe.PermissionError)

    frappe.db.set_value("Employee", employee, "custom_field_supervisor", None)
    frappe.db.set_value("Employee", employee, "custom_assigned_block", None)
    return {"employee": employee, "status": "removed"}


@frappe.whitelist()
def assign_block(employee, block):
    """Assign (or clear, if block is empty) an applicator's current block -
    only for employees on the calling supervisor's own team."""
    supervisor = _current_employee()
    if not _is_my_applicator(employee, supervisor):
        frappe.throw("This employee is not on your team.", frappe.PermissionError)

    if block and not frappe.db.exists("Farm Block", block):
        frappe.throw(f"Block {block} does not exist.")

    frappe.db.set_value("Employee", employee, "custom_assigned_block", block or None)
    return {"employee": employee, "block": block}


@frappe.whitelist()
def mark_attendance(employee, status):
    """Mark (or update) today's Field Attendance for an applicator on the
    current supervisor's team. Idempotent per employee/day - a second call
    the same day updates the existing row instead of duplicating it."""
    if status not in ("Present", "Absent"):
        frappe.throw("Status must be Present or Absent.")

    supervisor = _current_employee()
    if not _is_my_applicator(employee, supervisor):
        frappe.throw("This employee is not on your team.", frappe.PermissionError)

    existing = frappe.db.exists("Field Attendance", {
        "employee": employee,
        "attendance_date": today(),
    })
    if existing:
        doc = frappe.get_doc("Field Attendance", existing)
        doc.status = status
        doc.marked_by = supervisor
        doc.save(ignore_permissions=True)
    else:
        doc = frappe.get_doc({
            "doctype": "Field Attendance",
            "employee": employee,
            "attendance_date": today(),
            "status": status,
            "marked_by": supervisor,
        })
        doc.insert(ignore_permissions=True)
    return {"name": doc.name, "status": doc.status}


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
    """Return active farms, for the dashboard's farm selector - scoped to
    whatever the caller's Agronomist/Farm Manager role restricts them to,
    same as every other dashboard call (see resolve_farm_scope)."""
    from upandecnp.upandecnp.utils.farm_permissions import get_agronomist_farms, get_manager_farms

    farms = frappe.get_all("CNP Farm", filters={"is_active": 1}, fields=["name"], order_by="name")
    if "System Manager" in frappe.get_roles(frappe.session.user):
        return farms

    allowed = set(get_agronomist_farms(frappe.session.user) + get_manager_farms(frappe.session.user))
    if not allowed:
        return farms
    return [f for f in farms if f.name in allowed]


@frappe.whitelist()
def get_dashboard_summary(season=None, farm=None):
    """Return headline numbers for the dashboard."""
    farm = resolve_farm_scope(frappe.session.user, farm)
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

    # Pending store requests (Material Requests not yet fully issued from store)
    request_filter = {"custom_request_type": "Fertiliser Issuing", "per_ordered": ["<", 100]}
    if farm:
        request_filter["custom_farm"] = farm
    pending_requests = frappe.db.count("Material Request", request_filter)

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
    farm = resolve_farm_scope(frappe.session.user, farm)
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
    farm = resolve_farm_scope(frappe.session.user, farm)
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
    farm = resolve_farm_scope(frappe.session.user, farm)
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
    """Current stock for every fertilizer product actually scheduled for use -
    pulled from Production Calendar's Fertilizer Schedule (the real source of
    which products matter for a farm), not a fixed list. Scoping by farm also
    scopes which products are even considered, not just which warehouse."""
    farm = resolve_farm_scope(frappe.session.user, farm)
    calendar_filters = {"farm": farm} if farm else {}
    calendar_names = frappe.get_all("Production Calendar", filters=calendar_filters, pluck="name")

    products = []
    if calendar_names:
        products = frappe.get_all(
            "Fertilizer Schedule",
            filters={"parent": ["in", calendar_names]},
            pluck="fertilizer_product",
            distinct=True,
        )
    if not products:
        return []

    item_names = {
        row.item_code: row.item_name
        for row in frappe.get_all("Item", filters={"name": ["in", products]}, fields=["name as item_code", "item_name"])
    }

    warehouse = frappe.db.get_value("CNP Farm", farm, "warehouse") if farm else None
    bin_filters = {"item_code": ["in", products]}
    if warehouse:
        bin_filters["warehouse"] = warehouse
    stock_by_code = get_grouped_sum("Bin", "actual_qty", "item_code", bin_filters)

    result = []
    for code in products:
        result.append({
            "product": item_names.get(code, code),
            "item_code": code,
            "qty": round(stock_by_code.get(code, 0), 0),
        })
    return sorted(result, key=lambda x: x["product"])

# ---------------------------------------------------------------------------
# Dashboard - extended panels
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_budget_summary(season=None, farm=None):
    """Budget vs actual spend and cost per hectare."""
    farm = resolve_farm_scope(frappe.session.user, farm)
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
    farm = resolve_farm_scope(frappe.session.user, farm)
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
    farm = resolve_farm_scope(frappe.session.user, farm)
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
    farm = resolve_farm_scope(frappe.session.user, farm)
    prog_filter = {"docstatus": 1}
    if season and season != "All Seasons":
        prog_filter["season"] = season
    if farm:
        prog_filter["farm"] = farm

    programme_names = frappe.get_all("Fertilizer Programme", filters=prog_filter, pluck="name")
    required = {}
    if programme_names:
        required = get_grouped_sum(
            "Fertilizer Programme Line", "total_kg", "fertilizer_product",
            {"parent": ["in", programme_names]},
        )

    warehouse = frappe.db.get_value("CNP Farm", farm, "warehouse") if farm else None
    stock_by_product = {}
    if required:
        bin_filters = {"item_code": ["in", list(required.keys())]}
        if warehouse:
            bin_filters["warehouse"] = warehouse
        stock_by_product = get_grouped_sum("Bin", "actual_qty", "item_code", bin_filters)

    result = []
    for product, need in required.items():
        stock = stock_by_product.get(product, 0)
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
    farm = resolve_farm_scope(frappe.session.user, farm)
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
    farm = resolve_farm_scope(frappe.session.user, farm)
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
    farm = resolve_farm_scope(frappe.session.user, farm)
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
    farm = resolve_farm_scope(frappe.session.user, farm)
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
    farm = resolve_farm_scope(frappe.session.user, farm)
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
    farm = resolve_farm_scope(frappe.session.user, farm)
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
    farm = resolve_farm_scope(frappe.session.user, farm)
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
    farm = resolve_farm_scope(frappe.session.user, farm)
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
    farm = resolve_farm_scope(frappe.session.user, farm)
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
    farm = resolve_farm_scope(frappe.session.user, farm)
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
def get_operator_activity(farm=None, season=None, employees=None, group_by="applied_by"):
    """Applications count and total kg, grouped by Employee. Defaults to
    `applied_by` (who recorded the entry - used by the dashboards). Pass
    group_by="operator" and an `employees` list to get real applicator
    productivity for a supervisor's team roster instead (see
    get_my_applicators) - `applied_by` is the recording supervisor, not
    necessarily who did the physical work. Since an application can now
    have several applicators (a block is too big for one person), an
    application's kg is counted once per applicator on it when grouping by
    operator - it's a per-person activity count, not a stock ledger."""
    farm = resolve_farm_scope(frappe.session.user, farm)
    if group_by not in ("applied_by", "operator"):
        frappe.throw("group_by must be 'applied_by' or 'operator'.")

    if employees and isinstance(employees, str):
        employees = frappe.parse_json(employees)

    if group_by == "operator":
        filters = {"parenttype": "Fertilizer Application"}
        if employees:
            filters["employee"] = ["in", employees]
        rows = frappe.get_all(
            "Fertilizer Application Applicator",
            filters=filters,
            fields=["employee", "parent"],
        )
        parents = list({r.parent for r in rows})
        if not parents:
            return []
        app_filters = {"docstatus": 1, "name": ["in", parents]}
        if farm:
            app_filters["farm"] = farm
        apps_by_name = {
            a.name: a for a in frappe.get_all(
                "Fertilizer Application", filters=app_filters,
                fields=["name", "actual_quantity_applied_kg", "block_fertilizer_plan"],
            )
        }
        if season:
            plan_names = set(frappe.get_all("Block Fertilizer Plan", filters={"season": season}, pluck="name"))
            apps_by_name = {k: v for k, v in apps_by_name.items() if v.block_fertilizer_plan in plan_names}

        stats = {}
        for r in rows:
            app = apps_by_name.get(r.parent)
            if not app:
                continue
            s = stats.setdefault(r.employee, {"applications": 0, "total_kg": 0})
            s["applications"] += 1
            s["total_kg"] += flt(app.actual_quantity_applied_kg)

        return sorted(
            [{"operator": k, "applications": v["applications"], "total_kg": round(v["total_kg"], 1)}
             for k, v in stats.items()],
            key=lambda x: x["applications"], reverse=True,
        )

    filters = {"docstatus": 1}
    if farm:
        filters["farm"] = farm
    if employees:
        filters["applied_by"] = ["in", employees]
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
    farm = resolve_farm_scope(frappe.session.user, farm)
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
    farm = resolve_farm_scope(frappe.session.user, farm)
    prog_filter = {"docstatus": 1}
    if farm:
        prog_filter["farm"] = farm
    if season:
        prog_filter["season"] = season
    programme_names = frappe.get_all("Fertilizer Programme", filters=prog_filter, pluck="name")

    required = {}
    if programme_names:
        required = get_grouped_sum(
            "Fertilizer Programme Line", "total_kg", "fertilizer_product",
            {"parent": ["in", programme_names]},
        )

    prices = {}
    if required:
        for row in frappe.get_all(
            "Item Price",
            filters={"item_code": ["in", list(required.keys())], "buying": 1},
            fields=["item_code", "price_list_rate"],
        ):
            prices.setdefault(row.item_code, flt(row.price_list_rate))

    lines = []
    total = 0
    for product, qty in required.items():
        rate = prices.get(product, 0)
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