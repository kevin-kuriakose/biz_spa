import frappe
from frappe.utils import add_days, cint, flt, getdate, nowdate

from biz_spa.report_helpers import branch_open_minutes, col, shift_minutes


def execute(filters=None):
	f = filters or {}
	cond = "".join([" AND v.branch = %(branch)s" if f.get("branch") else "", " AND c.item = %(item)s" if f.get("item") else ""])
	columns = [col("Item", "item", "Link", "Item", 200), col("Branch", "branch", "Link", "Spa Branch"), col("Qty Used", "qty", "Float", width=100), col("Visits", "visits", "Int", width=80), col("Stock Value", "value", "Currency")]
	data = frappe.db.sql(f"""SELECT c.item, v.branch, SUM(c.qty) qty, COUNT(DISTINCT v.name) visits,
		ABS(COALESCE((SELECT SUM(sle.stock_value_difference) FROM `tabStock Ledger Entry` sle JOIN `tabSpa Visit` x ON x.stock_entry = sle.voucher_no
			WHERE x.docstatus = 1 AND sle.is_cancelled = 0 AND sle.item_code = c.item AND x.branch = v.branch AND x.posting_date BETWEEN %(from_date)s AND %(to_date)s), 0)) value
		FROM `tabSpa Visit Consumable` c JOIN `tabSpa Visit` v ON v.name = c.parent
		WHERE v.docstatus = 1 AND v.posting_date BETWEEN %(from_date)s AND %(to_date)s {cond} GROUP BY c.item, v.branch ORDER BY qty DESC""", f, as_dict=True)
	return columns, data
