from frappe.model.document import Document

from biz_spa.utils import ensure_item


class SpaPackage(Document):
	def after_insert(self):
		ensure_item(self)
