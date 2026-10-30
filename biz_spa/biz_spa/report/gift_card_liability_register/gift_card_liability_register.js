frappe.query_reports["Gift Card Liability Register"] = {
	filters: [
		{"fieldname": "branch", "label": "Branch", "fieldtype": "Link", "options": "Spa Branch"},
		{"fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "\nActive\nRedeemed\nExpired\nCancelled"},
		{"fieldname": "expiry_from", "label": "Expiry From", "fieldtype": "Date"},
		{"fieldname": "expiry_to", "label": "Expiry To", "fieldtype": "Date"},
	],
};
