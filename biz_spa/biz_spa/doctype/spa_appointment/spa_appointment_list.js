frappe.listview_settings["Spa Appointment"] = {
	add_fields: ["status"],
	get_indicator(doc) {
		const colors = {
			Scheduled: "blue",
			Confirmed: "blue",
			"Checked In": "orange",
			"In Progress": "orange",
			Completed: "green",
			Cancelled: "gray",
			"No Show": "red",
		};
		return [__(doc.status), colors[doc.status] || "gray", `status,=,${doc.status}`];
	},
};
