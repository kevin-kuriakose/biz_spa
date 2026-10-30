// Adds body.biz-spa on Biz Spa routes only; the theme in biz_spa.css is scoped to that class.
frappe.provide("biz_spa");

biz_spa.REPORTS = [
	"Daily Sales Summary", "Staff Utilization", "Staff Performance", "Commission Statement",
	"Service Revenue and Popularity", "Lapsed Clients", "No-Show and Cancellation Analysis",
	"Package Balance and Liability", "Gift Card Liability Register", "Membership Renewals Due",
	"Consumable Usage", "Room Utilization", "Cash Close Variance",
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
	document.body.classList.toggle("biz-spa-workspace", (frappe.get_route() || [])[0] === "Workspaces" && biz_spa.is_spa_route());
};

$(document).on("page-change", () => biz_spa.apply_theme());
frappe.router && frappe.router.on("change", () => biz_spa.apply_theme());
$(() => biz_spa.apply_theme());

// Lucide icons on workspace cards, per the design system's icon + title pattern (20px, 16px gap).
biz_spa.CARD_ICONS = {
	"Front Desk": "calendar-days", Billing: "receipt-text", Prepaid: "wallet", Staff: "users",
	Services: "flower-2", Quality: "star", Setup: "settings", Reports: "chart-column",
	"My Day": "calendar-days", "My Work": "clipboard-list", "My Pay and Leave": "wallet",
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
