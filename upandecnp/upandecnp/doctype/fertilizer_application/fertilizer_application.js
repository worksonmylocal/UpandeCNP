frappe.ui.form.on("Fertilizer Application", {
    block_fertilizer_plan(frm) {
        if (!frm.doc.block_fertilizer_plan) return;
        frappe.db.get_doc("Block Fertilizer Plan", frm.doc.block_fertilizer_plan).then(plan => {
            frm.set_value("block", plan.block);
            frm.set_value("fertilizer_product", plan.fertilizer_product);
            frm.set_value("planned_quantity_kg", plan.total_kg_required);
        });
    },

    store_request(frm) {
        if (!frm.doc.store_request) return;
        frappe.db.get_doc("Fertilizer Store Request", frm.doc.store_request).then(sr => {
            frm.set_value("block_fertilizer_plan", sr.block_fertilizer_plan);
            frm.set_value("block", sr.block);
            frm.set_value("fertilizer_product", sr.fertilizer_product);
            frm.set_value("planned_quantity_kg", sr.quantity_requested_kg);
            // If applied in full, default actual to the requested quantity
            if (frm.doc.applied_in_full && !frm.doc.actual_quantity_applied_kg) {
                frm.set_value("actual_quantity_applied_kg", sr.quantity_requested_kg);
            }
        });
    },

    applied_in_full(frm) {
        // If they tick "applied in full", set actual = planned
        if (frm.doc.applied_in_full && frm.doc.planned_quantity_kg) {
            frm.set_value("actual_quantity_applied_kg", frm.doc.planned_quantity_kg);
        }
    },

    actual_quantity_applied_kg(frm) {
        let variance = flt(frm.doc.actual_quantity_applied_kg) - flt(frm.doc.planned_quantity_kg);
        frm.set_value("variance_kg", variance.toFixed(2));
    }
});