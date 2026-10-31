from unittest.mock import patch

import frappe
from frappe.utils import add_days, get_datetime, nowdate

from biz_spa.api import booking
from biz_spa.booking_rules import (
	Day,
	SlotTaken,
	branch_hours,
	clean_date,
	clean_start,
	closed_reason,
	to_minutes,
)
from biz_spa.tests.utils import SpaTestCase, appointment, make_client, make_service, make_staff


class TestOverlap(SpaTestCase):
	def setUp(self):
		super().setUp()
		self.existing = appointment(self.branch, self.client, [(self.service, self.staff)]).insert()

	def clash(self, start, staff=None):
		other = make_client()
		return appointment(self.branch, other, [(self.service, staff or self.staff)], start=start)

	def test_buffer_blocks_the_next_quarter_hour(self):
		with self.assertRaises(SlotTaken):
			self.clash("11:00:00").insert()
		self.clash("11:15:00").insert()

	def test_another_staff_member_is_free(self):
		self.clash("10:00:00", make_staff(self.branch, [self.service])).insert()

	def test_cancelled_and_no_show_free_the_slot(self):
		for status in ("Cancelled", "No Show"):
			frappe.db.set_value("Spa Appointment", self.existing.name, "status", status)
			self.assertFalse(Day(self.branch.name, self.tomorrow).busy("staff", self.staff.name, 600, 660))

	def test_status_cannot_dodge_the_check(self):
		for status in ("Checked In", "In Progress", "Completed", "Cancelled", "No Show"):
			self.assertRaisesRegex(
				frappe.ValidationError,
				"cannot start as",
				self.clash("15:00:00").update({"status": status}).insert,
			)

	def test_status_only_moves_along_the_table(self):
		for start, end in (
			("Completed", "Scheduled"),
			("Checked In", "Scheduled"),
			("Scheduled", "Completed"),
		):
			frappe.db.set_value("Spa Appointment", self.existing.name, "status", start)
			doc = frappe.get_doc("Spa Appointment", self.existing.name)
			doc.status = end
			self.assertRaisesRegex(frappe.ValidationError, "cannot move to", doc.save)

	def test_cancelling_needs_a_reason_and_records_the_fee(self):
		doc = frappe.get_doc("Spa Appointment", self.existing.name)
		doc.status = "Cancelled"
		self.assertRaisesRegex(frappe.ValidationError, "reason", doc.save)
		hour_before = get_datetime(f"{self.tomorrow} 09:00:00")
		with patch("biz_spa.api.booking.now_datetime", return_value=hour_before):
			result = booking.cancel_appointment(self.existing.name, "Unwell")
		self.assertEqual(result["cancellation_fee"], 500)

	def test_reinstating_clears_the_cancellation(self):
		booking.cancel_appointment(self.existing.name, "Unwell")
		self.assertEqual(booking.set_appointment_status(self.existing.name, "Scheduled"), "Scheduled")
		row = frappe.db.get_value(
			"Spa Appointment", self.existing.name, ["cancellation_fee", "cancelled_reason"], as_dict=True
		)
		self.assertEqual((row.cancellation_fee, row.cancelled_reason), (0, None))

	def test_hand_status_api_refuses_the_rest(self):
		for status in ("Cancelled", "Completed", "Checked In"):
			self.assertRaises(
				frappe.ValidationError, booking.set_appointment_status, self.existing.name, status
			)

	def test_a_cancelled_booking_cannot_return_into_a_taken_slot(self):
		frappe.db.set_value("Spa Appointment", self.existing.name, "status", "Cancelled")
		self.clash("10:00:00").insert()
		doc = frappe.get_doc("Spa Appointment", self.existing.name)
		doc.status = "Scheduled"
		with self.assertRaises(SlotTaken):
			doc.save()

	def test_a_finished_booking_is_not_rechecked(self):
		frappe.db.set_value(
			"Spa Appointment", self.existing.name, "appointment_date", add_days(nowdate(), -3)
		)
		doc = frappe.get_doc("Spa Appointment", self.existing.name)
		doc.status = "No Show"
		doc.save()

	def test_every_save_path_shares_the_controller_check(self):
		other = appointment(
			self.branch, make_client(), [(self.service, self.staff)], start="14:00:00"
		).insert()
		with self.assertRaises(SlotTaken):
			booking.reschedule_appointment(other.name, self.tomorrow, "10:30:00")


class TestSlots(SpaTestCase):
	def test_search_cost_does_not_grow_with_the_day(self):
		for _ in range(6):
			make_staff(self.branch, [self.service])
		appointment(self.branch, self.client, [(self.service, self.staff)]).insert()
		rows = [{"service": self.service.name}]
		real, count = frappe.db.sql, []

		def counted(*args, **kwargs):
			count.append(args[0])
			return real(*args, **kwargs)

		with patch.object(frappe.db, "sql", counted):
			slots = booking.open_slots(self.branch.name, self.tomorrow, rows)
		self.assertGreater(len(slots), 40)
		self.assertLess(len(count), 40)

	def test_slot_list_and_single_start_agree(self):
		rows = [{"service": self.service.name}]
		appointment(self.branch, self.client, [(self.service, self.staff)]).insert()
		offered = {
			to_minutes(s["start_time"]) for s in booking.open_slots(self.branch.name, self.tomorrow, rows)
		}
		for start in range(9 * 60, 20 * 60, 15):
			plan = booking.plan_at(self.branch.name, self.tomorrow, rows, start)
			self.assertEqual(bool(plan), start in offered, start)

	def test_outside_the_window_or_grid_is_not_offered(self):
		rows = [{"service": self.service.name}]
		self.assertIsNone(booking.plan_at(self.branch.name, add_days(nowdate(), 500), rows, 600))
		self.assertIsNone(booking.plan_at(self.branch.name, add_days(nowdate(), -1), rows, 600))
		self.assertIsNone(booking.plan_at(self.branch.name, self.tomorrow, rows, 607))

	def test_room_is_required_when_the_service_needs_one(self):
		service = make_service(room_type_required="Hair Station")
		make_staff(self.branch, [service])
		self.assertEqual(booking.open_slots(self.branch.name, self.tomorrow, [{"service": service.name}]), [])

	def test_time_off_blocks_the_staff_member(self):
		frappe.get_doc(
			{
				"doctype": "Spa Staff Time Off",
				"staff": self.staff.name,
				"status": "Approved",
				"reason": "Leave",
				"from_datetime": f"{self.tomorrow} 09:00:00",
				"to_datetime": f"{self.tomorrow} 12:00:00",
			}
		).insert(ignore_permissions=True)
		self.assertIn(
			"time off",
			Day(self.branch.name, self.tomorrow).check(self.service.name, self.staff.name, None, 600, 660),
		)

	def test_closed_day_has_a_reason_and_no_hours(self):
		for row in self.branch.hours:
			row.is_closed = 1
		self.branch.save(ignore_permissions=True)
		self.assertIsNone(branch_hours(self.branch.name, self.tomorrow))
		self.assertIn("closed", closed_reason(self.branch.name, self.tomorrow))
		self.assertEqual(
			booking.open_slots(self.branch.name, self.tomorrow, [{"service": self.service.name}]), []
		)


class TestStaffBooking(SpaTestCase):
	def test_books_a_free_slot(self):
		name = booking.book_appointment(
			self.client.name, self.branch.name, self.tomorrow, "10:00:00", f'["{self.service.name}"]'
		)
		self.assertEqual(frappe.db.get_value("Spa Appointment", name, "status"), "Scheduled")

	def test_bad_input_is_a_validation_error(self):
		good = f'["{self.service.name}"]'
		for date, start, services in (
			(self.tomorrow, "10:00:00", "not json"),
			(self.tomorrow, "10:00:00", '{"a": 1}'),
			(self.tomorrow, "10:00:00", "[5]"),
			(self.tomorrow, "10:00:00", '["No Such Service"]'),
			("tomorrow", "10:00:00", good),
			("", "10:00:00", good),
			(self.tomorrow, "25:00", good),
			(self.tomorrow, "soon", good),
		):
			with self.assertRaises(frappe.ValidationError):
				booking.book_appointment(self.client.name, self.branch.name, date, start, services)

	def test_inactive_branch_is_refused(self):
		frappe.db.set_value("Spa Branch", self.branch.name, "is_active", 0)
		with self.assertRaises(frappe.ValidationError):
			booking.book_appointment(
				self.client.name, self.branch.name, self.tomorrow, "10:00:00", f'["{self.service.name}"]'
			)


class TestHelpers(SpaTestCase):
	def test_clean_date_and_start(self):
		self.assertEqual(clean_date("2026-11-02"), "2026-11-02")
		self.assertEqual(clean_start("9:30"), 570)
		self.assertEqual(clean_start("09:30:00"), 570)
		for value in ("", None, "2026-13-01", "31/12/2026"):
			self.assertRaises(frappe.ValidationError, clean_date, value)
		for value in ("", None, "24:00", "12:60", "x"):
			self.assertRaises(frappe.ValidationError, clean_start, value)

	def test_branch_hours_compare_as_times_not_text(self):
		self.branch.hours[0].open_time, self.branch.hours[0].close_time = "10:00:00", "9:00:00"
		self.assertRaises(frappe.ValidationError, self.branch.save, ignore_permissions=True)
		self.branch.reload()
		self.branch.hours[0].open_time, self.branch.hours[0].close_time = "9:00:00", "10:00:00"
		self.branch.save(ignore_permissions=True)

	def test_shift_compares_as_times_not_text(self):
		self.staff.shifts[0].from_time, self.staff.shifts[0].to_time = "10:00:00", "9:00:00"
		self.assertRaises(frappe.ValidationError, self.staff.save, ignore_permissions=True)
