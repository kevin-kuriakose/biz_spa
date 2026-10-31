from unittest.mock import patch

import frappe
from frappe.utils import add_days, flt, nowdate

from biz_spa import posting
from biz_spa.api import booking
from biz_spa.tests.test_access import make_user
from biz_spa.tests.utils import SpaTestCase, appointment, make_client, make_service, token


class MoneyCase(SpaTestCase):
	def visit(self, payments=None, lines=None, **values):
		return frappe.get_doc(
			{
				"doctype": "Spa Visit",
				"client": self.client.name,
				"branch": self.branch.name,
				"posting_date": nowdate(),
				"services": lines or [{"service": self.service.name, "staff": self.staff.name, "qty": 1}],
				"payments": payments or [],
				**values,
			}
		)

	def paid_in_cash(self, **values):
		doc = self.visit(**values).insert(ignore_permissions=True)
		doc.append("payments", {"mode_of_payment": "Cash", "amount": doc.grand_total})
		doc.save(ignore_permissions=True)
		return doc

	def gift_card(self, value=500):
		return (
			frappe.get_doc(
				{
					"doctype": "Spa Gift Card",
					"purchaser": self.client.customer
					or frappe.db.get_value("Spa Client Profile", self.client.name, "customer"),
					"branch": self.branch.name,
					"issue_date": nowdate(),
					"expiry_date": add_days(nowdate(), 30),
					"initial_value": value,
					"paid_amount": value,
					"mode_of_payment": "Cash",
				}
			)
			.insert(ignore_permissions=True)
			.submit()
		)

	def package(self, sessions=2):
		definition = frappe.get_doc(
			{
				"doctype": "Spa Package",
				"package_name": f"Test Package {token()}",
				"price": 1000,
				"validity_days": 30,
				"services": [{"service": self.service.name, "sessions": sessions, "unit_value": 500}],
			}
		).insert(ignore_permissions=True)
		return (
			frappe.get_doc(
				{
					"doctype": "Spa Client Package",
					"client": self.client.name,
					"package": definition.name,
					"branch": self.branch.name,
					"purchase_date": nowdate(),
					"paid_amount": 1000,
					"mode_of_payment": "Cash",
				}
			)
			.insert(ignore_permissions=True)
			.submit()
		)

	def membership(self, sessions=1):
		plan = frappe.get_doc(
			{
				"doctype": "Spa Membership Plan",
				"plan_name": f"Test Plan {token()}",
				"price": 1000,
				"validity_months": 3,
				"benefits": [{"service": self.service.name, "sessions_per_month": sessions}],
			}
		).insert(ignore_permissions=True)
		return (
			frappe.get_doc(
				{
					"doctype": "Spa Membership",
					"client": self.client.name,
					"plan": plan.name,
					"branch": self.branch.name,
					"start_date": nowdate(),
					"paid_amount": 1000,
					"mode_of_payment": "Cash",
				}
			)
			.insert(ignore_permissions=True)
			.submit()
		)

	def balance(self, account):
		value = frappe.db.sql(
			"SELECT SUM(credit - debit) FROM `tabGL Entry` WHERE account = %s AND is_cancelled = 0", account
		)
		return flt(value[0][0], 2)


class TestVisit(MoneyCase):
	def test_cash_visit_ties_to_its_invoice_and_payment(self):
		doc = self.paid_in_cash(
			lines=[
				{"service": self.service.name, "staff": self.staff.name, "qty": 3, "discount_percent": 12.5},
				{"service": self.service.name, "qty": 1, "rate": 99.99},
			]
		)
		self.assertEqual(flt(doc.outstanding_amount), 0)
		doc.submit()
		invoice = frappe.get_doc("Sales Invoice", doc.sales_invoice)
		self.assertEqual(flt(invoice.grand_total, 2), flt(doc.grand_total, 2))
		self.assertEqual(flt(invoice.outstanding_amount, 2), 0)
		self.assertTrue(
			frappe.db.exists("Payment Entry Reference", {"reference_name": invoice.name, "docstatus": 1})
		)

	def test_failed_payment_undoes_the_whole_submit(self):
		doc = self.paid_in_cash()
		frappe.db.savepoint("before_submit")
		with patch.object(posting, "make_payment", side_effect=frappe.ValidationError("Bank account closed")):
			with self.assertRaises(frappe.ValidationError):
				doc.submit()
		frappe.db.rollback(save_point="before_submit")
		self.assertEqual(frappe.db.get_value("Spa Visit", doc.name, "docstatus"), 0)
		self.assertFalse(frappe.db.exists("Sales Invoice", {"remarks": f"Spa Visit {doc.name}"}))

	def test_failed_gift_card_posting_keeps_the_balance_and_stops_the_submit(self):
		card = self.gift_card()
		doc = self.visit().insert(ignore_permissions=True)
		doc.append("payments", {"mode_of_payment": "Gift Card", "gift_card": card.name, "amount": 200})
		doc.append("payments", {"mode_of_payment": "Cash", "amount": doc.grand_total - 200})
		doc.save(ignore_permissions=True)
		frappe.db.savepoint("before_submit")
		with patch.object(posting, "move_gift_card", side_effect=frappe.ValidationError("no")):
			with self.assertRaises(frappe.ValidationError):
				doc.submit()
		frappe.db.rollback(save_point="before_submit")
		self.assertEqual(flt(frappe.db.get_value("Spa Gift Card", card.name, "balance")), 500)

	def test_a_real_invoice_error_reaches_the_user(self):
		with patch("frappe.get_doc", side_effect=frappe.ValidationError("Item out of stock")):
			with self.assertRaisesRegex(frappe.ValidationError, "Item out of stock"):
				posting.create_invoice({})

	def test_an_unexpected_invoice_error_stays_generic(self):
		with patch("frappe.get_doc", side_effect=KeyError("boom")), patch("frappe.log_error"):
			with self.assertRaisesRegex(frappe.ValidationError, "Nothing was submitted"):
				posting.create_invoice({})

	def test_a_one_paisa_gap_blocks_the_submit(self):
		doc = self.paid_in_cash()
		doc.payments[0].amount = flt(doc.grand_total) - 0.01
		doc.save(ignore_permissions=True)
		self.assertRaises(frappe.ValidationError, doc.submit)

	def test_tax_rounds_per_row_like_the_invoice(self):
		template = frappe.get_doc("Spa Settings").tax_template
		self.assertEqual(posting.tax_amount(template, 100.03), 18.0)


class TestPrepaid(MoneyCase):
	def redeem_card(self, card, amount):
		doc = self.visit().insert(ignore_permissions=True)
		doc.append("payments", {"mode_of_payment": "Gift Card", "gift_card": card.name, "amount": amount})
		doc.append("payments", {"mode_of_payment": "Cash", "amount": flt(doc.grand_total) - amount})
		doc.save(ignore_permissions=True)
		return doc

	def test_gift_card_drops_and_cancel_restores(self):
		card = self.gift_card()
		doc = self.redeem_card(card, 200).submit()
		self.assertEqual(flt(frappe.db.get_value("Spa Gift Card", card.name, "balance")), 300)
		doc.reload()
		doc.cancel()
		self.assertEqual(flt(frappe.db.get_value("Spa Gift Card", card.name, "balance")), 500)

	def test_gift_card_cannot_be_overspent_across_rows(self):
		card = self.gift_card()
		doc = self.visit().insert(ignore_permissions=True)
		doc.append("payments", {"mode_of_payment": "Gift Card", "gift_card": card.name, "amount": 300})
		doc.append("payments", {"mode_of_payment": "Gift Card", "gift_card": card.name, "amount": 300})
		doc.append("payments", {"mode_of_payment": "Cash", "amount": flt(doc.grand_total) - 600})
		doc.save(ignore_permissions=True)
		self.assertRaisesRegex(frappe.ValidationError, "only has", doc.submit)

	def test_package_cannot_be_overspent_across_lines(self):
		package = self.package(sessions=1)
		line = {
			"service": self.service.name,
			"qty": 1,
			"redeem_from": "Package",
			"client_package": package.name,
		}
		doc = self.visit(lines=[dict(line), dict(line)]).insert(ignore_permissions=True)
		self.assertRaisesRegex(frappe.ValidationError, "no sessions left", doc.submit)

	def test_membership_cannot_be_overspent_across_lines(self):
		membership = self.membership(sessions=1)
		line = {
			"service": self.service.name,
			"qty": 1,
			"redeem_from": "Membership",
			"membership": membership.name,
		}
		doc = self.visit(lines=[dict(line), dict(line)]).insert(ignore_permissions=True)
		self.assertRaisesRegex(frappe.ValidationError, "No membership sessions left", doc.submit)

	def test_membership_session_is_spent_and_restored(self):
		membership = self.membership(sessions=2)
		line = {
			"service": self.service.name,
			"qty": 1,
			"redeem_from": "Membership",
			"membership": membership.name,
		}
		doc = self.visit(lines=[line]).insert(ignore_permissions=True)
		doc.append("payments", {"mode_of_payment": "Cash", "amount": doc.outstanding_amount})
		doc.save(ignore_permissions=True) if flt(doc.outstanding_amount) else None
		doc.submit()
		self.assertEqual(
			posting.current_entitlement(membership.name, self.service.name, nowdate()).sessions_used, 1
		)
		doc.reload()
		doc.cancel()
		self.assertEqual(
			posting.current_entitlement(membership.name, self.service.name, nowdate()).sessions_used, 0
		)

	def test_membership_of_another_client_is_refused(self):
		membership = self.membership()
		frappe.db.set_value("Spa Membership", membership.name, "client", make_client().name)
		line = {
			"service": self.service.name,
			"qty": 1,
			"redeem_from": "Membership",
			"membership": membership.name,
		}
		doc = self.visit(lines=[line]).insert(ignore_permissions=True)
		self.assertRaisesRegex(frappe.ValidationError, "not an active membership", doc.submit)

	def test_boundary_day_uses_the_newer_period(self):
		membership = self.membership(sessions=1)
		first = frappe.get_doc("Spa Membership", membership.name).entitlements[0]
		frappe.db.set_value(
			"Spa Membership Entitlement",
			first.name,
			{"period_start": add_days(nowdate(), -30), "period_end": nowdate(), "sessions_used": 1},
		)
		row = frappe.get_doc("Spa Membership", membership.name).append(
			"entitlements",
			{
				"service": self.service.name,
				"period_start": nowdate(),
				"period_end": add_days(nowdate(), 30),
				"sessions_allowed": 1,
			},
		)
		row.db_insert()
		self.assertEqual(
			posting.current_entitlement(membership.name, self.service.name, nowdate()).name, row.name
		)

	def test_balance_checks_stop_a_path_that_skips_the_lock(self):
		card = self.gift_card()
		frappe.db.savepoint("direct")
		with self.assertRaises(Exception):
			frappe.db.sql("UPDATE `tabSpa Gift Card` SET balance = -1 WHERE name = %s", card.name)
		frappe.db.rollback(save_point="direct")

	def test_promotion_cap_holds_at_submit(self):
		promo = frappe.get_doc(
			{
				"doctype": "Spa Promotion",
				"promotion_name": f"Test Promo {token()}",
				"code": token(),
				"discount_type": "Percentage",
				"discount_value": 10,
				"valid_from": nowdate(),
				"valid_to": add_days(nowdate(), 5),
				"is_active": 1,
				"applies_to_all_services": 1,
				"max_uses": 1,
			}
		).insert(ignore_permissions=True)
		doc = self.paid_in_cash(promotion=promo.name)
		frappe.db.set_value("Spa Promotion", promo.name, "used_count", 1)
		frappe.clear_document_cache("Spa Promotion", promo.name)
		self.assertRaisesRegex(frappe.ValidationError, "usage limit", doc.submit)


class TestCommission(MoneyCase):
	def payout(self, **values):
		return frappe.get_doc(
			{
				"doctype": "Spa Commission Payout",
				"staff": self.staff.name,
				"company": self.branch.company,
				"from_date": nowdate(),
				"to_date": nowdate(),
				"posting_date": nowdate(),
				**values,
			}
		).insert(ignore_permissions=True)

	def test_earned_on_the_discounted_amount(self):
		doc = self.paid_in_cash(
			lines=[{"service": self.service.name, "staff": self.staff.name, "qty": 1, "discount_percent": 10}]
		)
		self.assertEqual(flt(doc.services[0].commission_amount), 90)

	def test_service_rate_beats_staff_rate(self):
		service = make_service(commission_rate=25)
		self.staff.append("skills", {"service": service.name})
		self.staff.save(ignore_permissions=True)
		frappe.clear_document_cache("Spa Staff Profile", self.staff.name)
		doc = self.paid_in_cash(lines=[{"service": service.name, "staff": self.staff.name, "qty": 1}])
		self.assertEqual(flt(doc.services[0].commission_amount), 250)

	def test_redeemed_line_earns_on_list_price(self):
		package = self.package()
		line = {
			"service": self.service.name,
			"staff": self.staff.name,
			"qty": 1,
			"redeem_from": "Package",
			"client_package": package.name,
		}
		doc = self.visit(lines=[line]).insert(ignore_permissions=True)
		self.assertEqual(flt(doc.services[0].commission_base), 1000)

	def test_same_entries_cannot_be_paid_twice(self):
		self.paid_in_cash().submit()
		first, second = self.payout(), self.payout()
		first.submit()
		self.assertRaisesRegex(frappe.ValidationError, "already been paid", second.submit)

	def test_paid_commission_blocks_the_visit_cancel(self):
		doc = self.paid_in_cash().submit()
		self.payout().submit()
		doc.reload()
		self.assertRaisesRegex(frappe.ValidationError, "has been paid", doc.cancel)

	def test_draft_payout_blocks_the_visit_cancel(self):
		doc = self.paid_in_cash().submit()
		payout = self.payout()
		doc.reload()
		self.assertRaisesRegex(frappe.ValidationError, payout.name, doc.cancel)

	def test_entry_removed_after_the_draft_is_refused(self):
		self.paid_in_cash().submit()
		payout = self.payout()
		frappe.db.delete("Spa Commission Entry", {"name": payout.entries[0].commission_entry})
		# Frappe's link check catches this first; claim_entries covers a row deleted after that check.
		self.assertRaisesRegex(frappe.ValidationError, "Could not find|no longer exists", payout.submit)

	def test_entry_of_another_staff_member_is_refused(self):
		self.paid_in_cash().submit()
		payout = self.payout()
		frappe.db.set_value(
			"Spa Commission Entry", payout.entries[0].commission_entry, "staff", "SOMEONE-ELSE"
		)
		self.assertRaisesRegex(frappe.ValidationError, "does not belong", payout.submit)

	def test_payable_balance_equals_net_payable_with_tips(self):
		"""The tip credits Commission Payable on the invoice and the payout credits the rest."""
		account = frappe.get_doc("Spa Settings").commission_payable_account
		before = self.balance(account)
		self.paid_in_cash(tip_amount=150, tip_staff=self.staff.name).submit()
		payout = self.payout(deductions=20)
		payout.submit()
		self.assertEqual(flt(payout.net_payable), 100 + 150 - 20)
		self.assertEqual(flt(self.balance(account) - before, 2), flt(payout.net_payable))

	def test_payable_still_ties_when_deductions_eat_into_tips(self):
		account = frappe.get_doc("Spa Settings").commission_payable_account
		before = self.balance(account)
		self.paid_in_cash(tip_amount=150, tip_staff=self.staff.name).submit()
		payout = self.payout(deductions=180)
		payout.submit()
		self.assertEqual(flt(payout.net_payable), 70)
		self.assertEqual(flt(self.balance(account) - before, 2), 70)

	def test_deductions_cannot_exceed_commission(self):
		self.paid_in_cash().submit()
		self.assertRaisesRegex(frappe.ValidationError, "Deductions", self.payout, deductions=101)


class TestLoyalty(MoneyCase):
	def test_points_pay_part_of_a_visit(self):
		customer = frappe.db.get_value("Spa Client Profile", self.client.name, "customer")
		program = frappe.db.get_value("Customer", customer, "loyalty_program")
		if not program:
			self.skipTest("Needs a default loyalty program")
		frappe.get_doc(
			{
				"doctype": "Loyalty Point Entry",
				"loyalty_program": program,
				"customer": customer,
				"company": self.branch.company,
				"loyalty_points": 100,
				"purchase_amount": 1000,
				"expiry_date": add_days(nowdate(), 90),
				"posting_date": nowdate(),
				"invoice_type": "Sales Invoice",
			}
		).insert(ignore_permissions=True)
		doc = self.visit(loyalty_points_redeemed=50).insert(ignore_permissions=True)
		doc.append("payments", {"mode_of_payment": "Cash", "amount": doc.outstanding_amount})
		doc.save(ignore_permissions=True)
		doc.submit()
		invoice = frappe.get_doc("Sales Invoice", doc.sales_invoice)
		self.assertEqual(flt(invoice.outstanding_amount, 2), 0)
		self.assertEqual(frappe.db.get_value("Spa Client Profile", self.client.name, "visit_count"), 1)


class TestCheckInToClose(MoneyCase):
	def test_appointment_to_visit_to_cash_close(self):
		appt = appointment(
			self.branch,
			self.client,
			[(self.service, self.staff)],
			date=nowdate(),
			start="20:00:00",
			source="Walk-in",
		).insert()
		name = booking.check_in(appt.name)
		doc = frappe.get_doc("Spa Visit", name)
		doc.append("payments", {"mode_of_payment": "Cash", "amount": doc.outstanding_amount})
		doc.save(ignore_permissions=True)
		doc.submit()
		self.assertEqual(frappe.db.get_value("Spa Appointment", appt.name, "status"), "Completed")
		close = frappe.get_doc(
			{
				"doctype": "Spa Cash Close",
				"branch": self.branch.name,
				"close_date": nowdate(),
				"opening_float": 0,
				"lines": [{"mode_of_payment": "Cash", "counted_amount": doc.grand_total}],
			}
		).insert(ignore_permissions=True)
		self.assertEqual(flt(close.variance), 0)
		doc.reload()
		doc.cancel()
		self.assertEqual(frappe.db.get_value("Spa Appointment", appt.name, "status"), "Checked In")


class TestAsStaff(MoneyCase):
	"""The postings as the people who run them: staff have no access to accounts or invoices."""

	def setUp(self):
		super().setUp()
		self.reception = make_user("Spa Receptionist")
		self.manager = make_user("Spa Manager")
		self.accountant = make_user("Spa Accountant")

	def assert_paid(self, invoice):
		self.assertEqual(flt(frappe.db.get_value("Sales Invoice", invoice, "outstanding_amount"), 2), 0)
		self.assertTrue(
			frappe.db.exists("Payment Entry Reference", {"reference_name": invoice, "docstatus": 1})
		)

	def test_reception_bills_and_manager_cancels(self):
		doc = self.paid_in_cash()
		frappe.set_user(self.reception)
		doc = frappe.get_doc("Spa Visit", doc.name)
		doc.submit()
		self.assert_paid(doc.sales_invoice)
		frappe.set_user(self.manager)
		doc.reload()
		doc.cancel()
		self.assertEqual(frappe.db.get_value("Sales Invoice", doc.sales_invoice, "docstatus"), 2)

	def test_a_failed_submit_gives_the_session_back(self):
		doc = self.paid_in_cash()
		frappe.set_user(self.reception)
		sid = frappe.session.sid
		doc = frappe.get_doc("Spa Visit", doc.name)
		with patch.object(posting, "make_payment", side_effect=frappe.ValidationError("no")):
			self.assertRaises(frappe.ValidationError, doc.submit)
		self.assertEqual((frappe.session.user, frappe.session.sid), (self.reception, sid))

	def test_reception_takes_a_gift_card(self):
		card = self.gift_card()
		doc = self.visit().insert(ignore_permissions=True)
		doc.append("payments", {"mode_of_payment": "Gift Card", "gift_card": card.name, "amount": 200})
		doc.append(
			"payments",
			{
				"mode_of_payment": "Card",
				"amount": flt(doc.grand_total) - 200,
				"reference_no": "T1",
				"reference_date": nowdate(),
			},
		)
		doc.save(ignore_permissions=True)
		frappe.set_user(self.reception)
		doc = frappe.get_doc("Spa Visit", doc.name)
		doc.submit()
		self.assertEqual(flt(frappe.db.get_value("Spa Gift Card", card.name, "balance")), 300)
		self.assert_paid(doc.sales_invoice)

	def test_reception_sells_prepaid(self):
		package = frappe.get_doc(
			{
				"doctype": "Spa Package",
				"package_name": f"Test Package {token()}",
				"price": 1000,
				"validity_days": 30,
				"services": [{"service": self.service.name, "sessions": 2, "unit_value": 500}],
			}
		).insert(ignore_permissions=True)
		plan = frappe.get_doc(
			{
				"doctype": "Spa Membership Plan",
				"plan_name": f"Test Plan {token()}",
				"price": 1000,
				"validity_months": 3,
				"benefits": [{"service": self.service.name, "sessions_per_month": 1}],
			}
		).insert(ignore_permissions=True)
		common = {
			"client": self.client.name,
			"branch": self.branch.name,
			"paid_amount": 1000,
			"mode_of_payment": "Cash",
		}
		frappe.set_user(self.reception)
		self.assert_paid(self.gift_card().sales_invoice)
		sold = frappe.get_doc(
			{"doctype": "Spa Client Package", "package": package.name, "purchase_date": nowdate(), **common}
		).insert()
		self.assert_paid(sold.submit().sales_invoice)
		sold = frappe.get_doc(
			{"doctype": "Spa Membership", "plan": plan.name, "start_date": nowdate(), **common}
		).insert()
		self.assert_paid(sold.submit().sales_invoice)

	def test_consumables_post_for_reception(self):
		row = frappe.db.get_value(
			"Bin",
			{"warehouse": self.branch.warehouse, "actual_qty": (">", 1)},
			["item_code", "stock_uom"],
			as_dict=True,
		)
		if not row:
			self.skipTest("Needs stock in the branch warehouse")
		service = make_service(consumables=[{"item": row.item_code, "qty": 1, "uom": row.stock_uom}])
		doc = self.visit(lines=[{"service": service.name, "qty": 1}], warehouse=self.branch.warehouse).insert(
			ignore_permissions=True
		)
		doc.append("payments", {"mode_of_payment": "Cash", "amount": doc.grand_total})
		doc.save(ignore_permissions=True)
		frappe.set_user(self.reception)
		doc = frappe.get_doc("Spa Visit", doc.name)
		with patch.object(posting, "guarded", lambda label, fn: fn()):
			doc.submit()
		self.assertTrue(frappe.db.get_value("Spa Visit", doc.name, "stock_entry"))

	def test_accountant_pays_commission_and_can_reverse_it(self):
		self.paid_in_cash().submit()
		payout = frappe.get_doc(
			{
				"doctype": "Spa Commission Payout",
				"staff": self.staff.name,
				"company": self.branch.company,
				"from_date": nowdate(),
				"to_date": nowdate(),
				"posting_date": nowdate(),
			}
		)
		frappe.set_user(self.accountant)
		payout.insert()
		payout.submit()
		self.assertTrue(payout.journal_entry)
		payout.reload()
		payout.cancel()
		self.assertEqual(frappe.db.get_value("Journal Entry", payout.journal_entry, "docstatus"), 2)

	def test_reception_closes_the_till(self):
		doc = self.paid_in_cash().submit()
		frappe.set_user(self.reception)
		close = frappe.get_doc(
			{
				"doctype": "Spa Cash Close",
				"branch": self.branch.name,
				"close_date": nowdate(),
				"lines": [{"mode_of_payment": "Cash", "counted_amount": doc.grand_total}],
			}
		).insert()
		close.submit()
		self.assertEqual(flt(close.variance), 0)


class TestConsumables(MoneyCase):
	def setUp(self):
		super().setUp()
		self.items = frappe.get_all(
			"Item", filters={"is_stock_item": 1, "disabled": 0}, pluck="name", limit=2
		)
		if len(self.items) < 2:
			self.skipTest("Needs two stock items")
		self.first = make_service(consumables=[{"item": self.items[0], "qty": 1, "uom": "Nos"}])
		self.second = make_service(consumables=[{"item": self.items[1], "qty": 2, "uom": "Nos"}])
		self.doc = self.visit(lines=[{"service": self.first.name, "qty": 1}]).insert(ignore_permissions=True)

	def test_changing_services_regenerates_their_rows(self):
		self.doc.services[0].service = self.second.name
		self.doc.save(ignore_permissions=True)
		self.assertEqual([r.item for r in self.doc.consumables], [self.items[1]])

	def test_manual_rows_survive_a_service_change(self):
		self.doc.append("consumables", {"item": self.items[1], "qty": 9, "uom": "Nos"})
		self.doc.save(ignore_permissions=True)
		self.doc.services[0].service = self.second.name
		self.doc.save(ignore_permissions=True)
		self.assertIn(9, [r.qty for r in self.doc.consumables])

	def test_edited_quantity_survives_a_plain_save(self):
		self.doc.consumables[0].qty = 4
		self.doc.save(ignore_permissions=True)
		self.assertEqual(self.doc.consumables[0].qty, 4)
