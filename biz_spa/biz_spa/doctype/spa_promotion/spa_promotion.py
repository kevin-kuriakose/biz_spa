from frappe.model.document import Document
import frappe
from frappe.utils import flt, getdate


class SpaPromotion(Document):
	def validate(self):
		if getdate(self.valid_from) > getdate(self.valid_to):
			frappe.throw("Valid From cannot be after Valid To.")
		if self.discount_type == "Percentage" and not 0 < flt(self.discount_value) <= 100:
			frappe.throw("A percentage discount must be between 0 and 100.")
		if not self.applies_to_all_services and not (self.services or []):
			frappe.throw("Add at least one service, or tick Applies To All Services.")
