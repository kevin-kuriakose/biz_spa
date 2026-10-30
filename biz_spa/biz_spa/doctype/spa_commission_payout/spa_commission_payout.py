from frappe.model.document import Document
import frappe
from biz_spa import posting
from frappe.utils import flt, getdate


class SpaCommissionPayout(Document):
	ignore_linked_doctypes = posting.LINKED

	def validate(self):
		if getdate(self.from_date) > getdate(self.to_date):
			frappe.throw("From Date cannot be after To Date.")
		if not (self.entries or []):
			filters = {"staff": self.staff, "status": "Unpaid", "posting_date": ("between", [self.from_date, self.to_date])}
			if self.branch:
				filters["branch"] = self.branch
			for row in frappe.get_all("Spa Commission Entry", filters=filters, fields=["name", "visit", "posting_date", "reference_name", "commission_amount"]):
				self.append("entries", {"commission_entry": row.name, "visit": row.visit, "entry_date": row.posting_date, "reference_name": row.reference_name, "amount": row.commission_amount})
		self.total_commission = sum(flt(r.amount) for r in (self.entries or []))
		self.net_payable = flt(self.total_commission) - flt(self.deductions)

	def on_submit(self):
		if not (self.entries or []):
			frappe.throw("There are no unpaid commission entries in this period.")
		posting.post_payout(self)
		for row in self.entries:
			frappe.db.set_value("Spa Commission Entry", row.commission_entry, {"status": "Paid", "payout": self.name})

	def on_cancel(self):
		posting.cancel_doc("Journal Entry", self.journal_entry)
		for row in self.entries or []:
			frappe.db.set_value("Spa Commission Entry", row.commission_entry, {"status": "Unpaid", "payout": None})
