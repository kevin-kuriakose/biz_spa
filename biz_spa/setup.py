import frappe

# Backstops under the row locks in posting.py: a path that forgets the lock fails instead of
# overspending. Frappe's schema sync leaves these alone.
CHECKS = (
	("Spa Gift Card", "spa_gift_card_balance", "balance >= 0"),
	("Spa Client Package", "spa_package_balance", "balance_sessions >= 0"),
	("Spa Client Package Item", "spa_package_item_balance", "balance_sessions >= 0"),
	("Spa Membership Entitlement", "spa_entitlement_used", "sessions_used <= sessions_allowed"),
	("Spa Promotion", "spa_promotion_used", "max_uses = 0 OR used_count <= max_uses"),
)


def ensure_customer_role():
	"""Spa Customer has no DocPerms on purpose: customers only reach data through biz_spa.api.customer."""
	if not frappe.db.exists("Role", "Spa Customer"):
		frappe.get_doc({"doctype": "Role", "role_name": "Spa Customer", "desk_access": 0}).insert(
			ignore_permissions=True
		)


def ensure_balance_checks():
	for doctype, name, rule in CHECKS:
		frappe.db.sql_ddl(f"ALTER TABLE `tab{doctype}` ADD CONSTRAINT IF NOT EXISTS `{name}` CHECK ({rule})")
