frappe.listview_settings["Farm Block"] = {
    onload(listview) {
        listview.page.add_inner_button("Sync from Kaitet", () => {
            frappe.call({
                method: "upandecnp.upandecnp.api.get_available_farms",
                callback: (r) => {
                    const farms = r.message || [];
                    const options = ["All Farms", ...farms];

                    const d = new frappe.ui.Dialog({
                        title: "Sync Farm Blocks from Kaitet",
                        fields: [
                            {
                                fieldname: "farm",
                                fieldtype: "Select",
                                label: "Farm",
                                options: options.join("\n"),
                                default: "All Farms",
                                description: "Pulls block name, area, and tree count from the Kaitet warehouse master. Existing blocks are updated; new ones are created.",
                            },
                        ],
                        primary_action_label: "Sync Now",
                        primary_action: (values) => {
                            d.hide();
                            frappe.show_alert({ message: "Syncing blocks from Kaitet...", indicator: "blue" });

                            frappe.call({
                                method: "upandecnp.upandecnp.api.sync_blocks_from_warehouse",
                                args: {
                                    farm: values.farm === "All Farms" ? null : values.farm,
                                },
                                callback: (res) => {
                                    const m = res.message;
                                    let msg = `✅ Created ${m.created}, updated ${m.updated} blocks (${m.total_processed} processed).`;
                                    if (m.errors && m.errors.length) {
                                        msg += ` ⚠️ ${m.errors.length} errors — check console.`;
                                        console.log("Sync errors:", m.errors);
                                    }
                                    frappe.msgprint({
                                        title: "Sync Complete",
                                        message: msg,
                                        indicator: m.errors.length ? "orange" : "green",
                                    });
                                    listview.refresh();
                                },
                            });
                        },
                    });
                    d.show();
                },
            });
        });
    },
};