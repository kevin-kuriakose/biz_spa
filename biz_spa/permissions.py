import frappe

FULL_VIEW = {"Spa Manager", "Spa Receptionist", "Spa Accountant", "System Manager"}


def own_staff(user=None):
	"""None when the user sees everything, otherwise their staff profile ("" if they have none)."""
	user = user or frappe.session.user
	if user == "Administrator" or set(frappe.get_roles(user)) & FULL_VIEW:
		return None
	return frappe.db.get_value("Spa Staff Profile", {"user": user}) or ""


def appointment_query(user=None):
	staff = own_staff(user)
	if staff is None:
		return ""
	return (
		"EXISTS (SELECT 1 FROM `tabSpa Appointment Service` l "
		f"WHERE l.parent = `tabSpa Appointment`.name AND l.staff = {frappe.db.escape(staff)})"
	)


def appointment_access(doc, ptype=None, user=None):
	staff = own_staff(user)
	if staff is None:
		return True
	return any(row.staff == staff for row in (doc.services or []))


def field_query(doctype, field):
	def query(user=None):
		staff = own_staff(user)
		if staff is None:
			return ""
		return f"`tab{doctype}`.`{field}` = {frappe.db.escape(staff)}"

	return query


def field_access(field):
	def access(doc, ptype=None, user=None):
		staff = own_staff(user)
		# A blank value is a new record the user is still filling in.
		return staff is None or doc.get(field) in (staff, None, "")

	return access


waitlist_query = field_query("Spa Waitlist Entry", "preferred_staff")
waitlist_access = field_access("preferred_staff")
consultation_query = field_query("Spa Consultation", "consultant")
consultation_access = field_access("consultant")
commission_query = field_query("Spa Commission Entry", "staff")
commission_access = field_access("staff")
feedback_query = field_query("Spa Feedback", "staff")
feedback_access = field_access("staff")
color_formula_query = field_query("Spa Color Formula", "staff")
color_formula_access = field_access("staff")
incident_query = field_query("Spa Incident Report", "staff")
incident_access = field_access("staff")


def therapist_only(user):
	return "Spa Therapist" in frappe.get_roles(user) and not set(frappe.get_roles(user)) & FULL_VIEW and user != "Administrator"


def user_query(user=None):
	"""Therapists cannot browse the staff directory; everyone else keeps standard behaviour."""
	user = user or frappe.session.user
	return f"`tabUser`.name = {frappe.db.escape(user)}" if therapist_only(user) else ""


def client_query(user=None):
	"""A therapist sees only clients they have an appointment with."""
	staff = own_staff(user)
	if staff is None:
		return ""
	return (
		"EXISTS (SELECT 1 FROM `tabSpa Appointment` a JOIN `tabSpa Appointment Service` l ON l.parent = a.name "
		f"WHERE a.client = `tabSpa Client Profile`.name AND l.staff = {frappe.db.escape(staff)})"
	)


def client_access(doc, ptype=None, user=None):
	staff = own_staff(user)
	if staff is None:
		return True
	return bool(frappe.db.sql(
		"""SELECT 1 FROM `tabSpa Appointment` a JOIN `tabSpa Appointment Service` l ON l.parent = a.name
		WHERE a.client = %s AND l.staff = %s LIMIT 1""",
		(doc.name, staff),
	))


SPA_ROLES = {"Spa Manager", "Spa Receptionist", "Spa Therapist", "Spa Accountant"}


def apply_staff_access(doc, method=None):
	"""Gives spa staff the Module Profile that hides every other app. System Managers keep theirs."""
	roles = {r.role for r in (doc.roles or [])}
	if doc.role_profile_name:
		roles |= set(frappe.get_all("Has Role", filters={"parent": doc.role_profile_name, "parenttype": "Role Profile"}, pluck="role"))
	if roles & SPA_ROLES and "System Manager" not in roles and doc.name != "Administrator":
		doc.module_profile = "Spa Staff"
