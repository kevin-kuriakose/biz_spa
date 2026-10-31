frappe.query_reports["Package Balance and Liability"] = {
	filters: [
		{ fieldname: "branch", label: "Branch", fieldtype: "Link", options: "Spa Branch" },
		{
			fieldname: "status",
			label: "Status",
			fieldtype: "Select",
			options: "\nActive\nExhausted\nExpired\nCancelled",
			default: "Active",
		},
		{ fieldname: "expiring_within_days", label: "Expiring Within Days", fieldtype: "Int" },
	],
};
