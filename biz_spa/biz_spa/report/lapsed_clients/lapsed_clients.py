import frappe
from frappe.utils import add_days, cint, nowdate

from biz_spa.report_helpers import col


def execute(filters=None):
	f = filters or {}
	cutoff = add_days(nowdate(), -cint(f.get("days_since_last_visit") or 30))
	cond = "AND preferred_branch = %(branch)s" if f.get("branch") else ""
	columns = [
		col("Client", "name", "Link", "Spa Client Profile", 150),
		col("Name", "client_name", width=170),
		col("Mobile", "mobile"),
		col("Last Visit", "last_visit_date", "Date", width=110),
		col("Days Away", "days_away", "Int", width=90),
		col("Visits", "visit_count", "Int", width=70),
		col("Total Spend", "total_spend", "Currency"),
		col("Preferred Branch", "preferred_branch", "Link", "Spa Branch"),
	]
	data = frappe.db.sql(
		f"""SELECT name, client_name, mobile, last_visit_date, DATEDIFF(CURDATE(), last_visit_date) days_away, visit_count, total_spend, preferred_branch
		FROM `tabSpa Client Profile` WHERE docstatus < 2 AND status = 'Active' AND last_visit_date IS NOT NULL AND last_visit_date < %(cutoff)s {cond} ORDER BY last_visit_date""",
		{**f, "cutoff": cutoff},
		as_dict=True,
	)
	return columns, data
