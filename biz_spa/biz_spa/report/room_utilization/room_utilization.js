frappe.query_reports["Room Utilization"] = {
	filters: [
		{ fieldname: "branch", label: "Branch", fieldtype: "Link", options: "Spa Branch" },
		{
			fieldname: "room_type",
			label: "Room Type",
			fieldtype: "Select",
			options:
				"\nTreatment Room\nCouple Suite\nHair Station\nNail Station\nPedicure Chair\nSteam and Sauna",
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
