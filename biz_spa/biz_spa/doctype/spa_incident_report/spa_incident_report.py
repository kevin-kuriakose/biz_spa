import frappe
from frappe.model.document import Document


class SpaIncidentReport(Document):
	def validate(self):
		self.reported_by = self.reported_by or frappe.session.user
		if self.follow_up_required and not self.follow_up_date:
			frappe.throw("Enter the follow up date.")
