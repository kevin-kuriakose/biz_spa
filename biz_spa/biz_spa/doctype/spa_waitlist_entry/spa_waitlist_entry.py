import frappe
from frappe.model.document import Document
from frappe.utils import getdate


class SpaWaitlistEntry(Document):
	def validate(self):
		if getdate(self.date_from) > getdate(self.date_to):
			frappe.throw("Date From cannot be after Date To.")
