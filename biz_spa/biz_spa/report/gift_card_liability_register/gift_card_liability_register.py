import frappe

from biz_spa.report_helpers import col


def execute(filters=None):
	f = filters or {}
	cond = "".join(
		[
			" AND branch = %(branch)s" if f.get("branch") else "",
			" AND status = %(status)s" if f.get("status") else "",
			" AND expiry_date >= %(expiry_from)s" if f.get("expiry_from") else "",
			" AND expiry_date <= %(expiry_to)s" if f.get("expiry_to") else "",
		]
	)
	columns = [
		col("Gift Card", "name", "Link", "Spa Gift Card", 160),
		col("Code", "card_code", width=140),
		col("Recipient", "recipient_name", width=150),
		col("Issued", "issue_date", "Date", width=110),
		col("Expiry", "expiry_date", "Date", width=110),
		col("Status", "status", width=90),
		col("Initial Value", "initial_value", "Currency"),
		col("Balance (Liability)", "balance", "Currency", width=140),
	]
	data = frappe.db.sql(
		f"""SELECT name, card_code, recipient_name, issue_date, expiry_date, status, initial_value, balance FROM `tabSpa Gift Card` WHERE docstatus = 1 {cond} ORDER BY expiry_date""",
		f,
		as_dict=True,
	)
	return columns, data
