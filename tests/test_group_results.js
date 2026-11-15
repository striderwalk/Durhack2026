// Unit tests for static/groupResults.js
// Run from the project folder:   node --test tests/test_group_results.js

const test = require("node:test");
const assert = require("node:assert/strict");
const { groupByCategory, flattenTagGroups, withCategoryMatches } = require("../static/groupResults.js");

const r = (id, name, category, score) => ({ id, name, url: `/interests/${id}`, category, score });

test("each interest keeps its best score", () => {
	const boxes = groupByCategory([r(1, "Chess", "recreation", 0.4), r(1, "Chess", "recreation", 0.9)]);
	assert.equal(boxes.length, 1);
	assert.equal(boxes[0].interests.length, 1);
	assert.equal(boxes[0].interests[0].score, 0.9);
});

test("an interest appears in exactly one box", () => {
	const boxes = groupByCategory([r(1, "Chess", "recreation", 0.5), r(1, "Chess", "recreation", 0.7), r(2, "Rugby", "sport", 0.6)]);
	const ids = boxes.flatMap((b) => b.interests.map((i) => i.id));
	assert.deepEqual(ids.sort(), [1, 2]);
});

test("boxes are ordered by their best interest", () => {
	const boxes = groupByCategory([
		r(1, "Rugby", "sport", 0.5),
		r(2, "Chemistry", "science", 0.95),
		r(3, "Running", "sport", 0.6),
		r(4, "Jazz", "music", 0.8),
	]);
	assert.deepEqual(boxes.map((b) => b.category), ["science", "music", "sport"]);
	assert.deepEqual(boxes.map((b) => b.best_score), [0.95, 0.8, 0.6]);
});

test("interests inside a box are ordered by score, then name", () => {
	const boxes = groupByCategory([r(1, "Rugby", "sport", 0.5), r(2, "Rowing", "sport", 0.9), r(3, "Archery", "sport", 0.5)]);
	assert.deepEqual(boxes[0].interests.map((i) => i.name), ["Rowing", "Archery", "Rugby"]);
});

test("categories with no matches are left out", () => {
	assert.deepEqual(groupByCategory([]), []);
	const boxes = groupByCategory([r(1, "Jazz", "music", 1)]);
	assert.deepEqual(boxes.map((b) => b.category), ["music"]);
});

test("fallback: tag groups become ranked, category-grouped results", () => {
	const categoryOf = (name) => ({ "Music and performing arts": "music", "Sport and physical activities": "sport" })[name];
	const tagGroups = [
		{ categories: ["Music and performing arts"], interests: [{ id: 1, name: "Jazz" }, { id: 2, name: "Choir" }] },
		{ categories: ["Sport and physical activities"], interests: [{ id: 3, name: "Rowing" }] },
		{ categories: [], interests: [{ id: 4, name: "Unsorted" }] },
	];
	const boxes = groupByCategory(flattenTagGroups(tagGroups, categoryOf));
	assert.deepEqual(boxes.map((b) => b.category), ["music", "sport", "other"]);
	assert.deepEqual(boxes[0].interests.map((i) => i.name), ["Jazz", "Choir"]);
	// No tag names leak into the results
	assert.ok(boxes.every((b) => b.interests.every((i) => !("tags" in i))));
});

test("uses each interest's own category and score when the backend sends them", () => {
	const categoryOf = (name) => ({ "Arts and creative expression": "arts", "Engineering and invention": "technology" })[name];
	const tagGroups = [
		{ categories: ["Arts and creative expression"], interests: [
			{ id: 1, name: "Cyanotype Printing", category: "Arts and creative expression", score: 7 },
			{ id: 2, name: "3D Printing", category: "Engineering and invention", score: 9 },
			{ id: 3, name: "Untagged", category: null, score: 3 },
		] },
	];
	const boxes = groupByCategory(flattenTagGroups(tagGroups, categoryOf));
	assert.deepEqual(boxes.map((b) => b.category), ["technology", "arts", "other"]);
	assert.equal(boxes[0].interests[0].name, "3D Printing");
});

test("category-name matches come first, in the backend's order", () => {
	const ranked = groupByCategory([r(1, "Chemistry Club", "science", 3), r(2, "Rowing", "sport", 5)]);
	const named = [
		{ category: "science", match: "exact", interests: [r(1, "Chemistry Club", "science"), r(3, "Physics", "science")] },
		{ category: "music", match: "prefix", interests: [r(4, "Choir", "music")] },
	];
	const boxes = withCategoryMatches(named, ranked);
	assert.deepEqual(boxes.map((b) => b.category), ["science", "music", "sport"]);
	assert.equal(boxes[0].isCategoryMatch, true);
	assert.equal(boxes[2].isCategoryMatch, undefined);
});

test("an interest in a category-match box is never repeated in another box", () => {
	// Interest 1 is in the Science category box AND scored in a ranked Recreation box
	const ranked = groupByCategory([r(1, "Stargazing", "recreation", 4), r(5, "Hiking", "recreation", 2)]);
	const boxes = withCategoryMatches([{ category: "science", match: "exact", interests: [r(1, "Stargazing", "science")] }], ranked);
	const ids = boxes.flatMap((b) => b.interests.map((i) => i.id));
	assert.deepEqual(ids.sort(), [1, 5]);
	assert.deepEqual(boxes.map((b) => b.category), ["science", "recreation"]);
});

test("ranked boxes left empty are dropped; empty category-match boxes stay", () => {
	const ranked = groupByCategory([r(1, "Stargazing", "recreation", 4)]);
	const boxes = withCategoryMatches([
		{ category: "science", match: "exact", interests: [r(1, "Stargazing", "science")] },
		{ category: "practical", match: "prefix", interests: [] },
	], ranked);
	assert.deepEqual(boxes.map((b) => b.category), ["science", "practical"]);
	assert.equal(boxes[1].interests.length, 0);
});

test("no category match: the ranked boxes are unchanged", () => {
	const ranked = groupByCategory([r(1, "Chess", "recreation", 1)]);
	assert.deepEqual(withCategoryMatches([], ranked), ranked);
});
