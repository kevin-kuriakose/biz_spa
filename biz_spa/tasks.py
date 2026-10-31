import frappe
from frappe.utils import add_months, add_to_date, cint, get_datetime, getdate, now_datetime, nowdate, today

from biz_spa.booking_rules import clock, minutes


def each(rows, label, fn):
	"""One bad row is logged and never stops the run (18.8)."""
	for row in rows:
		try:
			fn(row)
			frappe.db.commit()
		except Exception:
			frappe.db.rollback()
			frappe.log_error(frappe.get_traceback(), f"Biz Spa: {label} failed")


def start_of(row):
	return get_datetime(f"{row.appointment_date} {clock(minutes(row.start_time))}")


def hourly_appointments():
	now = now_datetime()
	open_rows = frappe.get_all(
		"Spa Appointment",
		filters={"status": ("in", ["Scheduled", "Confirmed"]), "appointment_date": ("<=", nowdate())},
		fields=["name", "appointment_date", "end_time"],
	)

	def no_show(row):
		if get_datetime(f"{row.appointment_date} {clock(minutes(row.end_time))}") < now:
			frappe.db.set_value("Spa Appointment", row.name, "status", "No Show")

	each(open_rows, "No Show", no_show)

	lead = cint(frappe.db.get_single_value("Spa Settings", "reminder_hours_before"))
	if not lead:
		return
	upcoming = frappe.get_all(
		"Spa Appointment",
		filters={
			"status": ("in", ["Scheduled", "Confirmed"]),
			"reminder_sent": 0,
			"appointment_date": (
				"between",
				[nowdate(), add_to_date(now, hours=lead, as_datetime=True).date()],
			),
		},
		fields=["name", "appointment_date", "start_time", "client_email", "branch"],
	)

	def remind(row):
		if not now <= start_of(row) <= add_to_date(now, hours=lead, as_datetime=True):
			return
		if row.client_email:
			frappe.sendmail(
				recipients=[row.client_email],
				subject="Your appointment reminder",
				message=f"Your appointment at {row.branch} is on {row.appointment_date} at {clock(minutes(row.start_time))[:5]}.",
			)
		frappe.db.set_value("Spa Appointment", row.name, "reminder_sent", 1)

	each(upcoming, "Reminder", remind)


def daily_housekeeping():
	date = today()
	each(
		frappe.get_all(
			"Spa Client Package",
			filters={"docstatus": 1, "status": "Active", "expiry_date": ("<", date)},
			pluck="name",
		),
		"Package expiry",
		lambda n: frappe.db.set_value("Spa Client Package", n, "status", "Expired"),
	)
	each(
		frappe.get_all(
			"Spa Gift Card",
			filters={"docstatus": 1, "status": "Active", "expiry_date": ("<", date)},
			pluck="name",
		),
		"Gift card expiry",
		lambda n: frappe.db.set_value("Spa Gift Card", n, "status", "Expired"),
	)

	def end_membership(row):
		if row.auto_renew:
			renew(row.name)
		frappe.db.set_value("Spa Membership", row.name, "status", "Expired")
		if not frappe.db.exists(
			"Spa Membership",
			{"client": row.client, "docstatus": 1, "status": "Active", "name": ("!=", row.name)},
		):
			frappe.db.set_value("Spa Client Profile", row.client, "membership_status", "Expired")

	each(
		frappe.get_all(
			"Spa Membership",
			filters={"docstatus": 1, "status": "Active", "end_date": ("<", date)},
			fields=["name", "client", "auto_renew"],
		),
		"Membership expiry",
		end_membership,
	)
	each(
		frappe.get_all("Spa Membership", filters={"docstatus": 1, "status": "Active"}, pluck="name"),
		"Entitlement rollover",
		roll_entitlements,
	)


def renew(name):
	old = frappe.get_doc("Spa Membership", name)
	new = frappe.get_doc(
		{
			"doctype": "Spa Membership",
			"client": old.client,
			"plan": old.plan,
			"branch": old.branch,
			"start_date": old.end_date,
			"auto_renew": 1,
			"renewed_from": old.name,
			"mode_of_payment": old.mode_of_payment,
		}
	)
	new.flags.ignore_permissions = True
	new.insert(ignore_permissions=True)
	new.submit()


def roll_entitlements(name):
	"""Starts the new month's allowance once the last period has ended."""
	doc = frappe.get_doc("Spa Membership", name)
	date = getdate(today())
	latest = {}
	for row in doc.entitlements or []:
		if row.service not in latest or getdate(row.period_end) > getdate(latest[row.service].period_end):
			latest[row.service] = row
	for row in latest.values():
		if getdate(row.period_end) < date:
			new = doc.append(
				"entitlements",
				{
					"service": row.service,
					"period_start": row.period_end,
					"period_end": add_months(row.period_end, 1),
					"sessions_allowed": row.sessions_allowed,
					"sessions_used": 0,
				},
			)
			new.db_insert()


def daily_greetings():
	date = getdate(today())
	clients = frappe.db.sql(
		"""SELECT name, client_name, email, date_of_birth, anniversary_date FROM `tabSpa Client Profile`
		WHERE marketing_consent = 1 AND status = 'Active' AND IFNULL(email, '') != ''
		AND ((MONTH(date_of_birth) = %(m)s AND DAY(date_of_birth) = %(d)s)
		OR (MONTH(anniversary_date) = %(m)s AND DAY(anniversary_date) = %(d)s))""",
		{"m": date.month, "d": date.day},
		as_dict=True,
	)

	def greet(row):
		birthday = row.date_of_birth and (row.date_of_birth.month, row.date_of_birth.day) == (
			date.month,
			date.day,
		)
		occasion = "Happy birthday" if birthday else "Happy anniversary"
		frappe.sendmail(
			recipients=[row.email],
			subject=f"{occasion} from Biz Spa",
			message=f"{occasion}, {row.client_name}!",
		)

	each(clients, "Greeting", greet)
