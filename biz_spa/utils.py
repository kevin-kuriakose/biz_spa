import frappe
from frappe.utils import flt


def ensure_item(doc):
	"""Creates the non-stock Item for a service, package or plan when none is linked (18.1)."""
	if doc.item:
		return
	item_code = f"SPA-{frappe.scrub(doc.name).upper().replace('_', '-')}"[:140]
	if not frappe.db.exists("Item", item_code):
		frappe.get_doc({
			"doctype": "Item",
			"item_code": item_code,
			"item_name": doc.name,
			"item_group": "Spa Services",
			"stock_uom": "Nos",
			"is_stock_item": 0,
			"standard_rate": flt(doc.price),
		}).insert(ignore_permissions=True)
	doc.db_set("item", item_code)
