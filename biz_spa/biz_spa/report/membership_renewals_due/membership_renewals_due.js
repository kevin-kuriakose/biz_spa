frappe.query_reports["Membership Renewals Due"] = {
	filters: [
		{ fieldname: "branch", label: "Branch", fieldtype: "Link", options: "Spa Branch" },
		{ fieldname: "days_ahead", label: "Days Ahead", fieldtype: "Int", default: 30 },
	],
};
