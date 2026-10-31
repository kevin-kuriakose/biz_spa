frappe.query_reports["Service Revenue and Popularity"] = {
	filters: [
		{ fieldname: "branch", label: "Branch", fieldtype: "Link", options: "Spa Branch" },
		{
			fieldname: "category",
			label: "Category",
			fieldtype: "Link",
			options: "Spa Service Category",
		},
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
