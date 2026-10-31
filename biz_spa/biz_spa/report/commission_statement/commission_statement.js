frappe.query_reports["Commission Statement"] = {
	filters: [
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
		{
			fieldname: "status",
			label: "Status",
			fieldtype: "Select",
			options: "\nUnpaid\nPaid\nCancelled",
		},
	],
};
