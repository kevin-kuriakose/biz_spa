import frappe
from frappe.model.document import Document
from frappe.utils import add_days, cint, flt

from biz_spa import posting


class SpaClientPackage(Document):
	ignore_linked_doctypes = posting.LINKED

	def validate(self):
		package = frappe.get_cached_doc("Spa Package", self.package)
		self.rate = flt(package.price)
		self.net_amount = flt(self.rate) - flt(self.discount_amount)
		self.expiry_date = add_days(self.purchase_date, cint(package.validity_days))
		if flt(self.paid_amount) > flt(self.net_amount):
			frappe.throw("Paid Amount cannot exceed the net amount.")
		if flt(self.paid_amount) and not self.mode_of_payment:
			frappe.throw("Select a Mode of Payment.")

	def before_submit(self):
		package = frappe.get_cached_doc("Spa Package", self.package)
		self.set("items", [])
		for row in package.services or []:
			self.append(
				"items",
				{
					"service": row.service,
					"total_sessions": row.sessions,
					"used_sessions": 0,
					"balance_sessions": row.sessions,
					"unit_value": row.unit_value,
				},
			)
		self.total_sessions = sum(cint(r.total_sessions) for r in self.items)
		self.used_sessions = 0
		self.balance_sessions = self.total_sessions
		self.status = "Active"

	def on_submit(self):
		package = frappe.get_cached_doc("Spa Package", self.package)
		posting.sell(
			self, package.item, self.net_amount, self.paid_amount, self.mode_of_payment, self.purchase_date
		)

	def before_cancel(self):
		if cint(self.used_sessions):
			frappe.throw("This package has used sessions and cannot be cancelled.")

	def on_cancel(self):
		posting.cancel_sale(self)
		self.db_set("status", "Cancelled")
