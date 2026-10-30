frappe.query_reports["Client Birthdays and Anniversaries"] = {
	filters: [
		{"fieldname": "month", "label": "Month", "fieldtype": "Select", "options": "1\n2\n3\n4\n5\n6\n7\n8\n9\n10\n11\n12", default: String(new Date().getMonth() + 1)},
		{"fieldname": "branch", "label": "Branch", "fieldtype": "Link", "options": "Spa Branch"},
	],
};
