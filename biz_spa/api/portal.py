import frappe
from frappe.utils import flt, getdate, nowdate

from biz_spa.booking_rules import minutes
from biz_spa.permissions import own_staff

FINANCE = {"System Manager", "Spa Manager", "Spa Accountant"}

MENU = [
	(
		"Front Desk",
		[
			("Spa Appointment", "Appointments", "calendar-check"),
			("Spa Client Profile", "Clients", "contact"),
			("Spa Waitlist Entry", "Waitlist", "clock"),
			("Spa Consultation", "Consultations", "clipboard-list"),
			("Spa Staff Time Off", "Time Off", "calendar-days"),
		],
	),
	("Billing", [("Spa Visit", "Visits", "receipt-text"), ("Spa Cash Close", "Cash Close", "landmark")]),
	(
		"Prepaid",
		[
			("Spa Client Package", "Packages Sold", "package"),
			("Spa Membership", "Memberships", "crown"),
			("Spa Gift Card", "Gift Cards", "gift"),
		],
	),
	(
		"Staff",
		[
			("Spa Staff Profile", "Staff", "users"),
			("Spa Commission Entry", "Commission", "hand-coins"),
			("Spa Commission Payout", "Payouts", "wallet"),
		],
	),
	(
		"Catalog",
		[
			("Spa Service", "Services", "flower-2"),
			("Spa Service Category", "Categories", "scissors"),
			("Spa Package", "Packages", "package"),
			("Spa Membership Plan", "Membership Plans", "crown"),
			("Spa Promotion", "Promotions", "badge-percent"),
			("Spa Consent Template", "Consent Templates", "clipboard-list"),
		],
	),
	(
		"Quality",
		[
			("Spa Feedback", "Feedback", "star"),
			("Spa Color Formula", "Color Formulas", "palette"),
			("Spa Incident Report", "Incidents", "shield-alert"),
		],
	),
	(
		"Setup",
		[
			("Spa Branch", "Branches", "map-pin"),
			("Spa Room", "Rooms", "door-open"),
			("Spa Settings", "Settings", "settings"),
		],
	),
]
MY_LABELS = {
	"Spa Appointment": "My Appointments",
	"Spa Client Profile": "My Clients",
	"Spa Consultation": "My Consultations",
	"Spa Commission Entry": "My Commission",
	"Spa Staff Time Off": "My Time Off",
	"Spa Feedback": "My Feedback",
}

RANGE = ["branch", "from_date", "to_date"]
REPORTS = [
	("Daily Sales Summary", RANGE),
	("Staff Utilization", ["branch", "staff", "from_date", "to_date"]),
	("Staff Performance", ["branch", "staff", "from_date", "to_date"]),
	("Commission Statement", ["staff", "from_date", "to_date"]),
	("Service Revenue and Popularity", RANGE),
	("Lapsed Clients", ["days_since_last_visit", "branch"]),
	("No-Show and Cancellation Analysis", RANGE),
	("Package Balance and Liability", ["branch"]),
	("Gift Card Liability Register", ["branch"]),
	("Membership Renewals Due", ["branch", "days_ahead"]),
	("Consumable Usage", RANGE),
	("Room Utilization", RANGE),
	("Cash Close Variance", RANGE),
	("Client Birthdays and Anniversaries", ["month", "branch"]),
]


def roles():
	return set(frappe.get_roles())


def sees_money():
	return bool(roles() & FINANCE)


def allowed_reports():
	mine = roles()
	return [
		{"name": name, "filters": filters}
		for name, filters in REPORTS
		if mine
		& set(frappe.get_all("Has Role", filters={"parent": name, "parenttype": "Report"}, pluck="role"))
	]


@frappe.whitelist()
def bootstrap():
	staff = own_staff()
	sections = []
	for title, items in MENU:
		rows = []
		for doctype, label, icon in items:
			if staff is not None and doctype in ("Spa Waitlist Entry", "Spa Staff Profile"):
				continue
			if frappe.has_permission(doctype, "read"):
				rows.append(
					{
						"doctype": doctype,
						"label": MY_LABELS.get(doctype, label) if staff is not None else label,
						"icon": icon,
					}
				)
		if rows:
			sections.append(
				{"title": "My Work" if staff is not None and title == "Front Desk" else title, "items": rows}
			)
	return {
		"user": frappe.session.user,
		"full_name": frappe.db.get_value("User", frappe.session.user, "full_name"),
		"is_therapist": staff is not None,
		"can_book": bool(frappe.has_permission("Spa Appointment", "create")),
		"has_desk": "System Manager" in roles(),
		"menu": sections,
		"reports": allowed_reports(),
		"branches": frappe.get_all(
			"Spa Branch", filters={"is_active": 1}, pluck="name", ignore_permissions=True
		),
		"currency": frappe.db.get_default("currency") or "INR",
	}


@frappe.whitelist()
def meta(doctype):
	frappe.has_permission(doctype, "read", throw=True)
	m = frappe.get_meta(doctype)
	levels = m.get_permlevel_access("read")
	children = {}
	fields = []
	for df in m.fields:
		if df.permlevel not in levels or df.hidden:
			continue
		fields.append(serialize(df))
		if df.fieldtype == "Table":
			child = frappe.get_meta(df.options)
			children[df.options] = [
				serialize(c)
				for c in child.fields
				if not c.hidden and c.fieldtype not in ("Section Break", "Column Break")
			]
	return {
		"name": doctype,
		"fields": fields,
		"children": children,
		"is_submittable": m.is_submittable,
		"issingle": m.issingle,
		"title_field": m.title_field,
		"autoname": m.autoname,
		"perms": {
			p: bool(frappe.has_permission(doctype, p))
			for p in ("create", "write", "submit", "cancel", "delete")
		},
	}


def serialize(df):
	keys = (
		"fieldname",
		"label",
		"fieldtype",
		"options",
		"reqd",
		"read_only",
		"depends_on",
		"read_only_depends_on",
		"in_list_view",
		"default",
		"fetch_from",
	)
	return {k: df.get(k) for k in keys}


@frappe.whitelist()
def dashboard(branch=None):
	frappe.has_permission("Spa Appointment", "read", throw=True)
	today = nowdate()
	staff = own_staff()
	lines = schedule(today, branch)["lines"]
	cards = [
		{
			"label": "Today's Appointments",
			"value": len({l["appointment"] for l in lines}),
			"icon": "calendar-check",
		}
	]
	active = [l for l in lines if l["status"] in ("Scheduled", "Confirmed", "Checked In", "In Progress")]
	cards.append(
		{"label": "Still To Come", "value": len({l["appointment"] for l in active}), "icon": "clock"}
	)
	if staff is not None:
		unpaid = frappe.db.sql(
			"SELECT SUM(commission_amount) FROM `tabSpa Commission Entry` WHERE staff = %s AND status = 'Unpaid'",
			staff or "",
		)[0][0]
		cards.append({"label": "Unpaid Commission", "value": flt(unpaid), "icon": "hand-coins", "money": 1})
		rating = frappe.db.sql(
			"SELECT AVG(CAST(staff_rating AS UNSIGNED)) FROM `tabSpa Feedback` WHERE staff = %s AND IFNULL(staff_rating, '') != ''",
			staff or "",
		)[0][0]
		cards.append({"label": "Average Rating", "value": flt(rating, 1), "icon": "star"})
	elif sees_money():
		cond = "AND branch = %(branch)s" if branch else ""
		start = getdate(today).replace(day=1)
		row = frappe.db.sql(
			f"""SELECT SUM(IF(posting_date = %(today)s, grand_total, 0)) day_total, SUM(grand_total) month_total FROM `tabSpa Visit`
			WHERE docstatus = 1 AND posting_date BETWEEN %(start)s AND %(today)s {cond}""",
			{"today": today, "start": start, "branch": branch},
			as_dict=True,
		)[0]
		cards.append(
			{"label": "Sales Today", "value": flt(row.day_total), "icon": "receipt-text", "money": 1}
		)
		cards.append(
			{"label": "Sales This Month", "value": flt(row.month_total), "icon": "chart-column", "money": 1}
		)
	else:
		cards.append(
			{
				"label": "Waitlist",
				"value": frappe.db.count("Spa Waitlist Entry", {"status": "Waiting"}),
				"icon": "clock",
			}
		)
		cards.append({"label": "Clients", "value": frappe.db.count("Spa Client Profile"), "icon": "contact"})
	return {"cards": cards, "lines": lines[:12]}


@frappe.whitelist()
def schedule(date, branch=None):
	frappe.has_permission("Spa Appointment", "read", throw=True)
	staff = own_staff()
	values = {"date": getdate(date), "branch": branch, "staff": staff}
	cond = ("AND a.branch = %(branch)s " if branch else "") + (
		"AND l.staff = %(staff)s" if staff is not None else ""
	)
	rows = frappe.db.sql(
		f"""SELECT a.name appointment, a.status, a.branch, c.client_name, l.service, l.staff, s.staff_name, l.start_time, l.end_time
		FROM `tabSpa Appointment Service` l JOIN `tabSpa Appointment` a ON a.name = l.parent
		JOIN `tabSpa Client Profile` c ON c.name = a.client LEFT JOIN `tabSpa Staff Profile` s ON s.name = l.staff
		WHERE a.appointment_date = %(date)s {cond} ORDER BY l.start_time""",
		values,
		as_dict=True,
	)
	for row in rows:
		row.start = minutes(row.pop("start_time"))
		row.end = minutes(row.pop("end_time"))
	return {"date": str(getdate(date)), "lines": rows}


@frappe.whitelist()
def services_for_booking():
	frappe.has_permission("Spa Appointment", "create", throw=True)
	return frappe.get_all(
		"Spa Service",
		filters={"is_active": 1},
		fields=["name", "category", "duration_minutes", "price"],
		order_by="category, name",
		ignore_permissions=True,
	)


@frappe.whitelist()
def titles(pairs):
	"""Display names for Link values, as {doctype: {name: title}}. Only titled spa records resolve."""
	result = {}
	for doctype, names in frappe.parse_json(pairs).items():
		title_field = frappe.get_meta(doctype).title_field
		if not doctype.startswith("Spa ") or not title_field or not frappe.has_permission(doctype, "select"):
			continue
		result[doctype] = dict(
			frappe.get_all(
				doctype,
				filters={"name": ("in", names)},
				fields=["name", title_field],
				as_list=True,
				ignore_permissions=True,
			)
		)
	return result
