// Copyright (c) 2026, Upande and contributors
// For license information, please see license.txt

// frappe.ui.form.on("Fertilizer Budget", {
// 	refresh(frm) {

// 	},
// });
frappe.ui.form.on("Fertilizer Budget", {
    refresh(frm) {
        if (frm.doc.docstatus === 0 && frm.doc.fertilizer_programme) {
            frm.add_custom_button(__("Fetch from Programme"), function() {
                frm.call({
                    doc: frm.doc,
                    method: "fetch_from_programme",
                    callback: function() {
                        frm.reload_doc();
                    }
                });
            });
        }
    }
});