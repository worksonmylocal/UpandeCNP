// Copyright (c) 2026, Upande and contributors
// For license information, please see license.txt

// frappe.ui.form.on("Fertilizer Application", {
// 	refresh(frm) {

// 	},
// });
frappe.ui.form.on("Fertilizer Application", {
    block_fertilizer_plan(frm) {
        if (!frm.doc.block_fertilizer_plan) return;

        frappe.db.get_doc("Block Fertilizer Plan", frm.doc.block_fertilizer_plan).then(plan => {
            frm.set_value("block", plan.block);
            frm.set_value("fertilizer_product", plan.fertilizer_product);
            frm.set_value("planned_quantity_kg", plan.total_kg_required);
        });
    },

    actual_quantity_applied_kg(frm) {
        let variance = flt(frm.doc.actual_quantity_applied_kg) - flt(frm.doc.planned_quantity_kg);
        frm.set_value("variance_kg", variance.toFixed(2));
    }
});