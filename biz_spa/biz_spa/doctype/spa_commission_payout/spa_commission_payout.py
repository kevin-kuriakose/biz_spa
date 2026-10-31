import frappe
from frappe.model.document import Document
from frappe.utils import flt, getdate

from biz_spa import posting


class SpaCommissionPayout(Document):
	ignore_linked_doctypes = posting.LINKED

	def validate(self):
		if getdate(self.from_date) > getdate(self.to_date):
			frappe.throw("From Date cannot be after To Date.")
		if not (self.entries or []):
			filters = {
				"staff": self.staff,
				"status": "Unpaid",
				"posting_date": ("between", [self.from_date, self.to_date]),
			}
			if self.branch:
				filters["branch"] = self.branch
			for row in frappe.get_all(
				"Spa Commission Entry",
				filters=filters,
				fields=["name", "visit", "posting_date", "reference_name", "commission_amount"],
			):
				self.append(
					"entries",
					{
						"commission_entry": row.name,
						"visit": row.visit,
						"entry_date": row.posting_date,
						"reference_name": row.reference_name,
						"amount": row.commission_amount,
					},
				)
		self.total_commission = sum(flt(r.amount) for r in (self.entries or []))
		self.net_payable = flt(self.total_commission) - flt(self.deductions)
		if flt(self.net_payable) < 0:
			frappe.throw("Deductions cannot be more than the total commission.")

	def before_submit(self):
		if not (self.entries or []):
			frappe.throw("There are no unpaid commission entries in this period.")
		self.claim_entries()

	def claim_entries(self):
		"""Locks each entry and proves it is still this payout's to pay, so a second payout holding
		the same entries waits here and is then refused."""
		seen = set()
		for row in sorted(self.entries, key=lambda r: r.commission_entry):
			entry = frappe.db.get_value(
				"Spa Commission Entry",
				row.commission_entry,
				["status", "payout", "staff", "branch", "commission_amount"],
				as_dict=True,
				for_update=True,
			)
			if not entry:
				frappe.throw(
					f"Commission entry {row.commission_entry} no longer exists. Remove it from this payout."
				)
			if row.commission_entry in seen or entry.status != "Unpaid" or entry.payout:
				frappe.throw(f"Commission entry {row.commission_entry} has already been paid.")
			if entry.staff != self.staff or (self.branch and entry.branch != self.branch):
				frappe.throw(f"Commission entry {row.commission_entry} does not belong to this payout.")
			if flt(entry.commission_amount, 2) != flt(row.amount, 2):
				frappe.throw(
					f"Commission entry {row.commission_entry} has changed. Remove it and add it again."
				)
			seen.add(row.commission_entry)

	@posting.as_system
	def on_submit(self):
		posting.post_payout(self)
		for row in self.entries:
			frappe.db.set_value(
				"Spa Commission Entry", row.commission_entry, {"status": "Paid", "payout": self.name}
			)

	@posting.as_system
	def on_cancel(self):
		posting.cancel_doc("Journal Entry", self.journal_entry)
		for row in self.entries or []:
			frappe.db.set_value(
				"Spa Commission Entry", row.commission_entry, {"status": "Unpaid", "payout": None}
			)
