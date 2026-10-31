import frappe
from frappe.model.document import Document
from frappe.utils import flt, nowtime

from biz_spa import posting
from biz_spa.utils import settings


class SpaVisit(Document):
	ignore_linked_doctypes = posting.LINKED

	def validate(self):
		self.posting_time = self.posting_time or nowtime()
		self.taxes_and_charges = self.taxes_and_charges or settings().tax_template
		self.compute_services()
		self.compute_products()
		self.compute_consumables()
		self.compute_totals()

	def compute_services(self):
		total = redeemed = 0
		for row in self.services or []:
			service = frappe.get_cached_doc("Spa Service", row.service)
			row.qty = flt(row.qty) or 1
			if not flt(row.rate):
				row.rate = flt(service.price)
			row.amount = posting.line_amount(row.qty, row.rate, row.discount_percent)
			total += flt(row.amount)
			if row.redeem_from in ("Package", "Membership"):
				redeemed += flt(row.amount)
			self.compute_commission(row, service)
		self.total_services = flt(total, 2)
		self.package_redeemed_value = flt(redeemed, 2)

	def compute_commission(self, row, service):
		"""18.4: redeemed lines earn on list price, everything else on the discounted amount."""
		row.commission_base = row.commission_rate = row.commission_amount = 0
		if not row.staff:
			return
		staff = frappe.get_cached_value(
			"Spa Staff Profile", row.staff, ["commission_type", "commission_rate"], as_dict=True
		)
		rate = flt(service.commission_rate) or flt(staff.commission_rate)
		redeemed = row.redeem_from in ("Package", "Membership")
		row.commission_base = flt(service.price) * flt(row.qty) if redeemed else flt(row.amount)
		row.commission_rate = rate
		if staff.commission_type == "Fixed per service":
			row.commission_amount = rate
		else:
			row.commission_amount = flt(row.commission_base) * rate / 100

	def compute_products(self):
		total = 0
		for row in self.products or []:
			row.qty = flt(row.qty) or 1
			if not flt(row.rate):
				row.rate = flt(frappe.db.get_value("Item", row.item, "standard_rate"))
			row.amount = posting.line_amount(row.qty, row.rate, row.discount_percent)
			total += flt(row.amount)
			row.commission_amount = 0
			if row.sold_by:
				row.commission_amount = (
					flt(row.amount)
					* flt(frappe.get_cached_value("Spa Staff Profile", row.sold_by, "commission_rate"))
					/ 100
				)
		self.total_products = flt(total, 2)

	def compute_consumables(self):
		"""Rows carrying a service came from the service definition; rows without one were added by
		hand and always stay. Unchanged services keep their rows, so edited quantities survive a save."""
		before = self.get_doc_before_save()
		if self.consumables and (not before or self.service_key(before) == self.service_key(self)):
			return
		self.set("consumables", [r for r in self.consumables or [] if not r.service])
		for row in self.services or []:
			for used in frappe.get_cached_doc("Spa Service", row.service).consumables or []:
				self.append(
					"consumables",
					{
						"item": used.item,
						"qty": flt(used.qty) * flt(row.qty),
						"uom": used.uom,
						"warehouse": self.warehouse,
						"service": row.service,
					},
				)

	@staticmethod
	def service_key(doc):
		return sorted((r.service, flt(r.qty)) for r in (doc.services or []))

	def billable(self):
		return flt(self.total_services) - flt(self.package_redeemed_value) + flt(self.total_products)

	def compute_totals(self):
		self.discount_amount = posting.promotion_discount(self)
		net = self.billable() - flt(self.discount_amount)
		self.tax_amount = posting.tax_amount(self.taxes_and_charges, net)
		self.grand_total = flt(
			flt(self.total_services)
			+ flt(self.total_products)
			- flt(self.discount_amount)
			+ flt(self.tax_amount)
			+ flt(self.tip_amount),
			2,
		)
		self.gift_card_redeemed = flt(sum(flt(r.amount) for r in (self.payments or []) if r.gift_card), 2)
		self.paid_amount = flt(sum(flt(r.amount) for r in (self.payments or []) if not r.gift_card), 2)
		self.outstanding_amount = flt(
			self.grand_total
			- flt(self.package_redeemed_value)
			- flt(self.gift_card_redeemed)
			- flt(self.paid_amount)
			- posting.loyalty_value(self),
			2,
		)
		if flt(self.tip_amount) and not self.tip_staff:
			frappe.throw("Select the staff member receiving the tip.")

	def before_submit(self):
		if not (self.services or self.products):
			frappe.throw("Add at least one service or product.")
		if flt(self.outstanding_amount, 2):
			frappe.throw(
				f"Payments and redemptions must equal the grand total. Difference: {self.outstanding_amount}"
			)
		posting.check_redemptions(self)

	@posting.as_system
	def on_submit(self):
		si = posting.post_visit_invoice(self)
		self.db_set("sales_invoice", si.name)
		posting.post_visit_payments(self, si)
		posting.post_gift_cards(self, si)
		posting.post_consumables(self)
		posting.consume_prepaid(self)
		posting.post_commissions(self)
		posting.update_after_visit(self, 1)

	def before_cancel(self):
		entries = frappe.db.get_values(
			"Spa Commission Entry", {"visit": self.name}, ["name", "status"], as_dict=True, for_update=True
		)
		if any(row.status == "Paid" for row in entries):
			frappe.throw("Commission from this visit has been paid. Cancel the payout first.")
		drafts = frappe.get_all(
			"Spa Commission Payout Line",
			filters={"commission_entry": ("in", [row.name for row in entries] or [""]), "docstatus": 0},
			pluck="parent",
			distinct=True,
		)
		if drafts:
			frappe.throw(
				f"Commission from this visit is on draft payout {', '.join(drafts)}. Remove it from the payout first."
			)

	@posting.as_system
	def on_cancel(self):
		frappe.db.delete("Spa Commission Entry", {"visit": self.name, "status": "Unpaid"})
		posting.cancel_doc("Stock Entry", self.stock_entry)
		posting.reverse_gift_cards(self)
		posting.restore_prepaid(self)
		posting.cancel_payments(self.sales_invoice)
		posting.cancel_doc("Sales Invoice", self.sales_invoice)
		posting.update_after_visit(self, -1)
