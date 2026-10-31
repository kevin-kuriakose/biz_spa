// Adds body.biz-spa on Biz Spa routes only; the theme in biz_spa.css is scoped to that class.
frappe.provide("biz_spa");

biz_spa.REPORTS = [
	"Daily Sales Summary",
	"Staff Utilization",
	"Staff Performance",
	"Commission Statement",
	"Service Revenue and Popularity",
	"Lapsed Clients",
	"No-Show and Cancellation Analysis",
	"Package Balance and Liability",
	"Gift Card Liability Register",
	"Membership Renewals Due",
	"Consumable Usage",
	"Room Utilization",
	"Cash Close Variance",
	"Client Birthdays and Anniversaries",
];

biz_spa.is_spa_route = function () {
	const route = frappe.get_route() || [];
	const [view, target] = route;
	if (!view) return false;
	if (view === "Workspaces") return route.includes("Biz Spa") || route.includes("My Spa");
	if (view === "query-report") return biz_spa.REPORTS.includes(target);
	return ["Form", "List", "Tree"].includes(view) && String(target || "").startsWith("Spa ");
};

biz_spa.apply_theme = function () {
	document.body.classList.toggle("biz-spa", biz_spa.is_spa_route());
	document.body.classList.toggle(
		"biz-spa-workspace",
		(frappe.get_route() || [])[0] === "Workspaces" && biz_spa.is_spa_route()
	);
};

$(document).on("page-change", () => biz_spa.apply_theme());
frappe.router && frappe.router.on("change", () => biz_spa.apply_theme());
$(() => biz_spa.apply_theme());

// Lucide icons on workspace cards, per the design system's icon + title pattern (20px, 16px gap).
biz_spa.CARD_ICONS = {
	"Front Desk": "calendar-days",
	Billing: "receipt-text",
	Prepaid: "wallet",
	Staff: "users",
	Services: "flower-2",
	Quality: "star",
	Setup: "settings",
	Reports: "chart-column",
	"My Day": "calendar-days",
	"My Work": "clipboard-list",
	"My Pay and Leave": "wallet",
};

biz_spa.decorate_cards = function () {
	if (!document.body.classList.contains("biz-spa")) return;
	document.querySelectorAll(".links-widget-box .widget-title").forEach((title) => {
		if (title.querySelector(".spa-card-icon")) return;
		const icon = biz_spa.CARD_ICONS[title.textContent.trim()];
		if (icon) {
			title.insertAdjacentHTML(
				"afterbegin",
				`<svg class="spa-card-icon" aria-hidden="true"><use href="#icon-spa-${icon}"></use></svg>`
			);
		}
	});
};

new MutationObserver(() => biz_spa.decorate_cards()).observe(document.documentElement, {
	childList: true,
	subtree: true,
});

// Spa staff are sent home from any Desk page they cannot open, such as a route left over from
// another login, instead of seeing the raw permission error. System Managers are unaffected.
// Wrapped at load time because Desk renders the first route before document ready.
biz_spa.user_roles = () => (frappe.boot && frappe.boot.user && frappe.boot.user.roles) || [];

biz_spa.is_staff_only = function () {
	const roles = biz_spa.user_roles();
	return roles.some((role) => role.startsWith("Spa ")) && !roles.includes("System Manager");
};

biz_spa.can_open_page = function (name) {
	return (
		!name ||
		frappe.standard_pages[name] ||
		(frappe.boot.page_info && frappe.boot.page_info[name])
	);
};

biz_spa.go_home = function () {
	frappe.show_alert({
		message: __("That page isn't available for your role."),
		indicator: "orange",
	});
	frappe.set_route(
		"Workspaces",
		biz_spa.user_roles().includes("Spa Therapist") ? "My Spa" : "Biz Spa"
	);
};

if (frappe.views && frappe.views.pageview) {
	const show_page = frappe.views.pageview.show;
	frappe.views.pageview.show = function (name) {
		if (biz_spa.is_staff_only() && !biz_spa.can_open_page(name)) {
			biz_spa.go_home();
			return;
		}
		return show_page.call(this, name);
	};
}
