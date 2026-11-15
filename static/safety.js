// Block and report (profile and interest pages) and unblock (Settings).
// The server checks every rule (moderation.py); this only sends the choices.

(function () {
	// Send JSON to the server; resolves with { ok, status, data }
	async function send(method, url, body) {
		try {
			const response = await fetch(url, {
				method,
				headers: { "Content-Type": "application/json" },
				body: body ? JSON.stringify(body) : undefined,
			});
			const data = await response.json().catch(() => ({}));
			// Banned meanwhile: reloading shows the ban screen
			if (response.status === 403 && data.error === "banned") location.reload();
			return { ok: response.ok, status: response.status, data };
		} catch {
			return { ok: false, status: 0, data: { error: "Couldn't reach the server. Check your connection and try again." } };
		}
	}

	// ---------- MoreMenu: the ⋯ button ----------
	document.querySelectorAll(".more-menu").forEach((menu) => {
		const toggle = menu.querySelector(".more-toggle");
		const list = menu.querySelector(".more-menu-list");
		const close = () => { list.hidden = true; toggle.setAttribute("aria-expanded", "false"); };
		toggle.addEventListener("click", () => {
			const open = list.hidden;
			list.hidden = !open;
			toggle.setAttribute("aria-expanded", String(open));
			if (open) list.querySelector("button").focus();
		});
		menu.addEventListener("keydown", (e) => { if (e.key === "Escape" && !list.hidden) { close(); toggle.focus(); } });
		document.addEventListener("click", (e) => { if (!menu.contains(e.target)) close(); });
		list.addEventListener("click", close);
	});

	// ---------- Dialogs ----------
	// Native modal <dialog>: keeps focus inside and closes with Escape
	document.querySelectorAll("[data-open-dialog]").forEach((button) => {
		button.addEventListener("click", () => {
			const dialog = document.getElementById(button.dataset.openDialog);
			dialog.querySelectorAll(".safety-error").forEach((p) => { p.textContent = ""; });
			dialog.showModal();
		});
	});
	document.querySelectorAll("dialog [data-close]").forEach((button) => {
		button.addEventListener("click", () => button.closest("dialog").close());
	});

	// ---------- ReportDialog ----------
	const reportDialog = document.getElementById("report-dialog");
	if (reportDialog) {
		const form = reportDialog.querySelector(".report-form");
		const done = reportDialog.querySelector(".report-done");
		const message = form.querySelector("textarea");
		const error = form.querySelector(".safety-error");
		message.addEventListener("input", () => { form.querySelector("[data-count]").textContent = message.value.length; });

		form.addEventListener("submit", async (event) => {
			event.preventDefault();
			const reason = form.querySelector("input[name='reason']:checked");
			if (!reason) { error.textContent = "Choose a reason."; return; }
			const submit = form.querySelector("button[type='submit']");
			submit.disabled = true;
			const result = await send("POST", "/api/flags", {
				target_type: reportDialog.dataset.targetType,
				target_id: Number(reportDialog.dataset.targetId),
				reason: reason.value,
				message: message.value.trim(),
			});
			submit.disabled = false;
			if (!result.ok) { error.textContent = result.data.error || "Couldn't send the report. Please try again."; return; }
			form.hidden = true;
			done.hidden = false;
			done.querySelector("button").focus();
		});
		// Ready for another report next time it opens
		reportDialog.addEventListener("close", () => {
			if (!done.hidden) { form.reset(); form.hidden = false; done.hidden = true; form.querySelector("[data-count]").textContent = "0"; }
		});
	}

	// ---------- BlockDialog ----------
	const blockDialog = document.getElementById("block-dialog");
	if (blockDialog) {
		blockDialog.querySelector("[data-confirm-block]").addEventListener("click", async (event) => {
			event.target.disabled = true;
			const result = await send("POST", "/api/blocks", { user_id: Number(blockDialog.dataset.userId) });
			if (result.ok) { location.href = "/"; return; }  // their profile is now hidden from you too
			event.target.disabled = false;
			blockDialog.querySelector(".safety-error").textContent = result.data.error || "Couldn't block. Please try again.";
		});
	}

	// ---------- Settings: Blocked users ----------
	const blockedList = document.getElementById("blocked-list");
	if (blockedList) {
		blockedList.addEventListener("click", async (event) => {
			const button = event.target.closest("[data-unblock]");
			if (!button) return;
			button.disabled = true;
			const row = button.closest("li");
			const status = document.getElementById("blocked-status");
			const result = await send("DELETE", `/api/blocks/${button.dataset.unblock}`);
			if (!result.ok) { button.disabled = false; status.textContent = "Couldn't unblock. Please try again."; return; }
			status.textContent = `Unblocked ${button.dataset.name}.`;
			row.remove();
			document.getElementById("blocked-empty").hidden = blockedList.children.length > 0;
		});
	}
})();
