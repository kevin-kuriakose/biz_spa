import frappe
from frappe.utils import cint, flt

from biz_spa.report_helpers import branch_open_minutes, col


def execute(filters=None):
	f = filters or {}
	columns = [
		col("Room", "room", "Link", "Spa Room", 130),
		col("Name", "room_name", width=170),
		col("Type", "room_type", width=140),
		col("Branch", "branch", "Link", "Spa Branch"),
		col("Open Minutes", "open_minutes", "Int"),
		col("Booked Minutes", "booked", "Int"),
		col("Utilization %", "utilization", "Percent"),
	]
	room_filters = {"is_active": 1}
	for key in ("branch", "room_type"):
		if f.get(key):
			room_filters[key] = f[key]
	data = []
	for room in frappe.get_all(
		"Spa Room", filters=room_filters, fields=["name", "room_name", "room_type", "branch"]
	):
		booked = frappe.db.sql(
			"""SELECT SUM(l.duration_minutes) FROM `tabSpa Appointment Service` l JOIN `tabSpa Appointment` a ON a.name = l.parent
			WHERE a.docstatus < 2 AND l.room = %s AND a.status NOT IN ('Cancelled', 'No Show') AND a.appointment_date BETWEEN %s AND %s""",
			(room.name, f["from_date"], f["to_date"]),
		)[0][0]
		open_minutes = branch_open_minutes(room.branch, f["from_date"], f["to_date"])
		data.append(
			{
				"room": room.name,
				"room_name": room.room_name,
				"room_type": room.room_type,
				"branch": room.branch,
				"open_minutes": open_minutes,
				"booked": cint(booked),
				"utilization": flt(cint(booked) * 100 / open_minutes, 1) if open_minutes else 0,
			}
		)
	return columns, sorted(data, key=lambda r: -r["utilization"])
