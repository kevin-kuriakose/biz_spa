frappe.query_reports["Lapsed Clients"] = {
	filters: [
		{"fieldname": "days_since_last_visit", "label": "Days Since Last Visit", "fieldtype": "Int", default: 30},
		{"fieldname": "branch", "label": "Branch", "fieldtype": "Link", "options": "Spa Branch"},
	],
};
