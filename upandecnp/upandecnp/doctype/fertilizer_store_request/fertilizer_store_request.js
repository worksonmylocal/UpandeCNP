// Copyright (c) 2026, Upande and contributors
// For license information, please see license.txt

// frappe.ui.form.on("Fertilizer Store Request", {
// 	refresh(frm) {

// 	},
// });
frappe.ui.form.on("Fertilizer Store Request", {
    block_fertilizer_plan(frm) {
        if (!frm.doc.block_fertilizer_plan) return;

        frappe.db.get_doc("Block Fertilizer Plan", frm.doc.block_fertilizer_plan).then(plan => {
            frm.set_value("block", plan.block);
            frm.set_value("fertilizer_product", plan.fertilizer_product);
            frm.set_value("application_month", plan.application_month);
            if (!frm.doc.quantity_requested_kg) {
                frm.set_value("quantity_requested_kg", plan.total_kg_required);
            }
        });
    }
});