// Copyright (c) 2026, Upande and contributors
// For license information, please see license.txt

// frappe.ui.form.on("Fertilizer Programme", {
// 	refresh(frm) {

// 	},
// });
frappe.ui.form.on("Fertilizer Programme", {
    refresh(frm) {
        if (frm.doc.docstatus === 0) {
            frm.add_custom_button(__("Run Calculation Engine"), function() {
                if (!frm.doc.block_yield_data || frm.doc.block_yield_data.length === 0) {
                    frappe.msgprint("Please add block yield data before running the calculation.");
                    return;
                }
                frm.save().then(() => {
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
                });
            }, __("Actions"));
        }
    }
});