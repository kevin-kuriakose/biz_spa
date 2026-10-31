const SPA_STATUS_ACTIONS = {
	Scheduled: [
		["Confirmed", "Confirm"],
		["No Show", "Mark No Show"],
	],
	Confirmed: [["No Show", "Mark No Show"]],
	"Checked In": [
		["In Progress", "Start Treatment"],
		["No Show", "Mark No Show"],
	],
	"In Progress": [["No Show", "Mark No Show"]],
	Cancelled: [["Scheduled", "Reinstate"]],
	"No Show": [["Scheduled", "Reinstate"]],
};

frappe.ui.form.on("Spa Appointment", {
	refresh(frm) {
		if (frm.is_new() || !frm.perm[0].write) return;
		(SPA_STATUS_ACTIONS[frm.doc.status] || []).forEach(([status, label]) => {
			frm.add_custom_button(
				__(label),
				() => {
					frappe.call({
						method: "biz_spa.api.booking.set_appointment_status",
						args: { name: frm.doc.name, status },
						freeze: true,
						callback: () => frm.reload_doc(),
					});
				},
				__("Status")
			);
		});
		if (!["Scheduled", "Confirmed"].includes(frm.doc.status)) return;
		frm.add_custom_button(
			__("Cancel Appointment"),
			() => {
				frappe.prompt(
					{ fieldname: "reason", label: __("Reason"), fieldtype: "Small Text", reqd: 1 },
					({ reason }) => {
						frappe.call({
							method: "biz_spa.api.booking.cancel_appointment",
							args: { name: frm.doc.name, reason },
							freeze: true,
							callback: () => frm.reload_doc(),
						});
					},
					__("Cancel Appointment")
				);
			},
			__("Status")
		);
		const button = frm.add_custom_button(__("Check In"), () => {
			frappe.call({
				method: "biz_spa.api.booking.check_in",
				args: { appointment: frm.doc.name },
				freeze: true,
				callback(r) {
					if (r.message) frappe.set_route("Form", "Spa Visit", r.message);
					else frm.reload_doc();
				},
			});
		});
		button.addClass("spa-btn-navy");
	},
});
