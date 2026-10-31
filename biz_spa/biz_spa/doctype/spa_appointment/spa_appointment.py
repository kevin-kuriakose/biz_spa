from frappe.model.document import Document

from biz_spa.booking_rules import ACTIVE, compute_lines, validate_lines


class SpaAppointment(Document):
	def validate(self):
		compute_lines(self)
		if self.status in ACTIVE and self.schedule_changed():
			validate_lines(self)

	def schedule_changed(self):
		# An existing booking is only re-checked when its timing changes, so a past appointment
		# can still move to Completed or No Show.
		before = self.get_doc_before_save()
		if not before:
			return True
		return self.schedule_key(self) != self.schedule_key(before)

	@staticmethod
	def schedule_key(doc):
		lines = [
			(r.service, r.staff, r.room, str(r.start_time), r.duration_minutes) for r in (doc.services or [])
		]
		return (doc.branch, str(doc.appointment_date), str(doc.start_time), lines)
