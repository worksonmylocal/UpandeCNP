frappe.query_reports["Plan vs Actual Application"] = {
    filters: [
        {
            fieldname: "season",
            label: "Season",
            fieldtype: "Data"
        },
        {
            fieldname: "block",
            label: "Block",
            fieldtype: "Link",
            options: "Farm Block"
        }
    ]
};