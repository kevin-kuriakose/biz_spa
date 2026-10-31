import frappe
from frappe.utils import flt

from biz_spa.report_helpers import col


def execute(filters=None):
	f = filters or {}
	cond = "".join(
		[
			" AND v.branch = %(branch)s" if f.get("branch") else "",
			" AND l.staff = %(staff)s" if f.get("staff") else "",
		]
	)
	columns = [
		col("Staff", "staff", "Link", "Spa Staff Profile"),
		col("Name", "staff_name", width=160),
		col("Services", "services", "Int", width=90),
		col("Service Revenue", "revenue", "Currency"),
		col("Retail Sales", "retail", "Currency"),
		col("Commission", "commission", "Currency"),
		col("Avg Rating", "rating", "Float", width=100),
	]
	rows = frappe.db.sql(
		f"""SELECT l.staff, s.staff_name, COUNT(*) services, SUM(l.amount) revenue, SUM(l.commission_amount) commission
		FROM `tabSpa Visit Service` l JOIN `tabSpa Visit` v ON v.name = l.parent JOIN `tabSpa Staff Profile` s ON s.name = l.staff
		WHERE v.docstatus = 1 AND v.posting_date BETWEEN %(from_date)s AND %(to_date)s {cond} GROUP BY l.staff, s.staff_name""",
		f,
		as_dict=True,
	)
	for row in rows:
		retail = frappe.db.sql(
			"""SELECT SUM(p.amount), SUM(p.commission_amount) FROM `tabSpa Visit Product` p JOIN `tabSpa Visit` v ON v.name = p.parent
			WHERE v.docstatus = 1 AND p.sold_by = %s AND v.posting_date BETWEEN %s AND %s""",
			(row.staff, f["from_date"], f["to_date"]),
		)[0]
		row.retail = flt(retail[0])
		row.commission = flt(row.commission) + flt(retail[1])
		rating = frappe.db.sql(
			"""SELECT AVG(CAST(fb.staff_rating AS UNSIGNED)) FROM `tabSpa Feedback` fb JOIN `tabSpa Visit` v ON v.name = fb.visit
			WHERE fb.staff = %s AND IFNULL(fb.staff_rating, '') != '' AND v.posting_date BETWEEN %s AND %s""",
			(row.staff, f["from_date"], f["to_date"]),
		)[0][0]
		row.rating = flt(rating, 1)
	return columns, sorted(rows, key=lambda r: -flt(r.revenue))
