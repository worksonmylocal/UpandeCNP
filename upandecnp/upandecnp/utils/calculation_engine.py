"""
Crop-agnostic fertilizer programme calculation engine.

All yield tiers, nutrient rates, bag compositions, and leaf-analysis norms are
master data on Crop (see doctype Crop / Crop Yield Tier / Crop Nutrient Rule /
Leaf Analysis Norm) rather than hardcoded constants, so a new crop/farm can be
onboarded by adding data, not code.

Algorithm (per the agronomist's spec, reproduced exactly):
  1. Each block is classified into a yield tier from its previous-year yield
     (Kg/Ha), using the crop's Crop Yield Tier thresholds.
  2. Blocks are grouped by (Section, Tier) - independently per section, never
     farm-wide - since each section's tier group gets its own area total and
     its own resulting Kg/Ha rate.
  3. For each nutrient rule (CAN/N, TSP/P, MOP+K2SO4/K, ...): compute the
     product's kg/ha requirement for the group, net off compost where
     applicable, scale by area, apply the group's leaf-analysis adjustment,
     and distribute back to each block as a total kg and a per-tree gram dose.
  4. Nutrients with more than one source (rows sharing a nutrient_source_group,
     e.g. MOP and K2SO4 for potassium) are both computed in full and both feed
     into programme_lines - which one supplies a given round is decided by the
     Production Calendar's Potassium Schedule, not by picking one up front.
  5. Annual per-block totals are split across months using the Production
     Calendar's Fertilizer Schedule (unchanged from the old engine).
  6. A programme may cover only part of the year. Rounds scheduled outside
     the window are dropped, NOT redistributed into it - running Jan-May
     should apply five months of nutrition, not a year's worth compressed.
  7. The Item each rule actually draws from comes from the programme's
     product_selections, so the same rule can be met from whichever of the
     site's near-duplicate Items ("MOP" vs "MURATE OF POTASIUM (MOP)")
     actually has stock this season.
"""

import frappe
from frappe.utils import cint, flt

from upandecnp.upandecnp.utils.rounding import round_half_up

MONTHS = [
	"January", "February", "March", "April", "May", "June",
	"July", "August", "September", "October", "November", "December",
]


def months_in_window(start_month, end_month):
	"""The months a Custom Period covers, inclusive. A window whose end month
	precedes its start (e.g. November to February) wraps through December
	rather than coming back empty - seasons here straddle the year end."""
	if not start_month or not end_month:
		return list(MONTHS)
	s, e = MONTHS.index(start_month), MONTHS.index(end_month)
	if s <= e:
		return MONTHS[s:e + 1]
	return MONTHS[s:] + MONTHS[:e + 1]


def resolve_products(programme):
	"""product code -> chosen Item, from the programme's selections."""
	return {
		row.product: row.fertilizer_item
		for row in programme.get("product_selections", [])
		if row.product and row.fertilizer_item
	}


def item_for_rule(rule, chosen):
	"""Which Item this rule draws from. The programme's pick for the rule's
	product wins; a rule with no product (or a programme that hasn't picked
	one) falls back to the Item named on the rule itself, so existing crops
	keep calculating exactly as before."""
	if rule.get("product") and chosen.get(rule.get("product")):
		return chosen[rule.get("product")]
	return rule.fertilizer_product


def get_yield_tier(crop_doc, yield_kg_ha):
	"""min_yield_kg_ha is an exclusive lower bound, max_yield_kg_ha an inclusive
	upper bound; blank means unbounded on that side."""
	yield_kg_ha = flt(yield_kg_ha)
	for tier in sorted(crop_doc.yield_tiers, key=lambda t: t.sort_order or 0):
		min_y, max_y = tier.min_yield_kg_ha, tier.max_yield_kg_ha
		below_max = (not max_y) or yield_kg_ha <= flt(max_y)
		above_min = (not min_y) or yield_kg_ha > flt(min_y)
		if above_min and below_max:
			return tier.tier_label, flt(tier.tier_tonnage)
	frappe.throw(f"No yield tier on crop {crop_doc.name} matches {yield_kg_ha} Kg/Ha.")


def group_blocks_by_section_tier(programme, crop_doc):
	"""Groups Programme Block Yield rows by (section, tier_label). Grouping is
	always per-section - a tier's totals in Section 1 are independent of the
	same tier's totals in Section 2."""
	groups = {}
	for row in programme.get("block_yield_data", []):
		tier_label, tier_tonnage = get_yield_tier(crop_doc, row.yield_kg_ha)
		key = (row.section, tier_label)
		group = groups.setdefault(key, {"tier_tonnage": tier_tonnage, "total_area_ha": 0, "blocks": []})
		group["total_area_ha"] += flt(row.area_ha)
		group["blocks"].append({
			"block": row.block,
			"area_ha": flt(row.area_ha),
			"tree_count": cint(row.tree_count),
		})
	return groups


def get_leaf_adjustment_pct(crop_doc, norm, section, yield_tier):
	"""Leaf Analysis is keyed 1:1 by (Section, Yield Tier) - looked up directly,
	no manual selection step. Returns +leaf_adjustment_pct if the norm's
	nutrient result is below midpoint, -leaf_adjustment_pct if strictly above
	the high bound (no midpoint buffer on that side), else 0."""
	leaf_analysis = frappe.db.get_value(
		"Leaf Analysis", {"section": section, "yield_tier": yield_tier}, "name"
	)
	if not leaf_analysis:
		frappe.throw(f"No Leaf Analysis found for Section {section} / Tier {yield_tier}.")

	result_value = frappe.db.get_value(
		"Leaf Analysis Nutrient Result",
		{"parent": leaf_analysis, "nutrient": norm.nutrient},
		"result_value",
	)
	if result_value is None:
		return 0

	adjustment = flt(crop_doc.leaf_adjustment_pct)
	if flt(result_value) < flt(norm.midpoint):
		return adjustment
	if flt(result_value) > flt(norm.high):
		return -adjustment
	return 0


def calculate_product_for_group(rule, tier_tonnage, group_area_ha, leaf_adjustment_pct, crop_doc):
	"""The 6-step per-product pattern, identical for every nutrient rule."""
	nutrient_need_per_ha = round_half_up(flt(rule.rate_per_tonne) * tier_tonnage)

	compost_offset = 0
	if rule.apply_compost_netting:
		# Per the agronomist's worked example (25kg compost x 2.5 -> 62.5 -> 63kg N),
		# this is a literal multiplier, not dose x (pct/100) - a true 2.5% of 25kg
		# compost would only be 0.625kg, which is not what was specified.
		compost_offset = round_half_up(flt(crop_doc.compost_dose_kg) * flt(crop_doc.compost_n_pct))
	nutrient_needed = nutrient_need_per_ha - compost_offset

	nutrient_kg_per_bag = flt(rule.bag_weight_kg) * flt(rule.product_nutrient_pct) / 100
	product_kg_per_ha = (
		round_half_up((nutrient_needed / nutrient_kg_per_bag) * flt(rule.bag_weight_kg))
		if nutrient_kg_per_bag else 0
	)

	# Rounded to whole kg at each step, per the agronomist's worked example
	# (192 x 8.68 -> 1666.56 -> 1667 kg, +10% leaf deficiency -> 1834 kg) -
	# the group's total is a physical quantity of fertilizer, not a figure
	# to carry fractional kilos through to the next step.
	total_product_kg = round_half_up(product_kg_per_ha * group_area_ha)
	adjusted_total = round_half_up(total_product_kg * (1 + leaf_adjustment_pct / 100))
	final_product_kg_per_ha = adjusted_total / group_area_ha if group_area_ha else 0

	return {
		"product_kg_per_ha": round_half_up(product_kg_per_ha, 2),
		"total_product_kg": total_product_kg,
		"final_product_kg_per_ha": final_product_kg_per_ha,
	}


def distribute_to_blocks(blocks, final_product_kg_per_ha, fertilizer_product, yield_tier, section, product=None):
	lines = []
	for block in blocks:
		# Whole kg, same reasoning as the group total above (211 x 1.5 -> 317,
		# not 316.94) - each block's annual total is also what gets rounded
		# again, per month, in apply_monthly_schedule.
		block_total_kg = round_half_up(block["area_ha"] * final_product_kg_per_ha)
		dose_per_tree_g = (
			round_half_up((block_total_kg / block["tree_count"]) * 1000, 1)
			if block["tree_count"] else 0
		)
		lines.append({
			"block": block["block"],
			"section": section,
			"fertilizer_product": fertilizer_product,
			"product": product,
			"yield_tier": yield_tier,
			"kg_per_ha_rate": round_half_up(final_product_kg_per_ha, 2),
			"total_kg": block_total_kg,
			"dose_per_tree_g": dose_per_tree_g,
			"tree_count": block["tree_count"],
		})
	return lines


def _schedule_map(rows):
	m = {}
	for row in rows:
		m.setdefault(row.fertilizer_product, []).append(
			(row.application_month, flt(row.percentage) / 100.0)
		)
	return m


def apply_monthly_schedule(annual_lines, calendar_doc, allowed_months=None):
	schedule_map = _schedule_map(calendar_doc.get("fertilizer_schedule", []))
	split_schedule_map = _schedule_map(calendar_doc.get("potassium_schedule", []))

	allowed = set(allowed_months) if allowed_months else None

	monthly_lines = []
	for line in annual_lines:
		# Potassium (and any future multi-source nutrient) is scheduled from
		# the Potassium Schedule - a percentage there is of that product's own
		# total, not a share of a combined pool, so MOP and K2SO4 are each
		# looked up and split independently even though both always apply.
		primary, fallback = (
			(split_schedule_map, schedule_map) if line.get("is_split_schedule")
			else (schedule_map, split_schedule_map)
		)
		# The calendar is written against whichever Item was current when it
		# was set up. If this programme swapped to a different Item for the
		# same product, fall back to the schedule of the Item the rule names,
		# so swapping Items doesn't silently break the split.
		schedule = (
			primary.get(line["fertilizer_product"])
			or primary.get(line.get("scheduled_as"))
			or fallback.get(line["fertilizer_product"])
			or fallback.get(line.get("scheduled_as"))
		)
		if not schedule:
			frappe.throw(
				f"No monthly application schedule configured for {line['fertilizer_product']} "
				f"on Production Calendar {calendar_doc.name}."
			)
		for month, fraction in schedule:
			if allowed is not None and month not in allowed:
				continue
			# Whole kg for the round's own total (70% of 317 -> 222, not
			# 221.86), then the tree dose comes from that rounded figure -
			# what the store actually weighs out, not a fraction of a
			# fraction (222 / 250 trees -> 0.888 kg, not 317 x 0.7 / 250).
			month_total_kg = round_half_up(line["total_kg"] * fraction)
			tree_count = line.get("tree_count") or 0
			monthly_lines.append({
				**line,
				"application_month": month,
				"kg_per_ha_rate": round_half_up(line["kg_per_ha_rate"] * fraction, 2),
				"total_kg": month_total_kg,
				"dose_per_tree_g": round_half_up((month_total_kg / tree_count) * 1000, 1) if tree_count else 0,
			})
	return monthly_lines


@frappe.whitelist()
def calculate_programme(programme_name):
	programme = frappe.get_doc("Fertilizer Programme", programme_name)

	if programme.docstatus == 1:
		frappe.throw("Cannot recalculate a submitted programme.")

	unchosen = [
		row.product for row in programme.get("product_selections", [])
		if not row.fertilizer_item
	]
	if unchosen:
		frappe.throw(
			"Choose an Item for: <b>" + "</b>, <b>".join(unchosen) + "</b> before "
			"calculating. Use the Choose button on each Product Selections row."
		)

	crop_doc = frappe.get_doc("Crop", programme.crop)
	calendar_doc = frappe.get_doc("Production Calendar", programme.production_calendar)
	norms = {
		n.nutrient: n
		for n in frappe.get_all(
			"Leaf Analysis Norm",
			filters={"crop": crop_doc.name},
			fields=["nutrient", "low", "high", "midpoint"],
		)
	}

	groups = group_blocks_by_section_tier(programme, crop_doc)
	chosen = resolve_products(programme)

	annual_lines = []

	for (section, tier_label), group in groups.items():
		for rule in crop_doc.get("nutrient_rules", []):
			norm = norms.get(rule.nutrient)
			leaf_pct = (
				get_leaf_adjustment_pct(crop_doc, norm, section, tier_label)
				if norm else 0
			)
			result = calculate_product_for_group(
				rule, group["tier_tonnage"], group["total_area_ha"], leaf_pct, crop_doc
			)

			lines = distribute_to_blocks(
				group["blocks"], result["final_product_kg_per_ha"],
				item_for_rule(rule, chosen), tier_label, section,
				product=rule.get("product"),
			)
			# Remember the Item the rule names, so apply_monthly_schedule can
			# still find a schedule if this programme swapped to another Item.
			for line in lines:
				line["scheduled_as"] = rule.fertilizer_product
				if rule.nutrient_source_group:
					line["is_split_schedule"] = True
			annual_lines += lines

	allowed_months = (
		months_in_window(programme.start_month, programme.end_month)
		if programme.period_type == "Custom Period" else None
	)
	monthly_lines = apply_monthly_schedule(annual_lines, calendar_doc, allowed_months)

	if not monthly_lines:
		frappe.throw(
			"That period contains no scheduled applications. The Production "
			f"Calendar {calendar_doc.name} schedules nothing between "
			f"{programme.start_month} and {programme.end_month}."
		)

	programme.set("programme_lines", [])
	for line in monthly_lines:
		programme.append("programme_lines", line)

	update_product_requirements(programme, monthly_lines)

	programme.save()
	return len(monthly_lines)


def update_product_requirements(programme, monthly_lines):
	"""Total each selected Item up across the whole programme and compare it
	with stock on hand, so the agronomist can see a shortfall before the
	season starts rather than when a store request bounces."""
	required = {}
	for line in monthly_lines:
		item = line["fertilizer_product"]
		required[item] = required.get(item, 0) + flt(line["total_kg"])

	for row in programme.get("product_selections", []):
		if not row.fertilizer_item:
			continue
		row.required_qty = round_half_up(required.get(row.fertilizer_item, 0), 2)
		row.available_qty = round_half_up(get_stock(row.fertilizer_item, farm_warehouse(programme.farm)), 2)
		row.shortfall = round_half_up(max(row.required_qty - row.available_qty, 0), 2)


def farm_warehouse(farm):
	"""The store a farm's fertilizer is issued from, or None if it has none set."""
	return frappe.db.get_value("CNP Farm", farm, "warehouse") if farm else None


def get_stock(item_code, warehouse=None):
	"""Stock on hand - in one warehouse when given, else across all of them.

	Applications issue from the farm's own store, so that is the number that
	says whether a programme can actually be carried out. Summing every
	warehouse on the site answers a different question: Lokitela's store holds
	97 kg of MOP while the site as a whole holds thousands, and "covered" on
	the strength of another farm's shelves is how an application ends up
	failing at the point of issue. With no warehouse (a farm that has none
	configured) it falls back to the site-wide figure rather than reporting
	nothing.
	"""
	if warehouse:
		total = frappe.db.sql(
			"select sum(actual_qty) from `tabBin` where item_code = %s and warehouse = %s",
			(item_code, warehouse),
		)
	else:
		total = frappe.db.sql(
			"select sum(actual_qty) from `tabBin` where item_code = %s", item_code
		)
	return flt(total[0][0]) if total and total[0] else 0.0
