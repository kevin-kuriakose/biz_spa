import secrets

import frappe
from frappe.model.document import Document
from frappe.utils import flt, getdate

from biz_spa import posting
from biz_spa.utils import settings


class SpaGiftCard(Document):
	ignore_linked_doctypes = posting.LINKED

	def validate(self):
		if flt(self.initial_value) <= 0:
			frappe.throw("Initial Value must be greater than zero.")
		if getdate(self.expiry_date) < getdate(self.issue_date):
			frappe.throw("Expiry Date cannot be before Issue Date.")
		if flt(self.paid_amount) > flt(self.initial_value):
			frappe.throw("Paid Amount cannot exceed the card value.")
		if flt(self.paid_amount) and not self.mode_of_payment:
			frappe.throw("Select a Mode of Payment.")

	def before_submit(self):
		while not self.card_code or frappe.db.exists("Spa Gift Card", {"card_code": self.card_code}):
			self.card_code = secrets.token_hex(6).upper()
		self.balance = flt(self.initial_value)
		self.status = "Active"
		self.set("transactions", [])
		self.append(
			"transactions",
			{
				"txn_date": self.issue_date,
				"txn_type": "Issue",
				"amount": self.initial_value,
				"balance_after": self.initial_value,
			},
		)

	@posting.as_system
	def on_submit(self):
		config = settings()
		if not config.gift_card_item:
			frappe.throw("Set Gift Card Item in Spa Settings.")
		posting.post_sale_invoice(
			self,
			item=config.gift_card_item,
			amount=self.initial_value,
			paid=self.paid_amount,
			mode=self.mode_of_payment,
			date=self.issue_date,
			taxed=False,
			income_account=config.gift_card_liability_account,
			customer=self.purchaser,
		)

	def before_cancel(self):
		if flt(self.balance) < flt(self.initial_value):
			frappe.throw("This gift card has been used and cannot be cancelled.")

	@posting.as_system
	def on_cancel(self):
		posting.cancel_sale(self)
		self.db_set("status", "Cancelled")
