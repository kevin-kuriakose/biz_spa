import frappe
from frappe.model.document import Document
from frappe.utils import get_datetime


class SpaStaffTimeOff(Document):
	def validate(self):
		if get_datetime(self.from_datetime) >= get_datetime(self.to_datetime):
			frappe.throw("From must be before To.")
		if self.status in ("Approved", "Rejected") and self.has_value_changed("status"):
			if not set(frappe.get_roles()) & {"Spa Manager", "System Manager"}:
				frappe.throw("Only a Spa Manager can approve or reject time off.")
			self.approved_by = frappe.session.user
