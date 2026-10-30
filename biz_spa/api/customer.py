"""Customer-facing API behind /spa. The Spa Customer role has no DocPerms, so every read here is
scoped to the signed-in customer's own client profile, and only these methods reach the data."""
import re

import frappe
from frappe.rate_limiter import rate_limit
from frappe.utils import add_days, cint, flt, get_datetime, getdate, now_datetime, nowdate, validate_email_address

from biz_spa.api.booking import as_list, assign, booking_lock, cancel_doc, client_balances, open_slots
from biz_spa.booking_rules import ACTIVE, clock, minutes

ROLE = "Spa Customer"
MAX_ACTIVE_BOOKINGS = 3
MAX_SERVICES = 5
PROFILE_FIELDS = ["date_of_birth", "gender", "allergies", "preferences", "preferred_branch", "marketing_consent"]


def settings():
	return frappe.get_cached_doc("Spa Settings")


def my_client(active=False):
	if frappe.session.user == "Guest":
		frappe.throw("Please sign in first.", frappe.AuthenticationError)
	client = frappe.db.get_value("Spa Client Profile", {"online_account": frappe.session.user}, ["name", "status"], as_dict=True)
	if not client:
		frappe.throw("Your account isn't linked to a client record yet. Please ask reception.", frappe.PermissionError)
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


def active_branch(branch):
	if not branch or not frappe.db.get_value("Spa Branch", branch, "is_active"):
		frappe.throw("Choose a branch.")
	return branch


def online_rows(services):
	names = [str(name) for name in as_list(services)]
	allowed = {service.name for service in online_services()}
	if not names or len(names) > MAX_SERVICES or not set(names) <= allowed:
		frappe.throw(f"Choose between 1 and {MAX_SERVICES} services that can be booked online.")
	return [{"service": name} for name in names]


def hours_until(doc):
	return (get_datetime(f"{doc.appointment_date} {clock(minutes(doc.start_time))}") - now_datetime()).total_seconds() / 3600


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
	client = frappe.db.get_value("Spa Client Profile", {"online_account": user}, ["name", "client_name", "status"], as_dict=True)
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
		"branches": frappe.get_all("Spa Branch", filters={"is_active": 1}, fields=["name", "phone", "address"], order_by="name"),
		"services": online_services(),
		"default_branch": config.default_branch,
		"today": nowdate(),
		"last_date": add_days(nowdate(), cint(config.booking_window_days or 60)),
		"cancellation_window_hours": cint(config.cancellation_window_hours),
		"late_fee_percent": flt(config.no_show_fee_percent),
		"currency": frappe.db.get_default("currency") or "INR",
	}


def public_slots(branch, date, rows, exclude=None):
	return [{"start_time": s["start_time"], "end_time": s["end_time"]} for s in open_slots(branch, date, rows, exclude=exclude)]


@frappe.whitelist(allow_guest=True)
@rate_limit(limit=120, seconds=60)
def slots(branch, date, services):
	return public_slots(active_branch(branch), date, online_rows(services))


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
		frappe.throw("That email already has an account. Please sign in.")

	user = frappe.get_doc({
		"doctype": "User",
		"email": email,
		"first_name": full_name,
		"enabled": 1,
		"send_welcome_email": 0,
		"new_password": password,
		"roles": [{"role": ROLE}],
	})
	user.flags.ignore_permissions = True
	user.flags.ignore_password_policy = True
	user.insert()

	# Email and mobile are unverified, so an account never attaches itself to an existing client's
	# history. Reception checks who they are and links the two with Online Account.
	on_file = frappe.db.exists("Spa Client Profile", {"mobile": mobile}) or frappe.db.exists("Spa Client Profile", {"email": email})
	if not on_file:
		frappe.get_doc({
			"doctype": "Spa Client Profile",
			"client_name": full_name,
			"mobile": mobile,
			"email": email,
			"online_account": email,
			"referral_source": "Website",
		}).insert(ignore_permissions=True)
	frappe.local.login_manager.login_as(email)
	return {"linked": not on_file}


@frappe.whitelist(methods=["POST"])
def book(branch, date, start_time, services, notes=None):
	client = my_client(active=True)
	rows = online_rows(services)
	active_branch(branch)
	start_time = clock(minutes(start_time))
	with booking_lock():
		booked = frappe.db.count("Spa Appointment", {"client": client, "status": ("in", ACTIVE), "appointment_date": (">=", nowdate())})
		if booked >= MAX_ACTIVE_BOOKINGS:
			frappe.throw(f"You already have {booked} upcoming bookings. Please call the spa to book more.")
		match = next((s for s in open_slots(branch, date, rows) if s["start_time"] == start_time), None)
		if not match:
			frappe.throw("That time was just taken. Please pick another.")
		doc = frappe.get_doc({
			"doctype": "Spa Appointment",
			"client": client,
			"branch": branch,
			"appointment_date": date,
			"start_time": start_time,
			"source": "Website",
			"notes": (notes or "").strip()[:500],
			"services": [{"service": p["service"], "staff": p["staff"], "room": p["room"], "start_time": p["start"]} for p in match["services"]],
		}).insert(ignore_permissions=True)
	return doc.name


@frappe.whitelist()
def appointments():
	client = my_client()
	window = cint(settings().cancellation_window_hours)
	docs = frappe.get_all(
		"Spa Appointment",
		filters={"client": client},
		fields=["name", "branch", "appointment_date", "start_time", "end_time", "status", "total_amount", "total_duration", "cancellation_fee"],
		order_by="appointment_date desc, start_time desc",
		limit=100,
	)
	lines = frappe.get_all(
		"Spa Appointment Service",
		filters={"parent": ("in", [d.name for d in docs or [""]])},
		fields=["parent", "service", "staff"],
		order_by="idx",
	)
	staff = dict(frappe.get_all("Spa Staff Profile", filters={"name": ("in", {l.staff for l in lines if l.staff})}, fields=["name", "staff_name"], as_list=True))
	for doc in docs:
		left = hours_until(doc)
		doc.update({
			"start_time": clock(minutes(doc.start_time)),
			"end_time": clock(minutes(doc.end_time)),
			"services": [{"service": l.service, "staff": staff.get(l.staff)} for l in lines if l.parent == doc.name],
			"upcoming": doc.status in ACTIVE and left > 0,
			"can_reschedule": doc.status in ACTIVE and left >= window,
			"late_fee": 0 if left >= window else flt(doc.total_amount) * flt(settings().no_show_fee_percent) / 100,
		})
	return docs


@frappe.whitelist()
def reschedule_slots(name, date):
	doc = my_appointment(name)
	return public_slots(doc.branch, date, [{"service": r.service} for r in doc.services], exclude=doc.name)


@frappe.whitelist(methods=["POST"])
def reschedule(name, date, start_time):
	start_time = clock(minutes(start_time))
	with booking_lock():
		doc = my_appointment(name)
		window = cint(settings().cancellation_window_hours)
		if doc.status not in ACTIVE or hours_until(doc) < window:
			frappe.throw(f"This booking can't be moved online within {window} hours of the start. Please call the spa.")
		rows = [{"service": r.service} for r in doc.services]
		match = next((s for s in open_slots(doc.branch, date, rows, exclude=doc.name) if s["start_time"] == start_time), None)
		if not match:
			frappe.throw("That time was just taken. Please pick another.")
		doc.appointment_date, doc.start_time, doc.reminder_sent = date, start_time, 0
		for row, plan in zip(doc.services, match["services"]):
			row.staff, row.room, row.start_time, row.fixed_start = plan["staff"], plan["room"], plan["start"], 0
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
	lines = frappe.get_all("Spa Visit Service", filters={"parent": ("in", names)}, fields=["parent", "service"], order_by="idx")
	rated = set(frappe.get_all("Spa Feedback", filters={"visit": ("in", names)}, pluck="visit"))
	for doc in docs:
		doc.services = [l.service for l in lines if l.parent == doc.name]
		doc.rated = doc.name in rated
	return docs


@frappe.whitelist(methods=["POST"])
def feedback(visit, service_rating, staff_rating=None, ambience_rating=None, would_recommend=0, comments=None):
	client = my_client()
	row = frappe.db.get_value("Spa Visit", visit, ["client", "branch", "docstatus"], as_dict=True)
	if not row or row.client != client or row.docstatus != 1:
		frappe.throw("Visit not found.", frappe.DoesNotExistError)
	if frappe.db.exists("Spa Feedback", {"visit": visit}):
		frappe.throw("You have already rated this visit.")
	frappe.get_doc({
		"doctype": "Spa Feedback",
		"visit": visit,
		"client": client,
		"branch": row.branch,
		"service_rating": str(service_rating),
		"staff_rating": str(staff_rating or ""),
		"ambience_rating": str(ambience_rating or ""),
		"would_recommend": cint(would_recommend),
		"comments": (comments or "").strip()[:1000],
	}).insert(ignore_permissions=True)


@frappe.whitelist()
def balances():
	return client_balances(my_client())


@frappe.whitelist()
def profile():
	return frappe.db.get_value("Spa Client Profile", my_client(), ["client_name", "mobile", "email", *PROFILE_FIELDS], as_dict=True)


@frappe.whitelist(methods=["POST"])
def update_profile(values):
	doc = frappe.get_doc("Spa Client Profile", my_client())
	values = frappe.parse_json(values)
	doc.update({field: values.get(field) for field in PROFILE_FIELDS if field in values})
	doc.save(ignore_permissions=True)


@frappe.whitelist()
def waitlist():
	return frappe.get_all(
		"Spa Waitlist Entry",
		filters={"client": my_client(), "status": ("in", ("Waiting", "Offered")), "date_to": (">=", nowdate())},
		fields=["name", "branch", "service", "date_from", "date_to", "status"],
		order_by="date_from",
	)


@frappe.whitelist(methods=["POST"])
def join_waitlist(branch, service, date):
	client = my_client(active=True)
	online_rows([service])
	active_branch(branch)
	date = getdate(date)
	if date < getdate(nowdate()):
		frappe.throw("Choose a date from today onwards.")
	if frappe.db.count("Spa Waitlist Entry", {"client": client, "status": ("in", ("Waiting", "Offered"))}) >= MAX_ACTIVE_BOOKINGS:
		frappe.throw("You are already on the waitlist for several dates. Please call the spa.")
	filters = {"client": client, "branch": branch, "service": service, "date_from": date, "date_to": date, "status": ("in", ("Waiting", "Offered"))}
	if frappe.db.exists("Spa Waitlist Entry", filters):
		return
	frappe.get_doc({
		"doctype": "Spa Waitlist Entry", "client": client, "branch": branch, "service": service,
		"date_from": date, "date_to": date, "time_window": "Any",
	}).insert(ignore_permissions=True)
