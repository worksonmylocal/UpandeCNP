frappe.ui.form.on("Fertilizer Programme", {
    refresh(frm) {
        if (frm.doc.docstatus === 0) {
            frm.add_custom_button(__("Run Calculation Engine"), function() {
                if (!frm.doc.block_yield_data || frm.doc.block_yield_data.length === 0) {
                    frappe.msgprint("Please add block yield data before running the calculation.");
                    return;
                }
                frappe.call({
                    method: "upandecnp.upandecnp.utils.calculation_engine.run_calculation",
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
    }
});

frappe.ui.form.on("Programme Block Yield", {
    block(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        if (!row.block) return;

        frappe.db.get_doc("Farm Block", row.block).then(block => {
            frappe.model.set_value(cdt, cdn, "area_ha", block.area_ha);
            frappe.model.set_value(cdt, cdn, "big_tree_count", block.big_tree_count);
            frappe.model.set_value(cdt, cdn, "small_tree_count", block.small_tree_count);
        });
    }
});