import json

import frappe
from frappe.utils import cint, flt, get_datetime, getdate, now_datetime, nowdate

from biz_spa.booking_rules import ACTIVE, Day, clean_date, clean_start, clock, to_minutes
from biz_spa.utils import settings


def as_list(value):
	try:
		rows = json.loads(value) if isinstance(value, str) else (value or [])
	except ValueError:
		frappe.throw("Services must be a list.")
	if not isinstance(rows, list):
		frappe.throw("Services must be a list.")
	return rows


def service_rows(services):
	rows = [row if isinstance(row, dict) else {"service": row} for row in as_list(services)]
	for row in rows:
		service = row.get("service")
		if not isinstance(service, str) or not frappe.db.get_value("Spa Service", service, "is_active"):
			frappe.throw("Choose a valid service.")
	return rows


def active_branch(branch):
	if not branch or not frappe.db.get_value("Spa Branch", branch, "is_active"):
		frappe.throw("Choose a branch.")
	return branch


def candidates(day, row, staff):
	picked = row.get("staff") or staff
	if picked:
		return [picked]
	return [person for person in day.skilled(row["service"]) if person in day.bookable]


def rooms_for(day, service, room):
	if room:
		return [room]
	room_type = frappe.get_cached_value("Spa Service", service, "room_type_required")
	return day.rooms_of_type(room_type) if room_type else [None]


def assign(day, start, services, staff=None):
	"""Picks free staff and rooms for services run back to back; None when the slot does not fit."""
	cursor, plan = start, []
	for row in services:
		service = row["service"]
		end = cursor + cint(frappe.get_cached_value("Spa Service", service, "duration_minutes"))
		choice = None
		for person in candidates(day, row, staff):
			if any(p["staff"] == person and p["start"] < end and cursor < p["end"] for p in plan):
				continue
			for room in rooms_for(day, service, row.get("room")):
				if any(room and p["room"] == room and p["start"] < end and cursor < p["end"] for p in plan):
					continue
				if not day.check(service, person, room, cursor, end):
					choice = {"service": service, "staff": person, "room": room, "start": cursor, "end": end}
					break
			if choice:
				break
		if not choice:
			return None
		plan.append(choice)
		cursor = end
	return plan


def slot_starts(day):
	"""Start times on offer for this day, inside the booking window and not yet past."""
	config = settings()
	today = getdate(nowdate())
	if not day.hours or day.date < today or (day.date - today).days > cint(config.booking_window_days or 60):
		return []
	floor = day.hours[0]
	if day.date == today:
		now = now_datetime()
		floor = max(floor, now.hour * 60 + now.minute)
	step = cint(config.slot_interval_minutes) or 15
	return [start for start in range(day.hours[0], day.hours[1], step) if start >= floor]


@frappe.whitelist()
def get_available_slots(branch, date, services, staff=None):
	frappe.has_permission("Spa Appointment", "read", throw=True)
	return open_slots(active_branch(branch), clean_date(date), service_rows(services), staff)


def open_slots(branch, date, rows, staff=None, exclude=None):
	if not rows:
		return []
	day = Day(branch, date, exclude)
	slots = []
	for start in slot_starts(day):
		plan = assign(day, start, rows, staff)
		if plan:
			slots.append(
				{
					"start_time": clock(start),
					"end_time": clock(plan[-1]["end"]),
					"services": [{**p, "start": clock(p["start"]), "end": clock(p["end"])} for p in plan],
				}
			)
	return slots


def plan_at(branch, date, rows, start, staff=None, exclude=None):
	"""The plan for the one start time being booked, under the same rules as open_slots. It only
	screens the request: the Spa Appointment controller claims the slot when the document saves."""
	day = Day(branch, date, exclude)
	return assign(day, start, rows, staff) if start in slot_starts(day) else None


@frappe.whitelist()
def book_appointment(client, branch, date, start_time, services, source="Phone"):
	frappe.has_permission("Spa Appointment", "create", throw=True)
	active_branch(branch)
	date, start = clean_date(date), clean_start(start_time)
	plan = plan_at(branch, date, service_rows(services), start)
	if not plan:
		frappe.throw("That slot is no longer available.")
	doc = frappe.get_doc(
		{
			"doctype": "Spa Appointment",
			"client": client,
			"branch": branch,
			"appointment_date": date,
			"start_time": clock(start),
			"source": source,
			"services": [
				{
					"service": p["service"],
					"staff": p["staff"],
					"room": p["room"],
					"start_time": clock(p["start"]),
				}
				for p in plan
			],
		}
	).insert()
	return doc.name


@frappe.whitelist()
def reschedule_appointment(name, date, start_time):
	doc = frappe.get_doc("Spa Appointment", name)
	doc.check_permission("write")
	if doc.status not in ACTIVE:
		frappe.throw(f"A {doc.status} appointment cannot be rescheduled.")
	date, start = clean_date(date), clean_start(start_time)
	shift = start - to_minutes(doc.start_time)
	doc.appointment_date, doc.start_time = date, clock(start)
	for row in doc.services or []:
		if row.fixed_start:
			row.start_time = clock(to_minutes(row.start_time) + shift)
	doc.reminder_sent = 0
	doc.save()
	return doc.name


@frappe.whitelist(methods=["POST"])
def set_appointment_status(name, status):
	"""The statuses staff set by hand. Check In, Cancel and Completed have their own paths because
	they create the visit, record the fee or follow the visit's submit."""
	doc = frappe.get_doc("Spa Appointment", name)
	doc.check_permission("write")
	if status not in ("Scheduled", "Confirmed", "In Progress", "No Show"):
		frappe.throw(f"{status} cannot be set by hand.")
	doc.status = status
	doc.save()
	return doc.status


@frappe.whitelist()
def cancel_appointment(name, reason):
	doc = frappe.get_doc("Spa Appointment", name)
	doc.check_permission("write")
	return cancel_doc(doc, reason)


def cancel_doc(doc, reason):
	if doc.status not in ACTIVE:
		frappe.throw(f"A {doc.status} appointment cannot be cancelled.")
	starts = get_datetime(f"{doc.appointment_date} {clock(to_minutes(doc.start_time))}")
	hours_left = (starts - now_datetime()).total_seconds() / 3600
	doc.status, doc.cancelled_reason = "Cancelled", reason
	if hours_left < flt(settings().cancellation_window_hours):
		doc.cancellation_fee = flt(flt(doc.total_amount) * flt(settings().no_show_fee_percent) / 100, 2)
	doc.save()
	offered = offer_slot(doc)
	return {"cancellation_fee": doc.cancellation_fee, "waitlist_offered": offered}


def offer_slot(doc):
	"""Marks matching waitlist rows as Offered once a slot frees up (18.3)."""
	start = to_minutes(doc.start_time)
	window = "Morning" if start < 720 else "Afternoon" if start < 1020 else "Evening"
	offered = []
	for row in doc.services or []:
		for name in frappe.get_all(
			"Spa Waitlist Entry",
			filters={
				"branch": doc.branch,
				"service": row.service,
				"status": "Waiting",
				"date_from": ("<=", doc.appointment_date),
				"date_to": (">=", doc.appointment_date),
				"time_window": ("in", ["Any", window]),
			},
			pluck="name",
		):
			frappe.db.set_value("Spa Waitlist Entry", name, "status", "Offered")
			offered.append(name)
	return offered


@frappe.whitelist()
def check_in(appointment):
	doc = frappe.get_doc("Spa Appointment", appointment)
	doc.check_permission("write")
	if doc.status not in ACTIVE:
		frappe.throw(f"A {doc.status} appointment cannot be checked in.")
	doc.status = "Checked In"
	doc.save()
	if not frappe.db.exists("DocType", "Spa Visit"):
		return None
	visit = frappe.get_doc(
		{
			"doctype": "Spa Visit",
			"appointment": doc.name,
			"client": doc.client,
			"branch": doc.branch,
			"posting_date": nowdate(),
			"promotion": doc.promotion,
			"services": [
				{
					"service": r.service,
					"staff": r.staff,
					"room": r.room,
					"start_time": r.start_time,
					"end_time": r.end_time,
					"qty": 1,
					"rate": r.rate,
					"discount_percent": r.discount_percent,
					"amount": r.amount,
					"notes": r.notes,
				}
				for r in (doc.services or [])
			],
		}
	).insert()
	return visit.name


@frappe.whitelist()
def get_client_balances(client):
	frappe.has_permission("Spa Client Profile", "read", throw=True)
	return client_balances(client)


def client_balances(client):
	profile = (
		frappe.db.get_value("Spa Client Profile", client, ["customer", "loyalty_points"], as_dict=True) or {}
	)
	result = {
		"loyalty_points": cint(profile.get("loyalty_points")),
		"packages": [],
		"memberships": [],
		"gift_cards": [],
	}
	if frappe.db.exists("DocType", "Spa Client Package"):
		result["packages"] = frappe.get_all(
			"Spa Client Package",
			filters={"client": client, "docstatus": 1, "status": "Active"},
			fields=["name", "package", "expiry_date", "balance_sessions"],
		)
	if frappe.db.exists("DocType", "Spa Membership"):
		result["memberships"] = frappe.get_all(
			"Spa Membership",
			filters={"client": client, "docstatus": 1, "status": "Active"},
			fields=["name", "plan", "end_date"],
		)
	if frappe.db.exists("DocType", "Spa Gift Card") and profile.get("customer"):
		result["gift_cards"] = frappe.get_all(
			"Spa Gift Card",
			filters={"purchaser": profile["customer"], "docstatus": 1, "status": "Active"},
			fields=["name", "card_code", "balance", "expiry_date"],
		)
	return result
