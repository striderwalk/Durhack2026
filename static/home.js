// Home page: resting carousel, category cards, category-grouped search, and create.
// The state is worked out from two values only (see render()):
//   isSearchMode  the person has clicked or focused the search
//   query         what is typed
(function () {
	const SEARCH_DEBOUNCE_MS = 250;  // wait for a pause in typing before searching
	const PILLS_PER_BOX = 8;         // more than this collapse behind "+N more"
	const TAG_DEBOUNCE_MS = 120;
	const MAX_TAGS = 8;
	const TAG_MIN = 2, TAG_MAX = 24;
	const NAME_MIN = 2, NAME_MAX = 40, DESC_MAX = 200;
	const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

	const $ = (id) => document.getElementById(id);
	const home = $("home");
	const input = $("search-input");
	const dropdown = $("search-results");
	const status = $("search-status");
	const noteText = $("groups-note-text");
	const createLink = $("groups-create");
	const retryButton = $("groups-retry");
	const nameInput = $("interest-name");  // null when signed out (no create form)
	const categoriesEl = $("categories");
	const resultsEl = $("results");
	const panels = home.querySelectorAll(".panel");
	// Category names and colours from colours.py (the single source):
	// { categories: {backend slug: group key}, groups: {group key: {name, colour}} }
	const PALETTE = JSON.parse($("category-palette").textContent);
	const slugify = (name) => name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");

	let isSearchMode = false;  // clicked or focused the search
	let isCreating = false;    // chose "Create a new interest"
	let nameEdited = false;
	let checkSimilar = () => {};  // replaced by setUpCreateForm() when the form exists
	let updateNamePreview = () => {};  // likewise
	let ignoreFocus = false;

	// ---------- Small helpers ----------

	// Run fn only after `ms` without another call
	function debounce(fn, ms) {
		let t;
		const d = (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
		d.cancel = () => clearTimeout(t);
		return d;
	}

	// Fetch JSON, cancelling the previous request from the same caller (AbortController).
	// Returns the data, null on error, or undefined if a newer request replaced it.
	function latestFetcher() {
		let controller;
		return async (url) => {
			controller?.abort();
			controller = new AbortController();
			try {
				const res = await fetch(url, { signal: controller.signal });
				return res.ok ? res.json() : null;
			} catch (e) {
				if (e.name === "AbortError") return undefined;
				return null;
			}
		};
	}

	// Make an element: el("a", { href: "/" }, "text")
	function el(tag, props = {}, ...children) {
		const node = document.createElement(tag);
		Object.entries(props).forEach(([k, v]) => {
			if (k === "class") node.className = v;
			else if (k in node && !k.includes("-")) node[k] = v;
			else node.setAttribute(k, v);
		});
		node.append(...children);
		return node;
	}

	// Wrap the matching part of `text` in <mark>
	function highlight(text, q) {
		const i = text.toLowerCase().indexOf(q);
		if (i < 0 || !q) return document.createTextNode(text);
		const frag = document.createDocumentFragment();
		frag.append(text.slice(0, i), el("mark", {}, text.slice(i, i + q.length)), text.slice(i + q.length));
		return frag;
	}

	// ---------- State ----------

	// Work out the state from isSearchMode and the query, and show it
	function render() {
		const hasQuery = input.value.trim() !== "";
		let state = "initial";                     // State 1: resting
		if (isCreating) state = "create";
		else if (hasQuery) state = "results";      // State 3: typing (stays, whatever the focus)
		else if (isSearchMode) state = "search";   // State 2: category cards
		if (home.dataset.state === state) return;

		const wasInitial = home.dataset.state === "initial";
		home.dataset.state = state;
		panels.forEach((p) => { p.inert = !p.dataset.for.split(" ").includes(state); });
		if (state === "search") showCategories();
		if (wasInitial && window.scrollY > 0) window.scrollTo({ top: 0, behavior: reduceMotion ? "auto" : "smooth" });
	}

	function enterSearchMode() {
		if (ignoreFocus) return;
		isSearchMode = true;
		render();
	}

	// Back to State 1 (Escape, the clear button, or leaving the search while it's empty)
	function leaveSearch() {
		input.value = "";
		isSearchMode = false;
		isCreating = false;
		nameEdited = false;
		updateResults.cancel();
		hideDropdown();
		status.textContent = "";
		showCategories();
		render();
	}

	// Is this element part of the search area (search bar, boxes, create form)?
	const inSearchArea = (node) => !!node?.closest?.("[data-search-area]");

	// Clicking outside the search area with an empty query closes search mode.
	// Clicks on a card or pill are inside, so they never collapse the view first.
	document.addEventListener("pointerdown", (event) => {
		if (!isSearchMode || isCreating || input.value.trim() || inSearchArea(event.target)) return;
		isSearchMode = false;
		render();
	});

	// Same for keyboard: tabbing out of the search area with an empty query
	home.addEventListener("focusout", (event) => {
		const next = event.relatedTarget;
		if (!next || inSearchArea(next) || isCreating || input.value.trim()) return;
		isSearchMode = false;
		render();
	});

	// ---------- Dropdown: interests whose names match (every keystroke) ----------
	const fetchMatches = latestFetcher();
	let matches = [];
	let active = -1;

	async function updateDropdown(raw) {
		const q = raw.trim().toLowerCase();
		if (!q) { hideDropdown(); return; }
		const data = await fetchMatches(`/api/interests?q=${encodeURIComponent(q)}`);
		if (data === undefined || input.value.trim().toLowerCase() !== q) return;
		matches = data?.results || [];
		if (!matches.length || document.activeElement !== input) { hideDropdown(); return; }

		active = -1;
		// Names only: tags are never shown
		dropdown.replaceChildren(...matches.map((item, i) => {
			const li = el("li", { id: `result-${i}`, role: "option", "aria-selected": "false" },
				el("span", { class: "result-dot" }),
				el("span", {}, highlight(item.name, q)));
			li.addEventListener("pointerdown", (e) => e.preventDefault());
			li.addEventListener("click", () => choose(i));
			return li;
		}));
		dropdown.hidden = false;
		input.setAttribute("aria-expanded", "true");
		input.removeAttribute("aria-activedescendant");
	}

	function hideDropdown() {
		dropdown.hidden = true;
		active = -1;
		input.setAttribute("aria-expanded", "false");
		input.removeAttribute("aria-activedescendant");
	}

	function setActive(i) {
		const items = dropdown.children;
		if (!items.length) return;
		active = (i + items.length) % items.length;
		[...items].forEach((li, n) => li.setAttribute("aria-selected", String(n === active)));
		items[active].scrollIntoView({ block: "nearest" });
		input.setAttribute("aria-activedescendant", items[active].id);
	}

	function choose(i) {
		if (matches[i]) window.location.href = matches[i].url;
	}

	// ---------- CategoryBox (one look for cards and results) ----------

	// Group key ("science", …) for a backend category name, or undefined
	const categoryOf = (name) => PALETTE.categories[slugify(name || "")];

	// A new, empty box copied from the <template> that index.html renders from the
	// same Jinja macro as the category cards, so the two can't look different
	function makeBox(categoryKey) {
		const group = PALETTE.groups[categoryKey] || PALETTE.groups.other;
		const box = $("cat-box-template").content.firstElementChild.cloneNode(true);
		const headingId = "res-" + categoryKey;
		box.dataset.category = categoryKey;
		box.style.setProperty("--cat", group.colour);
		box.setAttribute("aria-labelledby", headingId);
		box.querySelector(".cat-head").id = headingId;
		box.querySelector(".cat-name").textContent = group.name;
		box.querySelectorAll("p.cat-more").forEach((p) => p.remove());
		return box;
	}

	// One pill, copied from the same macro's <template>
	function makePill(item, categoryName) {
		const li = $("cat-pill-template").content.firstElementChild.cloneNode(true);
		const link = li.querySelector("a");
		link.href = item.url;
		link.querySelector(".cat-pill-name").textContent = item.name;
		link.querySelector(".visually-hidden").textContent = ", " + categoryName;
		return li;
	}

	// Fill a box with interests, showing the first 8. Ranked boxes say "+N more";
	// a category-match box says "Show all N". Both expand in place.
	function fillBox(box, interests, isCategoryMatch = false) {
		const name = box.querySelector(".cat-name").textContent;
		box.querySelector(".cat-pills").replaceChildren(...interests.map((i) => makePill(i, name)));
		const extra = interests.length - PILLS_PER_BOX;
		const more = box.querySelector(".cat-expand");
		more.hidden = extra <= 0 || box.classList.contains("expanded");
		more.textContent = isCategoryMatch ? `Show all ${interests.length}` : `+${extra} more`;
		more.setAttribute("aria-label", isCategoryMatch
			? `Show all ${interests.length} ${name} interests`
			: `Show ${extra} more ${name} interests`);
	}

	// CategoryMatch: a small "Category" label by the name, so it's clear why this box
	// is first; and, if the category has no interests yet, an offer to create one
	function markCategoryMatch(box, match, q) {
		box.classList.add("is-category-match");
		box.querySelector(".cat-head").append(el("span", { class: "cat-badge" }, "Category"));
		if (match.interests.length) return;
		const create = el("a", { class: "cat-create", href: "#create" }, "Create a new interest");
		create.addEventListener("click", (event) => {
			event.preventDefault();
			nameEdited = false;
			goToCreate(q);
			nameInput?.focus({ preventScroll: true });
		});
		box.append(el("p", { class: "cat-more" }, "No interests here yet. ", create));
	}

	// "+N more" reveals the rest of a box
	resultsEl.addEventListener("click", (event) => {
		const more = event.target.closest(".cat-expand");
		if (!more) return;
		const box = more.closest(".cat-box");
		box.classList.add("expanded");
		more.hidden = true;
		box.querySelector(`.cat-pills li:nth-child(${PILLS_PER_BOX + 1}) a`)?.focus();
	});

	// ---------- Results: category boxes ranked by match (debounced) ----------
	const fetchDiscover = latestFetcher();

	// Empty query: the 10 category cards (rendered by the server)
	function showCategories() {
		setLoading(false);
		resultsEl.hidden = true;
		categoriesEl.hidden = false;
		setNote("Browse by category", false);
	}

	async function runSearch(raw) {
		const q = raw.trim();
		if (!q) { showCategories(); return; }
		setLoading(true);
		const data = await fetchDiscover(`/api/discover?q=${encodeURIComponent(q)}`);
		if (data === undefined) return;  // replaced by a newer search
		setLoading(false);
		if (input.value.trim() !== q) return;
		if (data === null) { showError(() => runSearch(input.value)); return; }

		// /api/discover groups by tag; regroup by each interest's own category and score
		// (static/groupResults.js; see docs/search-ranking-spec.md)
		const ranked = GroupResults.groupByCategory(GroupResults.flattenTagGroups(data.groups, categoryOf));
		// Categories the query names ("science", "maths", "mus") come first, with all
		// their interests. Backend fields mapped here: categoryMatches[].category is a
		// group key, .match is exact / alias / prefix.
		const named = (data.categoryMatches || []).map((m) => ({
			category: m.category,
			match: m.match,
			interests: m.interests.map((i) => ({ id: i.id, name: i.name, url: i.url, category: m.category })),
		}));
		showResults(q, GroupResults.withCategoryMatches(named, ranked));
	}
	const updateResults = debounce(runSearch, SEARCH_DEBOUNCE_MS);

	// Show the ranked boxes, or the empty state
	function showResults(q, boxes) {
		categoriesEl.hidden = true;
		resultsEl.hidden = false;
		const count = boxes.reduce((n, b) => n + b.interests.length, 0);

		if (!boxes.length) {
			resultsEl.replaceChildren(el("p", { class: "results-empty" }, "No matches yet. Try a broader word."));
			setNote("", true);
			status.textContent = "No matches yet.";
			return;
		}

		resultsEl.replaceChildren(...boxes.map((b) => {
			const box = makeBox(b.category);
			if (b.isCategoryMatch) markCategoryMatch(box, b, q);
			fillBox(box, b.interests, b.isCategoryMatch);
			return box;
		}));
		setNote(`Interests matching “${q}”`, true);
		status.textContent = `${count} ${count === 1 ? "interest" : "interests"} in ${boxes.length} ${boxes.length === 1 ? "category" : "categories"}`;
		if (!reduceMotion) {
			resultsEl.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 180, easing: "ease-out" });
		}
	}

	// Dim the current boxes while a search runs, without removing them
	function setLoading(on) {
		if (on) resultsEl.setAttribute("aria-busy", "true");
		else resultsEl.removeAttribute("aria-busy");
	}

	// Error state: keep whatever is showing and offer a retry
	let retryAction = null;
	function showError(retry) {
		setLoading(false);
		setNote("Couldn't load interests. Check your connection and try again.", false);
		retryAction = retry;
		retryButton.hidden = false;
		status.textContent = "Couldn't load interests.";
	}
	retryButton.addEventListener("click", () => retryAction?.());

	// The line above the boxes, and whether to offer "Create a new interest"
	function setNote(text, offerCreate) {
		retryButton.hidden = true;
		noteText.textContent = text;
		noteText.hidden = !text;
		createLink.hidden = !offerCreate;
	}

	// Open the create form, pre-filled with what was typed
	function goToCreate(query) {
		isCreating = true;
		isSearchMode = true;
		hideDropdown();
		render();
		$("create-title").textContent = query ? `No match for “${query}”. Create it?` : "Create an interest";
		if (nameInput && !nameEdited) {
			nameInput.value = query;
			updateNamePreview();
			checkSimilar();
		}
	}

	// ---------- Search input events ----------
	function onQuery() {
		isCreating = false;
		isSearchMode = true;
		if (!input.value.trim()) {
			// Cleared by typing: back to the category cards
			hideDropdown();
			status.textContent = "";
			updateResults.cancel();
			showCategories();
		} else {
			updateDropdown(input.value);
			updateResults(input.value);
		}
		render();
	}

	input.addEventListener("focus", () => {
		enterSearchMode();
		if (input.value.trim()) updateDropdown(input.value);
	});
	input.addEventListener("click", enterSearchMode);
	input.addEventListener("blur", hideDropdown);
	input.addEventListener("input", onQuery);

	input.addEventListener("keydown", (e) => {
		const open = !dropdown.hidden;
		switch (e.key) {
			case "ArrowDown":
				e.preventDefault();
				if (open) setActive(active + 1);
				else updateDropdown(input.value);
				break;
			case "ArrowUp":
				if (open) { e.preventDefault(); setActive(active - 1); }
				break;
			case "Enter":
				e.preventDefault();
				if (open && active >= 0) choose(active);
				else if (isCreating) $("interest-desc")?.focus();
				else if (input.value.trim()) { hideDropdown(); updateResults.cancel(); runSearch(input.value); }
				break;
		}
	});

	// Escape in the search bar or the boxes: close the dropdown first, then back to resting
	document.addEventListener("keydown", (e) => {
		if (e.key !== "Escape" || e.defaultPrevented) return;
		if (!e.target.closest?.("#search-form, #explore")) return;
		if (!dropdown.hidden) { hideDropdown(); return; }
		if (home.dataset.state === "initial") return;
		leaveSearch();
		ignoreFocus = true;
		input.focus();
		ignoreFocus = false;
	});

	$("search-form").addEventListener("submit", (e) => e.preventDefault());

	// The clear button: back to resting, keeping focus on the input for keyboard users
	$("search-close").addEventListener("click", () => {
		leaveSearch();
		ignoreFocus = true;
		input.focus();
		ignoreFocus = false;
	});

	createLink.addEventListener("click", (event) => {
		event.preventDefault();
		nameEdited = false;
		goToCreate(input.value.trim());
		nameInput?.focus({ preventScroll: true });
	});

	// ---------- Resting state: carousel chips and the three options ----------

	// A carousel chip searches for that interest
	home.querySelectorAll(".chip").forEach((chip) => {
		chip.addEventListener("click", () => {
			input.value = chip.dataset.interest;
			ignoreFocus = true;
			input.focus();
			ignoreFocus = false;
			onQuery();
		});
	});

	// "Browse" opens the category cards; "Add an interest" opens the create form
	home.querySelectorAll("[data-go]").forEach((card) => {
		card.addEventListener("click", (e) => {
			e.preventDefault();
			if (card.dataset.go === "search") {
				input.focus();
			} else {
				nameEdited = false;
				goToCreate(input.value.trim());
				nameInput?.focus({ preventScroll: true });
			}
		});
	});

	// ---------- Create form (only there when signed in) ----------
	if (nameInput) setUpCreateForm();

	function setUpCreateForm() {
		const form = $("create-form");
		const descInput = $("interest-desc");
		const nameError = $("interest-name-error");
		const tagError = $("tag-error");
		const createStatus = $("create-status");
		const submitButton = $("create-submit");

		// The name as it will be saved: title case (static/titleCase.js), the same
		// rules the backend applies. The duplicate check and the request use this.
		const savedName = () => TitleCase.toInterestTitleCase(nameInput.value);

		// NamePreview: "Will be saved as: Rock Climbing", updated while typing.
		// The field itself is only rewritten on blur and submit, so the cursor never jumps.
		const namePreview = $("interest-name-preview");
		updateNamePreview = function () {
			const name = savedName();
			namePreview.hidden = !name;
			namePreview.textContent = name ? `Will be saved as: ${name}` : "";
		};

		nameInput.addEventListener("input", () => {
			nameEdited = true;
			nameError.textContent = "";
			updateNamePreview();
			checkSimilarSoon();
		});

		// Leaving the field: show the converted name in it
		nameInput.addEventListener("blur", () => {
			const name = savedName();
			if (name !== nameInput.value) nameInput.value = name;
			updateNamePreview();
		});

		// Description counter
		descInput.addEventListener("input", () => {
			form.querySelector("[data-desc-count]").textContent = descInput.value.length;
		});

		// "Did you mean one of these?": up to 3 existing interests with similar names,
		// from the same search the home page uses (GET /api/interests)
		const fetchSimilar = latestFetcher();
		let exactMatch = null;
		checkSimilar = async function () {
			const q = savedName();
			const box = $("similar");
			if (q.length < NAME_MIN) { box.hidden = true; exactMatch = null; return; }
			const data = await fetchSimilar(`/api/interests?q=${encodeURIComponent(q)}`);
			if (data === undefined || savedName() !== q) return;
			const results = data?.results || [];
			const found = results.slice(0, 3);
			// Duplicate check ignores case: "astronomy" matches "Astronomy"
			exactMatch = results.find((i) => i.name.toLowerCase() === q.toLowerCase()) || null;
			$("similar-list").replaceChildren(...found.map((item) => {
				const add = el("button", { type: "button", class: "btn btn-sm btn-outline-primary" }, "Add this instead");
				add.setAttribute("aria-label", `Add ${item.name} to your interests instead`);
				add.addEventListener("click", () => addExisting(item, add));
				return el("li", {}, el("a", { href: item.url }, item.name), add);
			}));
			box.hidden = !found.length;
		};
		const checkSimilarSoon = debounce(checkSimilar, TAG_DEBOUNCE_MS * 2);

		// Add an existing interest to your profile, then open it
		async function addExisting(item, button) {
			button.disabled = true;
			createStatus.textContent = `Adding ${item.name}…`;
			try {
				await addToMyInterests(item.name);
				window.location.href = item.url;
			} catch {
				button.disabled = false;
				createStatus.textContent = "Couldn't add it. Please try again.";
			}
		}

		// Check the fields; returns true if the form can be sent
		function validate() {
			const name = savedName();
			nameError.textContent = "";
			if (name.length < NAME_MIN || name.length > NAME_MAX) {
				nameError.textContent = `Give it a name of ${NAME_MIN} to ${NAME_MAX} characters.`;
				nameInput.focus();
				return false;
			}
			if (exactMatch) {
				nameError.textContent = `“${exactMatch.name}” already exists. Add it instead, or choose another name.`;
				nameInput.focus();
				return false;
			}
			if (descInput.value.length > DESC_MAX) return false;
			return true;
		}

		// Create through POST /interests/new, add it to your profile, then open it
		form.addEventListener("submit", async (event) => {
			event.preventDefault();
			// Send the converted name (the backend converts it again, so this can't be skipped)
			nameInput.value = savedName();
			updateNamePreview();
			if (!validate()) return;
			submitButton.disabled = true;
			createStatus.textContent = "Creating…";
			try {
				const response = await fetch(form.action, { method: "POST", body: new FormData(form) });
				// The backend answers with a redirect to the new interest's page
				if (!response.ok || !response.url.includes("/interests/")) throw new Error(response.status);
				await addToMyInterests(savedName());
				createStatus.textContent = "Created. Opening it…";
				window.location.href = response.url;
			} catch {
				submitButton.disabled = false;
				createStatus.textContent = "Couldn't create it. Check your connection and try again.";
			}
		});

		// ---------- Tag chips ----------
		const tagBox = $("tag-input");
		const tagEntry = $("tag-entry");
		const tagChips = $("tag-chips");
		const tagList = $("tag-suggestions");
		const tagValues = $("tag-values");
		const fetchTags = latestFetcher();
		const chosen = [];
		let tagOptions = [];
		let tagActive = -1;

		// Lower case, single spaces, no leading #
		const normalise = (s) => s.trim().toLowerCase().replace(/^#+/, "").replace(/\s+/g, " ");

		function renderChosen() {
			tagChips.replaceChildren(...chosen.map((name) => {
				const remove = el("button", { type: "button", "aria-label": `Remove tag ${name}` }, "×");
				remove.addEventListener("click", () => { removeTag(name); tagEntry.focus(); });
				return el("li", { class: "tag-chip" }, "#" + name, remove);
			}));
			tagValues.replaceChildren(...chosen.map((name) => el("input", { type: "hidden", name: "tags", value: name })));
			const full = chosen.length >= MAX_TAGS;
			tagEntry.disabled = full;
			tagEntry.placeholder = full ? "That’s the maximum" : chosen.length ? "Add another" : "Add a tag";
		}

		function addTag(name) {
			const tag = normalise(name);
			tagError.textContent = "";
			if (!tag) return;
			if (tag.length < TAG_MIN || tag.length > TAG_MAX) {
				tagError.textContent = `Tags need ${TAG_MIN} to ${TAG_MAX} characters.`;
				return;
			}
			if (chosen.includes(tag)) { tagError.textContent = `#${tag} is already added.`; return; }
			if (chosen.length >= MAX_TAGS) { tagError.textContent = `Up to ${MAX_TAGS} tags.`; return; }
			chosen.push(tag);
			tagEntry.value = "";
			renderChosen();
			refreshTagSuggestions();
		}

		function removeTag(name) {
			const i = chosen.indexOf(name);
			if (i >= 0) chosen.splice(i, 1);
			tagError.textContent = "";
			renderChosen();
		}

		async function refreshTagSuggestions() {
			const q = normalise(tagEntry.value);
			const params = new URLSearchParams({ q });
			chosen.forEach((t) => params.append("exclude", t));
			const data = await fetchTags(`/api/tags?${params}`);
			if (data === undefined || normalise(tagEntry.value) !== q || document.activeElement !== tagEntry) return;

			tagOptions = (data?.results || []).map((t) => ({ name: t.name, count: t.count, isNew: false }));
			if (q.length >= TAG_MIN && !tagOptions.some((t) => t.name === q) && !chosen.includes(q)) {
				tagOptions.push({ name: q, isNew: true });
			}
			if (!tagOptions.length) { hideTagSuggestions(); return; }

			tagActive = q ? 0 : -1;
			tagList.replaceChildren(...tagOptions.map((t, i) => {
				const li = t.isNew
					? el("li", { id: `tag-opt-${i}`, role: "option" }, el("span", { class: "new-tag" }, `Create “#${t.name}”`))
					: el("li", { id: `tag-opt-${i}`, role: "option" },
						el("span", {}, "#", highlight(t.name, q)),
						el("span", { class: "count" }, t.count === 1 ? "1 interest" : `${t.count} interests`));
				li.addEventListener("pointerdown", (e) => e.preventDefault());
				li.addEventListener("click", () => { addTag(t.name); tagEntry.focus(); });
				return li;
			}));
			tagList.hidden = false;
			tagEntry.setAttribute("aria-expanded", "true");
			setTagActive(tagActive);
		}
		const refreshTagsSoon = debounce(refreshTagSuggestions, TAG_DEBOUNCE_MS);

		function setTagActive(i) {
			const items = tagList.children;
			if (!items.length) return;
			tagActive = i < 0 ? -1 : (i + items.length) % items.length;
			[...items].forEach((li, n) => li.setAttribute("aria-selected", String(n === tagActive)));
			if (tagActive >= 0) {
				items[tagActive].scrollIntoView({ block: "nearest" });
				tagEntry.setAttribute("aria-activedescendant", items[tagActive].id);
			} else {
				tagEntry.removeAttribute("aria-activedescendant");
			}
		}

		function hideTagSuggestions() {
			tagList.hidden = true;
			tagActive = -1;
			tagEntry.setAttribute("aria-expanded", "false");
			tagEntry.removeAttribute("aria-activedescendant");
		}

		tagBox.addEventListener("click", (e) => { if (e.target === tagBox) tagEntry.focus(); });
		tagEntry.addEventListener("focus", refreshTagSuggestions);
		tagEntry.addEventListener("blur", hideTagSuggestions);
		tagEntry.addEventListener("input", () => {
			// A typed comma adds the tag before it
			if (tagEntry.value.includes(",")) {
				const parts = tagEntry.value.split(",");
				tagEntry.value = parts.pop();
				parts.forEach(addTag);
			}
			refreshTagsSoon();
		});

		tagEntry.addEventListener("keydown", (e) => {
			const open = !tagList.hidden;
			switch (e.key) {
				case "ArrowDown":
					e.preventDefault();
					if (open) setTagActive(tagActive + 1); else refreshTagSuggestions();
					break;
				case "ArrowUp":
					if (open) { e.preventDefault(); setTagActive(tagActive - 1); }
					break;
				case "Enter":
				case ",":
					e.preventDefault();  // never submit the form from here
					if (e.key === "Enter" && open && tagActive >= 0) addTag(tagOptions[tagActive].name);
					else if (tagEntry.value.trim()) addTag(tagEntry.value);
					break;
				case "Backspace":
					if (!tagEntry.value && chosen.length) removeTag(chosen[chosen.length - 1]);
					break;
				case "Escape":
					if (open) { e.preventDefault(); e.stopPropagation(); hideTagSuggestions(); }
					break;
			}
		});

		renderChosen();
	}

	// Add an interest (by its exact name) to the signed-in user's profile.
	// Uses the backend's POST /update-account, which redirects to /account when done.
	async function addToMyInterests(name) {
		const body = new URLSearchParams({ "new-interests": name });
		const response = await fetch("/update-account", { method: "POST", body });
		if (!response.ok || !response.url.endsWith("/account")) throw new Error(response.status);
	}

	// ---------- Start ----------
	panels.forEach((p) => { p.inert = !p.dataset.for.split(" ").includes("initial"); });

	// /?q=… (e.g. from a tag on an interest page) opens straight into results,
	// and /?q=…&create=1 (from the profile's "Create a new interest") opens the form
	const params = new URLSearchParams(location.search);
	const startQuery = params.get("q");
	if (startQuery && params.get("create")) {
		input.value = startQuery;
		nameEdited = false;
		goToCreate(startQuery);
		nameInput?.focus({ preventScroll: true });
	} else if (startQuery) {
		input.value = startQuery;
		isSearchMode = true;
		render();
		runSearch(startQuery);
	}
})();
