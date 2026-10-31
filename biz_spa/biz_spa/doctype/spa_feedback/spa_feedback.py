import frappe
from frappe.model.document import Document


class SpaFeedback(Document):
	def validate(self):
		if not self.staff:
			self.staff = frappe.db.get_value(
				"Spa Visit Service", {"parent": self.visit, "staff": ("is", "set")}, "staff", order_by="idx"
			)
		if self.status != "New" and self.has_value_changed("status"):
			self.reviewed_by = frappe.session.user
