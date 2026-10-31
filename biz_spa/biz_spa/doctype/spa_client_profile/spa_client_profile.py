import frappe
from frappe.model.document import Document

from biz_spa.utils import settings


class SpaClientProfile(Document):
	def validate(self):
		duplicate = frappe.db.get_value(
			"Spa Client Profile", {"mobile": self.mobile, "name": ("!=", self.name)}
		)
		if duplicate:
			frappe.throw(f"Mobile {self.mobile} is already registered to {duplicate}.")
		if self.online_account:
			if not frappe.db.exists("User", self.online_account):
				frappe.throw(f"There is no online account for {self.online_account}.")
			linked = frappe.db.get_value(
				"Spa Client Profile", {"online_account": self.online_account, "name": ("!=", self.name)}
			)
			if linked:
				frappe.throw(f"{self.online_account} is already linked to {linked}.")

	def after_insert(self):
		if self.customer:
			return
		config = settings()
		if not config.default_customer_group:
			frappe.throw("Set Default Customer Group in Spa Settings before adding clients.")
		customer = frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": self.client_name,
				"customer_type": "Individual",
				"customer_group": config.default_customer_group,
				"mobile_no": self.mobile,
				"email_id": self.email,
				"loyalty_program": self.loyalty_program or config.default_loyalty_program,
			}
		).insert(ignore_permissions=True)
		self.db_set("customer", customer.name)
