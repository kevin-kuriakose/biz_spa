from datetime import timedelta

import frappe
from frappe.utils import add_to_date, cint, flt, get_datetime, getdate, nowdate

ACTIVE = ("Scheduled", "Confirmed")
CLOSED = ("Cancelled", "No Show")


def minutes(value):
	if value in (None, ""):
		return None
	if isinstance(value, timedelta):
		return int(value.total_seconds() // 60)
	parts = str(value).split(":")
	return int(parts[0]) * 60 + int(parts[1])


def clock(total):
	return f"{total // 60:02d}:{total % 60:02d}:00"


def weekday(date):
	return getdate(date).strftime("%A")


def compute_lines(doc):
	"""Sets line times and parent totals (18.2). Lines run back to back unless Fixed Start is
	ticked; a blank start cannot mean "follow on" because Frappe stamps new Time fields with now."""
	cursor = minutes(doc.start_time)
	last_end = cursor
	total = 0
	for row in doc.services or []:
		service = frappe.get_cached_value("Spa Service", row.service, ["duration_minutes", "price"], as_dict=True) or {}
		row.duration_minutes = cint(row.duration_minutes) or cint(service.get("duration_minutes"))
		if not flt(row.rate):
			row.rate = flt(service.get("price"))
		start = minutes(row.start_time) if row.fixed_start and row.start_time else cursor
		end = start + cint(row.duration_minutes)
		row.start_time, row.end_time = clock(start), clock(end)
		row.amount = flt(row.rate) * (1 - flt(row.discount_percent) / 100)
		total += flt(row.amount)
		cursor = end
		last_end = max(last_end, end)
	doc.end_time = clock(last_end)
	doc.total_duration = last_end - minutes(doc.start_time)
	doc.total_amount = total


def branch_hours(branch, date):
	"""Returns (open, close) in minutes, or a message string when the branch is shut."""
	holiday_list = frappe.get_cached_value("Spa Branch", branch, "holiday_list")
	if holiday_list and frappe.db.exists("Holiday", {"parent": holiday_list, "holiday_date": getdate(date)}):
		return f"{branch} is closed on {date} (holiday)."
	row = frappe.db.get_value("Spa Branch Hours", {"parent": branch, "weekday": weekday(date)}, ["is_closed", "open_time", "close_time"], as_dict=True)
	if not row or row.is_closed:
		return f"{branch} is closed on {weekday(date)}."
	return minutes(row.open_time), minutes(row.close_time)


def check_line(branch, date, service, staff, room, start, end, exclude=None):
	"""Returns the first reason this line cannot be booked, or None (18.2)."""
	hours = branch_hours(branch, date)
	if isinstance(hours, str):
		return hours
	if start < hours[0] or end > hours[1]:
		return f"{clock(start)[:5]}-{clock(end)[:5]} is outside {branch} opening hours."
	name = frappe.utils.escape_html(service)
	if staff:
		shifts = frappe.get_all("Spa Staff Shift", filters={"parent": staff, "weekday": weekday(date)}, fields=["from_time", "to_time", "branch"])
		if not any(minutes(s.from_time) <= start and end <= minutes(s.to_time) and (not s.branch or s.branch == branch) for s in shifts):
			return f"{staff} is not on shift for {name} at {clock(start)[:5]}."
		day = get_datetime(f"{getdate(date)} 00:00:00")
		if frappe.db.exists("Spa Staff Time Off", {
			"staff": staff, "status": "Approved",
			"from_datetime": ("<", add_to_date(day, minutes=end)),
			"to_datetime": (">", add_to_date(day, minutes=start)),
		}):
			return f"{staff} has approved time off during {name}."
		if not frappe.db.exists("Spa Staff Skill", {"parent": staff, "service": service}):
			return f"{staff} is not skilled for {name}."
	buffer = cint(frappe.get_cached_value("Spa Service", service, "buffer_minutes"))
	for field, value in (("staff", staff), ("room", room)):
		if value and overlapping(field, value, date, start, end + buffer, exclude):
			return f"{value} is already booked around {clock(start)[:5]}."
	return None


def overlapping(field, value, date, start, end, exclude):
	return frappe.db.sql(
		f"""SELECT l.parent FROM `tabSpa Appointment Service` l
		JOIN `tabSpa Appointment` a ON a.name = l.parent
		LEFT JOIN `tabSpa Service` s ON s.name = l.service
		WHERE a.appointment_date = %(date)s AND a.status NOT IN ('Cancelled', 'No Show')
		AND a.name != %(exclude)s AND l.{field} = %(value)s
		AND l.start_time < %(end)s
		AND ADDTIME(l.end_time, SEC_TO_TIME(COALESCE(s.buffer_minutes, 0) * 60)) > %(start)s
		LIMIT 1""",
		{"date": getdate(date), "exclude": exclude or "", "value": value, "start": clock(start), "end": clock(end)},
	)


def validate_lines(doc):
	if not (doc.services or []):
		frappe.throw("Add at least one service.")
	if getdate(doc.appointment_date) < getdate(nowdate()) and doc.source != "Walk-in":
		frappe.throw("The appointment date is in the past.")
	for row in doc.services:
		problem = check_line(doc.branch, doc.appointment_date, row.service, row.staff, row.room, minutes(row.start_time), minutes(row.end_time), doc.name)
		if problem:
			frappe.throw(f"Row {row.idx}: {problem}")
	lines = sorted(doc.services, key=lambda r: minutes(r.start_time))
	for one, two in zip(lines, lines[1:]):
		if minutes(two.start_time) < minutes(one.end_time) and ((one.staff and one.staff == two.staff) or (one.room and one.room == two.room)):
			frappe.throw(f"Rows {one.idx} and {two.idx} overlap for the same staff member or room.")
