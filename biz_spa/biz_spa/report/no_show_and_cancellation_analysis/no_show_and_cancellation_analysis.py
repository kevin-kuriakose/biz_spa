import frappe
from frappe.utils import add_days, cint, flt, getdate, nowdate

from biz_spa.report_helpers import branch_open_minutes, col, shift_minutes


def execute(filters=None):
	f = filters or {}
	cond = "AND branch = %(branch)s" if f.get("branch") else ""
	columns = [col("Branch", "branch", "Link", "Spa Branch"), col("Booked", "total", "Int", width=90), col("No Shows", "no_shows", "Int", width=90), col("Cancelled", "cancelled", "Int", width=90), col("No Show %", "no_show_rate", "Percent", width=100), col("Cancel %", "cancel_rate", "Percent", width=100), col("Lost Value", "lost", "Currency"), col("Fees Recorded", "fees", "Currency")]
	data = frappe.db.sql(f"""SELECT branch, COUNT(*) total, SUM(status = 'No Show') no_shows, SUM(status = 'Cancelled') cancelled, SUM(IF(status IN ('No Show', 'Cancelled'), total_amount, 0)) lost, SUM(cancellation_fee) fees
		FROM `tabSpa Appointment` WHERE docstatus < 2 AND appointment_date BETWEEN %(from_date)s AND %(to_date)s {cond} GROUP BY branch""", f, as_dict=True)
	for row in data:
		row.no_show_rate = flt(cint(row.no_shows) * 100 / row.total, 1)
		row.cancel_rate = flt(cint(row.cancelled) * 100 / row.total, 1)
	return columns, data
