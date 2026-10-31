import frappe
from frappe.model.document import Document


class SpaStaffProfile(Document):
	def validate(self):
		seen = set()
		for row in self.skills or []:
			if row.service in seen:
				frappe.throw(f"{row.service} appears twice in Skills.")
			seen.add(row.service)
		for row in self.shifts or []:
			if str(row.from_time).zfill(8) >= str(row.to_time).zfill(8):
				frappe.throw(f"Shift start must be before its end on {row.weekday}.")
		if self.user:
			other = frappe.db.get_value("Spa Staff Profile", {"user": self.user, "name": ("!=", self.name)})
			if other:
				frappe.throw(f"User {self.user} is already linked to {other}.")

	def after_insert(self):
		self.sync_user_permission()

	def on_update(self):
		self.sync_user_permission()

	def sync_user_permission(self):
		# Scoped to the staff-owned doctypes: a permission applied to all doctypes would also hide
		# every client whose preferred_staff is someone else from a Therapist.
		if not self.user:
			return
		for applicable_for in ("Spa Staff Profile", "Spa Staff Time Off", "Spa Commission Entry"):
			if not frappe.db.exists("DocType", applicable_for):
				continue
			filters = {
				"user": self.user,
				"allow": "Spa Staff Profile",
				"for_value": self.name,
				"applicable_for": applicable_for,
			}
			if not frappe.db.exists("User Permission", filters):
				frappe.get_doc({"doctype": "User Permission", "apply_to_all_doctypes": 0, **filters}).insert(
					ignore_permissions=True
				)
