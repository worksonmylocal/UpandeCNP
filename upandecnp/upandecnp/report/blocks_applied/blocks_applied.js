frappe.query_reports["Blocks Applied"] = {
    filters: [
        {
            fieldname: "from_date",
            label: "From Date",
            fieldtype: "Date"
        },
        {
            fieldname: "to_date",
            label: "To Date",
            fieldtype: "Date"
        },
        {
            fieldname: "block",
            label: "Block",
            fieldtype: "Link",
            options: "Farm Block"
        },
        {
            fieldname: "applied_by",
            label: "Applied By",
            fieldtype: "Link",
            options: "Employee"
        },
        {
            fieldname: "only_partial",
            label: "Only Partial Applications",
            fieldtype: "Check"
        }
    ]
};