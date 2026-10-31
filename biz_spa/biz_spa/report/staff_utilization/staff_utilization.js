frappe.query_reports["Staff Utilization"] = {
	filters: [
		{ fieldname: "branch", label: "Branch", fieldtype: "Link", options: "Spa Branch" },
		{ fieldname: "staff", label: "Staff", fieldtype: "Link", options: "Spa Staff Profile" },
		{
			fieldname: "from_date",
			label: "From Date",
			fieldtype: "Date",
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -1),
		},
		{
			fieldname: "to_date",
			label: "To Date",
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
		},
	],
};
