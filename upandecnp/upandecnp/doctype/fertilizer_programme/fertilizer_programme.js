frappe.ui.form.on("Fertilizer Programme", {
    refresh(frm) {
        if (frm.doc.docstatus === 0) {
            frm.add_custom_button(__("Pull Blocks from Farm"), function() {
                if (!frm.doc.farm) {
                    frappe.msgprint("Please set the Farm first.");
                    return;
                }
                frm.call("pull_blocks_from_farm").then((r) => {
                    frm.reload_doc();
                    frappe.show_alert({
                        message: `Pulled ${r.message} blocks from ${frm.doc.farm}.`,
                        indicator: "green"
                    });
                });
            }, __("Actions"));

            frm.add_custom_button(__("Load Products"), function() {
                if (!frm.doc.crop) {
                    frappe.msgprint("Please set the Crop first.");
                    return;
                }
                frappe.call({
                    method: "upandecnp.upandecnp.api.load_programme_products",
                    args: { programme: frm.doc.name },
                    callback(r) {
                        if (r.message) {
                            frm.reload_doc();
                            const n = r.message.products.length;
                            frappe.show_alert({
                                message: `${n} product${n === 1 ? "" : "s"} to choose an Item for. `
                                    + `Click "Choose" on each row.`,
                                indicator: "blue"
                            });
                        }
                    }
                });
            }, __("Actions"));

            frm.add_custom_button(__("Run Calculation Engine"), function() {
                if (!frm.doc.block_yield_data || frm.doc.block_yield_data.length === 0) {
                    frappe.msgprint("Please pull block yield data before running the calculation.");
                    return;
                }
                if (!frm.doc.potassium_source) {
                    frappe.msgprint("Please select a Potassium Source before running the calculation.");
                    return;
                }
                frappe.call({
                    method: "upandecnp.upandecnp.utils.calculation_engine.calculate_programme",
                    args: { programme_name: frm.doc.name },
                    callback(r) {
                        if (r.message) {
                            frm.reload_doc();
                            frappe.show_alert({
                                message: `Generated ${r.message} programme lines.`,
                                indicator: "green"
                            });
                        }
                    }
                });
            }, __("Actions"));
        }
    },
    crop(frm) {
        set_potassium_source_query(frm);
    },
    onload(frm) {
        set_potassium_source_query(frm);
    }
});

function set_potassium_source_query(frm) {
    if (!frm.doc.crop) return;
    frappe.db.get_doc("Crop", frm.doc.crop).then(crop => {
        const products = (crop.nutrient_rules || [])
            .filter(r => r.nutrient_source_group)
            .map(r => r.fertilizer_product);
        frm.set_query("potassium_source", () => ({ filters: { name: ["in", products] } }));
    });
}

frappe.ui.form.on("Programme Block Yield", {
    block(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        if (!row.block) return;

        frappe.db.get_doc("Farm Block", row.block).then(block => {
            frappe.model.set_value(cdt, cdn, "section", block.section);
            frappe.model.set_value(cdt, cdn, "area_ha", block.area_ha);
            frappe.model.set_value(cdt, cdn, "tree_count", block.tree_count);
            frappe.model.set_value(cdt, cdn, "yield_kg_ha", block.previous_year_yield_kg_ha);
        });
    }
});


/* ------------------------------------------------------------------ *
 * Choosing the Item for a product.
 *
 * The list is never picked for the agronomist: several Items are the same
 * fertilizer under different spellings, and only they know which bin is
 * really usable. The dialog shows stock beside each candidate, and the
 * nutrient rule that will be applied whichever one they pick - because the
 * rule follows the product, not the Item, and that is the thing people
 * assume changes when it doesn't.
 * ------------------------------------------------------------------ */

function choose_item_for(frm, row) {
    if (!row.product) {
        frappe.msgprint(__("Set the Product on this row first."));
        return;
    }
    frappe.call({
        method: "upandecnp.upandecnp.api.get_product_choices",
        args: { programme: frm.doc.name, product: row.product },
        freeze: true,
        freeze_message: __("Loading {0} items…", [row.product]),
        callback(r) {
            const data = r.message || {};
            const options = data.options || [];
            if (!options.length) {
                frappe.msgprint({
                    title: __("No matching items"),
                    indicator: "orange",
                    message: __(
                        "No Item in the fertilizer group matches the search terms on {0}. "
                        + "Add the spelling used on site to that Fertilizer Product.",
                        [row.product]
                    ),
                });
                return;
            }

            const rule = data.rule;
            const rule_html = rule
                ? `<div style="margin-bottom:12px;padding:10px 12px;background:var(--bg-light-gray,#f4f5f6);border-radius:6px">
                     <b>${__("Nutrient rule applied to whichever you pick")}</b><br>
                     ${__("Nutrient")}: <b>${frappe.utils.escape_html(rule.nutrient || "-")}</b> &middot;
                     ${__("Rate")}: <b>${rule.rate_per_tonne || 0}</b> ${__("per tonne")} &middot;
                     ${__("Bag")}: <b>${rule.bag_weight_kg || 0}</b> kg &middot;
                     ${__("Nutrient content")}: <b>${rule.product_nutrient_pct || 0}%</b>
                     ${rule.apply_compost_netting ? " &middot; " + __("compost netted") : ""}
                   </div>`
                : `<div class="text-muted" style="margin-bottom:12px">${
                     __("No nutrient rule on this crop names {0}.", [row.product])}</div>`;

            const d = new frappe.ui.Dialog({
                title: __("Choose the {0} item", [row.product]),
                size: "large",
                fields: [
                    { fieldtype: "HTML", fieldname: "rule", options: rule_html },
                    {
                        fieldtype: "Select", fieldname: "item", reqd: 1,
                        label: __("Item"),
                        default: data.current || options[0].item_code,
                        options: options.map((o) => ({
                            value: o.item_code,
                            label: `${o.item_name || o.item_code} — ${__("in stock")}: `
                                 + `${frappe.format(o.stock_qty, { fieldtype: "Float" })} `
                                 + `${o.stock_uom || ""}`,
                        })),
                    },
                ],
                primary_action_label: __("Use this item"),
                primary_action(values) {
                    frappe.call({
                        method: "upandecnp.upandecnp.api.set_product_item",
                        args: {
                            programme: frm.doc.name,
                            product: row.product,
                            item: values.item,
                        },
                        callback() {
                            d.hide();
                            frm.reload_doc();
                            frappe.show_alert({
                                message: __("{0} will be drawn from {1}.",
                                            [row.product, values.item]),
                                indicator: "green",
                            });
                        },
                    });
                },
            });
            d.show();
        },
    });
}

frappe.ui.form.on("Fertilizer Programme Product", {
    choose(frm, cdt, cdn) {
        choose_item_for(frm, locals[cdt][cdn]);
    },

    // Opening the row form is itself a request to decide, when nothing is set.
    form_render(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        if (row.product && !row.fertilizer_item) choose_item_for(frm, row);
    },
});
