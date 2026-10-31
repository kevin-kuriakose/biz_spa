"""Real races: each thread has its own database connection and transaction. These commit, so every
test deletes what it made. Nothing here goes near the ledger; the fixtures are written directly."""

import threading
from unittest import TestCase

import frappe
from frappe.utils import add_days, flt, nowdate

from biz_spa import posting
from biz_spa.booking_rules import SlotTaken
from biz_spa.tests.utils import appointment, make_branch, make_service, make_staff, token


def race(*jobs):
	"""Runs each job in its own connection, past a barrier, and returns what each one raised."""
	site = frappe.local.site
	gate = threading.Barrier(len(jobs))
	outcomes = [None] * len(jobs)

	def worker(index, job):
		frappe.init(site=site)
		frappe.connect()
		frappe.flags.in_test = True
		frappe.set_user("Administrator")
		try:
			# A first read fixes this transaction's snapshot before the other job commits, which is
			# what a real request has done by the time it reaches the check.
			frappe.get_all("Spa Appointment", limit=1)
			gate.wait(10)
			job()
			frappe.db.commit()
		except Exception as error:
			frappe.db.rollback()
			outcomes[index] = error
		finally:
			frappe.destroy()

	threads = [threading.Thread(target=worker, args=(i, job)) for i, job in enumerate(jobs)]
	for thread in threads:
		thread.start()
	for thread in threads:
		thread.join(60)
	return outcomes


class TestRaces(TestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.visit = frappe._dict(
			name="SPA-VIS-RACE",
			posting_date=nowdate(),
			client=None,
			customer=None,
			services=[],
			payments=[],
			promotion=None,
			loyalty_points_redeemed=0,
		)
		self.cleanup = []

	def tearDown(self):
		frappe.db.rollback()
		for doctype, filters in self.cleanup:
			frappe.db.delete(doctype, filters)
		frappe.db.commit()

	def track(self, doc):
		self.cleanup.append((doc.doctype, {"name": doc.name}))
		return doc

	def test_two_bookings_for_one_slot(self):
		branch, service = self.track(make_branch()), self.track(make_service())
		staff = self.track(make_staff(branch, [service]))
		# Existing clients: a new one would leave a Customer and Contact behind.
		one, two = (
			frappe._dict(name=name) for name in frappe.get_all("Spa Client Profile", pluck="name", limit=2)
		)
		self.cleanup += [
			("Spa Branch Hours", {"parent": branch.name}),
			("Spa Staff Skill", {"parent": staff.name}),
			("Spa Staff Shift", {"parent": staff.name}),
			("Item", {"name": frappe.db.get_value("Spa Service", service.name, "item")}),
		]
		frappe.db.commit()

		def book(client):
			return lambda: appointment(branch, client, [(service, staff)]).insert(ignore_permissions=True)

		outcomes = race(book(one), book(two))
		saved = frappe.get_all("Spa Appointment", filters={"branch": branch.name}, pluck="name")
		self.cleanup += [
			("Spa Appointment Service", {"parent": ("in", saved or [""])}),
			("Spa Appointment", {"name": ("in", saved or [""])}),
		]
		self.assertEqual(len(saved), 1, outcomes)
		self.assertEqual(sum(isinstance(o, SlotTaken) for o in outcomes), 1, outcomes)

	def card(self, balance):
		name = f"SPA-GC-RACE-{token()}"
		frappe.db.sql(
			"""INSERT INTO `tabSpa Gift Card` (name, docstatus, status, balance, initial_value, expiry_date, creation, modified)
			VALUES (%s, 1, 'Active', %s, %s, %s, NOW(), NOW())""",
			(name, balance, balance, add_days(nowdate(), 30)),
		)
		self.cleanup += [("Spa Gift Card", {"name": name}), ("Spa Gift Card Transaction", {"parent": name})]
		frappe.db.commit()
		return name

	def test_two_visits_spending_one_gift_card(self):
		name = self.card(100)

		def spend():
			visit = frappe._dict(
				self.visit,
				payments=[frappe._dict(idx=1, mode_of_payment="Gift Card", gift_card=name, amount=60)],
			)
			posting.check_redemptions(visit)
			posting.move_gift_card(name, -60, "Redeem", visit)

		outcomes = race(spend, spend)
		self.assertEqual(sum(o is None for o in outcomes), 1, outcomes)
		self.assertEqual(flt(frappe.db.get_value("Spa Gift Card", name, "balance")), 40)

	def test_two_visits_spending_the_last_package_session(self):
		name = f"SPA-PKG-RACE-{token()}"
		frappe.db.sql(
			"""INSERT INTO `tabSpa Client Package` (name, docstatus, status, client, total_sessions, balance_sessions, used_sessions, expiry_date, creation, modified)
			VALUES (%s, 1, 'Active', 'RACE', 1, 1, 0, %s, NOW(), NOW())""",
			(name, add_days(nowdate(), 30)),
		)
		frappe.db.sql(
			"""INSERT INTO `tabSpa Client Package Item` (name, parent, parenttype, parentfield, service, total_sessions, used_sessions, balance_sessions, creation, modified)
			VALUES (%s, %s, 'Spa Client Package', 'items', 'RACE', 1, 0, 1, NOW(), NOW())""",
			(token(), name),
		)
		self.cleanup += [
			("Spa Client Package", {"name": name}),
			("Spa Client Package Item", {"parent": name}),
			("Spa Client Package Usage", {"parent": name}),
		]
		frappe.db.commit()

		def spend():
			line = frappe._dict(
				idx=1, service="RACE", qty=1, redeem_from="Package", client_package=name, staff=None
			)
			visit = frappe._dict(self.visit, client="RACE", services=[line])
			posting.check_redemptions(visit)
			posting.consume_prepaid(visit)

		outcomes = race(spend, spend)
		self.assertEqual(sum(o is None for o in outcomes), 1, outcomes)
		self.assertEqual(frappe.db.get_value("Spa Client Package", name, "balance_sessions"), 0)

	def test_two_visits_taking_the_last_membership_session(self):
		name = f"SPA-MEM-RACE-{token()}"
		frappe.db.sql(
			"""INSERT INTO `tabSpa Membership` (name, docstatus, status, client, creation, modified)
			VALUES (%s, 1, 'Active', 'RACE', NOW(), NOW())""",
			name,
		)
		frappe.db.sql(
			"""INSERT INTO `tabSpa Membership Entitlement` (name, parent, parenttype, parentfield, service, period_start, period_end, sessions_allowed, sessions_used, creation, modified)
			VALUES (%s, %s, 'Spa Membership', 'entitlements', 'RACE', %s, %s, 1, 0, NOW(), NOW())""",
			(token(), name, nowdate(), add_days(nowdate(), 30)),
		)
		self.cleanup += [("Spa Membership", {"name": name}), ("Spa Membership Entitlement", {"parent": name})]
		frappe.db.commit()

		def spend():
			line = frappe._dict(
				idx=1, service="RACE", qty=1, redeem_from="Membership", membership=name, staff=None
			)
			visit = frappe._dict(self.visit, client="RACE", services=[line])
			posting.check_redemptions(visit)
			posting.consume_prepaid(visit)

		outcomes = race(spend, spend)
		self.assertEqual(sum(o is None for o in outcomes), 1, outcomes)
		self.assertEqual(
			frappe.db.get_value("Spa Membership Entitlement", {"parent": name}, "sessions_used"), 1
		)

	def test_two_payouts_claiming_one_commission_entry(self):
		name = f"SPA-COM-RACE-{token()}"
		frappe.db.sql(
			"""INSERT INTO `tabSpa Commission Entry` (name, staff, status, commission_amount, creation, modified)
			VALUES (%s, 'RACE', 'Unpaid', 100, NOW(), NOW())""",
			name,
		)
		self.cleanup.append(("Spa Commission Entry", {"name": name}))
		frappe.db.commit()

		def claim():
			payout = frappe.new_doc("Spa Commission Payout")
			payout.update({"staff": "RACE", "name": "RACE"})
			payout.append("entries", {"commission_entry": name, "amount": 100})
			payout.claim_entries()
			frappe.db.set_value("Spa Commission Entry", name, {"status": "Paid", "payout": "RACE"})

		outcomes = race(claim, claim)
		self.assertEqual(sum(o is None for o in outcomes), 1, outcomes)

	def test_two_visits_taking_the_last_promotion_use(self):
		name = f"RACE {token()}"
		frappe.db.sql(
			"""INSERT INTO `tabSpa Promotion` (name, max_uses, used_count, creation, modified) VALUES (%s, 1, 0, NOW(), NOW())""",
			name,
		)
		self.cleanup.append(("Spa Promotion", {"name": name}))
		frappe.db.commit()

		def spend():
			visit = frappe._dict(self.visit, promotion=name)
			posting.check_redemptions(visit)
			frappe.db.set_value("Spa Promotion", name, "used_count", 1)

		outcomes = race(spend, spend)
		self.assertEqual(sum(o is None for o in outcomes), 1, outcomes)
