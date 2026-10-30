import frappe
from frappe.utils import add_days, cint, flt, getdate, nowdate

from biz_spa.report_helpers import branch_open_minutes, col, shift_minutes


def execute(filters=None):
	f = filters or {}
	cond = "AND branch = %(branch)s" if f.get("branch") else ""
	columns = [col("Date", "posting_date", "Date", width=110), col("Branch", "branch", "Link", "Spa Branch"), col("Visits", "visits", "Int", width=80), col("Services", "services", "Currency"), col("Products", "products", "Currency"), col("Discount", "discount", "Currency"), col("Tax", "tax", "Currency"), col("Tips", "tips", "Currency"), col("Grand Total", "grand_total", "Currency"), col("Prepaid Redeemed", "prepaid", "Currency", width=140), col("Gift Cards", "gift", "Currency"), col("Collected", "collected", "Currency")]
	data = frappe.db.sql(f"""SELECT posting_date, branch, COUNT(*) visits, SUM(total_services) services, SUM(total_products) products, SUM(discount_amount) discount, SUM(tax_amount) tax, SUM(tip_amount) tips, SUM(grand_total) grand_total, SUM(package_redeemed_value) prepaid, SUM(gift_card_redeemed) gift, SUM(paid_amount) collected
		FROM `tabSpa Visit` WHERE docstatus = 1 AND posting_date BETWEEN %(from_date)s AND %(to_date)s {cond}
		GROUP BY posting_date, branch ORDER BY posting_date DESC, branch""", f, as_dict=True)
	return columns, data
