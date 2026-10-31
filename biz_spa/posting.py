from functools import wraps

import frappe
from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry
from erpnext.accounts.doctype.sales_invoice.sales_invoice import get_bank_cash_account
from frappe.utils import cint, flt, getdate, nowdate

from biz_spa.utils import settings

LINKED = (
	"Sales Invoice",
	"Payment Entry",
	"Journal Entry",
	"Stock Entry",
	"GL Entry",
	"Stock Ledger Entry",
	"Payment Ledger Entry",
	"Loyalty Point Entry",
	"Spa Commission Entry",
	"Spa Client Package",
	"Spa Membership",
	"Spa Gift Card",
	"Spa Feedback",
	"Spa Color Formula",
	"Spa Commission Payout",
)


def as_system(method):
	"""Runs a document's postings as Administrator. Frappe has already checked that the user may
	submit or cancel the document; the invoices and entries behind it are the system's work, and
	reception has no access to accounts. The user's session is put back unchanged afterwards."""

	@wraps(method)
	def wrapper(*args, **kwargs):
		session, form_dict = frappe.local.session, frappe.local.form_dict
		user, sid, data = session.user, session.sid, session.data
		frappe.set_user("Administrator")
		try:
			return method(*args, **kwargs)
		finally:
			frappe.set_user(user)
			session.sid, session.data = sid, data
			frappe.local.form_dict = form_dict

	return wrapper


def guarded(label, fn):
	"""Runs a step the sale can survive without, such as issuing consumables: a failure is rolled back,
	logged and shown as a warning. Anything recording money must not use this, because the document
	would then commit saying the money moved when it did not."""
	frappe.db.savepoint("biz_spa_step")
	try:
		return fn()
	except Exception:
		frappe.db.rollback(save_point="biz_spa_step")
		frappe.log_error(frappe.get_traceback(), f"Biz Spa: {label} failed")
		frappe.clear_messages()
		frappe.msgprint(
			f"{label} failed and was not posted. Please post it by hand.", indicator="orange", alert=True
		)


def line_amount(qty: float, rate: float, discount_percent: float) -> float:
	"""Rounds the same way as a Sales Invoice line, rate first and then rate times qty, so the visit
	and its invoice cannot drift apart."""
	return flt(flt(flt(rate) * (1 - flt(discount_percent) / 100), 2) * flt(qty), 2)


def tax_amount(template, net: float) -> float:
	"""Each tax row rounds on its own, as it does on the invoice."""
	if not template:
		return 0
	rows = frappe.get_cached_doc("Sales Taxes and Charges Template", template).taxes or []
	return flt(sum(flt(flt(net) * flt(r.rate) / 100, 2) for r in rows), 2)


def tax_rows(template, cost_center, inclusive=False):
	rows = []
	for row in frappe.get_cached_doc("Sales Taxes and Charges Template", template).taxes or []:
		rows.append(
			{
				"charge_type": row.charge_type,
				"account_head": row.account_head,
				"rate": row.rate,
				"description": row.description,
				"cost_center": cost_center,
				"included_in_print_rate": 1 if inclusive else 0,
			}
		)
	return rows


def create_invoice(values):
	"""Section 5 rule 7: any failure stops the submit."""
	try:
		invoice = frappe.get_doc(
			{"doctype": "Sales Invoice", "set_posting_time": 1, "disable_rounded_total": 1, **values}
		)
		invoice.flags.ignore_permissions = True
		invoice.insert(ignore_permissions=True)
		invoice.submit()
	except frappe.ValidationError:
		# Stock, account and closed period errors say what to fix, so they reach the user unchanged.
		raise
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Biz Spa: Sales Invoice failed")
		frappe.throw("Sales Invoice could not be created. Nothing was submitted.")
	return invoice


def promotion_discount(visit):
	if not visit.promotion:
		return 0
	promo = frappe.get_cached_doc("Spa Promotion", visit.promotion)
	date = getdate(visit.posting_date)
	if not promo.is_active or date < getdate(promo.valid_from) or date > getdate(promo.valid_to):
		frappe.throw(f"Promotion {promo.name} is not valid on this date.")
	if promo.branch and promo.branch != visit.branch:
		frappe.throw(f"Promotion {promo.name} is not valid at {visit.branch}.")
	if cint(promo.max_uses) and cint(promo.used_count) >= cint(promo.max_uses) and visit.docstatus == 0:
		frappe.throw(f"Promotion {promo.name} has reached its usage limit.")
	allowed = None if promo.applies_to_all_services else {r.service for r in promo.services or []}
	base = sum(
		flt(r.amount)
		for r in visit.services or []
		if r.redeem_from not in ("Package", "Membership") and (allowed is None or r.service in allowed)
	)
	if allowed is None:
		base += flt(visit.total_products)
	if base < flt(promo.min_bill_amount):
		return 0
	off = (
		base * flt(promo.discount_value) / 100
		if promo.discount_type == "Percentage"
		else flt(promo.discount_value)
	)
	return min(flt(off, 2), base)


def loyalty_account(customer):
	program = frappe.db.get_value("Customer", customer, "loyalty_program")
	return frappe.get_cached_doc("Loyalty Program", program) if program else None


def loyalty_value(visit) -> float:
	points = cint(visit.loyalty_points_redeemed)
	if not points:
		return 0
	program = loyalty_account(visit.customer)
	if not program:
		frappe.throw("This client is not in a Loyalty Program.")
	return flt(points * flt(program.conversion_factor), 2)


def points_balance(customer) -> int:
	value = frappe.db.sql(
		"SELECT SUM(loyalty_points) FROM `tabLoyalty Point Entry` WHERE customer = %s", customer
	)
	return cint(value[0][0]) if value else 0


def check_redemptions(visit):
	"""Locks everything this visit spends. The locks last until the submit commits, so a second visit
	spending the same value waits here and then checks against the balance the first one left."""
	if cint(visit.loyalty_points_redeemed) > points_balance(visit.customer):
		frappe.throw("The client does not have enough loyalty points.")
	needed = {}
	allowance = {}
	for row in visit.services or []:
		if row.redeem_from == "Package":
			if not row.client_package:
				frappe.throw(f"Row {row.idx}: select the Client Package.")
			needed[(row.client_package, row.service)] = needed.get(
				(row.client_package, row.service), 0
			) + flt(row.qty)
		elif row.redeem_from == "Membership":
			if not row.membership:
				frappe.throw(f"Row {row.idx}: select the Membership.")
			key = (row.membership, row.service)
			allowance[key] = allowance.get(key, 0) + flt(row.qty)
	for (membership, service), qty in sorted(allowance.items()):
		owner = frappe.db.get_value(
			"Spa Membership", membership, ["client", "docstatus", "status"], as_dict=True
		)
		if not owner or owner.docstatus != 1 or owner.status != "Active" or owner.client != visit.client:
			frappe.throw(f"{membership} is not an active membership for this client.")
		entitlement = current_entitlement(membership, service, visit.posting_date)
		if not entitlement or cint(entitlement.sessions_allowed) - cint(entitlement.sessions_used) < qty:
			frappe.throw(f"No membership sessions left for {service} this period.")
	for (name, service), qty in sorted(needed.items()):
		package = frappe.get_doc("Spa Client Package", name, for_update=True)
		if package.docstatus != 1 or package.status != "Active" or package.client != visit.client:
			frappe.throw(f"{name} is not an active package for this client.")
		if getdate(package.expiry_date) < getdate(visit.posting_date):
			frappe.throw(f"{name} has expired.")
		row = next((r for r in package.items if r.service == service), None)
		if not row or cint(row.balance_sessions) < qty:
			frappe.throw(f"{name} has no sessions left for {service}.")
	cards = {}
	for row in visit.payments or []:
		if row.mode_of_payment == "Gift Card" and not row.gift_card:
			frappe.throw(f"Payment row {row.idx}: select the Gift Card.")
		if row.gift_card:
			cards[row.gift_card] = cards.get(row.gift_card, 0) + flt(row.amount)
	for name, amount in sorted(cards.items()):
		card = frappe.get_doc("Spa Gift Card", name, for_update=True)
		if (
			card.docstatus != 1
			or card.status != "Active"
			or getdate(card.expiry_date) < getdate(visit.posting_date)
		):
			frappe.throw(f"Gift card {card.name} is not active.")
		if amount > flt(card.balance):
			frappe.throw(f"Gift card {card.name} only has {card.balance} left.")
	if visit.promotion:
		promo = frappe.db.get_value(
			"Spa Promotion", visit.promotion, ["max_uses", "used_count"], as_dict=True, for_update=True
		)
		if cint(promo.max_uses) and cint(promo.used_count) >= cint(promo.max_uses):
			frappe.throw(f"Promotion {visit.promotion} has reached its usage limit.")


def current_entitlement(membership, service, date):
	"""Locks the row: every caller goes on to spend or restore sessions from it."""
	return frappe.db.get_value(
		"Spa Membership Entitlement",
		{"parent": membership, "service": service, "period_start": ("<=", date), "period_end": (">=", date)},
		["name", "sessions_allowed", "sessions_used"],
		as_dict=True,
		for_update=True,
		order_by="period_start desc",
	)


def post_visit_invoice(visit):
	items = []
	for row in visit.services or []:
		redeemed = row.redeem_from in ("Package", "Membership")
		line = {
			"item_code": frappe.get_cached_value("Spa Service", row.service, "item"),
			"qty": row.qty,
			"rate": 0 if redeemed else flt(flt(row.amount) / flt(row.qty), 2),
			"cost_center": visit.cost_center,
		}
		if redeemed:
			# Without this ERPNext treats rate 0 as unset and re-prices the line from the Item.
			line.update(is_free_item=1, price_list_rate=0, discount_percentage=0)
		items.append(line)
	for row in visit.products or []:
		items.append(
			{
				"item_code": row.item,
				"qty": row.qty,
				"rate": flt(flt(row.amount) / flt(row.qty), 2),
				"cost_center": visit.cost_center,
				"warehouse": visit.warehouse,
			}
		)
	taxes = tax_rows(visit.taxes_and_charges, visit.cost_center) if visit.taxes_and_charges else []
	if flt(visit.tip_amount):
		taxes.append(
			{
				"charge_type": "Actual",
				"account_head": settings().commission_payable_account,
				"tax_amount": flt(visit.tip_amount),
				"description": "Tip",
				"cost_center": visit.cost_center,
			}
		)
	values = {
		"customer": visit.customer,
		"company": visit.company,
		"cost_center": visit.cost_center,
		"posting_date": visit.posting_date,
		"due_date": visit.posting_date,
		"items": items,
		"taxes": taxes,
		"remarks": f"Spa Visit {visit.name}",
	}
	if flt(visit.discount_amount):
		values.update(apply_discount_on="Net Total", discount_amount=flt(visit.discount_amount))
	if visit.products:
		values.update(update_stock=1, set_warehouse=visit.warehouse)
	if cint(visit.loyalty_points_redeemed):
		program = loyalty_account(visit.customer)
		values.update(
			redeem_loyalty_points=1,
			loyalty_points=cint(visit.loyalty_points_redeemed),
			loyalty_amount=loyalty_value(visit),
			loyalty_redemption_account=program.expense_account,
			loyalty_redemption_cost_center=program.cost_center,
		)
	return create_invoice(values)


def make_payment(invoice, mode, amount, reference_no=None, reference_date=None):
	payment = get_payment_entry(
		"Sales Invoice", invoice.name, party_amount=flt(amount), bank_amount=flt(amount)
	)
	account = get_bank_cash_account(mode, invoice.company).get("account")
	payment.mode_of_payment = mode
	payment.paid_to = account
	payment.paid_to_account_currency = frappe.db.get_value("Account", account, "account_currency")
	payment.paid_amount = flt(amount)
	payment.received_amount = flt(amount)
	payment.reference_no = reference_no or invoice.name
	payment.reference_date = reference_date or invoice.posting_date
	payment.posting_date = invoice.posting_date
	for row in payment.references or []:
		row.allocated_amount = flt(amount)
	payment.flags.ignore_permissions = True
	payment.insert(ignore_permissions=True)
	payment.submit()
	return payment


def post_visit_payments(visit, invoice):
	for row in visit.payments or []:
		if row.gift_card or not flt(row.amount):
			continue
		make_payment(
			invoice,
			row.mode_of_payment,
			row.amount,
			row.reference_no,
			row.reference_date or visit.posting_date,
		)


def post_gift_cards(visit, invoice):
	lines = [r for r in (visit.payments or []) if r.gift_card and flt(r.amount)]
	if not lines:
		return
	total = sum(flt(r.amount) for r in lines)
	journal = frappe.get_doc(
		{
			"doctype": "Journal Entry",
			"voucher_type": "Journal Entry",
			"company": visit.company,
			"posting_date": visit.posting_date,
			"user_remark": f"Gift card redemption on {visit.name}",
			"accounts": [
				{
					"account": settings().gift_card_liability_account,
					"debit_in_account_currency": total,
					"cost_center": visit.cost_center,
				},
				{
					"account": invoice.debit_to,
					"party_type": "Customer",
					"party": visit.customer,
					"credit_in_account_currency": total,
					"reference_type": "Sales Invoice",
					"reference_name": invoice.name,
					"cost_center": visit.cost_center,
				},
			],
		}
	)
	journal.flags.ignore_permissions = True
	journal.insert(ignore_permissions=True)
	journal.submit()
	visit.db_set("journal_entry", journal.name)
	for row in lines:
		move_gift_card(row.gift_card, -flt(row.amount), "Redeem", visit)


def move_gift_card(card_name, change, txn_type, visit):
	card = frappe.get_doc("Spa Gift Card", card_name, for_update=True)
	balance = flt(card.balance) + change
	if balance < 0:
		frappe.throw(f"Gift card {card.name} only has {card.balance} left.")
	row = card.append(
		"transactions",
		{
			"txn_date": nowdate(),
			"txn_type": txn_type,
			"amount": abs(change),
			"balance_after": balance,
			"visit": visit.name,
		},
	)
	row.db_insert()
	card.db_set({"balance": balance, "status": "Redeemed" if balance <= 0 else "Active"})


def reverse_gift_cards(visit):
	cancel_doc("Journal Entry", visit.journal_entry)
	if not visit.journal_entry:
		return
	for row in visit.payments or []:
		if row.gift_card and flt(row.amount):
			move_gift_card(row.gift_card, flt(row.amount), "Refund", visit)


def post_consumables(visit):
	rows = [r for r in (visit.consumables or []) if flt(r.qty)]
	if not rows:
		return

	def run():
		stock_entry = frappe.get_doc(
			{
				"doctype": "Stock Entry",
				"stock_entry_type": "Material Issue",
				"company": visit.company,
				"posting_date": visit.posting_date,
				"set_posting_time": 1,
				"from_warehouse": visit.warehouse,
				"remarks": f"Consumables for {visit.name}",
				"items": [
					{
						"item_code": r.item,
						"qty": flt(r.qty),
						"s_warehouse": r.warehouse or visit.warehouse,
						"uom": r.uom,
						"cost_center": visit.cost_center,
					}
					for r in rows
				],
			}
		)
		stock_entry.flags.ignore_permissions = True
		stock_entry.insert(ignore_permissions=True)
		stock_entry.submit()
		visit.db_set("stock_entry", stock_entry.name)

	guarded(f"Stock Entry {visit.name}", run)


def recount_package(name):
	package = frappe.get_doc("Spa Client Package", name, for_update=True)
	used = 0
	for row in package.items or []:
		spent = sum(
			cint(u.sessions) for u in (package.usage or []) if u.service == row.service and not u.reversed
		)
		if spent > cint(row.total_sessions):
			frappe.throw(f"{name} has no sessions left for {row.service}.")
		row.db_set({"used_sessions": spent, "balance_sessions": cint(row.total_sessions) - spent})
		used += spent
	total = cint(package.total_sessions)
	package.db_set(
		{
			"used_sessions": used,
			"balance_sessions": total - used,
			"status": "Exhausted" if used >= total else "Active",
		}
	)


def consume_prepaid(visit):
	for row in visit.services or []:
		if row.redeem_from == "Package":
			package = frappe.get_doc("Spa Client Package", row.client_package, for_update=True)
			usage = package.append(
				"usage",
				{
					"visit": visit.name,
					"visit_date": visit.posting_date,
					"service": row.service,
					"sessions": cint(row.qty),
					"staff": row.staff,
				},
			)
			usage.db_insert()
			recount_package(package.name)
		elif row.redeem_from == "Membership":
			entitlement = current_entitlement(row.membership, row.service, visit.posting_date)
			if not entitlement:
				frappe.throw(f"Row {row.idx}: no membership sessions left for {row.service} this period.")
			frappe.db.set_value(
				"Spa Membership Entitlement",
				entitlement.name,
				"sessions_used",
				cint(entitlement.sessions_used) + cint(row.qty),
			)


def restore_prepaid(visit):
	touched = set()
	for row in frappe.get_all(
		"Spa Client Package Usage", filters={"visit": visit.name, "reversed": 0}, fields=["name", "parent"]
	):
		frappe.db.set_value("Spa Client Package Usage", row.name, "reversed", 1)
		touched.add(row.parent)
	for name in touched:
		recount_package(name)
	for row in visit.services or []:
		if row.redeem_from == "Membership":
			entitlement = current_entitlement(row.membership, row.service, visit.posting_date)
			if entitlement:
				frappe.db.set_value(
					"Spa Membership Entitlement",
					entitlement.name,
					"sessions_used",
					max(cint(entitlement.sessions_used) - cint(row.qty), 0),
				)


def post_commissions(visit):
	def entry(staff, source, reference, base, rate, amount):
		frappe.get_doc(
			{
				"doctype": "Spa Commission Entry",
				"staff": staff,
				"branch": visit.branch,
				"visit": visit.name,
				"posting_date": visit.posting_date,
				"source_type": source,
				"reference_name": reference,
				"base_amount": base,
				"commission_rate": rate,
				"commission_amount": amount,
				"status": "Unpaid",
			}
		).insert(ignore_permissions=True)

	for row in visit.services or []:
		if row.staff:
			entry(
				row.staff,
				"Service",
				row.service,
				row.commission_base,
				row.commission_rate,
				row.commission_amount,
			)
	for row in visit.products or []:
		if row.sold_by:
			rate = frappe.get_cached_value("Spa Staff Profile", row.sold_by, "commission_rate")
			entry(row.sold_by, "Retail", row.item, row.amount, rate, row.commission_amount)
	if flt(visit.tip_amount) and visit.tip_staff:
		entry(visit.tip_staff, "Tip", "Tip", visit.tip_amount, 0, visit.tip_amount)


def update_after_visit(visit, sign):
	client = frappe.db.get_value(
		"Spa Client Profile", visit.client, ["visit_count", "total_spend"], as_dict=True, for_update=True
	)
	values = {
		"visit_count": max(cint(client.visit_count) + sign, 0),
		"total_spend": max(flt(client.total_spend) + sign * flt(visit.grand_total), 0),
		"loyalty_points": points_balance(visit.customer),
	}
	if sign > 0:
		values["last_visit_date"] = visit.posting_date
	else:
		rows = frappe.get_all(
			"Spa Visit",
			filters={"client": visit.client, "docstatus": 1, "name": ("!=", visit.name)},
			fields=["posting_date"],
			order_by="posting_date desc",
			limit=1,
		)
		values["last_visit_date"] = rows[0].posting_date if rows else None
	frappe.db.set_value("Spa Client Profile", visit.client, values)
	if visit.appointment:
		frappe.db.set_value(
			"Spa Appointment", visit.appointment, "status", "Completed" if sign > 0 else "Checked In"
		)
	if visit.promotion:
		used = cint(frappe.db.get_value("Spa Promotion", visit.promotion, "used_count", for_update=True))
		frappe.db.set_value("Spa Promotion", visit.promotion, "used_count", max(used + sign, 0))


def cancel_doc(doctype, name):
	if not name:
		return
	doc = frappe.get_doc(doctype, name)
	if doc.docstatus == 1:
		doc.flags.ignore_links = True
		doc.flags.ignore_permissions = True
		doc.cancel()


def cancel_payments(invoice):
	if not invoice:
		return
	names = frappe.get_all(
		"Payment Entry Reference",
		filters={"reference_doctype": "Sales Invoice", "reference_name": invoice, "docstatus": 1},
		pluck="parent",
	)
	for name in set(names):
		cancel_doc("Payment Entry", name)


def post_sale_invoice(doc, *, item, amount, paid, mode, date, taxed=True, income_account=None, customer=None):
	"""18.7. Prices of packages and memberships are GST-inclusive, so the invoice equals the price."""
	branch = frappe.get_cached_value("Spa Branch", doc.branch, ["company", "cost_center"], as_dict=True)
	item_row = {"item_code": item, "qty": 1, "rate": flt(amount), "cost_center": branch.cost_center}
	if income_account:
		item_row["income_account"] = income_account
	template = settings().tax_template
	invoice = create_invoice(
		{
			"customer": customer or doc.customer,
			"company": branch.company,
			"cost_center": branch.cost_center,
			"posting_date": date,
			"due_date": date,
			"items": [item_row],
			"taxes": tax_rows(template, branch.cost_center, inclusive=True) if taxed and template else [],
			"remarks": f"{doc.doctype} {doc.name}",
		}
	)
	doc.db_set("sales_invoice", invoice.name)
	if flt(paid):
		make_payment(invoice, mode, paid, reference_date=date)


def cancel_sale(doc):
	cancel_payments(doc.sales_invoice)
	cancel_doc("Sales Invoice", doc.sales_invoice)


def post_payout(payout):
	"""Commission is expensed when paid out. Tips went to the payable account on the invoice, so they
	stay out of this entry and the payable balance still ends up equal to the payout's net_payable."""
	tips = sum(
		flt(frappe.db.get_value("Spa Commission Entry", r.commission_entry, "commission_amount"))
		for r in payout.entries
		if frappe.db.get_value("Spa Commission Entry", r.commission_entry, "source_type") == "Tip"
	)
	amount = flt(flt(payout.total_commission) - tips - flt(payout.deductions), 2)
	if not amount:
		return
	# Deductions larger than the commission eat into tips: the entry flips and takes the difference
	# back out of the payable, so the balance still equals net_payable.
	debit, credit = settings().commission_expense_account, settings().commission_payable_account
	if amount < 0:
		debit, credit = credit, debit
	cost_center = (
		frappe.get_cached_value("Spa Branch", payout.branch, "cost_center")
		if payout.branch
		else frappe.db.get_value("Company", payout.company, "cost_center")
	)
	journal = frappe.get_doc(
		{
			"doctype": "Journal Entry",
			"voucher_type": "Journal Entry",
			"company": payout.company,
			"posting_date": payout.posting_date,
			"user_remark": f"Commission payout {payout.name}",
			"accounts": [
				{
					"account": debit,
					"debit_in_account_currency": abs(amount),
					"cost_center": cost_center,
				},
				{
					"account": credit,
					"credit_in_account_currency": abs(amount),
					"cost_center": cost_center,
				},
			],
		}
	)
	journal.flags.ignore_permissions = True
	journal.insert(ignore_permissions=True)
	journal.submit()
	payout.db_set("journal_entry", journal.name)
