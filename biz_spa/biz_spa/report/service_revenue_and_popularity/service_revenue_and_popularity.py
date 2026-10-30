import frappe
from frappe.utils import add_days, cint, flt, getdate, nowdate

from biz_spa.report_helpers import branch_open_minutes, col, shift_minutes


def execute(filters=None):
	f = filters or {}
	cond = "".join([" AND v.branch = %(branch)s" if f.get("branch") else "", " AND s.category = %(category)s" if f.get("category") else ""])
	columns = [col("Service", "service", "Link", "Spa Service", 200), col("Category", "category", "Link", "Spa Service Category", 150), col("Times Sold", "sold", "Int", width=100), col("Billed", "billed", "Currency"), col("Redeemed Prepaid", "redeemed", "Currency", width=140), col("Total Value", "total", "Currency")]
	data = frappe.db.sql(f"""SELECT l.service, s.category, SUM(l.qty) sold,
		SUM(IF(l.redeem_from IN ('Package', 'Membership'), 0, l.amount)) billed, SUM(IF(l.redeem_from IN ('Package', 'Membership'), l.amount, 0)) redeemed, SUM(l.amount) total
		FROM `tabSpa Visit Service` l JOIN `tabSpa Visit` v ON v.name = l.parent JOIN `tabSpa Service` s ON s.name = l.service
		WHERE v.docstatus = 1 AND v.posting_date BETWEEN %(from_date)s AND %(to_date)s {cond} GROUP BY l.service, s.category ORDER BY total DESC""", f, as_dict=True)
	return columns, data
