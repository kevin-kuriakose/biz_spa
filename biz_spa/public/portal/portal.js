// Biz Spa portal: a standalone single-page app over Frappe's API. Permissions are enforced by the
// server; the menu only reflects them.
(() => {
	const app = document.getElementById("app");
	const state = { boot: null, metas: {} };
	const API = "/api/method/";
	const BIZ = "biz_spa.api.portal.";

	const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
	const icon = (name, cls = "") => `<svg class="icon ${cls}" aria-hidden="true"><use href="#icon-spa-${name}"></use></svg>`;
	const money = (v) => new Intl.NumberFormat("en-IN", { style: "currency", currency: state.boot?.currency || "INR" }).format(Number(v || 0));
	const today = () => new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10);
	const fmtDate = (v) => (v ? String(v).slice(0, 10).split("-").reverse().join("-") : "");
	const clock = (m) => `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
	const go = (hash) => { location.hash = hash; };
	const slug = (d) => encodeURIComponent(d);

	function toast(message, error = false) {
		const el = document.createElement("div");
		el.className = `toast${error ? " error" : ""}`;
		el.textContent = message;
		document.getElementById("toasts").append(el);
		setTimeout(() => el.remove(), error ? 7000 : 3500);
	}

	function serverMessage(body) {
		try {
			if (body._server_messages) {
				const list = JSON.parse(body._server_messages).map((m) => JSON.parse(m).message);
				return list.join(" ").replace(/<[^>]+>/g, "");
			}
		} catch (e) { /* fall through to the generic text */ }
		return body.message || body.exception || "Something went wrong.";
	}

	async function call(method, args = {}, { post = false } = {}) {
		const headers = { Accept: "application/json", "X-Frappe-CSRF-Token": window.PORTAL.csrf || "fetch" };
		let url = API + method;
		const options = { headers, credentials: "same-origin" };
		if (post) {
			options.method = "POST";
			headers["Content-Type"] = "application/json";
			options.body = JSON.stringify(args);
		} else {
			const query = new URLSearchParams();
			Object.entries(args).forEach(([k, v]) => { if (v !== undefined && v !== null && v !== "") query.set(k, typeof v === "object" ? JSON.stringify(v) : v); });
			url += `?${query}`;
		}
		const response = await fetch(url, options);
		const body = await response.json().catch(() => ({}));
		if (response.status === 401 || (response.status === 403 && body.exc_type === "SessionExpired")) { location.href = "/portal"; throw new Error("Session expired"); }
		if (!response.ok) throw new Error(serverMessage(body));
		return body.message;
	}
	const guard = async (fn) => { try { return await fn(); } catch (e) { toast(e.message, true); return undefined; } };

	async function loadSprite() {
		const svg = await (await fetch("/assets/biz_spa/icons/biz_spa_lucide.svg")).text();
		document.getElementById("sprite").innerHTML = svg;
	}

	/* Login */
	function renderLogin(mode = "login") {
		app.innerHTML = `<div class="login">
			<section class="login-brand">
				<div class="wordmark">Bizaxl</div>
				<div><h1>Run your spa from one calm place.</h1>
					<p>Appointments, billing, prepaid value and staff commission, all in the Biz Spa portal.</p>
					<div class="feature">${icon("check", "sm")}Today's schedule at a glance</div>
					<div class="feature">${icon("check", "sm")}Billing that posts straight to your books</div>
					<div class="feature">${icon("check", "sm")}Each role sees only what it needs</div>
				</div><div class="small muted">Biz Spa Portal</div>
			</section>
			<section class="login-panel"><form class="login-card" id="login-form">
				<h2>${mode === "login" ? "Welcome back" : "Reset your password"}</h2>
				<p class="muted" style="margin-bottom:24px">${mode === "login" ? "Sign in to your Biz Spa portal." : "We'll email you a reset link."}</p>
				<div id="login-error"></div>
				<label class="field"><span class="field-label">Email</span><input id="email" type="email" autocomplete="username" required></label>
				${mode === "login" ? `<label class="field"><span class="field-label">Password</span><input id="password" type="password" autocomplete="current-password" required></label>` : ""}
				<button class="btn btn-primary" type="submit">${mode === "login" ? "Sign in" : "Send reset link"}</button>
				<p style="margin-top:16px;text-align:center"><button type="button" class="link-btn" id="switch">${mode === "login" ? "Forgot password?" : "Back to sign in"}</button></p>
			</form></section></div>`;
		document.getElementById("switch").onclick = () => renderLogin(mode === "login" ? "reset" : "login");
		document.getElementById("login-form").onsubmit = async (event) => {
			event.preventDefault();
			const button = event.target.querySelector(".btn");
			const usr = document.getElementById("email").value.trim();
			const showError = (text) => { document.getElementById("login-error").innerHTML = `<div class="alert">${esc(text)}</div>`; };
			button.disabled = true;
			try {
				if (mode === "reset") {
					const body = new URLSearchParams({ cmd: "frappe.core.doctype.user.user.reset_password", user: usr });
					await fetch("/", { method: "POST", body, headers: { Accept: "application/json" } });
					toast("If that account exists, a reset link is on its way.");
					renderLogin();
					return;
				}
				const body = new URLSearchParams({ usr, pwd: document.getElementById("password").value });
				const response = await fetch(`${API}login`, { method: "POST", body, headers: { Accept: "application/json" } });
				if (!response.ok) { showError("That email or password isn't right."); button.disabled = false; return; }
				location.href = "/portal";
			} catch (e) {
				showError("We couldn't reach the server. Please try again.");
				button.disabled = false;
			}
		};
	}

	/* Shell */
	function renderShell() {
		const b = state.boot;
		const nav = (hash, label, ic) => `<a class="nav-item" href="#${hash}" data-nav="${esc(hash)}">${icon(ic)}${esc(label)}</a>`;
		let links = nav("/dashboard", "Dashboard", "chart-column") + nav("/schedule", b.is_therapist ? "My Schedule" : "Schedule", "calendar-days");
		if (b.can_book) links += nav("/book", "New Booking", "sparkles");
		b.menu.forEach((section) => {
			links += `<div class="nav-group">${esc(section.title)}</div>`;
			section.items.forEach((i) => {
				const target = i.doctype === "Spa Settings" ? `/form/${slug(i.doctype)}/${slug(i.doctype)}` : `/list/${slug(i.doctype)}`;
				links += nav(target, i.label, i.icon);
			});
		});
		if (b.reports.length) links += `<div class="nav-group">Insights</div>${nav("/reports", "Reports", "chart-column")}`;
		const initials = (b.full_name || b.user).split(" ").map((w) => w[0]).slice(0, 2).join("").toUpperCase();
		app.innerHTML = `<div class="shell">
			<aside class="side" id="side"><div class="wordmark">Bizaxl</div><nav>${links}</nav>
				<div class="side-foot">${b.has_desk ? `<a class="nav-item" href="/app">${icon("settings")}Admin Desk</a>` : ""}
				<button class="nav-item" id="logout">${icon("door-open")}Sign out</button></div></aside>
			<div class="main"><header class="topbar">
				<button class="icon-btn menu-btn" id="menu" aria-label="Open menu">${icon("clipboard-list")}</button>
				<span class="muted">Biz Spa</span>
				<div class="who"><span>${esc(b.full_name)}</span><span class="avatar">${esc(initials)}</span></div>
			</header><main class="content" id="view"></main></div></div>`;
		document.getElementById("logout").onclick = async () => { await guard(() => call("logout", {}, { post: true })); location.href = "/portal"; };
		document.getElementById("menu").onclick = () => document.getElementById("side").classList.toggle("open");
	}

	function view(html) {
		const el = document.getElementById("view");
		el.innerHTML = html;
		return el;
	}
	const pageHead = (title, actions = "") => `<div class="page-head"><h1>${esc(title)}</h1><div class="actions">${actions}</div></div>`;

	const statusColor = (s) => ({ Completed: "green", Active: "green", Paid: "green", Closed: "green", Approved: "green", Submitted: "green", Actioned: "green", Reviewed: "green", Booked: "green",
		Scheduled: "blue", Confirmed: "blue", Open: "blue", New: "blue", Waiting: "blue", Offered: "blue",
		"Checked In": "amber", "In Progress": "amber", Pending: "amber", Unpaid: "amber", Draft: "amber", "Under Review": "amber", Paused: "amber",
		Cancelled: "red", "No Show": "red", Expired: "red", Rejected: "red", Exhausted: "red", Redeemed: "" }[s] || "");
	const badge = (s) => (s ? `<span class="badge ${statusColor(s)}">${esc(s)}</span>` : "");

	/* Dashboard */
	async function dashboard() {
		view(`${pageHead(`Hello, ${esc((state.boot.full_name || "").split(" ")[0])}`)}<div class="empty">Loading…</div>`);
		const d = await guard(() => call(`${BIZ}dashboard`));
		if (!d) return;
		const cards = d.cards.map((c) => `<div class="card stat"><div class="stat-top"><span>${esc(c.label)}</span>${icon(c.icon)}</div><div class="stat-value">${c.money ? money(c.value) : esc(c.value)}</div></div>`).join("");
		const rows = d.lines.map((l) => `<tr class="row-link" data-go="/form/Spa%20Appointment/${slug(l.appointment)}"><td>${clock(l.start)}</td><td>${esc(l.client_name)}</td><td>${esc(l.service)}</td>${state.boot.is_therapist ? "" : `<td>${esc(l.staff_name || "")}</td>`}<td>${badge(l.status)}</td></tr>`).join("");
		const el = view(`${pageHead(`Hello, ${(state.boot.full_name || "").split(" ")[0]}`, state.boot.can_book ? `<a class="btn btn-primary" href="#/book">New Booking</a>` : "")}
			<div class="grid stats">${cards}</div>
			<div class="card"><h2 style="margin-bottom:16px">Today</h2>${rows ? `<div class="table-wrap"><table><thead><tr><th>Time</th><th>Client</th><th>Service</th>${state.boot.is_therapist ? "" : "<th>Staff</th>"}<th>Status</th></tr></thead><tbody>${rows}</tbody></table></div>` : `<div class="empty">Nothing booked today.</div>`}</div>`);
		rowLinks(el);
	}
	const rowLinks = (el) => el.querySelectorAll("[data-go]").forEach((r) => { r.onclick = () => go(r.dataset.go); });

	/* Schedule */
	async function schedule(date = today(), branch = "") {
		const branches = state.boot.branches.map((b) => `<option ${b === branch ? "selected" : ""}>${esc(b)}</option>`).join("");
		const el = view(`${pageHead(state.boot.is_therapist ? "My Schedule" : "Schedule", state.boot.can_book ? `<a class="btn btn-primary" href="#/book">New Booking</a>` : "")}
			<div class="toolbar"><input type="date" id="d" value="${date}"><select id="b"><option value="">All branches</option>${branches}</select></div><div class="card" id="day"><div class="empty">Loading…</div></div>`);
		const reload = () => schedule(el.querySelector("#d").value, el.querySelector("#b").value);
		el.querySelector("#d").onchange = reload;
		el.querySelector("#b").onchange = reload;
		const d = await guard(() => call(`${BIZ}schedule`, { date, branch }));
		if (!d) return;
		const box = el.querySelector("#day");
		if (!d.lines.length) { box.innerHTML = `<div class="empty">No appointments on this day.</div>`; return; }
		const from = Math.min(600, ...d.lines.map((l) => l.start));
		const to = Math.max(1200, ...d.lines.map((l) => l.end));
		const px = 1.1;
		const height = (to - from) * px;
		const staff = [...new Set(d.lines.map((l) => l.staff_name || "Unassigned"))];
		let hours = "";
		for (let h = Math.ceil(from / 60); h * 60 < to; h++) hours += `<div class="hour" style="top:${(h * 60 - from) * px}px">${String(h).padStart(2, "0")}:00</div>`;
		const col = (name) => {
			const slots = d.lines.filter((l) => (l.staff_name || "Unassigned") === name).map((l) => {
				const cls = l.status === "Completed" ? "done" : ["Checked In", "In Progress"].includes(l.status) ? "progress" : ["Cancelled", "No Show"].includes(l.status) ? "off" : "";
				return `<button class="slot ${cls}" data-go="/form/Spa%20Appointment/${slug(l.appointment)}" style="top:${(l.start - from) * px}px;height:${Math.max((l.end - l.start) * px - 2, 34)}px"><strong>${esc(l.client_name)}</strong><br>${clock(l.start)} ${esc(l.service)}</button>`;
			}).join("");
			return `<div class="day-col"><div class="day-head">${esc(name)}</div><div class="day-body" style="height:${height}px">${hours.replace(/>\d\d:00</g, "><")}${slots}</div></div>`;
		};
		box.innerHTML = `<div class="day"><div class="day-times"><div class="day-head"></div><div class="day-body" style="height:${height}px">${hours}</div></div>${staff.map(col).join("")}</div>`;
		rowLinks(box);
	}

	/* Metadata */
	async function getMeta(doctype) {
		if (!state.metas[doctype]) state.metas[doctype] = await call(`${BIZ}meta`, { doctype });
		return state.metas[doctype];
	}
	const denied = () => view(`${pageHead("Not available")}<div class="card"><div class="empty">This page isn't available for your role.</div></div>`);
	const quietMeta = (doctype) => getMeta(doctype).catch(() => null);
	const resolveTitles = async (wanted) => {
		const pairs = {};
		Object.entries(wanted).forEach(([d, set]) => { if (set.size) pairs[d] = [...set]; });
		if (!Object.keys(pairs).length) return {};
		return (await call(`${BIZ}titles`, { pairs }).catch(() => null)) || {};
	};
	const docTitle = (doctype) => {
		for (const s of state.boot.menu) for (const i of s.items) if (i.doctype === doctype) return i.label;
		return doctype.replace(/^Spa /, "");
	};

	/* List */
	async function list(doctype, page = 0, search = "") {
		const size = 20;
		const el = view(`${pageHead(docTitle(doctype))}<div class="empty">Loading…</div>`);
		const meta = await quietMeta(doctype);
		if (!meta) { denied(); return; }
		const shown = meta.fields.filter((f) => f.in_list_view && !["Table", "Section Break", "Column Break"].includes(f.fieldtype)).slice(0, 6);
		const fields = ["name", "docstatus", ...shown.map((f) => f.fieldname)];
		const filters = [];
		const searchField = meta.title_field && meta.fields.some((f) => f.fieldname === meta.title_field) ? meta.title_field : "name";
		if (search) filters.push([doctype, searchField, "like", `%${search}%`]);
		const rows = await guard(() => call("frappe.client.get_list", { doctype, fields, filters, limit_start: page * size, limit_page_length: size + 1, order_by: "creation desc" }));
		if (!rows) return;
		const more = rows.length > size;
		const wanted = {};
		shown.filter((f) => f.fieldtype === "Link").forEach((f) => { wanted[f.options] = wanted[f.options] || new Set(); rows.forEach((r) => { if (r[f.fieldname]) wanted[f.options].add(r[f.fieldname]); }); });
		const names = await resolveTitles(wanted);
		const cell = (r, f) => {
			const v = r[f.fieldname];
			if (["status"].includes(f.fieldname)) return `<td>${badge(v)}</td>`;
			if (["Currency"].includes(f.fieldtype)) return `<td class="num">${money(v)}</td>`;
			if (f.fieldtype === "Date") return `<td>${fmtDate(v)}</td>`;
			if (f.fieldtype === "Check") return `<td>${v ? icon("check", "sm") : ""}</td>`;
			if (f.fieldtype === "Link") return `<td>${esc(names[f.options]?.[v] || v)}</td>`;
			return `<td>${esc(v)}</td>`;
		};
		const body = rows.slice(0, size).map((r) => `<tr class="row-link" data-go="/form/${slug(doctype)}/${slug(r.name)}"><td><strong>${esc(r.name)}</strong></td>${shown.map((f) => cell(r, f)).join("")}${meta.is_submittable ? `<td>${badge(["Draft", "Submitted", "Cancelled"][r.docstatus])}</td>` : ""}</tr>`).join("");
		const head = `<th>ID</th>${shown.map((f) => `<th class="${f.fieldtype === "Currency" ? "num" : ""}">${esc(f.label)}</th>`).join("")}${meta.is_submittable ? "<th>State</th>" : ""}`;
		const add = meta.perms.create ? `<a class="btn btn-primary" href="#/form/${slug(doctype)}/new">Add ${esc(doctype.replace(/^Spa /, ""))}</a>` : "";
		const root = view(`${pageHead(docTitle(doctype), add)}<div class="card">
			<div class="toolbar"><input id="search" placeholder="Search ${esc(meta.fields.find((f) => f.fieldname === searchField)?.label || "ID")}" value="${esc(search)}"></div>
			${body ? `<div class="table-wrap"><table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>` : `<div class="empty">No records yet.</div>`}
			<div class="pager"><span class="muted small">Page ${page + 1}</span><div class="actions"><button class="btn btn-ghost btn-sm" id="prev" ${page ? "" : "disabled"}>Previous</button><button class="btn btn-ghost btn-sm" id="next" ${more ? "" : "disabled"}>Next</button></div></div></div>`);
		rowLinks(root);
		root.querySelector("#prev").onclick = () => list(doctype, page - 1, search);
		root.querySelector("#next").onclick = () => list(doctype, page + 1, search);
		const input = root.querySelector("#search");
		input.onkeydown = (e) => { if (e.key === "Enter") list(doctype, 0, input.value.trim()); };
	}

	/* Fields */
	const shows = (f, doc) => {
		if (!f.depends_on) return true;
		if (!f.depends_on.startsWith("eval:")) return !!doc[f.depends_on];
		try { return !!new Function("doc", `return ${f.depends_on.slice(5)}`)(doc); } catch (e) { return true; }
	};
	const lockedBy = (f, doc) => {
		if (!f.read_only_depends_on) return false;
		try { return !!new Function("doc", `return ${f.read_only_depends_on.replace(/^eval:/, "")}`)(doc); } catch (e) { return false; }
	};

	let linkNames = {};
	function control(f, value, disabled) {
		const name = `data-f="${esc(f.fieldname)}"`;
		const off = disabled ? "disabled" : "";
		const v = value ?? "";
		switch (f.fieldtype) {
			case "Check": return `<input type="checkbox" ${name} ${value ? "checked" : ""} ${off}>`;
			case "Select": return `<select ${name} ${off}>${(f.options || "").split("\n").map((o) => `<option ${o === String(v) ? "selected" : ""}>${esc(o)}</option>`).join("")}</select>`;
			case "Int": return `<input type="number" step="1" ${name} value="${esc(v)}" ${off}>`;
			case "Float": case "Currency": case "Percent": return `<input type="number" step="any" ${name} value="${esc(v)}" ${off}>`;
			case "Date": return `<input type="date" ${name} value="${esc(v)}" ${off}>`;
			case "Time": return `<input type="time" step="60" ${name} value="${esc(String(v).padStart(8, "0").slice(0, 5).replace(/^00:00$/, v ? "00:00" : ""))}" ${off}>`;
			case "Datetime": return `<input type="datetime-local" ${name} value="${esc(String(v).slice(0, 16).replace(" ", "T"))}" ${off}>`;
			case "Small Text": case "Text": case "Text Editor": case "Long Text": return `<textarea ${name} ${off}>${esc(f.fieldtype === "Text Editor" ? String(v).replace(/<[^>]+>/g, "") : v)}</textarea>`;
			case "Color": return `<input type="color" ${name} value="${esc(v || "#114eff")}" ${off}>`;
			case "Link": return `<div class="link-box"><input ${name} data-link="${esc(f.options)}" data-id="${esc(v)}" value="${esc(linkNames[f.options]?.[v] || v)}" autocomplete="off" ${off}></div>`;
			case "Attach Image": case "Signature":
				return v ? `<div class="muted small">${f.fieldtype === "Signature" ? "Signature captured" : `<a href="${esc(v)}" target="_blank">View image</a>`}</div>` : `<div class="muted small">Not captured</div>`;
			default: return `<input ${name} value="${esc(v)}" ${off}>`;
		}
	}

	function bindLinks(root) {
		root.querySelectorAll("[data-link]").forEach((input) => {
			let timer;
			const close = () => input.parentElement.querySelector(".suggest")?.remove();
			const open = async () => {
				const rows = await call("frappe.desk.search.search_link", { doctype: input.dataset.link, txt: input.value, page_length: 8 }).catch(() => null) ?? [];
				close();
				if (!rows.length) return;
				const list = document.createElement("div");
				list.className = "suggest";
				list.innerHTML = rows.map((r) => `<button type="button" data-v="${esc(r.value)}" data-t="${esc(r.label || r.value)}">${esc(r.label || r.value)}${r.description ? `<small>${esc(r.description)}</small>` : ""}</button>`).join("");
				list.onmousedown = (e) => {
					const b = e.target.closest("button");
					if (!b) return;
					e.preventDefault();
					input.dataset.id = b.dataset.v;
					input.value = b.dataset.t || b.dataset.v;
					close();
					input.dispatchEvent(new Event("change", { bubbles: true }));
				};
				input.parentElement.append(list);
			};
			input.onfocus = open;
			input.oninput = () => { input.dataset.id = input.value; clearTimeout(timer); timer = setTimeout(open, 200); };
			input.onblur = () => setTimeout(close, 150);
		});
	}

	const readValue = (el, f) => {
		if (f.fieldtype === "Link") return el.dataset.id || null;
		if (f.fieldtype === "Check") return el.checked ? 1 : 0;
		if (["Int", "Float", "Currency", "Percent"].includes(f.fieldtype)) return el.value === "" ? null : Number(el.value);
		if (f.fieldtype === "Time") return el.value ? `${el.value}:00` : null;
		if (f.fieldtype === "Datetime") return el.value ? `${el.value.replace("T", " ")}:00` : null;
		return el.value === "" ? null : el.value;
	};

	/* Form */
	async function form(doctype, name) {
		view(`${pageHead(docTitle(doctype))}<div class="empty">Loading…</div>`);
		const meta = await quietMeta(doctype);
		if (!meta) { denied(); return; }
		const isNew = name === "new";
		let doc;
		if (isNew) {
			doc = { doctype, docstatus: 0 };
			meta.fields.forEach((f) => { if (f.default) doc[f.fieldname] = f.default; });
		} else {
			doc = await guard(() => call("frappe.client.get", { doctype, name }));
			if (!doc) { denied(); return; }
		}
		const wanted = {};
		const note = (d, v) => { if (v) { wanted[d] = wanted[d] || new Set(); wanted[d].add(v); } };
		meta.fields.forEach((f) => {
			if (f.fieldtype === "Link") note(f.options, doc[f.fieldname]);
			if (f.fieldtype === "Table") (meta.children[f.options] || []).filter((c) => c.fieldtype === "Link").forEach((c) => (doc[f.fieldname] || []).forEach((r) => note(c.options, r[c.fieldname])));
		});
		linkNames = await resolveTitles(wanted);
		const editable = doc.docstatus === 0 && (isNew ? meta.perms.create : meta.perms.write);
		const fieldDisabled = (f) => !editable || !!f.read_only || !!f.fetch_from || lockedBy(f, doc);

		const fieldHtml = (f) => {
			if (!shows(f, doc)) return "";
			if (f.fieldtype === "Table") return gridHtml(f);
			if (f.fieldtype === "Check") return `<label class="check"><span>${control(f, doc[f.fieldname], fieldDisabled(f))}</span><span>${esc(f.label)}</span></label>`;
			return `<label class="field"><span class="field-label">${esc(f.label)}${f.reqd ? ' <span class="req">*</span>' : ""}</span>${control(f, doc[f.fieldname], fieldDisabled(f))}</label>`;
		};
		const gridHtml = (f) => {
			const cols = (meta.children[f.options] || []).filter((c) => c.in_list_view).slice(0, 6);
			const rows = doc[f.fieldname] || [];
			return `<div class="table-wrap" data-grid="${esc(f.fieldname)}" style="margin-bottom:16px"><table class="grid-edit"><thead><tr>${cols.map((c) => `<th>${esc(c.label)}</th>`).join("")}${editable ? "<th></th>" : ""}</tr></thead><tbody>
				${rows.map((r, i) => `<tr data-row="${i}">${cols.map((c) => `<td>${control(c, r[c.fieldname], !editable || !!c.read_only || !!c.fetch_from)}</td>`).join("")}${editable ? `<td><button type="button" class="icon-btn" data-del="${i}" aria-label="Remove row">✕</button></td>` : ""}</tr>`).join("") || `<tr><td class="muted" colspan="${cols.length + 1}">No rows yet.</td></tr>`}
				</tbody></table>${editable ? `<button type="button" class="btn btn-ghost btn-sm" data-add="${esc(f.fieldname)}" style="margin-top:8px">Add row</button>` : ""}</div>`;
		};
		const sections = () => {
			const out = [];
			let cur = { label: "", columns: [[]] };
			meta.fields.forEach((f) => {
				if (f.fieldtype === "Section Break") { out.push(cur); cur = { label: f.label, columns: [[]] }; } else if (f.fieldtype === "Column Break") { cur.columns.push([]); } else if (f.fieldname !== "naming_series" && f.fieldname !== "amended_from") { cur.columns[cur.columns.length - 1].push(f); }
			});
			out.push(cur);
			return out.filter((s) => s.columns.some((c) => c.some((f) => shows(f, doc))));
		};
		const collect = (root) => {
			meta.fields.forEach((f) => {
				if (f.fieldtype === "Table") return;
				const el = root.querySelector(`.form-body [data-f="${f.fieldname}"]:not([data-grid] *)`);
				if (el && !el.disabled) doc[f.fieldname] = readValue(el, f);
			});
			root.querySelectorAll("[data-grid]").forEach((g) => {
				const f = meta.fields.find((x) => x.fieldname === g.dataset.grid);
				const cols = meta.children[f.options] || [];
				g.querySelectorAll("tr[data-row]").forEach((tr) => {
					const row = doc[f.fieldname][Number(tr.dataset.row)];
					cols.forEach((c) => { const el = tr.querySelector(`[data-f="${c.fieldname}"]`); if (el && !el.disabled) row[c.fieldname] = readValue(el, c); });
				});
			});
		};

		const actionsHtml = () => {
			let a = "";
			if (editable) a += `<button class="btn ${meta.is_submittable && !isNew ? "btn-ghost" : "btn-primary"}" id="save">Save</button>`;
			if (!isNew && meta.is_submittable && doc.docstatus === 0 && meta.perms.submit) a += `<button class="btn btn-primary" id="submit">Submit</button>`;
			if (!isNew && meta.is_submittable && doc.docstatus === 1 && meta.perms.cancel) a += `<button class="btn btn-danger" id="cancel">Cancel</button>`;
			if (doctype === "Spa Appointment" && !isNew && ["Scheduled", "Confirmed"].includes(doc.status) && meta.perms.write) a += `<button class="btn btn-navy" id="checkin">Check In</button>`;
			return a;
		};
		const paint = () => {
			const title = isNew ? `New ${doctype.replace(/^Spa /, "")}` : doc[meta.title_field] || doc.name;
			const state_ = meta.is_submittable && !isNew ? badge(["Draft", "Submitted", "Cancelled"][doc.docstatus]) : "";
			const root = view(`<div class="page-head"><div><a class="muted small" href="#/list/${slug(doctype)}">${esc(docTitle(doctype))}</a><h1>${esc(title)}</h1>${state_}</div><div class="actions">${actionsHtml()}</div></div>
				<div class="form-body">${sections().map((s) => `<div class="card form-section">${s.label ? `<h2>${esc(s.label)}</h2>` : ""}<div class="columns">${s.columns.map((c) => `<div>${c.map(fieldHtml).join("")}</div>`).join("")}</div></div>`).join("")}</div>`);
			bindLinks(root);
			root.querySelectorAll("[data-add]").forEach((b) => { b.onclick = () => { collect(root); (doc[b.dataset.add] = doc[b.dataset.add] || []).push({ doctype: meta.fields.find((x) => x.fieldname === b.dataset.add).options }); paint(); }; });
			root.querySelectorAll("[data-del]").forEach((b) => { b.onclick = () => { collect(root); doc[b.closest("[data-grid]").dataset.grid].splice(Number(b.dataset.del), 1); paint(); }; });
			root.querySelector(".form-body").addEventListener("change", (e) => { if (e.target.matches("select,input[type=checkbox]") && meta.fields.some((f) => f.depends_on)) { collect(root); paint(); } });
			const saveDoc = async () => {
				collect(root);
				const saved = isNew ? await call("frappe.client.insert", { doc }, { post: true }) : await call("frappe.client.save", { doc }, { post: true });
				return saved;
			};
			const bind = (id, fn) => { const b = root.querySelector(id); if (b) b.onclick = fn; };
			bind("#save", () => guard(async () => { const s = await saveDoc(); toast("Saved"); if (isNew) go(`/form/${slug(doctype)}/${slug(s.name)}`); else form(doctype, s.name); }));
			bind("#submit", () => guard(async () => { const s = await saveDoc(); await call("frappe.client.submit", { doc: s }, { post: true }); toast("Submitted"); form(doctype, s.name); }));
			bind("#cancel", () => { if (confirm("Cancel this document? Its postings will be reversed.")) guard(async () => { await call("frappe.client.cancel", { doctype, name: doc.name }, { post: true }); toast("Cancelled"); form(doctype, doc.name); }); });
			bind("#checkin", () => guard(async () => { const v = await call("biz_spa.api.booking.check_in", { appointment: doc.name }, { post: true }); toast("Checked in"); if (v) go(`/form/Spa%20Visit/${slug(v)}`); else form(doctype, doc.name); }));
		};
		paint();
	}

	/* Booking */
	async function book() {
		const flow = { client: "", clientName: "", branch: state.boot.branches[0] || "", date: today(), services: [], slot: null };
		const all = await guard(() => call(`${BIZ}services_for_booking`));
		if (!all) return;
		const render = async () => {
			const picks = all.map((s) => `<button type="button" class="pick ${flow.services.includes(s.name) ? "on" : ""}" data-s="${esc(s.name)}"><span>${esc(s.name)}<br><span class="muted small">${s.duration_minutes} min</span></span><span>${money(s.price)}</span></button>`).join("");
			const root = view(`${pageHead("New Booking")}
				<div class="card"><h2 style="margin-bottom:16px">Client and date</h2><div class="columns">
					<label class="field"><span class="field-label">Client <span class="req">*</span></span><div class="link-box"><input id="client" data-link="Spa Client Profile" data-id="${esc(flow.client)}" value="${esc(flow.clientName)}" autocomplete="off"></div></label>
					<label class="field"><span class="field-label">Branch</span><select id="branch">${state.boot.branches.map((b) => `<option ${b === flow.branch ? "selected" : ""}>${esc(b)}</option>`).join("")}</select></label>
					<label class="field"><span class="field-label">Date</span><input id="date" type="date" min="${today()}" value="${flow.date}"></label></div></div>
				<div class="card"><h2 style="margin-bottom:16px">Services</h2><div class="pick-list">${picks}</div></div>
				<div class="card"><h2 style="margin-bottom:16px">Available times</h2><div id="slots"><div class="muted">Choose at least one service.</div></div>
				<div class="actions" style="margin-top:16px"><button class="btn btn-primary" id="confirm" disabled>Confirm Booking</button></div></div>`);
			bindLinks(root);
			root.querySelector("#client").onchange = (e) => { flow.client = e.target.dataset.id; flow.clientName = e.target.value; toggle(); };
			root.querySelector("#branch").onchange = (e) => { flow.branch = e.target.value; flow.slot = null; render(); };
			root.querySelector("#date").onchange = (e) => { flow.date = e.target.value; flow.slot = null; render(); };
			root.querySelectorAll("[data-s]").forEach((b) => { b.onclick = () => { const s = b.dataset.s; flow.services = flow.services.includes(s) ? flow.services.filter((x) => x !== s) : [...flow.services, s]; flow.slot = null; render(); }; });
			const confirmBtn = root.querySelector("#confirm");
			const toggle = () => { confirmBtn.disabled = !(flow.client && flow.slot && flow.services.length); };
			confirmBtn.onclick = () => guard(async () => {
				const name = await call("biz_spa.api.booking.book_appointment", { client: flow.client, branch: flow.branch, date: flow.date, start_time: flow.slot, services: JSON.stringify(flow.services), source: "Phone" }, { post: true });
				toast("Appointment booked");
				go(`/form/Spa%20Appointment/${slug(name)}`);
			});
			if (flow.services.length) {
				const slots = await guard(() => call("biz_spa.api.booking.get_available_slots", { branch: flow.branch, date: flow.date, services: JSON.stringify(flow.services) }));
				const box = root.querySelector("#slots");
				if (slots) {
					box.innerHTML = slots.length ? `<div class="slots">${slots.map((s) => `<button type="button" class="slot-pick ${s.start_time === flow.slot ? "on" : ""}" data-t="${s.start_time}">${s.start_time.slice(0, 5)}</button>`).join("")}</div>` : `<div class="muted">No free times on this day. Try another date.</div>`;
					box.querySelectorAll("[data-t]").forEach((b) => { b.onclick = () => { flow.slot = b.dataset.t; box.querySelectorAll(".slot-pick").forEach((x) => x.classList.toggle("on", x === b)); toggle(); }; });
				}
			}
			toggle();
		};
		render();
	}

	/* Reports */
	function reports() {
		const el = view(`${pageHead("Reports")}<div class="pick-list">${state.boot.reports.map((r) => `<a class="pick" href="#/report/${slug(r.name)}"><span>${esc(r.name)}</span>${icon("chart-column", "sm")}</a>`).join("")}</div>`);
		return el;
	}

	async function report(name, values) {
		const def = state.boot.reports.find((r) => r.name === name);
		if (!def) { view(`${pageHead("Reports")}<div class="card"><div class="empty">This report isn't available for your role.</div></div>`); return; }
		const month = String(new Date().getMonth() + 1);
		const start = new Date(); start.setMonth(start.getMonth() - 1);
		const defaults = { from_date: start.toISOString().slice(0, 10), to_date: today(), days_since_last_visit: 30, days_ahead: 30, month };
		const f = { ...defaults, ...values };
		const input = (key) => {
			if (key === "branch") return `<select data-k="branch"><option value="">All branches</option>${state.boot.branches.map((b) => `<option ${b === f.branch ? "selected" : ""}>${esc(b)}</option>`).join("")}</select>`;
			if (key.endsWith("_date")) return `<input type="date" data-k="${key}" value="${f[key] || ""}">`;
			if (key === "staff") return `<div class="link-box"><input data-k="staff" data-link="Spa Staff Profile" data-id="${esc(f.staff || "")}" placeholder="Any staff" value="${esc(f.staffName || "")}"></div>`;
			if (key === "month") return `<select data-k="month">${Array.from({ length: 12 }, (_, i) => `<option ${String(i + 1) === String(f.month) ? "selected" : ""}>${i + 1}</option>`).join("")}</select>`;
			return `<input type="number" data-k="${key}" value="${esc(f[key] ?? "")}">`;
		};
		const el = view(`${pageHead(name)}<div class="card"><div class="toolbar">${def.filters.map(input).join("")}<button class="btn btn-ghost" id="run">Run</button></div><div id="out"><div class="empty">Loading…</div></div></div>`);
		bindLinks(el);
		el.querySelector("#run").onclick = () => {
			const next = {};
			el.querySelectorAll("[data-k]").forEach((i) => { next[i.dataset.k] = i.dataset.link ? i.dataset.id || "" : i.value; });
			report(name, next);
		};
		const r = await guard(() => call("frappe.desk.query_report.run", { report_name: name, filters: f }));
		const out = el.querySelector("#out");
		if (!r) { out.innerHTML = `<div class="empty">The report couldn't run.</div>`; return; }
		const cols = r.columns || [];
		const num = (c) => ["Currency", "Int", "Float", "Percent"].includes(c.fieldtype);
		const show = (c, v) => (c.fieldtype === "Currency" ? money(v) : c.fieldtype === "Date" ? fmtDate(v) : c.fieldtype === "Percent" ? `${Number(v || 0)}%` : c.fieldtype === "Check" ? (v ? "Yes" : "") : esc(v));
		out.innerHTML = r.result?.length ? `<div class="table-wrap"><table><thead><tr>${cols.map((c) => `<th class="${num(c) ? "num" : ""}">${esc(c.label)}</th>`).join("")}</tr></thead><tbody>${r.result.map((row) => `<tr>${cols.map((c) => `<td class="${num(c) ? "num" : ""}">${show(c, row[c.fieldname])}</td>`).join("")}</tr>`).join("")}</tbody></table></div>` : `<div class="empty">No results for these filters.</div>`;
	}

	/* Router */
	function route() {
		if (!state.boot) return;
		const parts = location.hash.replace(/^#\/?/, "").split("/").map(decodeURIComponent);
		const [page, a, b] = parts;
		document.querySelectorAll(".nav-item[data-nav]").forEach((n) => {
			const target = n.dataset.nav.split("/").map(decodeURIComponent).join("/");
			const here = `/${parts.join("/")}`;
			n.classList.toggle("active", here === target || (page === "form" && target === `/list/${a}`));
		});
		document.getElementById("side")?.classList.remove("open");
		window.scrollTo(0, 0);
		if (page === "schedule") schedule();
		else if (page === "book" && state.boot.can_book) book();
		else if (page === "list" && a) list(a);
		else if (page === "form" && a && b) form(a, b);
		else if (page === "reports") reports();
		else if (page === "report" && a) report(a);
		else dashboard();
	}

	async function start() {
		await loadSprite().catch(() => {});
		if (!window.PORTAL.loggedIn) { renderLogin(); return; }
		try {
			state.boot = await call(`${BIZ}bootstrap`);
		} catch (e) {
			app.innerHTML = `<div class="login-panel" style="min-height:100vh"><div class="login-card"><h2>No portal access</h2><p class="muted" style="margin:8px 0 16px">This account isn't set up for the Biz Spa portal.</p><button class="btn btn-ghost" id="out">Sign out</button></div></div>`;
			document.getElementById("out").onclick = async () => { await call("logout", {}, { post: true }).catch(() => {}); location.href = "/portal"; };
			return;
		}
		renderShell();
		window.addEventListener("hashchange", route);
		route();
	}
	start();
})();
