import frappe

from biz_spa.report_helpers import col


def execute(filters=None):
	f = filters or {}
	cond = "".join(
		[
			" AND staff = %(staff)s" if f.get("staff") else "",
			" AND status = %(status)s" if f.get("status") else "",
		]
	)
	columns = [
		col("Date", "posting_date", "Date", width=110),
		col("Entry", "name", "Link", "Spa Commission Entry", 170),
		col("Staff", "staff", "Link", "Spa Staff Profile"),
		col("Visit", "visit", "Link", "Spa Visit", 170),
		col("Source", "source_type", width=90),
		col("Reference", "reference_name", width=170),
		col("Base", "base_amount", "Currency"),
		col("Rate", "commission_rate", "Float", width=80),
		col("Commission", "commission_amount", "Currency"),
		col("Status", "status", width=90),
		col("Payout", "payout", "Link", "Spa Commission Payout", 170),
	]
	data = frappe.db.sql(
		f"""SELECT name, posting_date, staff, visit, source_type, reference_name, base_amount, commission_rate, commission_amount, status, payout
		FROM `tabSpa Commission Entry` WHERE docstatus < 2 AND posting_date BETWEEN %(from_date)s AND %(to_date)s {cond} ORDER BY posting_date DESC""",
		f,
		as_dict=True,
	)
	return columns, data
