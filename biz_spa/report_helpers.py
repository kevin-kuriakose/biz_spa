import frappe
from frappe.utils import add_days, date_diff, getdate

from biz_spa.booking_rules import minutes


def col(label, fieldname, fieldtype="Data", options=None, width=130):
	column = {"label": label, "fieldname": fieldname, "fieldtype": fieldtype, "width": width}
	if options:
		column["options"] = options
	return column


def days(from_date, to_date):
	return [add_days(from_date, i) for i in range(date_diff(to_date, from_date) + 1)]


def shift_minutes(staff, from_date, to_date):
	shifts = frappe.get_all(
		"Spa Staff Shift", filters={"parent": staff}, fields=["weekday", "from_time", "to_time"]
	)
	total = 0
	for day in days(from_date, to_date):
		name = getdate(day).strftime("%A")
		total += sum(minutes(s.to_time) - minutes(s.from_time) for s in shifts if s.weekday == name)
	return total


def branch_open_minutes(branch, from_date, to_date):
	hours = frappe.get_all(
		"Spa Branch Hours",
		filters={"parent": branch, "is_closed": 0},
		fields=["weekday", "open_time", "close_time"],
	)
	total = 0
	for day in days(from_date, to_date):
		name = getdate(day).strftime("%A")
		total += sum(minutes(h.close_time) - minutes(h.open_time) for h in hours if h.weekday == name)
	return total
