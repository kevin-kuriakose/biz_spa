import re
from unittest.mock import patch

import frappe
from frappe.utils import add_days

from biz_spa import tasks
from biz_spa.api import customer, portal
from biz_spa.booking_rules import to_minutes
from biz_spa.tests.utils import SpaTestCase, appointment, make_client, make_staff, token


def make_user(*roles):
	return (
		frappe.get_doc(
			{
				"doctype": "User",
				"email": f"{token()}@example.com",
				"first_name": "Test",
				"send_welcome_email": 0,
				"roles": [{"role": role} for role in roles],
			}
		)
		.insert(ignore_permissions=True)
		.name
	)


class TestTherapistScope(SpaTestCase):
	def setUp(self):
		super().setUp()
		self.user = make_user("Spa Therapist")
		self.staff.db_set("user", self.user)
		self.other_staff = make_staff(self.branch, [self.service])
		self.other_client = make_client()
		self.mine = appointment(self.branch, self.client, [(self.service, self.staff)]).insert()
		self.theirs = appointment(self.branch, self.other_client, [(self.service, self.other_staff)]).insert()

	def test_appointment_list_is_their_own(self):
		frappe.set_user(self.user)
		names = frappe.get_list("Spa Appointment", pluck="name")
		self.assertIn(self.mine.name, names)
		self.assertNotIn(self.theirs.name, names)

	def test_without_a_profile_nothing_is_visible(self):
		frappe.set_user(make_user("Spa Therapist"))
		self.assertEqual(frappe.get_list("Spa Appointment", pluck="name"), [])

	def test_titles_only_resolves_their_own_clients(self):
		frappe.set_user(self.user)
		result = portal.titles(
			frappe.as_json({"Spa Client Profile": [self.client.name, self.other_client.name]})
		)
		self.assertEqual(list(result["Spa Client Profile"]), [self.client.name])

	def test_titles_skips_bad_doctypes_without_failing_the_batch(self):
		result = portal.titles(
			frappe.as_json(
				{"No Such DocType": ["x"], "User": ["Administrator"], "Spa Client Profile": self.client.name}
			)
		)
		self.assertEqual(list(result), ["Spa Client Profile"])


class TestCustomerApi(SpaTestCase):
	def setUp(self):
		super().setUp()
		self.user = make_user("Spa Customer")
		self.client.db_set("online_account", self.user)

	def test_update_profile_needs_an_object(self):
		frappe.set_user(self.user)
		for value in ("5", "[1]", "not json"):
			self.assertRaises(frappe.ValidationError, customer.update_profile, value)

	def test_update_profile_only_touches_allowed_fields(self):
		frappe.set_user(self.user)
		customer.update_profile('{"allergies": "Nuts", "status": "Blocked"}')
		row = frappe.db.get_value(
			"Spa Client Profile", self.client.name, ["allergies", "status"], as_dict=True
		)
		self.assertEqual(row.allergies, "Nuts")
		self.assertNotEqual(row.status, "Blocked")

	def test_join_waitlist_says_whether_it_added_a_row(self):
		frappe.set_user(self.user)
		self.assertEqual(
			customer.join_waitlist(self.branch.name, self.service.name, self.tomorrow), {"created": True}
		)
		self.assertEqual(
			customer.join_waitlist(self.branch.name, self.service.name, self.tomorrow), {"created": False}
		)

	def test_guest_input_is_validated(self):
		names = f'["{self.service.name}"]'
		self.assertRaises(frappe.ValidationError, customer.slots, self.branch.name, "garbage", names)
		frappe.set_user(self.user)
		with patch.object(frappe.db, "commit"):
			self.assertRaises(
				frappe.ValidationError, customer.book, self.branch.name, self.tomorrow, "99:99", names
			)

	def test_a_lost_slot_gets_the_friendly_message(self):
		frappe.set_user(self.user)
		names = f'["{self.service.name}"]'
		frappe.set_user("Administrator")
		appointment(self.branch, make_client(), [(self.service, self.staff)]).insert()
		frappe.set_user(self.user)
		with (
			patch.object(frappe.db, "commit"),
			patch(
				"biz_spa.api.customer.plan_at",
				return_value=[
					{
						"service": self.service.name,
						"staff": self.staff.name,
						"room": None,
						"start": 600,
						"end": 660,
					},
				],
			),
		):
			self.assertRaisesRegex(
				frappe.ValidationError,
				"just taken",
				customer.book,
				self.branch.name,
				self.tomorrow,
				"10:00:00",
				names,
			)

	def test_books_moves_and_stops_at_the_limit(self):
		frappe.set_user(self.user)
		names = f'["{self.service.name}"]'
		with patch.object(frappe.db, "commit"):
			first = customer.book(self.branch.name, self.tomorrow, "10:00:00", names)
			customer.book(self.branch.name, self.tomorrow, "12:00:00", names)
			customer.book(self.branch.name, self.tomorrow, "14:00:00", names)
			self.assertRaisesRegex(
				frappe.ValidationError,
				"upcoming bookings",
				customer.book,
				self.branch.name,
				self.tomorrow,
				"16:00:00",
				names,
			)
		later = add_days(self.tomorrow, 2)
		customer.reschedule(first, later, "11:00:00")
		doc = frappe.get_doc("Spa Appointment", first)
		self.assertEqual(
			(str(doc.appointment_date), to_minutes(doc.start_time), to_minutes(doc.services[0].start_time)),
			(later, 660, 660),
		)

	def test_every_account_page_works_with_no_history(self):
		frappe.set_user(self.user)
		self.assertEqual(customer.appointments(), [])
		self.assertEqual(customer.visits(), [])
		self.assertEqual(customer.waitlist(), [])
		customer.balances()
		customer.profile()


class TestTasks(SpaTestCase):
	def test_no_show_reminder_and_expiry_jobs(self):
		overdue = appointment(
			self.branch, self.client, [(self.service, self.staff)], source="Walk-in"
		).insert()
		frappe.db.set_value("Spa Appointment", overdue.name, "appointment_date", add_days(self.tomorrow, -3))
		soon = appointment(self.branch, self.client, [(self.service, self.staff)], start="15:00:00").insert()
		frappe.db.set_value(
			"Spa Appointment",
			soon.name,
			{"appointment_date": frappe.utils.nowdate(), "start_time": "23:59:00"},
		)
		with (
			patch.object(frappe.db, "commit"),
			patch.object(tasks, "each", lambda rows, label, fn: [fn(r) for r in rows]),
			patch("frappe.sendmail"),
		):
			tasks.hourly_appointments()
			tasks.daily_housekeeping()
			tasks.daily_greetings()
		self.assertEqual(frappe.db.get_value("Spa Appointment", overdue.name, "status"), "No Show")
		self.assertEqual(frappe.db.get_value("Spa Appointment", soon.name, "reminder_sent"), 1)


class TestSignup(SpaTestCase):
	def signup(self, password, mobile=None):
		frappe.set_user("Guest")
		email = f"{token()}@example.com"
		frappe.local.login_manager = patch("frappe.auth.LoginManager").start()
		try:
			result = customer.signup(
				"Test Person",
				email,
				mobile or f"98{frappe.utils.random_string(0)}{abs(hash(email)) % 10**8:08d}",
				password,
			)
		finally:
			patch.stopall()
			frappe.set_user("Administrator")
		return email, result

	def test_weak_password_is_refused_by_site_policy(self):
		if not frappe.db.get_single_value("System Settings", "enable_password_policy"):
			self.skipTest("Password policy is off on this site")
		# User skips the strength check while in_test is set.
		frappe.flags.in_test = False
		try:
			with self.assertRaises(frappe.ValidationError):
				self.signup("password")
		finally:
			frappe.flags.in_test = True

	def test_strong_password_makes_a_linked_client(self):
		email, _ = self.signup("Tr0ub4dor&3-horse-staple")
		self.assertTrue(frappe.db.exists("Spa Client Profile", {"online_account": email}))

	def test_on_file_email_can_link_through_the_mailed_link(self):
		email = f"{token()}@example.com"
		on_file = make_client(email=email)
		with patch("frappe.sendmail") as sendmail, patch.object(frappe.local, "login_manager", create=True):
			frappe.set_user("Guest")
			customer.signup("Test Person", email, on_file.mobile, "Tr0ub4dor&3-horse-staple")
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value("Spa Client Profile", on_file.name, "online_account"), None)
		self.assertEqual(sendmail.call_args.kwargs["recipients"], [email])
		link = re.search(r"verify/(\w+)", sendmail.call_args.kwargs["message"])[1]
		customer.verify_link(link)
		self.assertEqual(frappe.db.get_value("Spa Client Profile", on_file.name, "online_account"), email)
		self.assertRaisesRegex(frappe.ValidationError, "expired", customer.verify_link, link)

	def test_mobile_match_alone_mails_nobody(self):
		with patch("frappe.sendmail") as sendmail:
			self.signup("Tr0ub4dor&3-horse-staple", make_client(email=f"{token()}@example.com").mobile)
		sendmail.assert_not_called()

	def test_response_does_not_say_whether_the_contact_is_on_file(self):
		_, known = self.signup("Tr0ub4dor&3-horse-staple", self.client.mobile)
		_, unknown = self.signup("Tr0ub4dor&3-horse-staple")
		self.assertEqual(known, unknown)
