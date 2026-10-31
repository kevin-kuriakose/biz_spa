import frappe
from frappe.model.document import Document
from frappe.utils import add_months, cint, flt

from biz_spa import posting


class SpaMembership(Document):
	ignore_linked_doctypes = posting.LINKED

	def validate(self):
		plan = frappe.get_cached_doc("Spa Membership Plan", self.plan)
		self.rate = flt(plan.price)
		self.end_date = add_months(self.start_date, cint(plan.validity_months))
		if flt(self.paid_amount) > flt(self.rate):
			frappe.throw("Paid Amount cannot exceed the plan price.")
		if flt(self.paid_amount) and not self.mode_of_payment:
			frappe.throw("Select a Mode of Payment.")

	def before_submit(self):
		plan = frappe.get_cached_doc("Spa Membership Plan", self.plan)
		self.set("entitlements", [])
		period_end = add_months(self.start_date, 1)
		for row in plan.benefits or []:
			self.append(
				"entitlements",
				{
					"service": row.service,
					"period_start": self.start_date,
					"period_end": period_end,
					"sessions_allowed": row.sessions_per_month,
					"sessions_used": 0,
				},
			)
		self.status = "Active"

	@posting.as_system
	def on_submit(self):
		plan = frappe.get_cached_doc("Spa Membership Plan", self.plan)
		posting.post_sale_invoice(
			self,
			item=plan.item,
			amount=self.rate,
			paid=self.paid_amount,
			mode=self.mode_of_payment,
			date=self.start_date,
		)
		frappe.db.set_value("Spa Client Profile", self.client, "membership_status", "Active")

	def before_cancel(self):
		if any(cint(r.sessions_used) for r in (self.entitlements or [])):
			frappe.throw("This membership has used sessions and cannot be cancelled.")

	@posting.as_system
	def on_cancel(self):
		posting.cancel_sale(self)
		self.db_set("status", "Cancelled")
		frappe.db.set_value("Spa Client Profile", self.client, "membership_status", None)
