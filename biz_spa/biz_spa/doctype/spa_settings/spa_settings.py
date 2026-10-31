import frappe
from frappe.model.document import Document
from frappe.utils import cint


class SpaSettings(Document):
	def validate(self):
		if cint(self.slot_interval_minutes) <= 0:
			frappe.throw("Slot Interval must be greater than zero.")
