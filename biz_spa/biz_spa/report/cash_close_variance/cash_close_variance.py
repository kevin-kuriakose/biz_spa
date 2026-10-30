import frappe
from frappe.utils import add_days, cint, flt, getdate, nowdate

from biz_spa.report_helpers import branch_open_minutes, col, shift_minutes


def execute(filters=None):
	f = filters or {}
	cond = "AND branch = %(branch)s" if f.get("branch") else ""
	columns = [col("Close", "name", "Link", "Spa Cash Close", 170), col("Date", "close_date", "Date", width=110), col("Branch", "branch", "Link", "Spa Branch"), col("Status", "state", width=100), col("Expected", "expected_total", "Currency"), col("Counted", "counted_total", "Currency"), col("Variance", "variance", "Currency"), col("Closed By", "closed_by", "Link", "User", 170)]
	data = frappe.db.sql(f"""SELECT name, close_date, branch, IF(docstatus = 1, 'Submitted', 'Draft') state, expected_total, counted_total, variance, closed_by
		FROM `tabSpa Cash Close` WHERE docstatus < 2 AND close_date BETWEEN %(from_date)s AND %(to_date)s {cond} ORDER BY close_date DESC""", f, as_dict=True)
	return columns, data
