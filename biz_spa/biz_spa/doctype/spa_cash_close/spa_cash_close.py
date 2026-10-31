import frappe
from frappe.model.document import Document
from frappe.utils import flt


class SpaCashClose(Document):
	def validate(self):
		self.closed_by = self.closed_by or frappe.session.user
		expected = self.expected_by_mode()
		counted = {r.mode_of_payment: r.counted_amount for r in (self.lines or [])}
		self.set("lines", [])
		for mode in sorted(set(expected) | set(counted)):
			amount = flt(expected.get(mode))
			self.append(
				"lines",
				{
					"mode_of_payment": mode,
					"expected_amount": amount,
					"counted_amount": flt(counted.get(mode)),
					"variance": flt(counted.get(mode)) - amount,
				},
			)
		self.expected_total = sum(flt(r.expected_amount) for r in self.lines)
		self.counted_total = sum(flt(r.counted_amount) for r in self.lines)
		self.variance = flt(self.counted_total) - flt(self.expected_total)

	def before_submit(self):
		other = frappe.db.exists(
			"Spa Cash Close",
			{"branch": self.branch, "close_date": self.close_date, "docstatus": 1, "name": ("!=", self.name)},
		)
		if other:
			frappe.throw(f"{self.branch} is already closed for {self.close_date}: {other}.")

	def expected_by_mode(self):
		"""Takings for the day by mode; gift card redemptions are not money in the till."""
		totals = {}
		for mode, amount in frappe.db.sql(
			"""SELECT p.mode_of_payment, SUM(p.amount) FROM `tabSpa Visit Payment` p JOIN `tabSpa Visit` v ON v.name = p.parent
			WHERE v.docstatus = 1 AND v.branch = %s AND v.posting_date = %s AND IFNULL(p.gift_card, '') = ''
			GROUP BY p.mode_of_payment""",
			(self.branch, self.close_date),
		):
			totals[mode] = flt(amount)
		for doctype, date_field in (
			("Spa Client Package", "purchase_date"),
			("Spa Membership", "start_date"),
			("Spa Gift Card", "issue_date"),
		):
			for row in frappe.get_all(
				doctype,
				filters={
					"docstatus": 1,
					"branch": self.branch,
					date_field: self.close_date,
					"paid_amount": (">", 0),
				},
				fields=["mode_of_payment", "paid_amount"],
			):
				totals[row.mode_of_payment] = totals.get(row.mode_of_payment, 0) + flt(row.paid_amount)
		if flt(self.opening_float):
			totals["Cash"] = totals.get("Cash", 0) + flt(self.opening_float)
		return totals
