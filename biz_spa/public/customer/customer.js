// Biz Spa customer site: browse and book as a guest, then manage bookings from an account. Every
// rule (slots, windows, ownership) is enforced in biz_spa.api.customer; this only reflects them.
(() => {
	const app = document.getElementById("app");
	const API = "/api/method/";
	const BIZ = "biz_spa.api.customer.";
	const DRAFT = "biz_spa_booking";
	const state = { me: { user: null }, cat: null };
	const flow = { branch: "", services: [], date: "", slot: null, notes: "" };

	const esc = (v) =>
		String(v ?? "").replace(
			/[&<>"']/g,
			(c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
		);
	const icon = (name, cls = "") =>
		`<svg class="icon ${cls}" aria-hidden="true"><use href="#icon-spa-${name}"></use></svg>`;
	const money = (v) =>
		new Intl.NumberFormat("en-IN", {
			style: "currency",
			currency: state.cat?.currency || "INR",
		}).format(Number(v || 0));
	const asDate = (v) => new Date(`${String(v).slice(0, 10)}T00:00:00`);
	const fmtDate = (v) =>
		asDate(v).toLocaleDateString("en-IN", {
			weekday: "short",
			day: "numeric",
			month: "short",
			year: "numeric",
		});
	const time = (t) =>
		new Date(`2000-01-01T${t}`).toLocaleTimeString("en-IN", {
			hour: "numeric",
			minute: "2-digit",
		});
	const iso = (d) =>
		`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(
			d.getDate()
		).padStart(2, "0")}`;
	const signedIn = () => Boolean(state.me.user);
	const canUseAccount = () => Boolean(state.me.is_customer && state.me.client);

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
				return JSON.parse(body._server_messages)
					.map((m) => JSON.parse(m).message)
					.join(" ")
					.replace(/<[^>]+>/g, "");
			}
		} catch (e) {
			/* fall through to the generic text */
		}
		return body.message || "Something went wrong. Please try again.";
	}

	async function call(method, args = {}, { post = false } = {}) {
		const headers = {
			Accept: "application/json",
			"X-Frappe-CSRF-Token": window.SPA.csrf || "fetch",
		};
		const options = { headers, credentials: "same-origin" };
		let url = API + BIZ + method;
		if (post) {
			options.method = "POST";
			headers["Content-Type"] = "application/json";
			options.body = JSON.stringify(args);
		} else {
			url += `?${new URLSearchParams(
				Object.entries(args).map(([k, v]) => [
					k,
					typeof v === "object" ? JSON.stringify(v) : v,
				])
			)}`;
		}
		const response = await fetch(url, options);
		const body = await response.json().catch(() => ({}));
		if (!response.ok) throw new Error(serverMessage(body));
		return body.message;
	}
	const guard = async (fn) => {
		try {
			return await fn();
		} catch (e) {
			toast(e.message, true);
			return undefined;
		}
	};

	const saveDraft = () => {
		try {
			sessionStorage.setItem(DRAFT, JSON.stringify(flow));
		} catch (e) {
			/* a draft is only a convenience */
		}
	};
	const loadDraft = () => {
		try {
			Object.assign(flow, JSON.parse(sessionStorage.getItem(DRAFT) || "{}"));
		} catch (e) {
			/* start clean */
		}
	};
	const clearDraft = () => {
		try {
			sessionStorage.removeItem(DRAFT);
		} catch (e) {
			/* nothing stored */
		}
	};

	/* Layout */
	function page(html, tab = "") {
		const links = canUseAccount()
			? [
					["/", "Book"],
					["/bookings", "My Bookings"],
					["/visits", "Visits"],
					["/wallet", "Wallet"],
					["/profile", "Profile"],
			  ]
			: [["/", "Book"]];
		const nav = links
			.map(
				([href, label]) =>
					`<a href="#${href}" class="${tab === href ? "on" : ""}">${label}</a>`
			)
			.join("");
		const auth = signedIn()
			? `<button class="btn btn-ghost btn-sm" id="signout">Sign out</button>`
			: `<a class="btn btn-primary btn-sm" href="#/signin">Sign in</a>`;
		app.innerHTML = `<header class="cx-head"><div class="cx-bar"><a class="wordmark" href="#/">Biz Spa</a><nav>${nav}</nav>${auth}</div></header>${html}`;
		const out = document.getElementById("signout");
		if (out)
			out.onclick = () =>
				guard(async () => {
					await fetch(`${API}logout`, {
						method: "POST",
						headers: { "X-Frappe-CSRF-Token": window.SPA.csrf },
					});
					clearDraft();
					location.href = "/spa";
				});
		window.scrollTo(0, 0);
	}
	const main = (html, tab) => {
		page(`<main class="cx-main">${html}</main>`, tab);
		return app.querySelector(".cx-main");
	};
	const steps = (on) =>
		`<div class="cx-steps">${["Services", "Date and time", "Confirm"]
			.map((s, i) => `<span class="${i <= on ? "on" : ""}">${s}</span>`)
			.join("")}</div>`;
	const chosen = () => state.cat.services.filter((s) => flow.services.includes(s.name));
	const total = () => chosen().reduce((sum, s) => sum + Number(s.price), 0);
	const length = () => chosen().reduce((sum, s) => sum + Number(s.duration_minutes), 0);

	function dayPicker(selected) {
		const days = [];
		const last = asDate(state.cat.last_date);
		for (let d = asDate(state.cat.today); d <= last; d.setDate(d.getDate() + 1))
			days.push(new Date(d));
		return `<div class="cx-days">${days
			.map(
				(d) =>
					`<button type="button" class="cx-day ${
						iso(d) === selected ? "on" : ""
					}" data-day="${iso(d)}"><span class="small">${d.toLocaleDateString("en-IN", {
						weekday: "short",
					})}</span><strong>${d.getDate()}</strong><span class="small">${d.toLocaleDateString(
						"en-IN",
						{ month: "short" }
					)}</span></button>`
			)
			.join("")}</div>`;
	}

	/* Step 1: services */
	function services() {
		const groups = {};
		state.cat.services.forEach((s) => {
			(groups[s.category] = groups[s.category] || []).push(s);
		});
		const list = Object.entries(groups)
			.map(
				([category, rows]) =>
					`<div class="cx-cat">${esc(category)}</div>${rows
						.map(
							(s) => `
			<button type="button" class="cx-service ${
				flow.services.includes(s.name) ? "on" : ""
			}" data-s="${esc(s.name)}" aria-pressed="${flow.services.includes(s.name)}">
				<span><strong>${esc(s.name)}</strong><br><span class="muted small">${
								s.duration_minutes
							} min · ${money(s.price)}</span></span>
				<span class="cx-tick">${flow.services.includes(s.name) ? icon("check", "sm") : ""}</span>
			</button>`
						)
						.join("")}`
			)
			.join("");
		const branches = state.cat.branches
			.map(
				(b) =>
					`<option ${b.name === flow.branch ? "selected" : ""}>${esc(b.name)}</option>`
			)
			.join("");
		page(
			`<section class="cx-hero"><div><h1>Book your time to unwind</h1><p>Choose your treatments, pick a time, and we'll take care of the rest.</p></div></section>
			<main class="cx-main">${steps(0)}
				<label class="field"><span class="field-label">Branch</span><select id="branch">${branches}</select></label>
				${
					state.cat.services.length
						? list
						: `<div class="empty">Online booking isn't open yet. Please call the spa.</div>`
				}
				<p class="muted small" style="margin-top:16px">Treatments that need a patch test or consultation are booked with the spa directly.</p>
			</main>
			<div class="cx-bottom"><div><span id="sum"></span><button class="btn btn-primary" id="next">Choose a time</button></div></div>`,
			"/"
		);
		const paint = () => {
			document.getElementById("sum").textContent = flow.services.length
				? `${flow.services.length} selected · ${length()} min · ${money(total())}`
				: "Select a service";
			document.getElementById("next").disabled = !flow.services.length;
		};
		document.getElementById("branch").onchange = (e) => {
			flow.branch = e.target.value;
			flow.slot = null;
			saveDraft();
		};
		app.querySelectorAll("[data-s]").forEach((b) => {
			b.onclick = () => {
				const s = b.dataset.s;
				if (!flow.services.includes(s) && flow.services.length >= 5) {
					toast("You can book up to 5 services at once.", true);
					return;
				}
				flow.services = flow.services.includes(s)
					? flow.services.filter((x) => x !== s)
					: [...flow.services, s];
				flow.slot = null;
				saveDraft();
				const on = flow.services.includes(s);
				b.classList.toggle("on", on);
				b.setAttribute("aria-pressed", on);
				b.querySelector(".cx-tick").innerHTML = on ? icon("check", "sm") : "";
				paint();
			};
		});
		document.getElementById("next").onclick = () => {
			location.hash = "/time";
		};
		paint();
	}

	/* Step 2: date and time */
	function times() {
		if (!flow.services.length) {
			location.hash = "/";
			return;
		}
		flow.date =
			flow.date && flow.date >= state.cat.today && flow.date <= state.cat.last_date
				? flow.date
				: state.cat.today;
		const root = main(
			`${steps(
				1
			)}<div class="page-head"><h1>Pick a time</h1><a href="#/" class="link-btn">Change services</a></div>
			<p class="muted" style="margin-bottom:16px">${esc(flow.branch)} · ${length()} min</p>
			${dayPicker(flow.date)}<div id="slots" class="muted">Loading times…</div>`,
			"/"
		);
		const load = async () => {
			const box = root.querySelector("#slots");
			box.textContent = "Loading times…";
			const asked = flow.date;
			const slots = await guard(() =>
				call("slots", { branch: flow.branch, date: asked, services: flow.services })
			);
			if (!slots || asked !== flow.date) return;
			if (!slots.length) {
				const first = flow.services[0];
				box.innerHTML = `<div class="empty">No times left on ${esc(
					fmtDate(asked)
				)}.<br>Try another day${
					canUseAccount()
						? `, or join the waitlist for ${esc(
								first
						  )} and reception will offer you a slot if one opens.<br><br><button class="btn btn-ghost" id="waitlist">Join waitlist</button>`
						: "."
				}</div>`;
				const join = box.querySelector("#waitlist");
				if (join)
					join.onclick = () =>
						guard(async () => {
							await call(
								"join_waitlist",
								{ branch: flow.branch, service: first, date: asked },
								{ post: true }
							);
							toast("You're on the waitlist");
							join.disabled = true;
						});
				return;
			}
			box.innerHTML = `<div class="slots">${slots
				.map(
					(s) =>
						`<button type="button" class="slot-pick" data-t="${s.start_time}">${time(
							s.start_time
						)}</button>`
				)
				.join("")}</div>`;
			box.querySelectorAll("[data-t]").forEach((b) => {
				b.onclick = () => {
					flow.slot = b.dataset.t;
					saveDraft();
					location.hash = "/confirm";
				};
			});
		};
		root.querySelectorAll("[data-day]").forEach((b) => {
			b.onclick = () => {
				flow.date = b.dataset.day;
				flow.slot = null;
				root.querySelectorAll("[data-day]").forEach((x) =>
					x.classList.toggle("on", x === b)
				);
				load();
			};
		});
		root.querySelector(".cx-day.on")?.scrollIntoView({ block: "nearest", inline: "center" });
		load();
	}

	/* Step 3: confirm */
	function confirmBooking() {
		if (!flow.services.length || !flow.slot) {
			location.hash = flow.services.length ? "/time" : "/";
			return;
		}
		const lines = chosen()
			.map(
				(s) =>
					`<div class="cx-row"><span>${esc(s.name)}<br><span class="muted small">${
						s.duration_minutes
					} min</span></span><span>${money(s.price)}</span></div>`
			)
			.join("");
		const ready = canUseAccount() && state.me.client.status === "Active";
		const root = main(
			`${steps(2)}<h1 style="margin-bottom:16px">Confirm your booking</h1>
			<div class="card cx-card-gap"><p><strong>${esc(fmtDate(flow.date))} at ${time(
				flow.slot
			)}</strong></p><p class="muted" style="margin-bottom:8px">${esc(
				flow.branch
			)}</p>${lines}
				<div class="cx-row"><strong>Total, paid at the spa</strong><strong>${money(
					total()
				)}</strong></div></div>
			${
				ready
					? `<label class="field"><span class="field-label">Anything we should know? (optional)</span><textarea id="notes" rows="3" maxlength="500">${esc(
							flow.notes
					  )}</textarea></label>
				<p class="muted small" style="margin-bottom:16px">Free to change up to ${
					state.cat.cancellation_window_hours
				} hours before. Later cancellations may be charged ${
							state.cat.late_fee_percent
					  }% of the booking.</p>
				<div class="actions"><button class="btn btn-primary" id="confirm">Confirm booking</button><a class="btn btn-ghost" href="#/time">Back</a></div>`
					: `<div id="account"></div>`
			}`,
			"/"
		);
		if (!ready) {
			if (signedIn()) root.querySelector("#account").innerHTML = accountProblem();
			else authForm(root.querySelector("#account"), "signup");
			return;
		}
		root.querySelector("#confirm").onclick = (e) =>
			guard(async () => {
				e.target.disabled = true;
				try {
					const name = await call(
						"book",
						{
							branch: flow.branch,
							date: flow.date,
							start_time: flow.slot,
							services: flow.services,
							notes: root.querySelector("#notes").value,
						},
						{ post: true }
					);
					Object.assign(flow, { services: [], slot: null, notes: "" });
					clearDraft();
					location.hash = `/booked/${encodeURIComponent(name)}`;
				} catch (err) {
					e.target.disabled = false;
					throw err;
				}
			});
	}

	function accountProblem() {
		if (!state.me.is_customer)
			return `<div class="cx-notice">You're signed in with a staff account. Sign out to book as a customer.</div>`;
		if (!state.me.client)
			return `<div class="cx-notice">We found your details on file. To protect your history, reception needs to link this account before you can book. Please call the spa and give them <strong>${esc(
				state.me.user
			)}</strong>.</div>`;
		return `<div class="cx-notice">Online booking isn't available on your account. Please call the spa.</div>`;
	}

	/* Sign in and sign up */
	function authForm(box, mode) {
		const signup = mode === "signup";
		box.innerHTML = `<div class="card"><div class="cx-tabs"><button type="button" class="${
			signup ? "on" : ""
		}" data-mode="signup">New here</button><button type="button" class="${
			signup ? "" : "on"
		}" data-mode="login">Sign in</button></div>
			<form id="auth"><div id="auth-error"></div>
				${
					signup
						? `<label class="field"><span class="field-label">Full name</span><input id="name" autocomplete="name" required></label>
				<label class="field"><span class="field-label">Mobile</span><input id="mobile" type="tel" autocomplete="tel" required></label>`
						: ""
				}
				<label class="field"><span class="field-label">Email</span><input id="email" type="email" autocomplete="email" required></label>
				<label class="field"><span class="field-label">Password${
					signup ? " (at least 8 characters)" : ""
				}</span><input id="password" type="password" minlength="${
			signup ? 8 : 1
		}" autocomplete="${signup ? "new-password" : "current-password"}" required></label>
				<button class="btn btn-primary" type="submit">${signup ? "Create account" : "Sign in"}</button>
				${
					signup
						? ""
						: `<p class="muted small" style="margin-top:12px">Forgot your password? Please call the spa.</p>`
				}
			</form></div>`;
		box.querySelectorAll("[data-mode]").forEach((b) => {
			b.onclick = () => authForm(box, b.dataset.mode);
		});
		box.querySelector("#auth").onsubmit = async (event) => {
			event.preventDefault();
			const value = (id) => box.querySelector(`#${id}`).value;
			const button = box.querySelector("[type=submit]");
			button.disabled = true;
			try {
				if (signup) {
					await call(
						"signup",
						{
							full_name: value("name"),
							email: value("email"),
							mobile: value("mobile"),
							password: value("password"),
						},
						{ post: true }
					);
				} else {
					const body = new URLSearchParams({
						usr: value("email"),
						pwd: value("password"),
					});
					const response = await fetch(`${API}login`, {
						method: "POST",
						body,
						headers: { Accept: "application/json" },
					});
					if (!response.ok) throw new Error("That email and password don't match.");
				}
				// The session's CSRF token only reaches the page on a fresh load.
				saveDraft();
				location.reload();
			} catch (e) {
				button.disabled = false;
				box.querySelector("#auth-error").innerHTML = `<div class="alert">${esc(
					e.message
				)}</div>`;
			}
		};
	}

	function signin() {
		if (signedIn()) {
			location.hash = "/bookings";
			return;
		}
		const root = main(
			`<h1 style="margin-bottom:16px">Your account</h1><div id="account"></div>`
		);
		authForm(root.querySelector("#account"), "login");
	}

	function booked(name) {
		main(`<div class="card" style="text-align:center"><div class="cx-tick" style="margin:0 auto 12px;background:var(--mint);border-color:var(--mint)">${icon(
			"check",
			"sm"
		)}</div>
			<h1>You're booked</h1><p class="muted" style="margin:8px 0 16px">Reference ${esc(
				name
			)}. Please arrive 10 minutes early.</p>
			<div class="actions" style="justify-content:center"><a class="btn btn-primary" href="#/bookings">View my bookings</a><a class="btn btn-ghost" href="#/">Book another</a></div></div>`);
	}

	/* Account */
	const needAccount = (tab) => {
		if (canUseAccount()) return false;
		if (signedIn()) main(accountProblem(), tab);
		else location.hash = "/signin";
		return true;
	};
	const badge = (s) =>
		`<span class="badge ${
			{
				Scheduled: "blue",
				Confirmed: "green",
				Completed: "green",
				Cancelled: "red",
				"No Show": "red",
				Offered: "green",
				Waiting: "amber",
			}[s] || ""
		}">${esc(s)}</span>`;

	async function bookings() {
		if (needAccount("/bookings")) return;
		const root = main(
			`<h1 style="margin-bottom:16px">My bookings</h1><div class="muted">Loading…</div>`,
			"/bookings"
		);
		const [rows, waits] = await Promise.all([
			guard(() => call("appointments")),
			guard(() => call("waitlist")),
		]);
		if (!rows) return;
		const card = (a) => `<div class="card cx-card-gap"><div class="cx-top"><div><strong>${esc(
			fmtDate(a.appointment_date)
		)} · ${time(a.start_time)}</strong><p class="muted small">${esc(a.branch)} · ${esc(
			a.name
		)}</p></div>${badge(a.status)}</div>
			<div style="margin-top:8px">${a.services
				.map(
					(s) =>
						`<div class="cx-row"><span>${esc(
							s.service
						)}</span><span class="muted">${esc(s.staff || "")}</span></div>`
				)
				.join("")}<div class="cx-row"><strong>Total</strong><strong>${money(
			a.total_amount
		)}</strong></div></div>
			${
				a.cancellation_fee
					? `<p class="muted small">Late cancellation fee: ${money(
							a.cancellation_fee
					  )}</p>`
					: ""
			}
			${
				a.upcoming
					? `<div class="actions" style="margin-top:12px">${
							a.can_reschedule
								? `<a class="btn btn-ghost btn-sm" href="#/move/${encodeURIComponent(
										a.name
								  )}">Reschedule</a>`
								: ""
					  }<button class="btn btn-danger btn-sm" data-cancel="${esc(
							a.name
					  )}" data-fee="${a.late_fee}">Cancel</button></div>`
					: ""
			}</div>`;
		const next = rows.filter((a) => a.upcoming).reverse();
		const past = rows.filter((a) => !a.upcoming);
		const queue = (waits || [])
			.map(
				(w) =>
					`<div class="cx-row"><span>${esc(w.service)} · ${esc(
						fmtDate(w.date_from)
					)}<br><span class="muted small">${esc(w.branch)}${
						w.status === "Offered"
							? " · a slot opened, book it before someone else does"
							: ""
					}</span></span>${badge(w.status)}</div>`
			)
			.join("");
		root.innerHTML = `<div class="page-head"><h1>My bookings</h1><a class="btn btn-primary" href="#/">New booking</a></div>
			${
				queue
					? `<div class="card cx-card-gap"><h2 style="margin-bottom:8px">Waitlist</h2>${queue}</div>`
					: ""
			}
			<h2 style="margin-bottom:12px">Upcoming</h2>${
				next.map(card).join("") || `<div class="empty">Nothing booked yet.</div>`
			}
			${past.length ? `<h2 style="margin:24px 0 12px">Past</h2>${past.map(card).join("")}` : ""}`;
		root.querySelectorAll("[data-cancel]").forEach((b) => {
			b.onclick = () => {
				const fee = Number(b.dataset.fee);
				if (
					!confirm(
						fee
							? `This is within the cancellation window, so a fee of ${money(
									fee
							  )} applies. Cancel anyway?`
							: "Cancel this booking?"
					)
				)
					return;
				guard(async () => {
					await call("cancel", { name: b.dataset.cancel }, { post: true });
					toast("Booking cancelled");
					bookings();
				});
			};
		});
	}

	function move(name) {
		if (needAccount("/bookings")) return;
		let date = state.cat.today;
		const root = main(
			`<div class="page-head"><h1>Reschedule</h1><a href="#/bookings" class="link-btn">Keep current time</a></div>${dayPicker(
				date
			)}<div id="slots" class="muted">Loading times…</div>`,
			"/bookings"
		);
		const load = async () => {
			const box = root.querySelector("#slots");
			const asked = date;
			const slots = await guard(() => call("reschedule_slots", { name, date: asked }));
			if (!slots || asked !== date) return;
			box.innerHTML = slots.length
				? `<div class="slots">${slots
						.map(
							(s) =>
								`<button type="button" class="slot-pick" data-t="${
									s.start_time
								}">${time(s.start_time)}</button>`
						)
						.join("")}</div>`
				: `<div class="empty">No times left on this day.</div>`;
			box.querySelectorAll("[data-t]").forEach((b) => {
				b.onclick = () => {
					if (!confirm(`Move to ${fmtDate(asked)} at ${time(b.dataset.t)}?`)) return;
					guard(async () => {
						await call(
							"reschedule",
							{ name, date: asked, start_time: b.dataset.t },
							{ post: true }
						);
						toast("Booking moved");
						location.hash = "/bookings";
					});
				};
			});
		};
		root.querySelectorAll("[data-day]").forEach((b) => {
			b.onclick = () => {
				date = b.dataset.day;
				root.querySelectorAll("[data-day]").forEach((x) =>
					x.classList.toggle("on", x === b)
				);
				root.querySelector("#slots").textContent = "Loading times…";
				load();
			};
		});
		load();
	}

	async function visits() {
		if (needAccount("/visits")) return;
		const root = main(
			`<h1 style="margin-bottom:16px">Visits</h1><div class="muted">Loading…</div>`,
			"/visits"
		);
		const rows = await guard(() => call("visits"));
		if (!rows) return;
		root.innerHTML = `<h1 style="margin-bottom:16px">Visits</h1>${
			rows
				.map(
					(v) => `<div class="card cx-card-gap"><div class="cx-top"><div><strong>${esc(
						fmtDate(v.posting_date)
					)}</strong><p class="muted small">${esc(v.branch)} · ${esc(
						v.name
					)}</p></div><strong>${money(v.grand_total)}</strong></div>
			<p style="margin-top:8px">${esc(v.services.join(", "))}</p>
			${
				Number(v.outstanding_amount) > 0
					? `<p class="small" style="color:var(--amber);margin-top:4px">${money(
							v.outstanding_amount
					  )} outstanding</p>`
					: ""
			}
			<div class="actions" style="margin-top:12px">${
				v.rated
					? `<span class="badge green">Rated, thank you</span>`
					: `<a class="btn btn-ghost btn-sm" href="#/rate/${encodeURIComponent(
							v.name
					  )}">Rate this visit</a>`
			}</div></div>`
				)
				.join("") || `<div class="empty">Your visits will appear here.</div>`
		}`;
	}

	function rate(visit) {
		if (needAccount("/visits")) return;
		const scores = {};
		const stars = (key, label) =>
			`<div class="field" style="margin-bottom:16px"><span class="field-label">${label}</span><div class="cx-stars" data-key="${key}">${[
				1, 2, 3, 4, 5,
			]
				.map(
					(n) =>
						`<button type="button" data-n="${n}" aria-label="${n} of 5">${icon(
							"star"
						)}</button>`
				)
				.join("")}</div></div>`;
		const root = main(
			`<h1 style="margin-bottom:16px">Rate your visit</h1><div class="card">${stars(
				"service_rating",
				"Treatment"
			)}${stars("staff_rating", "Your therapist")}${stars("ambience_rating", "Ambience")}
			<label class="check" style="margin-bottom:16px"><input type="checkbox" id="recommend"> <span>I'd recommend Biz Spa</span></label>
			<label class="field"><span class="field-label">Comments (optional)</span><textarea id="comments" rows="3" maxlength="1000"></textarea></label>
			<button class="btn btn-primary" id="send">Send feedback</button></div>`,
			"/visits"
		);
		root.querySelectorAll(".cx-stars").forEach((group) => {
			group.querySelectorAll("[data-n]").forEach((b) => {
				b.onclick = () => {
					scores[group.dataset.key] = Number(b.dataset.n);
					group
						.querySelectorAll("[data-n]")
						.forEach((x) =>
							x.classList.toggle("on", Number(x.dataset.n) <= Number(b.dataset.n))
						);
				};
			});
		});
		root.querySelector("#send").onclick = () => {
			if (!scores.service_rating) {
				toast("Please rate the treatment.", true);
				return;
			}
			guard(async () => {
				await call(
					"feedback",
					{
						visit,
						...scores,
						would_recommend: root.querySelector("#recommend").checked ? 1 : 0,
						comments: root.querySelector("#comments").value,
					},
					{ post: true }
				);
				toast("Thank you for your feedback");
				location.hash = "/visits";
			});
		};
	}

	async function wallet() {
		if (needAccount("/wallet")) return;
		const root = main(
			`<h1 style="margin-bottom:16px">Wallet</h1><div class="muted">Loading…</div>`,
			"/wallet"
		);
		const b = await guard(() => call("balances"));
		if (!b) return;
		const section = (title, rows, render) =>
			`<div class="card cx-card-gap"><h2 style="margin-bottom:8px">${title}</h2>${
				rows.map(render).join("") || `<p class="muted">None yet.</p>`
			}</div>`;
		const until = (d) => (d ? `valid until ${esc(fmtDate(d))}` : "");
		root.innerHTML = `<h1 style="margin-bottom:16px">Wallet</h1>
			<div class="card cx-card-gap"><p class="muted small">Loyalty points</p><p style="font-size:32px;font-weight:700">${
				b.loyalty_points
			}</p></div>
			${section(
				"Memberships",
				b.memberships,
				(m) =>
					`<div class="cx-row"><span>${esc(
						m.plan
					)}</span><span class="muted small">${until(m.end_date)}</span></div>`
			)}
			${section(
				"Packages",
				b.packages,
				(p) =>
					`<div class="cx-row"><span>${esc(
						p.package
					)}<br><span class="muted small">${until(p.expiry_date)}</span></span><span>${
						p.balance_sessions
					} left</span></div>`
			)}
			${section(
				"Gift cards",
				b.gift_cards,
				(g) =>
					`<div class="cx-row"><span>${esc(
						g.card_code
					)}<br><span class="muted small">${until(
						g.expiry_date
					)}</span></span><span>${money(g.balance)}</span></div>`
			)}`;
	}

	async function profile() {
		if (needAccount("/profile")) return;
		const root = main(
			`<h1 style="margin-bottom:16px">Profile</h1><div class="muted">Loading…</div>`,
			"/profile"
		);
		const p = await guard(() => call("profile"));
		if (!p) return;
		const genders = ["", "Female", "Male", "Other"]
			.map((g) => `<option ${g === (p.gender || "") ? "selected" : ""}>${g}</option>`)
			.join("");
		const branches = ["", ...state.cat.branches.map((b) => b.name)]
			.map(
				(b) =>
					`<option ${b === (p.preferred_branch || "") ? "selected" : ""}>${esc(
						b
					)}</option>`
			)
			.join("");
		root.innerHTML = `<h1 style="margin-bottom:16px">Profile</h1><div class="card"><div class="columns">
				<label class="field"><span class="field-label">Name</span><input value="${esc(
					p.client_name
				)}" disabled></label>
				<label class="field"><span class="field-label">Mobile</span><input value="${esc(
					p.mobile
				)}" disabled></label>
				<label class="field"><span class="field-label">Email</span><input value="${esc(
					p.email
				)}" disabled></label>
				<label class="field"><span class="field-label">Date of birth</span><input id="date_of_birth" type="date" value="${esc(
					p.date_of_birth
				)}"></label>
				<label class="field"><span class="field-label">Gender</span><select id="gender">${genders}</select></label>
				<label class="field"><span class="field-label">Preferred branch</span><select id="preferred_branch">${branches}</select></label></div>
			<label class="field"><span class="field-label">Allergies</span><textarea id="allergies" rows="2">${esc(
				p.allergies
			)}</textarea></label>
			<label class="field"><span class="field-label">Preferences</span><textarea id="preferences" rows="2">${esc(
				p.preferences
			)}</textarea></label>
			<label class="check" style="margin-bottom:16px"><input type="checkbox" id="marketing_consent" ${
				p.marketing_consent ? "checked" : ""
			}> <span>Send me offers and news</span></label>
			<p class="muted small" style="margin-bottom:16px">To change your name, mobile or email, please contact reception.</p>
			<button class="btn btn-primary" id="save">Save</button></div>`;
		root.querySelector("#save").onclick = () =>
			guard(async () => {
				const value = (id) => root.querySelector(`#${id}`).value || null;
				await call(
					"update_profile",
					{
						values: {
							date_of_birth: value("date_of_birth"),
							gender: value("gender"),
							preferred_branch: value("preferred_branch"),
							allergies: value("allergies"),
							preferences: value("preferences"),
							marketing_consent: root.querySelector("#marketing_consent").checked
								? 1
								: 0,
						},
					},
					{ post: true }
				);
				toast("Saved");
			});
	}

	/* Routing */
	function route() {
		const [page_, arg] = location.hash.replace(/^#\/?/, "").split("/");
		const name = decodeURIComponent(arg || "");
		((
			{ time: times, confirm: confirmBooking, signin, bookings, visits, wallet, profile }[
				page_
			] ||
			(page_ === "booked" && (() => booked(name))) ||
			(page_ === "move" && (() => move(name))) ||
			(page_ === "rate" && (() => rate(name))) ||
			services
		)());
	}

	async function start() {
		document.getElementById("sprite").innerHTML = await (
			await fetch("/assets/biz_spa/icons/biz_spa_lucide.svg")
		).text();
		[state.me, state.cat] = await Promise.all([call("me"), call("catalog")]);
		loadDraft();
		const known = new Set(state.cat.services.map((s) => s.name));
		flow.services = flow.services.filter((s) => known.has(s));
		if (!state.cat.branches.some((b) => b.name === flow.branch))
			flow.branch = state.cat.default_branch || state.cat.branches[0]?.name || "";
		window.addEventListener("hashchange", route);
		route();
	}
	start().catch(() => {
		app.innerHTML = `<div class="empty">The booking site isn't available right now. Please try again shortly.</div>`;
	});
})();
