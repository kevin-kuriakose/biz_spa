app_name = "biz_spa"
app_title = "Biz Spa"
app_publisher = "Kevin Kuriakose"
app_description = "Appointments, billing, prepaid value and staff commission for a spa and salon, posting into ERPNext"
app_email = "gps.tech@bizaxl.com"
app_license = "mit"

# Apps
# ------------------

required_apps = ["frappe", "erpnext"]

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "biz_spa",
# 		"logo": "/assets/biz_spa/logo.png",
# 		"title": "Biz Spa",
# 		"route": "/biz_spa",
# 		"has_permission": "biz_spa.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/biz_spa/css/biz_spa.css"
# app_include_js = "/assets/biz_spa/js/biz_spa.js"

# include js, css files in header of web template
# web_include_css = "/assets/biz_spa/css/biz_spa.css"
# web_include_js = "/assets/biz_spa/js/biz_spa.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "biz_spa/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "biz_spa/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "biz_spa.utils.jinja_methods",
# 	"filters": "biz_spa.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "biz_spa.install.before_install"
# after_install = "biz_spa.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "biz_spa.uninstall.before_uninstall"
# after_uninstall = "biz_spa.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "biz_spa.utils.before_app_install"
# after_app_install = "biz_spa.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "biz_spa.utils.before_app_uninstall"
# after_app_uninstall = "biz_spa.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "biz_spa.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"biz_spa.tasks.all"
# 	],
# 	"daily": [
# 		"biz_spa.tasks.daily"
# 	],
# 	"hourly": [
# 		"biz_spa.tasks.hourly"
# 	],
# 	"weekly": [
# 		"biz_spa.tasks.weekly"
# 	],
# 	"monthly": [
# 		"biz_spa.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "biz_spa.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "biz_spa.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "biz_spa.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["biz_spa.utils.before_request"]
# after_request = ["biz_spa.utils.after_request"]

# Job Events
# ----------
# before_job = ["biz_spa.utils.before_job"]
# after_job = ["biz_spa.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"biz_spa.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []

override_doctype_class = {
	"Spa Cash Close Line": "biz_spa.biz_spa.doctype.spa_cash_close_line.spa_cash_close_line.SpaCashCloseLine",
	"Spa Cash Close": "biz_spa.biz_spa.doctype.spa_cash_close.spa_cash_close.SpaCashClose",
	"Spa Commission Payout Line": "biz_spa.biz_spa.doctype.spa_commission_payout_line.spa_commission_payout_line.SpaCommissionPayoutLine",
	"Spa Commission Payout": "biz_spa.biz_spa.doctype.spa_commission_payout.spa_commission_payout.SpaCommissionPayout",
	"Spa Commission Entry": "biz_spa.biz_spa.doctype.spa_commission_entry.spa_commission_entry.SpaCommissionEntry",
	"Spa Gift Card Transaction": "biz_spa.biz_spa.doctype.spa_gift_card_transaction.spa_gift_card_transaction.SpaGiftCardTransaction",
	"Spa Gift Card": "biz_spa.biz_spa.doctype.spa_gift_card.spa_gift_card.SpaGiftCard",
	"Spa Membership Entitlement": "biz_spa.biz_spa.doctype.spa_membership_entitlement.spa_membership_entitlement.SpaMembershipEntitlement",
	"Spa Membership": "biz_spa.biz_spa.doctype.spa_membership.spa_membership.SpaMembership",
	"Spa Client Package Usage": "biz_spa.biz_spa.doctype.spa_client_package_usage.spa_client_package_usage.SpaClientPackageUsage",
	"Spa Client Package Item": "biz_spa.biz_spa.doctype.spa_client_package_item.spa_client_package_item.SpaClientPackageItem",
	"Spa Client Package": "biz_spa.biz_spa.doctype.spa_client_package.spa_client_package.SpaClientPackage",
	"Spa Visit Payment": "biz_spa.biz_spa.doctype.spa_visit_payment.spa_visit_payment.SpaVisitPayment",
	"Spa Visit Consumable": "biz_spa.biz_spa.doctype.spa_visit_consumable.spa_visit_consumable.SpaVisitConsumable",
	"Spa Visit Product": "biz_spa.biz_spa.doctype.spa_visit_product.spa_visit_product.SpaVisitProduct",
	"Spa Visit Service": "biz_spa.biz_spa.doctype.spa_visit_service.spa_visit_service.SpaVisitService",
	"Spa Visit": "biz_spa.biz_spa.doctype.spa_visit.spa_visit.SpaVisit",
	"Spa Waitlist Entry": "biz_spa.biz_spa.doctype.spa_waitlist_entry.spa_waitlist_entry.SpaWaitlistEntry",
	"Spa Staff Time Off": "biz_spa.biz_spa.doctype.spa_staff_time_off.spa_staff_time_off.SpaStaffTimeOff",
	"Spa Appointment Service": "biz_spa.biz_spa.doctype.spa_appointment_service.spa_appointment_service.SpaAppointmentService",
	"Spa Appointment": "biz_spa.biz_spa.doctype.spa_appointment.spa_appointment.SpaAppointment",
	"Spa Consultation": "biz_spa.biz_spa.doctype.spa_consultation.spa_consultation.SpaConsultation",
	"Spa Client Profile": "biz_spa.biz_spa.doctype.spa_client_profile.spa_client_profile.SpaClientProfile",
	"Spa Consent Template": "biz_spa.biz_spa.doctype.spa_consent_template.spa_consent_template.SpaConsentTemplate",
	"Spa Promotion Service": "biz_spa.biz_spa.doctype.spa_promotion_service.spa_promotion_service.SpaPromotionService",
	"Spa Promotion": "biz_spa.biz_spa.doctype.spa_promotion.spa_promotion.SpaPromotion",
	"Spa Membership Plan Benefit": "biz_spa.biz_spa.doctype.spa_membership_plan_benefit.spa_membership_plan_benefit.SpaMembershipPlanBenefit",
	"Spa Membership Plan": "biz_spa.biz_spa.doctype.spa_membership_plan.spa_membership_plan.SpaMembershipPlan",
	"Spa Package Item": "biz_spa.biz_spa.doctype.spa_package_item.spa_package_item.SpaPackageItem",
	"Spa Package": "biz_spa.biz_spa.doctype.spa_package.spa_package.SpaPackage",
	"Spa Staff Shift": "biz_spa.biz_spa.doctype.spa_staff_shift.spa_staff_shift.SpaStaffShift",
	"Spa Staff Skill": "biz_spa.biz_spa.doctype.spa_staff_skill.spa_staff_skill.SpaStaffSkill",
	"Spa Staff Profile": "biz_spa.biz_spa.doctype.spa_staff_profile.spa_staff_profile.SpaStaffProfile",
	"Spa Service Consumable": "biz_spa.biz_spa.doctype.spa_service_consumable.spa_service_consumable.SpaServiceConsumable",
	"Spa Service": "biz_spa.biz_spa.doctype.spa_service.spa_service.SpaService",
	"Spa Service Category": "biz_spa.biz_spa.doctype.spa_service_category.spa_service_category.SpaServiceCategory",
	"Spa Room": "biz_spa.biz_spa.doctype.spa_room.spa_room.SpaRoom",
	"Spa Branch Hours": "biz_spa.biz_spa.doctype.spa_branch_hours.spa_branch_hours.SpaBranchHours",
	"Spa Branch": "biz_spa.biz_spa.doctype.spa_branch.spa_branch.SpaBranch",
	"Spa Settings": "biz_spa.biz_spa.doctype.spa_settings.spa_settings.SpaSettings",
}

app_include_css = "/assets/biz_spa/css/biz_spa.css"
app_include_js = "/assets/biz_spa/js/biz_spa.js"
app_include_icons = ["biz_spa/icons/biz_spa_lucide.svg"]

scheduler_events = {
	"hourly": ["biz_spa.tasks.hourly_appointments"],
	"daily": [
		"biz_spa.tasks.daily_housekeeping",
		"biz_spa.tasks.daily_greetings",
	],
}

after_install = "biz_spa.setup.ensure_customer_role"
after_migrate = "biz_spa.setup.ensure_customer_role"
doc_events = {
	"User": {"before_validate": "biz_spa.permissions.apply_staff_access"},
}

permission_query_conditions = {
	"Spa Appointment": "biz_spa.permissions.appointment_query",
	"Spa Waitlist Entry": "biz_spa.permissions.waitlist_query",
	"Spa Client Profile": "biz_spa.permissions.client_query",
	"Spa Consultation": "biz_spa.permissions.consultation_query",
	"Spa Commission Entry": "biz_spa.permissions.commission_query",
	"Spa Feedback": "biz_spa.permissions.feedback_query",
	"Spa Color Formula": "biz_spa.permissions.color_formula_query",
	"Spa Incident Report": "biz_spa.permissions.incident_query",
	"User": "biz_spa.permissions.user_query",
}

has_permission = {
	"Spa Appointment": "biz_spa.permissions.appointment_access",
	"Spa Waitlist Entry": "biz_spa.permissions.waitlist_access",
	"Spa Client Profile": "biz_spa.permissions.client_access",
	"Spa Consultation": "biz_spa.permissions.consultation_access",
	"Spa Commission Entry": "biz_spa.permissions.commission_access",
	"Spa Feedback": "biz_spa.permissions.feedback_access",
	"Spa Color Formula": "biz_spa.permissions.color_formula_access",
	"Spa Incident Report": "biz_spa.permissions.incident_access",
}
