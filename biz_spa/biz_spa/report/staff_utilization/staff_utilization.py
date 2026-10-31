import frappe
from frappe.utils import cint, flt

from biz_spa.report_helpers import col, shift_minutes


def execute(filters=None):
	f = filters or {}
	columns = [
		col("Staff", "staff", "Link", "Spa Staff Profile"),
		col("Name", "staff_name", width=160),
		col("Branch", "branch", "Link", "Spa Branch"),
		col("Available Minutes", "available", "Int"),
		col("Booked Minutes", "booked", "Int"),
		col("Utilization %", "utilization", "Percent"),
	]
	staff_filters = {"is_bookable": 1}
	for key in ("branch",):
		if f.get(key):
			staff_filters[key] = f[key]
	if f.get("staff"):
		staff_filters["name"] = f["staff"]
	data = []
	for row in frappe.get_all(
		"Spa Staff Profile", filters=staff_filters, fields=["name", "staff_name", "branch"]
	):
		booked = frappe.db.sql(
			"""SELECT SUM(l.duration_minutes) FROM `tabSpa Appointment Service` l JOIN `tabSpa Appointment` a ON a.name = l.parent
			WHERE a.docstatus < 2 AND l.staff = %s AND a.status NOT IN ('Cancelled', 'No Show') AND a.appointment_date BETWEEN %s AND %s""",
			(row.name, f["from_date"], f["to_date"]),
		)[0][0]
		available = shift_minutes(row.name, f["from_date"], f["to_date"])
		data.append(
			{
				"staff": row.name,
				"staff_name": row.staff_name,
				"branch": row.branch,
				"available": available,
				"booked": cint(booked),
				"utilization": flt(cint(booked) * 100 / available, 1) if available else 0,
			}
		)
	return columns, sorted(data, key=lambda r: -r["utilization"])
