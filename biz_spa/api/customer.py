"""Customer-facing API behind /spa. The Spa Customer role has no DocPerms, so every read here is
scoped to the signed-in customer's own client profile, and only these methods reach the data."""

import re
from contextlib import contextmanager

import frappe
from frappe.rate_limiter import rate_limit
from frappe.utils import (
	add_days,
	cint,
	flt,
	get_datetime,
	getdate,
	now_datetime,
	nowdate,
	validate_email_address,
)

from biz_spa.api.booking import active_branch, as_list, cancel_doc, client_balances, open_slots, plan_at
from biz_spa.booking_rules import ACTIVE, SlotTaken, clean_date, clean_start, clock, to_minutes
from biz_spa.utils import settings

ROLE = "Spa Customer"
MAX_ACTIVE_BOOKINGS = 3
MAX_SERVICES = 5
LINK_SECONDS = 24 * 60 * 60
PROFILE_FIELDS = [
	"date_of_birth",
	"gender",
	"allergies",
	"preferences",
	"preferred_branch",
	"marketing_consent",
]


def my_client(active=False):
	if frappe.session.user == "Guest":
		frappe.throw("Please sign in first.", frappe.AuthenticationError)
	client = frappe.db.get_value(
		"Spa Client Profile", {"online_account": frappe.session.user}, ["name", "status"], as_dict=True
	)
	if not client:
		frappe.throw(
			"Your account isn't linked to a client record yet. Please ask reception.", frappe.PermissionError
		)
	if active and client.status != "Active":
		frappe.throw("Online booking isn't available on your account. Please call the spa.")
	return client.name


def my_appointment(name):
	client = my_client(active=True)
	if not name or frappe.db.get_value("Spa Appointment", name, "client") != client:
		frappe.throw("Appointment not found.", frappe.DoesNotExistError)
	return frappe.get_doc("Spa Appointment", name)


def online_services():
	# Services that need a patch test or consultation are arranged with the spa, so they stay off this flow.
	return frappe.get_all(
		"Spa Service",
		filters={"is_active": 1, "online_bookable": 1, "requires_consultation": 0, "requires_patch_test": 0},
		fields=["name", "category", "duration_minutes", "price"],
		order_by="category, name",
	)


def online_rows(services):
	names = [str(name) for name in as_list(services)]
	allowed = {service.name for service in online_services()}
	if not names or len(names) > MAX_SERVICES or not set(names) <= allowed:
		frappe.throw(f"Choose between 1 and {MAX_SERVICES} services that can be booked online.")
	return [{"service": name} for name in names]


def hours_until(doc) -> float:
	return (
		get_datetime(f"{doc.appointment_date} {clock(to_minutes(doc.start_time))}") - now_datetime()
	).total_seconds() / 3600


@contextmanager
def claiming_slot():
	"""Someone else may take the slot between the search and the save; the save is what decides."""
	try:
		yield
	except SlotTaken:
		frappe.clear_messages()
		frappe.throw("That time was just taken. Please pick another.")


def upcoming_bookings(client):
	# Holding the client row queues this customer's other requests. The commit starts a new snapshot
	# after the lock is held, so the count includes whatever the request before this one saved.
	frappe.db.commit()
	frappe.db.get_value("Spa Client Profile", client, "name", for_update=True)
	return frappe.db.count(
		"Spa Appointment", {"client": client, "status": ("in", ACTIVE), "appointment_date": (">=", nowdate())}
	)


def clean_mobile(mobile):
	mobile = re.sub(r"[\s()-]", "", mobile or "")
	if not re.fullmatch(r"\+?\d{10,15}", mobile):
		frappe.throw("Enter a valid mobile number.")
	return mobile


@frappe.whitelist(allow_guest=True)
def me():
	user = frappe.session.user
	if user == "Guest":
		return {"user": None}
	client = frappe.db.get_value(
		"Spa Client Profile", {"online_account": user}, ["name", "client_name", "status"], as_dict=True
	)
	return {
		"user": user,
		"full_name": frappe.db.get_value("User", user, "full_name"),
		"is_customer": ROLE in frappe.get_roles(),
		"client": client,
	}


@frappe.whitelist(allow_guest=True)
def catalog():
	config = settings()
	return {
		"branches": frappe.get_all(
			"Spa Branch", filters={"is_active": 1}, fields=["name", "phone", "address"], order_by="name"
		),
		"services": online_services(),
		"default_branch": config.default_branch,
		"today": nowdate(),
		"last_date": add_days(nowdate(), cint(config.booking_window_days or 60)),
		"cancellation_window_hours": cint(config.cancellation_window_hours),
		"late_fee_percent": flt(config.no_show_fee_percent),
		"currency": frappe.db.get_default("currency") or "INR",
	}


def public_slots(branch, date, rows, exclude=None):
	return [
		{"start_time": s["start_time"], "end_time": s["end_time"]}
		for s in open_slots(branch, date, rows, exclude=exclude)
	]


@frappe.whitelist(allow_guest=True)
@rate_limit(limit=120, seconds=60)
def slots(branch, date, services):
	return public_slots(active_branch(branch), clean_date(date), online_rows(services))


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=10, seconds=3600)
def signup(full_name, email, mobile, password):
	if frappe.session.user != "Guest":
		frappe.throw("You are already signed in.")
	full_name = (full_name or "").strip()
	email = (email or "").strip().lower()
	mobile = clean_mobile(mobile)
	if not full_name:
		frappe.throw("Enter your name.")
	if not validate_email_address(email):
		frappe.throw("Enter a valid email address.")
	if len(password or "") < 8:
		frappe.throw("Use a password of at least 8 characters.")
	if frappe.db.exists("User", email):
		frappe.throw(
			"We couldn't create an account with those details. If you already have one, please sign in."
		)

	user = frappe.get_doc(
		{
			"doctype": "User",
			"email": email,
			"first_name": full_name,
			"enabled": 1,
			"send_welcome_email": 0,
			"new_password": password,
			"roles": [{"role": ROLE}],
		}
	)
	user.flags.ignore_permissions = True
	user.insert()

	# Email and mobile are unverified, so an account never attaches itself to an existing client's
	# history. Reception checks who they are and links the two with Online Account.
	on_file = frappe.db.exists("Spa Client Profile", {"mobile": mobile}) or frappe.db.exists(
		"Spa Client Profile", {"email": email}
	)
	if not on_file:
		frappe.get_doc(
			{
				"doctype": "Spa Client Profile",
				"client_name": full_name,
				"mobile": mobile,
				"email": email,
				"online_account": email,
				"referral_source": "Website",
			}
		).insert(ignore_permissions=True)
	else:
		offer_link(email)
	frappe.local.login_manager.login_as(email)


def offer_link(email):
	"""Mails a link to the address already on file, so clicking it proves the new account owns that
	address. A match on mobile alone proves nothing, so those stay with reception."""
	client = frappe.db.get_value("Spa Client Profile", {"email": email, "online_account": ("is", "not set")})
	if not client:
		return
	token = frappe.generate_hash(length=32)
	frappe.cache.set_value(
		f"spa_link:{token}", {"user": email, "client": client}, expires_in_sec=LINK_SECONDS
	)
	url = frappe.utils.get_url(f"/spa#/verify/{token}")
	try:
		frappe.sendmail(
			recipients=[email],
			subject="Confirm your Biz Spa account",
			message=f'<a href="{url}">Confirm your account</a> to see your bookings and book online.',
		)
	except Exception:
		# With no email set up the customer still gets an account, and reception can link it.
		frappe.log_error(frappe.get_traceback(), "Biz Spa: account link email failed")
		frappe.clear_messages()


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=10, seconds=3600)
def verify_link(token):
	key = f"spa_link:{token}"
	claim = frappe.cache.get_value(key)
	if not claim:
		frappe.throw("This link has expired. Please call the spa.")
	if frappe.db.get_value("Spa Client Profile", claim["client"], "online_account"):
		frappe.throw("This client record is already linked to an account.")
	frappe.db.set_value("Spa Client Profile", claim["client"], "online_account", claim["user"])
	frappe.cache.delete_value(key)


@frappe.whitelist(methods=["POST"])
def book(branch, date, start_time, services, notes=None):
	client = my_client(active=True)
	rows = online_rows(services)
	active_branch(branch)
	date, start = clean_date(date), clean_start(start_time)
	booked = upcoming_bookings(client)
	if booked >= MAX_ACTIVE_BOOKINGS:
		frappe.throw(f"You already have {booked} upcoming bookings. Please call the spa to book more.")
	plan = plan_at(branch, date, rows, start)
	if not plan:
		frappe.throw("That time was just taken. Please pick another.")
	with claiming_slot():
		doc = frappe.get_doc(
			{
				"doctype": "Spa Appointment",
				"client": client,
				"branch": branch,
				"appointment_date": date,
				"start_time": clock(start),
				"source": "Website",
				"notes": (notes or "").strip()[:500],
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
		).insert(ignore_permissions=True)
	return doc.name


@frappe.whitelist()
def appointments():
	client = my_client()
	window = cint(settings().cancellation_window_hours)
	docs = frappe.get_all(
		"Spa Appointment",
		filters={"client": client},
		fields=[
			"name",
			"branch",
			"appointment_date",
			"start_time",
			"end_time",
			"status",
			"total_amount",
			"total_duration",
			"cancellation_fee",
		],
		order_by="appointment_date desc, start_time desc",
		limit=100,
	)
	if not docs:
		return []
	lines = frappe.get_all(
		"Spa Appointment Service",
		filters={"parent": ("in", [d.name for d in docs])},
		fields=["parent", "service", "staff"],
		order_by="idx",
	)
	staff = dict(
		frappe.get_all(
			"Spa Staff Profile",
			filters={"name": ("in", [line.staff for line in lines if line.staff] or [""])},
			fields=["name", "staff_name"],
			as_list=True,
		)
	)
	for doc in docs:
		left = hours_until(doc)
		doc.update(
			{
				"start_time": clock(to_minutes(doc.start_time)),
				"end_time": clock(to_minutes(doc.end_time)),
				"services": [
					{"service": line.service, "staff": staff.get(line.staff)}
					for line in lines
					if line.parent == doc.name
				],
				"upcoming": doc.status in ACTIVE and left > 0,
				"can_reschedule": doc.status in ACTIVE and left >= window,
				"late_fee": 0
				if left >= window
				else flt(doc.total_amount) * flt(settings().no_show_fee_percent) / 100,
			}
		)
	return docs


@frappe.whitelist()
def reschedule_slots(name, date):
	doc = my_appointment(name)
	return public_slots(
		doc.branch, clean_date(date), [{"service": r.service} for r in doc.services], exclude=doc.name
	)


@frappe.whitelist(methods=["POST"])
def reschedule(name, date, start_time):
	date, start = clean_date(date), clean_start(start_time)
	doc = my_appointment(name)
	window = cint(settings().cancellation_window_hours)
	if doc.status not in ACTIVE or hours_until(doc) < window:
		frappe.throw(
			f"This booking can't be moved online within {window} hours of the start. Please call the spa."
		)
	plan = plan_at(doc.branch, date, [{"service": r.service} for r in doc.services], start, exclude=doc.name)
	if not plan:
		frappe.throw("That time was just taken. Please pick another.")
	doc.appointment_date, doc.start_time, doc.reminder_sent = date, clock(start), 0
	for row, line in zip(doc.services, plan, strict=True):
		row.staff, row.room, row.start_time, row.fixed_start = (
			line["staff"],
			line["room"],
			clock(line["start"]),
			0,
		)
	with claiming_slot():
		doc.save(ignore_permissions=True)
	return doc.name


@frappe.whitelist(methods=["POST"])
def cancel(name, reason=None):
	doc = my_appointment(name)
	if hours_until(doc) <= 0:
		frappe.throw("This booking has already started. Please call the spa.")
	doc.flags.ignore_permissions = True
	return cancel_doc(doc, (reason or "Cancelled online").strip()[:500])


@frappe.whitelist()
def visits():
	client = my_client()
	docs = frappe.get_all(
		"Spa Visit",
		filters={"client": client, "docstatus": 1},
		fields=["name", "branch", "posting_date", "grand_total", "paid_amount", "outstanding_amount"],
		order_by="posting_date desc",
		limit=100,
	)
	names = [d.name for d in docs] or [""]
	lines = frappe.get_all(
		"Spa Visit Service", filters={"parent": ("in", names)}, fields=["parent", "service"], order_by="idx"
	)
	rated = set(frappe.get_all("Spa Feedback", filters={"visit": ("in", names)}, pluck="visit"))
	for doc in docs:
		doc.services = [line.service for line in lines if line.parent == doc.name]
		doc.rated = doc.name in rated
	return docs


@frappe.whitelist(methods=["POST"])
def feedback(
	visit, service_rating, staff_rating=None, ambience_rating=None, would_recommend=0, comments=None
):
	client = my_client()
	row = frappe.db.get_value("Spa Visit", visit, ["client", "branch", "docstatus"], as_dict=True)
	if not row or row.client != client or row.docstatus != 1:
		frappe.throw("Visit not found.", frappe.DoesNotExistError)
	if frappe.db.exists("Spa Feedback", {"visit": visit}):
		frappe.throw("You have already rated this visit.")
	frappe.get_doc(
		{
			"doctype": "Spa Feedback",
			"visit": visit,
			"client": client,
			"branch": row.branch,
			"service_rating": str(service_rating),
			"staff_rating": str(staff_rating or ""),
			"ambience_rating": str(ambience_rating or ""),
			"would_recommend": cint(would_recommend),
			"comments": (comments or "").strip()[:1000],
		}
	).insert(ignore_permissions=True)


@frappe.whitelist()
def balances():
	return client_balances(my_client())


@frappe.whitelist()
def profile():
	return frappe.db.get_value(
		"Spa Client Profile", my_client(), ["client_name", "mobile", "email", *PROFILE_FIELDS], as_dict=True
	)


@frappe.whitelist(methods=["POST"])
def update_profile(values):
	doc = frappe.get_doc("Spa Client Profile", my_client())
	try:
		values = frappe.parse_json(values)
	except ValueError:
		values = None
	if not isinstance(values, dict):
		frappe.throw("Profile details are not in the expected format.")
	doc.update({field: values.get(field) for field in PROFILE_FIELDS if field in values})
	doc.save(ignore_permissions=True)


@frappe.whitelist()
def waitlist():
	return frappe.get_all(
		"Spa Waitlist Entry",
		filters={
			"client": my_client(),
			"status": ("in", ("Waiting", "Offered")),
			"date_to": (">=", nowdate()),
		},
		fields=["name", "branch", "service", "date_from", "date_to", "status"],
		order_by="date_from",
	)


@frappe.whitelist(methods=["POST"])
def join_waitlist(branch, service, date):
	client = my_client(active=True)
	online_rows([service])
	active_branch(branch)
	date = getdate(clean_date(date))
	if date < getdate(nowdate()):
		frappe.throw("Choose a date from today onwards.")
	if (
		frappe.db.count("Spa Waitlist Entry", {"client": client, "status": ("in", ("Waiting", "Offered"))})
		>= MAX_ACTIVE_BOOKINGS
	):
		frappe.throw("You are already on the waitlist for several dates. Please call the spa.")
	filters = {
		"client": client,
		"branch": branch,
		"service": service,
		"date_from": date,
		"date_to": date,
		"status": ("in", ("Waiting", "Offered")),
	}
	if frappe.db.exists("Spa Waitlist Entry", filters):
		return {"created": False}
	frappe.get_doc(
		{
			"doctype": "Spa Waitlist Entry",
			"client": client,
			"branch": branch,
			"service": service,
			"date_from": date,
			"date_to": date,
			"time_window": "Any",
		}
	).insert(ignore_permissions=True)
	return {"created": True}
