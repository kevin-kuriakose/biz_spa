frappe.ui.form.on("Spa Appointment", {
	refresh(frm) {
		if (frm.is_new() || !["Scheduled", "Confirmed"].includes(frm.doc.status)) return;
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
