import frappe
from frappe.utils import add_days, cint, flt, getdate, nowdate

from biz_spa.report_helpers import branch_open_minutes, col, shift_minutes


def execute(filters=None):
	f = filters or {}
	cond = "AND branch = %(branch)s" if f.get("branch") else ""
	columns = [col("Membership", "name", "Link", "Spa Membership", 170), col("Client", "client", "Link", "Spa Client Profile", 140), col("Plan", "plan", "Link", "Spa Membership Plan", 150), col("Branch", "branch", "Link", "Spa Branch"), col("End Date", "end_date", "Date", width=110), col("Days Left", "days_left", "Int", width=90), col("Auto Renew", "auto_renew", "Check", width=100), col("Rate", "rate", "Currency")]
	data = frappe.db.sql(f"""SELECT name, client, plan, branch, end_date, DATEDIFF(end_date, CURDATE()) days_left, auto_renew, rate FROM `tabSpa Membership`
		WHERE docstatus = 1 AND status = 'Active' AND end_date <= %(limit)s {cond} ORDER BY end_date""", {**f, "limit": add_days(nowdate(), cint(f.get("days_ahead") or 30))}, as_dict=True)
	return columns, data
