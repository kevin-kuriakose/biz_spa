import json

import frappe
from contextlib import contextmanager

from frappe.utils import add_days, cint, flt, get_datetime, getdate, now_datetime, nowdate
from frappe.utils.synchronization import filelock

from biz_spa.booking_rules import ACTIVE, branch_hours, check_line, clock, minutes


@contextmanager
def booking_lock():
	"""One booking at a time, so two people cannot both take the last free slot."""
	with filelock("spa_booking", timeout=15):
		# A fresh read, so a booking saved while this one waited is seen.
		frappe.db.commit()
		yield
		frappe.db.commit()


def as_list(value):
	return json.loads(value) if isinstance(value, str) else (value or [])


def service_rows(services):
	return [row if isinstance(row, dict) else {"service": row} for row in as_list(services)]


def candidates(row, branch, staff):
	picked = row.get("staff") or staff
	if picked:
		return [picked]
	return frappe.get_all(
		"Spa Staff Skill",
		filters={"service": row["service"], "parenttype": "Spa Staff Profile"},
		pluck="parent",
	)


def rooms_for(service, branch, room):
	if room:
		return [room]
	room_type = frappe.get_cached_value("Spa Service", service, "room_type_required")
	if not room_type:
		return [None]
	return frappe.get_all("Spa Room", filters={"branch": branch, "room_type": room_type, "is_active": 1}, pluck="name") or []


def assign(branch, date, start, services, staff=None, exclude=None):
	"""Picks free staff and rooms for services run back to back; None when the slot does not fit."""
	cursor, plan = start, []
	for row in services:
		service = row["service"]
		duration = cint(frappe.get_cached_value("Spa Service", service, "duration_minutes"))
		end = cursor + duration
		choice = None
		for person in candidates(row, branch, staff):
			if not row.get("staff") and not staff and not frappe.db.get_value("Spa Staff Profile", person, "is_bookable"):
				continue
			if any(p["staff"] == person and p["start"] < end and cursor < p["end"] for p in plan):
				continue
			for room in rooms_for(service, branch, row.get("room")):
				if any(room and p["room"] == room and p["start"] < end and cursor < p["end"] for p in plan):
					continue
				if not check_line(branch, date, service, person, room, cursor, end, exclude):
					choice = {"service": service, "staff": person, "room": room, "start": cursor, "end": end}
					break
			if choice:
				break
		if not choice:
			return None
		plan.append(choice)
		cursor = end
	return plan


@frappe.whitelist()
def get_available_slots(branch, date, services, staff=None):
	frappe.has_permission("Spa Appointment", "read", throw=True)
	return open_slots(branch, date, service_rows(services), staff)


def open_slots(branch, date, rows, staff=None, exclude=None):
	settings = frappe.get_cached_doc("Spa Settings")
	today = getdate(nowdate())
	if not rows or getdate(date) < today or (getdate(date) - today).days > cint(settings.booking_window_days or 60):
		return []
	hours = branch_hours(branch, date)
	if isinstance(hours, str):
		return []
	step = cint(settings.slot_interval_minutes) or 15
	floor = hours[0]
	if getdate(date) == today:
		now = now_datetime()
		floor = max(floor, now.hour * 60 + now.minute)
	slots = []
	for start in range(hours[0], hours[1], step):
		if start < floor:
			continue
		plan = assign(branch, date, start, rows, staff, exclude)
		if plan:
			slots.append({
				"start_time": clock(start),
				"end_time": clock(plan[-1]["end"]),
				"services": [{**p, "start": clock(p["start"]), "end": clock(p["end"])} for p in plan],
			})
	return slots


@frappe.whitelist()
def book_appointment(client, branch, date, start_time, services, source="Phone"):
	frappe.has_permission("Spa Appointment", "create", throw=True)
	with booking_lock():
		plan = assign(branch, date, minutes(start_time), service_rows(services))
		if not plan:
			frappe.throw("That slot is no longer available.")
		doc = frappe.get_doc({
			"doctype": "Spa Appointment",
			"client": client,
			"branch": branch,
			"appointment_date": date,
			"start_time": start_time,
			"source": source,
			"services": [{"service": p["service"], "staff": p["staff"], "room": p["room"], "start_time": clock(p["start"])} for p in plan],
		}).insert()
	return doc.name


@frappe.whitelist()
def reschedule_appointment(name, date, start_time):
	doc = frappe.get_doc("Spa Appointment", name)
	doc.check_permission("write")
	if doc.status not in ACTIVE:
		frappe.throw(f"A {doc.status} appointment cannot be rescheduled.")
	shift = minutes(start_time) - minutes(doc.start_time)
	doc.appointment_date, doc.start_time = date, start_time
	for row in doc.services or []:
		if row.fixed_start:
			row.start_time = clock(minutes(row.start_time) + shift)
	doc.reminder_sent = 0
	doc.save()
	return doc.name


@frappe.whitelist()
def cancel_appointment(name, reason):
	doc = frappe.get_doc("Spa Appointment", name)
	doc.check_permission("write")
	return cancel_doc(doc, reason)


def cancel_doc(doc, reason):
	if doc.status not in ACTIVE:
		frappe.throw(f"A {doc.status} appointment cannot be cancelled.")
	settings = frappe.get_cached_doc("Spa Settings")
	starts = get_datetime(f"{doc.appointment_date} {clock(minutes(doc.start_time))}")
	hours_left = (starts - now_datetime()).total_seconds() / 3600
	doc.status, doc.cancelled_reason = "Cancelled", reason
	if hours_left < flt(settings.cancellation_window_hours):
		doc.cancellation_fee = flt(doc.total_amount) * flt(settings.no_show_fee_percent) / 100
	doc.save()
	offered = offer_slot(doc)
	return {"cancellation_fee": doc.cancellation_fee, "waitlist_offered": offered}


def offer_slot(doc):
	"""Marks matching waitlist rows as Offered once a slot frees up (18.3)."""
	start = minutes(doc.start_time)
	window = "Morning" if start < 720 else "Afternoon" if start < 1020 else "Evening"
	offered = []
	for row in doc.services or []:
		for name in frappe.get_all("Spa Waitlist Entry", filters={
			"branch": doc.branch, "service": row.service, "status": "Waiting",
			"date_from": ("<=", doc.appointment_date), "date_to": (">=", doc.appointment_date),
			"time_window": ("in", ["Any", window]),
		}, pluck="name"):
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
	visit = frappe.get_doc({
		"doctype": "Spa Visit",
		"appointment": doc.name,
		"client": doc.client,
		"branch": doc.branch,
		"posting_date": nowdate(),
		"promotion": doc.promotion,
		"services": [{
			"service": r.service, "staff": r.staff, "room": r.room, "start_time": r.start_time,
			"end_time": r.end_time, "qty": 1, "rate": r.rate, "discount_percent": r.discount_percent,
			"amount": r.amount, "notes": r.notes,
		} for r in (doc.services or [])],
	}).insert()
	return visit.name


@frappe.whitelist()
def get_client_balances(client):
	frappe.has_permission("Spa Client Profile", "read", throw=True)
	return client_balances(client)


def client_balances(client):
	profile = frappe.db.get_value("Spa Client Profile", client, ["customer", "loyalty_points"], as_dict=True) or {}
	result = {"loyalty_points": cint(profile.get("loyalty_points")), "packages": [], "memberships": [], "gift_cards": []}
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
