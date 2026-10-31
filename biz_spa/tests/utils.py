import random

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, nowdate

WEEK = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def token():
	return frappe.generate_hash(length=8)


def mobile():
	return "9" + str(random.randint(10**8, 10**9 - 1)) + "0"


def make_branch():
	base = frappe.get_cached_doc("Spa Branch", frappe.get_all("Spa Branch", pluck="name", limit=1)[0])
	return frappe.get_doc(
		{
			"doctype": "Spa Branch",
			"branch_name": f"Test Branch {token()}",
			"company": base.company,
			"cost_center": base.cost_center,
			"warehouse": base.warehouse,
			"is_active": 1,
			"hours": [{"weekday": day, "open_time": "09:00:00", "close_time": "21:00:00"} for day in WEEK],
		}
	).insert(ignore_permissions=True)


def make_service(price=1000, duration=60, buffer=15, **values):
	category = frappe.get_all("Spa Service Category", pluck="name", limit=1)[0]
	return frappe.get_doc(
		{
			"doctype": "Spa Service",
			"service_name": f"Test Service {token()}",
			"category": category,
			"price": price,
			"duration_minutes": duration,
			"buffer_minutes": buffer,
			"is_active": 1,
			"online_bookable": 1,
			**values,
		}
	).insert(ignore_permissions=True)


def make_staff(branch, services, **values):
	return frappe.get_doc(
		{
			"doctype": "Spa Staff Profile",
			"staff_name": f"Test Staff {token()}",
			"designation": "Therapist",
			"branch": branch.name,
			"commission_type": "Percentage",
			"commission_rate": 10,
			"is_bookable": 1,
			"skills": [{"service": s.name} for s in services],
			"shifts": [{"weekday": day, "from_time": "09:00:00", "to_time": "21:00:00"} for day in WEEK],
			**values,
		}
	).insert(ignore_permissions=True)


def make_client(**values):
	return frappe.get_doc(
		{
			"doctype": "Spa Client Profile",
			"client_name": f"Test Client {token()}",
			"mobile": mobile(),
			**values,
		}
	).insert(ignore_permissions=True)


def appointment(branch, client, lines, date=None, start="10:00:00", **values):
	"""Lines are (service, staff) pairs; values go straight on the document."""
	return frappe.get_doc(
		{
			"doctype": "Spa Appointment",
			"client": client.name,
			"branch": branch.name,
			"source": "Phone",
			"appointment_date": date or add_days(nowdate(), 1),
			"start_time": start,
			"services": [
				{"service": service.name, "staff": staff.name if staff else None} for service, staff in lines
			],
			**values,
		}
	)


class SpaTestCase(FrappeTestCase):
	"""Each test builds its own branch, service, staff and client, and rolls them back afterwards."""

	def setUp(self):
		frappe.set_user("Administrator")
		self.branch = make_branch()
		self.service = make_service()
		self.staff = make_staff(self.branch, [self.service])
		self.client = make_client()
		self.tomorrow = add_days(nowdate(), 1)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		frappe.clear_messages()
