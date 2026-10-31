import frappe
from frappe.model.document import Document
from frappe.utils import getdate


class SpaConsultation(Document):
	def validate(self):
		if self.valid_until and getdate(self.valid_until) < getdate(self.consultation_date):
			frappe.throw("Valid Until cannot be before the consultation date.")
		if self.patch_test_done and not self.patch_test_date:
			frappe.throw("Enter the patch test date.")
		if self.consent_given and not self.signature:
			frappe.throw("Capture the client's signature to record consent.")
