// Search results grouped by category (pure functions: no page, no network).
// Used by home.js in the browser and by tests/test_group_results.js in Node.
//
// A result is { id, name, url, category, score }:
//   category  display group key ("science", "sport", … or "other")
//   score     how well it matches the query; higher is better
// It is never given tags: tags are not shown to people.

(function (root) {
	// Group results into one box per category, ranked by match.
	// Returns [{ category, best_score, interests: [result, …] }]:
	//  - each interest appears once, with its best score if it came in more than once
	//  - interests inside a box: best score first (ties: name A–Z)
	//  - boxes: best interest's score first (ties: category key A–Z)
	//  - categories with no matches are left out
	function groupByCategory(results) {
		// Keep each interest's best score
		const best = new Map();
		for (const r of results) {
			const seen = best.get(r.id);
			if (!seen || r.score > seen.score) best.set(r.id, r);
		}

		// One box per category
		const boxes = new Map();
		for (const r of best.values()) {
			if (!boxes.has(r.category)) boxes.set(r.category, []);
			boxes.get(r.category).push(r);
		}

		const byScore = (a, b) => b.score - a.score || a.name.localeCompare(b.name);
		return [...boxes.entries()]
			.map(([category, interests]) => {
				interests.sort(byScore);
				return { category, best_score: interests[0].score, interests };
			})
			.sort((a, b) => b.best_score - a.best_score || a.category.localeCompare(b.category));
	}

	// Turn /api/discover's groups [{ categories, interests: [{ id, name, url, category?, score? }] }]
	// into flat results for groupByCategory().
	//  - category: the interest's OWN category from the backend, mapped to a group by
	//    categoryOf(); "other" if it has none (untagged)
	//  - score: the backend's match score
	// FALLBACK (marked, for older responses without those fields): use the tag group's
	// first known category, and a score from position (earlier = better).
	function flattenTagGroups(groups, categoryOf) {
		const out = [];
		groups.forEach((g, gi) => {
			const groupCategory = (g.categories || []).map(categoryOf).find(Boolean) || "other";
			g.interests.forEach((item, ii) => {
				const hasOwn = "category" in item;
				out.push({
					id: item.id,
					name: item.name,
					url: item.url,
					category: hasOwn ? (categoryOf(item.category) || "other") : groupCategory,
					score: typeof item.score === "number" ? item.score : (groups.length - gi) * 1000 - ii,
				});
			});
		});
		return out;
	}

	// Put category-name matches first ("science" -> the Science box with ALL its
	// interests), then the ranked boxes. categoryBoxes: [{ category, match, interests }]
	// in the backend's order (exact, alias, prefix). An interest shown in a category
	// box is left out of the ranked boxes, so it appears exactly once; ranked boxes
	// left empty are dropped. Category boxes are kept even when empty, so the page
	// can offer to create the first interest there.
	function withCategoryMatches(categoryBoxes, rankedBoxes) {
		const shown = new Set();
		const first = categoryBoxes.map((b) => {
			b.interests.forEach((i) => shown.add(i.id));
			return { category: b.category, match: b.match, isCategoryMatch: true, interests: b.interests };
		});
		const firstKeys = new Set(first.map((b) => b.category));
		const rest = rankedBoxes
			.filter((b) => !firstKeys.has(b.category))
			.map((b) => ({ ...b, interests: b.interests.filter((i) => !shown.has(i.id)) }))
			.filter((b) => b.interests.length);
		return [...first, ...rest];
	}

	const api = { groupByCategory, flattenTagGroups, withCategoryMatches };
	if (typeof module !== "undefined" && module.exports) module.exports = api;
	else root.GroupResults = api;
})(this);
