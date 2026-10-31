import re
from datetime import date as Date
from itertools import pairwise

import frappe
from frappe.utils import cint, flt, get_datetime, getdate, nowdate

ACTIVE = ("Scheduled", "Confirmed")
CLOSED = ("Cancelled", "No Show")
TRANSITIONS = {
	"Scheduled": ("Confirmed", "Checked In", "Cancelled", "No Show"),
	"Confirmed": ("Checked In", "Cancelled", "No Show"),
	"Checked In": ("In Progress", "No Show"),
	"In Progress": ("No Show",),
	"Completed": (),
	"Cancelled": ("Scheduled",),
	"No Show": ("Scheduled",),
}


class SlotTaken(frappe.ValidationError):
	pass


def to_minutes(value) -> int | None:
	if value in (None, ""):
		return None
	if hasattr(value, "total_seconds"):
		return int(value.total_seconds() // 60)
	parts = str(value).split(":")
	return int(parts[0]) * 60 + int(parts[1])


def clock(total: int) -> str:
	return f"{total // 60:02d}:{total % 60:02d}:00"


def clean_date(value) -> str:
	"""Checks a yyyy-mm-dd string from a request; getdate would read a blank as today."""
	try:
		return str(Date.fromisoformat(str(value or "")))
	except ValueError:
		frappe.throw("Choose a valid date.")


def clean_start(value) -> int:
	"""Minutes for an HH:MM or HH:MM:SS string from a request."""
	match = re.fullmatch(r"(\d{1,2}):(\d{2})(:\d{2})?", str(value or ""))
	if not match or int(match[1]) > 23 or int(match[2]) > 59:
		frappe.throw("Choose a valid time.")
	return int(match[1]) * 60 + int(match[2])


def weekday(date) -> str:
	return getdate(date).strftime("%A")


def compute_lines(doc):
	"""Sets line times and parent totals (18.2). Lines run back to back unless Fixed Start is
	ticked; a blank start cannot mean "follow on" because Frappe stamps new Time fields with now."""
	cursor = to_minutes(doc.start_time)
	last_end = cursor
	total = 0
	for row in doc.services or []:
		service = (
			frappe.get_cached_value("Spa Service", row.service, ["duration_minutes", "price"], as_dict=True)
			or {}
		)
		row.duration_minutes = cint(row.duration_minutes) or cint(service.get("duration_minutes"))
		if not flt(row.rate):
			row.rate = flt(service.get("price"))
		start = to_minutes(row.start_time) if row.fixed_start and row.start_time else cursor
		end = start + cint(row.duration_minutes)
		row.start_time, row.end_time = clock(start), clock(end)
		row.amount = flt(flt(row.rate) * (1 - flt(row.discount_percent) / 100), 2)
		total += flt(row.amount)
		cursor = end
		last_end = max(last_end, end)
	doc.end_time = clock(last_end)
	doc.total_duration = last_end - to_minutes(doc.start_time)
	doc.total_amount = flt(total, 2)


def closed_reason(branch, date) -> str | None:
	"""Why the branch is shut on this date, or None when it opens."""
	holiday_list = frappe.get_cached_value("Spa Branch", branch, "holiday_list")
	if holiday_list and frappe.db.exists("Holiday", {"parent": holiday_list, "holiday_date": getdate(date)}):
		return f"{branch} is closed on {date} (holiday)."
	is_closed = frappe.db.get_value(
		"Spa Branch Hours", {"parent": branch, "weekday": weekday(date)}, "is_closed"
	)
	if is_closed is None or is_closed:
		return f"{branch} is closed on {weekday(date)}."
	return None


def branch_hours(branch, date) -> tuple[int, int] | None:
	"""(open, close) in minutes, or None when the branch is shut."""
	if closed_reason(branch, date):
		return None
	row = frappe.db.get_value(
		"Spa Branch Hours",
		{"parent": branch, "weekday": weekday(date)},
		["open_time", "close_time"],
		as_dict=True,
	)
	return to_minutes(row.open_time), to_minutes(row.close_time)


def booked_lines(date, exclude, latest):
	"""Lines that hold staff or a room on this date. `latest` makes this a locking read: a plain read
	inside a transaction sees its opening snapshot, which can predate a booking that just committed."""
	lock = "LOCK IN SHARE MODE" if latest else ""
	return frappe.db.sql(
		f"""SELECT l.staff, l.room, l.start_time, l.end_time, COALESCE(s.buffer_minutes, 0) AS buffer
		FROM `tabSpa Appointment` a
		JOIN `tabSpa Appointment Service` l ON l.parent = a.name
		LEFT JOIN `tabSpa Service` s ON s.name = l.service
		WHERE a.appointment_date = %(date)s AND a.status NOT IN ('Cancelled', 'No Show')
		AND a.name != %(exclude)s {lock}""",
		{"date": getdate(date), "exclude": exclude or ""},
		as_dict=True,
	)


class Day:
	"""What the booking rules need for one branch and date, read once, so that testing a candidate
	line costs no queries. Every booking path checks lines through `check`."""

	def __init__(self, branch, date, exclude=None, latest=False):
		self.branch, self.date = branch, getdate(date)
		self.closed = closed_reason(branch, date)
		self.hours = None if self.closed else branch_hours(branch, date)
		self.rooms = frappe.get_all(
			"Spa Room", filters={"branch": branch, "is_active": 1}, fields=["name", "room_type"]
		)
		self.bookable = set(frappe.get_all("Spa Staff Profile", filters={"is_bookable": 1}, pluck="name"))
		self.skills = frappe.get_all(
			"Spa Staff Skill", filters={"parenttype": "Spa Staff Profile"}, fields=["parent", "service"]
		)
		self.skill_keys = {(row.parent, row.service) for row in self.skills}
		self.shifts = {}
		for row in frappe.get_all(
			"Spa Staff Shift",
			filters={"parenttype": "Spa Staff Profile", "weekday": weekday(date)},
			fields=["parent", "from_time", "to_time", "branch"],
		):
			self.shifts.setdefault(row.parent, []).append(row)
		midnight = get_datetime(f"{self.date} 00:00:00")
		self.time_off = {}
		for row in frappe.get_all(
			"Spa Staff Time Off",
			filters={
				"status": "Approved",
				"from_datetime": ("<", frappe.utils.add_days(midnight, 1)),
				"to_datetime": (">", midnight),
			},
			fields=["staff", "from_datetime", "to_datetime"],
		):
			away = (
				(get_datetime(row.from_datetime) - midnight).total_seconds() / 60,
				(get_datetime(row.to_datetime) - midnight).total_seconds() / 60,
			)
			self.time_off.setdefault(row.staff, []).append(away)
		self.lines = [
			{
				"staff": row.staff,
				"room": row.room,
				"start": to_minutes(row.start_time),
				"end": to_minutes(row.end_time) + cint(row.buffer),
			}
			for row in booked_lines(date, exclude, latest)
		]

	def skilled(self, service):
		return [row.parent for row in self.skills if row.service == service]

	def rooms_of_type(self, room_type):
		return [room.name for room in self.rooms if room.room_type == room_type]

	def busy(self, field, value, start, end):
		return any(
			line[field] == value and line["start"] < end and line["end"] > start for line in self.lines
		)

	def check(self, service, staff, room, start, end):
		"""Returns the first reason this line cannot be booked, or None (18.2)."""
		if self.closed:
			return self.closed
		if start < self.hours[0] or end > self.hours[1]:
			return f"{clock(start)[:5]}-{clock(end)[:5]} is outside {self.branch} opening hours."
		name = frappe.utils.escape_html(service)
		if staff:
			if not any(
				to_minutes(s.from_time) <= start
				and end <= to_minutes(s.to_time)
				and (not s.branch or s.branch == self.branch)
				for s in self.shifts.get(staff, [])
			):
				return f"{staff} is not on shift for {name} at {clock(start)[:5]}."
			if any(away < end and back > start for away, back in self.time_off.get(staff, [])):
				return f"{staff} has approved time off during {name}."
			if (staff, service) not in self.skill_keys:
				return f"{staff} is not skilled for {name}."
		buffer = cint(frappe.get_cached_value("Spa Service", service, "buffer_minutes"))
		for field, value in (("staff", staff), ("room", room)):
			if value and self.busy(field, value, start, end + buffer):
				return f"{value} is already booked around {clock(start)[:5]}."
		return None


def lock_resources(doc):
	"""Queues saves that compete for the same branch, staff or rooms. Row locks live in the database,
	so this holds across Desk, API and import, and across app servers. The order is fixed to avoid
	deadlocks, and the branch goes first because new lines insert next to each other in the index."""
	staff = sorted({row.staff for row in doc.services if row.staff})
	rooms = sorted({row.room for row in doc.services if row.room})
	for doctype, names in (("Spa Branch", [doc.branch]), ("Spa Staff Profile", staff), ("Spa Room", rooms)):
		if names:
			frappe.db.sql(
				f"SELECT name FROM `tab{doctype}` WHERE name IN %(names)s ORDER BY name FOR UPDATE",
				{"names": names},
			)


def validate_lines(doc):
	if not (doc.services or []):
		frappe.throw("Add at least one service.")
	if getdate(doc.appointment_date) < getdate(nowdate()) and doc.source != "Walk-in":
		frappe.throw("The appointment date is in the past.")
	lock_resources(doc)
	day = Day(doc.branch, doc.appointment_date, doc.name, latest=True)
	for row in doc.services:
		problem = day.check(
			row.service, row.staff, row.room, to_minutes(row.start_time), to_minutes(row.end_time)
		)
		if problem:
			frappe.throw(f"Row {row.idx}: {problem}", SlotTaken)
	lines = sorted(doc.services, key=lambda r: to_minutes(r.start_time))
	for one, two in pairwise(lines):
		if to_minutes(two.start_time) < to_minutes(one.end_time) and (
			(one.staff and one.staff == two.staff) or (one.room and one.room == two.room)
		):
			frappe.throw(f"Rows {one.idx} and {two.idx} overlap for the same staff member or room.")
