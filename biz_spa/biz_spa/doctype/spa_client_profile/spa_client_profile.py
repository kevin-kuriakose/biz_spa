from frappe.model.document import Document
import frappe


class SpaClientProfile(Document):
	def validate(self):
		duplicate = frappe.db.get_value("Spa Client Profile", {"mobile": self.mobile, "name": ("!=", self.name)})
		if duplicate:
			frappe.throw(f"Mobile {self.mobile} is already registered to {duplicate}.")

	def after_insert(self):
		if self.customer:
			return
		settings = frappe.get_cached_doc("Spa Settings")
		if not settings.default_customer_group:
			frappe.throw("Set Default Customer Group in Spa Settings before adding clients.")
		customer = frappe.get_doc({
			"doctype": "Customer",
			"customer_name": self.client_name,
			"customer_type": "Individual",
			"customer_group": settings.default_customer_group,
			"mobile_no": self.mobile,
			"email_id": self.email,
			"loyalty_program": self.loyalty_program or settings.default_loyalty_program,
		}).insert(ignore_permissions=True)
		self.db_set("customer", customer.name)
