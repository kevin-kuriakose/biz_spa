from frappe.model.document import Document
import frappe


class SpaBranch(Document):
	def validate(self):
		seen = set()
		for row in self.hours or []:
			if row.weekday in seen:
				frappe.throw(f"{row.weekday} appears twice in Opening Hours.")
			seen.add(row.weekday)
			if not row.is_closed and (not row.open_time or not row.close_time):
				frappe.throw(f"Set open and close time for {row.weekday}, or mark it closed.")
			if not row.is_closed and str(row.open_time) >= str(row.close_time) and len(str(row.open_time)) == len(str(row.close_time)):
				frappe.throw(f"Open time must be before close time on {row.weekday}.")
