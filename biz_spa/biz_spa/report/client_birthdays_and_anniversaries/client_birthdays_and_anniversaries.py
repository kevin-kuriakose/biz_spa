import frappe
from frappe.utils import add_days, cint, flt, getdate, nowdate

from biz_spa.report_helpers import branch_open_minutes, col, shift_minutes


def execute(filters=None):
	f = filters or {}
	cond = "AND preferred_branch = %(branch)s" if f.get("branch") else ""
	columns = [col("Client", "name", "Link", "Spa Client Profile", 150), col("Name", "client_name", width=170), col("Occasion", "occasion", width=110), col("Date", "occasion_date", "Date", width=110), col("Mobile", "mobile"), col("Marketing Consent", "marketing_consent", "Check", width=140), col("Preferred Branch", "preferred_branch", "Link", "Spa Branch")]
	data = []
	for field, label in (("date_of_birth", "Birthday"), ("anniversary_date", "Anniversary")):
		data += frappe.db.sql(f"""SELECT name, client_name, '{label}' occasion, {field} occasion_date, mobile, marketing_consent, preferred_branch
			FROM `tabSpa Client Profile` WHERE docstatus < 2 AND MONTH({field}) = %(month)s {cond}""", f, as_dict=True)
	return columns, sorted(data, key=lambda r: getdate(r.occasion_date).day)
