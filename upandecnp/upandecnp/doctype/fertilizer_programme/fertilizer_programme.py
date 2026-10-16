import frappe
from frappe.model.document import Document
from frappe.utils import flt


class FertilizerProgramme(Document):

	def validate(self):
		self.validate_period()
		self.validate_scope()
		self.warn_on_stock_shortfall()

	def before_submit(self):
		self.require_approval()
		self.require_sign_off()
		self.require_product_choices()

	def require_sign_off(self):
		"""The approval chain below is the generated-Workflow one, which stays
		off until a farm actually asks for a consultant/farm-manager review.
		Day to day, the only gate on submitting is this: Elvis Koskey, Bramuel
		and Richard Collins all have to tick their own box first - a plain
		sign-off, not a workflow, because nobody asked for one of those
		either."""
		missing = []
		if not self.approved_by_elvis_koskey:
			missing.append("Elvis Koskey")
		if not self.approved_by_bramuel:
			missing.append("Bramuel")
		if not self.approved_by_richard_collins:
			missing.append("Richard Collins")
		if missing:
			frappe.throw(
				"Waiting on sign-off from: <b>" + "</b>, <b>".join(missing) + "</b> "
				"before this can be submitted."
			)

	def require_approval(self):
		"""Submitting is what splits a programme into Block Fertilizer Plans and
		puts it in front of the field app, so it must only be reachable through
		the approval chain.

		The desk already hides Submit while a workflow is active, but any code
		calling doc.submit() walks straight past it: Frappe's
		set_workflow_state_on_action() then stamps the document "Approved"
		because that is the state carrying doc_status=1, and 156 block plans
		appear that no consultant ever saw.

		It stamps that *after* validate_workflow() has passed, so the in-memory
		state cannot be trusted here. What can is the state still in the
		database: a genuine approval arrives from a state the workflow allows
		into Approved, a bypass arrives from Draft.
		"""
		from upandecnp.upandecnp.utils.approval import APPROVED, WORKFLOW

		if not frappe.db.get_value("Workflow", WORKFLOW, "is_active"):
			return

		stored = frappe.db.get_value(self.doctype, self.name, "workflow_state")
		if not stored:
			return   # pre-workflow document being submitted by a migration

		allowed_from = frappe.get_all(
			"Workflow Transition",
			filters={"parent": WORKFLOW, "next_state": APPROVED},
			pluck="state",
		)
		if stored not in allowed_from:
			frappe.throw(
				f"This programme is <b>{stored}</b>. It has to go through "
				"consultant review and farm-manager approval before it can be "
				"split into Block Fertilizer Plans."
			)

	def require_product_choices(self):
		"""Every listed product needs an Item chosen. Nothing is picked
		automatically any more, so an empty row means a decision nobody has
		made - and the engine would quietly fall back to the Item named on
		the crop's nutrient rule, which is often not the one with stock."""
		missing = [
			row.product for row in self.get("product_selections", [])
			if not row.fertilizer_item
		]
		if missing:
			frappe.throw(
				"Choose an Item for: <b>" + "</b>, <b>".join(missing) + "</b>.<br>"
				"Use the Choose button on each row - it shows what is in stock."
			)

	def validate_period(self):
		if self.period_type != "Custom Period":
			# Leave the months set but inert, so switching back and forth
			# doesn't lose what the agronomist typed.
			return
		if not self.start_month or not self.end_month:
			frappe.throw("A Custom Period needs both a start and an end month.")

	def validate_scope(self):
		"""Entire Farm is the long-standing default; Section and Block narrow
		which blocks pull_blocks_from_farm() picks up. The unused side is
		cleared so a programme switched back to Entire Farm doesn't silently
		keep a stale section or block it no longer scopes to."""
		if self.scope_type == "Section":
			self.scope_block = None
			if self.scope_section and frappe.db.get_value("Section", self.scope_section, "farm") != self.farm:
				frappe.throw("That Section does not belong to this programme's Farm.")
		elif self.scope_type == "Block":
			self.scope_section = None
			if self.scope_block and frappe.db.get_value("Farm Block", self.scope_block, "farm") != self.farm:
				frappe.throw("That Block does not belong to this programme's Farm.")
		else:
			self.scope_section = None
			self.scope_block = None

	def warn_on_stock_shortfall(self):
		"""Flag products whose selected Item can't cover the programme, but
		never block on it - fertilizer is routinely ordered against a
		programme rather than the other way round, so refusing to submit
		would stop legitimate forward planning. The agronomist is told, and
		decides."""
		short = [
			row for row in self.get("product_selections", [])
			if row.fertilizer_item and flt(row.shortfall) > 0
		]
		if not short:
			return

		lines = "".join(
			f"<li><b>{row.product}</b> ({row.fertilizer_item}): needs "
			f"{flt(row.required_qty):,.0f} kg, {flt(row.available_qty):,.0f} kg in stock "
			f"- short {flt(row.shortfall):,.0f} kg</li>"
			for row in short
		)
		frappe.msgprint(
			f"<p>This programme needs more than the store currently holds:</p><ul>{lines}</ul>"
			"<p>You can still submit - order the balance before those months fall due.</p>",
			title="Not enough stock",
			indicator="orange",
		)

	def on_submit(self):
		self.sync_workflow_state()
		self.create_block_fertilizer_plans()
		self.create_material_requests()

	def sync_workflow_state(self):
		"""Leave the stored state saying what is true.

		With approval switched off the Workflow is inactive, and an inactive
		Workflow does not move workflow_state on submit - so a programme could
		be submitted, with its block plans created, while the field still read
		"Draft" for ever. Anything reading that field (reports, list filters,
		the desk) then disagreed with docstatus. "Approved" is the Workflow's
		own terminal state, so a site that later turns approval on finds these
		programmes already in a state the chain recognises.
		"""
		if frappe.db.has_column(self.doctype, "workflow_state"):
			self.db_set("workflow_state", "Approved", update_modified=False)

	def on_cancel(self):
		self.cancel_block_fertilizer_plans()

	@frappe.whitelist()
	def pull_blocks_from_farm(self):
		"""Populate block_yield_data from the Farm Blocks this programme is
		scoped to - the single source of truth for area/tree_count/yield/
		section, replacing manual re-entry.

		Entire Farm (the default) pulls every block on the farm, same as
		before Programme Scope existed. Section or Block narrows that to just
		the chosen piece, so a programme can be built for one part of a farm
		without touching the rest of it."""
		if not self.farm:
			frappe.throw("Please set the Farm first.")

		filters = {"farm": self.farm}
		if self.scope_type == "Section":
			if not self.scope_section:
				frappe.throw("Please choose a Section first.")
			filters["section"] = self.scope_section
		elif self.scope_type == "Block":
			if not self.scope_block:
				frappe.throw("Please choose a Block first.")
			filters["name"] = self.scope_block

		blocks = frappe.get_all(
			"Farm Block",
			filters=filters,
			fields=["name", "section", "area_ha", "tree_count", "previous_year_yield_kg_ha"],
		)

		self.set("block_yield_data", [])
		for block in blocks:
			self.append("block_yield_data", {
				"block": block.name,
				"section": block.section,
				"area_ha": block.area_ha,
				"tree_count": block.tree_count,
				"yield_kg_ha": block.previous_year_yield_kg_ha,
			})

		self.save()
		return len(blocks)

	def create_block_fertilizer_plans(self):
		created = 0
		for line in self.get("programme_lines", []):
			if frappe.db.exists("Block Fertilizer Plan", {
				"fertilizer_programme": self.name,
				"block": line.block,
				"fertilizer_product": line.fertilizer_product,
				"application_month": line.application_month,
			}):
				continue

			plan = frappe.get_doc({
				"doctype": "Block Fertilizer Plan",
				"fertilizer_programme": self.name,
				"season": self.season,
				"block": line.block,
				"fertilizer_product": line.fertilizer_product,
				"application_month": line.application_month,
				"application_year": self.season_start_year(),
				"yield_tier": line.yield_tier,
				"application_rate_kg_ha": line.kg_per_ha_rate,
				"dose_per_tree_g": line.dose_per_tree_g,
				"tree_count": self.get_tree_count(line.block),
				"total_kg_required": line.total_kg,
				"status": "Planned",
			})
			plan.insert(ignore_permissions=True)
			plan.submit()
			created += 1

		frappe.msgprint(f"{created} Block Fertilizer Plans created.", alert=True)

	def season_start_year(self):
		"""Seasons read "2025/2026"; months run from the first of the two
		years. Plans carry the year explicitly so a round pushed past
		December can roll into January without ambiguity."""
		import re
		match = re.search(r"(\d{4})", self.season or "")
		return int(match.group(1)) if match else int(frappe.utils.nowdate()[:4])

	def create_material_requests(self):
		from upandecnp.upandecnp.utils.integration import create_material_requests_for_programme
		create_material_requests_for_programme(self.name)

	def get_tree_count(self, block_name):
		return frappe.db.get_value("Farm Block", block_name, "tree_count") or 0

	def cancel_block_fertilizer_plans(self):
		plans = frappe.get_all(
			"Block Fertilizer Plan",
			filters={
				"fertilizer_programme": self.name,
				"docstatus": 1,
			},
			fields=["name"],
		)
		for p in plans:
			doc = frappe.get_doc("Block Fertilizer Plan", p.name)
			doc.cancel()
