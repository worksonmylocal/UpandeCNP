"""The Fertilizer Programme approval chain, generated as a Frappe Workflow.

A programme is built by an agronomist, reviewed by a consultant who may edit
it, and approved by the farm's own manager. Only then does it become the plan
the rest of the system works from.

Why a generated Workflow rather than bespoke state handling: the terminal state
carries doc_status=1, so Frappe's apply_workflow() calls doc.submit() on
approval - and Fertilizer Programme.on_submit() already creates the Block
Fertilizer Plans and Material Requests. Approval therefore *is* the act that
publishes the programme to the field app, with no extra wiring, and the
calculation engine's existing "cannot recalculate a submitted programme" guard
becomes "cannot recalculate an approved one" for free.

Why generated rather than a fixture: the farm-manager step is per-farm. A
Workflow Transition matches on role, so scoping it to a farm needs one
transition per farm, each conditioned on doc.farm, using the "Farm Manager
<Farm>" roles farm_permissions.py already trusts. Farms are added over time, so
the transitions are rebuilt on every migrate instead of being frozen into a
file. This mirrors how the Work Management app builds its own chains.
"""

import frappe

WORKFLOW = "Fertilizer Programme Approval"
DOCTYPE = "Fertilizer Programme"
STATE_FIELD = "workflow_state"

DRAFT = "Draft"
CONSULTANT = "Pending Consultant"
FARM_MANAGER = "Pending Farm Manager"
APPROVED = "Approved"
REJECTED = "Rejected"

AGRONOMIST = "CNP Agronomist"
# The agronomy consultant has no account yet, so the review step sits with the
# General Manager, who does have one. This is the only line that has to change
# when the consultant is onboarded - the stage, its state and its transitions
# all stay as they are. Deliberately an existing role rather than a shipped
# "CNP Consultant" nobody holds: a Workflow Transition's role is a Link, so an
# unused role would still have to exist, and an empty role in the list reads
# like access somebody forgot to grant.
CONSULTANT_ROLE = "General Manager"
MANAGER_ROLE = "Farm Manager"
MANAGER_PREFIX = "Farm Manager "

SEND = "Send for Consultant Review"
APPROVE = "Approve"
REJECT = "Reject"
RESUBMIT = "Re-submit"


def build_workflow():
	"""Create or update the workflow. Idempotent - safe on every migrate."""
	if not frappe.db.exists("DocType", DOCTYPE):
		return None
	if not frappe.db.exists("Role", CONSULTANT_ROLE):
		# Never write a Workflow whose transitions name a role that is not
		# there - the save fails and leaves no chain at all.
		return None

	states = [
		# state, docstatus, who may edit while it sits here
		(DRAFT, 0, AGRONOMIST),
		(CONSULTANT, 0, CONSULTANT_ROLE),
		(FARM_MANAGER, 0, MANAGER_ROLE),
		(APPROVED, 1, MANAGER_ROLE),
		(REJECTED, 0, AGRONOMIST),
	]

	transitions = [
		# state, action, next state, role, condition
		(DRAFT, SEND, CONSULTANT, AGRONOMIST, None),
		# The consultant's edit rights come from the state's allow_edit above -
		# "approve or amend" is one step, not two.
		(CONSULTANT, APPROVE, FARM_MANAGER, CONSULTANT_ROLE, None),
		(CONSULTANT, REJECT, REJECTED, CONSULTANT_ROLE, None),
		(REJECTED, RESUBMIT, CONSULTANT, AGRONOMIST, None),
	]

	# The farm manager step, scoped. A manager of one farm must not approve
	# another's, so each farm gets its own transition guarded on doc.farm.
	for farm in frappe.get_all("CNP Farm", pluck="name"):
		role = MANAGER_PREFIX + farm
		if not frappe.db.exists("Role", role):
			continue
		condition = f'doc.farm == "{farm}"'
		transitions.append((FARM_MANAGER, APPROVE, APPROVED, role, condition))
		transitions.append((FARM_MANAGER, REJECT, REJECTED, role, condition))

	# The unscoped "Farm Manager" role is the all-farm one (see
	# farm_permissions.get_manager_farms), so it approves anywhere.
	transitions.append((FARM_MANAGER, APPROVE, APPROVED, MANAGER_ROLE, None))
	transitions.append((FARM_MANAGER, REJECT, REJECTED, MANAGER_ROLE, None))

	_ensure_vocabulary([s[0] for s in states], [t[1] for t in transitions])

	if frappe.db.exists("Workflow", WORKFLOW):
		doc = frappe.get_doc("Workflow", WORKFLOW)
	else:
		doc = frappe.new_doc("Workflow")
		doc.workflow_name = WORKFLOW

	doc.document_type = DOCTYPE
	doc.workflow_state_field = STATE_FIELD
	doc.is_active = 1
	doc.send_email_alert = 0
	# Fertilizer Programme has no `status` field to keep in step any more, and
	# docstatus is what every query in this app actually gates on.
	doc.override_status = 0

	doc.set("states", [])
	for state, docstatus, editor in states:
		doc.append("states", {
			"state": state, "doc_status": docstatus, "allow_edit": editor,
		})

	doc.set("transitions", [])
	for state, action, next_state, role, condition in transitions:
		doc.append("transitions", {
			"state": state, "action": action, "next_state": next_state,
			"allowed": role, "condition": condition or "",
		})

	doc.flags.ignore_permissions = True
	doc.save()
	frappe.db.commit()
	return doc.name


def _ensure_vocabulary(states, actions):
	"""Workflow State and Workflow Action Master are Links - the rows have to
	exist before a transition naming them can save."""
	for state in set(states):
		if not frappe.db.exists("Workflow State", state):
			frappe.get_doc({"doctype": "Workflow State", "workflow_state_name": state}
			               ).insert(ignore_permissions=True)
	for action in set(actions):
		if not frappe.db.exists("Workflow Action Master", action):
			frappe.get_doc({"doctype": "Workflow Action Master", "workflow_action_name": action}
			               ).insert(ignore_permissions=True)
