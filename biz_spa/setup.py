import frappe


def ensure_customer_role():
	"""Spa Customer has no DocPerms on purpose: customers only reach data through biz_spa.api.customer."""
	if not frappe.db.exists("Role", "Spa Customer"):
		frappe.get_doc({"doctype": "Role", "role_name": "Spa Customer", "desk_access": 0}).insert(
			ignore_permissions=True
		)
