import frappe
from frappe.utils import add_days, cint, flt, nowdate

from biz_spa.report_helpers import col


def execute(filters=None):
	f = filters or {}
	cond = "".join(
		[
			" AND branch = %(branch)s" if f.get("branch") else "",
			" AND status = %(status)s" if f.get("status") else "",
		]
	)
	if cint(f.get("expiring_within_days")):
		cond += " AND expiry_date <= %(limit)s"
	columns = [
		col("Package Sale", "name", "Link", "Spa Client Package", 170),
		col("Client", "client", "Link", "Spa Client Profile", 140),
		col("Package", "package", "Link", "Spa Package", 170),
		col("Expiry", "expiry_date", "Date", width=110),
		col("Status", "status", width=90),
		col("Total Sessions", "total_sessions", "Int", width=110),
		col("Balance Sessions", "balance_sessions", "Int", width=120),
		col("Net Amount", "net_amount", "Currency"),
		col("Liability", "liability", "Currency"),
	]
	data = frappe.db.sql(
		f"""SELECT name, client, package, expiry_date, status, total_sessions, balance_sessions, net_amount FROM `tabSpa Client Package`
		WHERE docstatus = 1 {cond} ORDER BY expiry_date""",
		{**f, "limit": add_days(nowdate(), cint(f.get("expiring_within_days")))},
		as_dict=True,
	)
	for row in data:
		row.liability = (
			flt(flt(row.net_amount) * cint(row.balance_sessions) / cint(row.total_sessions), 2)
			if cint(row.total_sessions)
			else 0
		)
	return columns, data
