import frappe
from frappe.model.document import Document

from biz_spa.booking_rules import ACTIVE, CLOSED, TRANSITIONS, compute_lines, validate_lines


class SpaAppointment(Document):
	def validate(self):
		before = self.get_doc_before_save()
		self.check_status(before)
		compute_lines(self)
		if self.status not in CLOSED and self.needs_slot_check(before):
			validate_lines(self)

	def check_status(self, before):
		# Status is read-only on the form, but an API save can still send it. Completed is set only
		# by submitting the visit.
		if not before:
			if self.status not in ACTIVE:
				frappe.throw(f"A new appointment cannot start as {self.status}.")
			return
		if self.status != before.status and self.status not in TRANSITIONS.get(before.status, ()):
			frappe.throw(f"A {before.status} appointment cannot move to {self.status}.")
		if self.status == "Cancelled" and not self.cancelled_reason:
			frappe.throw("Cancel the appointment with a reason.")
		if before.status in CLOSED and self.status not in CLOSED:
			self.cancelled_reason, self.cancellation_fee = None, 0

	def needs_slot_check(self, before):
		# Anything that takes up a slot is checked: a new booking, a change of timing, or a cancelled
		# booking coming back. An unchanged booking is not re-checked, so a past appointment can
		# still be checked in or marked No Show.
		if not before or before.status in CLOSED:
			return True
		return self.schedule_key(self) != self.schedule_key(before)

	@staticmethod
	def schedule_key(doc):
		lines = [
			(r.service, r.staff, r.room, str(r.start_time), r.duration_minutes) for r in (doc.services or [])
		]
		return (doc.branch, str(doc.appointment_date), str(doc.start_time), lines)
