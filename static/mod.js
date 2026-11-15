// Moderator panel (/mod): sends each action to the moderator API, asking first for
// destructive ones. The server checks the moderator allowlist on every call.

(function () {
	const confirmDialog = document.getElementById("mod-confirm");

	// Ask "Are you sure?" in a modal dialog; resolves true or false
	function askFirst(text) {
		return new Promise((resolve) => {
			document.getElementById("mod-confirm-text").textContent = text;
			const go = document.getElementById("mod-confirm-go");
			const done = (answer) => { go.onclick = null; confirmDialog.onclose = null; resolve(answer); };
			go.onclick = () => { confirmDialog.close(); done(true); };
			confirmDialog.onclose = () => done(false);
			confirmDialog.showModal();
		});
	}
	confirmDialog.querySelectorAll("[data-close]").forEach((b) => b.addEventListener("click", () => confirmDialog.close()));

	// ModActionForm: collect the fields, confirm if needed, POST as JSON, then reload
	document.querySelectorAll("form[data-mod-action]").forEach((form) => {
		form.addEventListener("submit", async (event) => {
			event.preventDefault();
			const error = form.querySelector(".safety-error");
			error.textContent = "";
			const required = [...form.querySelectorAll("[required]")].find((f) => !f.value.trim());
			if (required) { error.textContent = "Fill in the reason first."; required.focus(); return; }
			if (form.dataset.confirm && !(await askFirst(form.dataset.confirm))) return;

			const url = event.submitter?.getAttribute("formaction") || form.dataset.modAction;
			const body = Object.fromEntries(new FormData(form));
			try {
				const response = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
				const data = await response.json().catch(() => ({}));
				if (!response.ok) { error.textContent = data.error || `That didn't work (${response.status}).`; return; }
				location.reload();
			} catch {
				error.textContent = "Couldn't reach the server. Check your connection and try again.";
			}
		});
	});

	// Ages: "3 hours ago" (the exact time stays in the tooltip)
	document.querySelectorAll("time.mod-age").forEach((t) => {
		const when = new Date(t.dateTime);
		if (isNaN(when)) return;
		const minutes = Math.round((Date.now() - when) / 60000);
		const future = minutes < 0, m = Math.abs(minutes);
		const text = m < 60 ? `${m} min` : m < 1440 ? `${Math.round(m / 60)} h` : `${Math.round(m / 1440)} days`;
		t.title = t.textContent;
		t.textContent = future ? `in ${text}` : `${text} ago`;
	});
})();
