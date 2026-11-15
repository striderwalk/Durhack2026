"""
Interest discovery: search, tag-based relations and grouping.

How a query becomes groupings:
  1. Interests whose names contain the query           (strongest signal)
  2. Tags whose names contain the query, plus the tags of the interests from 1
  3. Other interests sharing those tags                (scored by shared tags)
  4. Tags that often appear alongside them             (weaker, widens the net)
  5. Results are grouped under the tags that connect them best

Everything is done with a handful of aggregate queries, so it stays practical
as the number of interests and tags grows.
"""

from sqlalchemy import case, func, select
from sqlalchemy.orm import selectinload

from colours import GROUPS, category_slug, group_of, match_categories
from models import Interest, Tag, UserInterest, db, interest_tags, normalise_tag

# Scoring weights
NAME_MATCH = 3.0
TAG_EQUALS_QUERY = 2.5
TAG_MATCHES_QUERY = 2.0
TAG_FROM_NAME_MATCH = 1.0
CO_OCCURRING_TAG = 0.5

MIN_SCORE = 1.0  # a direct tag link, or two weaker co-occurring ones
MAX_RESULTS = 36
MAX_GROUPS = 6
MAX_PER_GROUP = 10
WIDEN_BELOW = 18  # only add co-occurring tags when direct results are thin


def interest_json(interest: Interest, score: float | None = None) -> dict:
	data = {
		"id": interest.interest_id,
		"name": interest.interest_name,
		"url": f"/interests/{interest.interest_id}",
		"tags": [t.tag_name for t in interest.tags],
	}
	if score is not None:
		# Search results only: the interest's own main category and its match score
		category = interest.category
		data["category"] = category.category_name if category else None
		data["score"] = round(score, 3)
	return data


def _contains(column, q):
	return func.lower(column).contains(q, autoescape=True)


def _starts_first(column, q):
	return case((func.lower(column).startswith(q, autoescape=True), 0), else_=1)


# ---------- Name search (dropdown) ----------

def search_interests(query: str, limit: int = 8) -> list[Interest]:
	q = query.strip().lower()
	if not q:
		return []
	stmt = (
		select(Interest)
		.where(_contains(Interest.interest_name, q))
		.order_by(_starts_first(Interest.interest_name, q), Interest.interest_name)
		.limit(limit)
		.options(selectinload(Interest.tags))
	)
	return list(db.session.scalars(stmt))


# ---------- Tag suggestions (create form) ----------

def suggest_tags(query: str, exclude=(), limit: int = 8) -> list[dict]:
	q = normalise_tag(query)
	usage = func.count(interest_tags.c.interest_id)
	stmt = (
		select(Tag, usage)
		.outerjoin(interest_tags, Tag.tag_id == interest_tags.c.tag_id)
		.group_by(Tag.tag_id)
		.options(selectinload(Tag.categories))
		.limit(limit)
	)
	excluded = [normalise_tag(e) for e in exclude if e]
	if excluded:
		stmt = stmt.where(Tag.tag_name.not_in(excluded))
	if q:
		stmt = stmt.where(_contains(Tag.tag_name, q)).order_by(
			_starts_first(Tag.tag_name, q), usage.desc(), Tag.tag_name
		)
	else:
		stmt = stmt.order_by(usage.desc(), Tag.tag_name)

	return [
		{
			"name": tag.tag_name,
			"count": count,
			"categories": [c.category_name for c in tag.categories],
		}
		for tag, count in db.session.execute(stmt)
	]


def get_or_create_tags(names) -> list[Tag]:
	"""Look up tags by name, creating any that don't exist yet (uncategorised)."""
	wanted = list(dict.fromkeys(n for n in (normalise_tag(x) for x in names) if n))
	if not wanted:
		return []
	# no_autoflush: callers may be building interests that aren't in the session yet
	with db.session.no_autoflush:
		existing = {t.tag_name: t for t in db.session.scalars(select(Tag).where(Tag.tag_name.in_(wanted)))}
	tags = []
	for name in wanted:
		tag = existing.get(name)
		if tag is None:
			tag = Tag(tag_name=name)
			db.session.add(tag)
		tags.append(tag)
	return tags


# ---------- Discovery (groupings) ----------

def discover(query: str) -> dict:
	q = query.strip().lower()
	if not q:
		return {"query": "", "nameMatches": 0, "groups": initial_groups()}

	name_ids = list(db.session.scalars(
		select(Interest.interest_id).where(_contains(Interest.interest_name, q)).limit(40)
	))

	# Tags to explore from, with how strongly each one points at the query
	tag_weight: dict[int, float] = {}
	for tag_id, tag_name in db.session.execute(
		select(Tag.tag_id, Tag.tag_name).where(_contains(Tag.tag_name, q)).limit(10)
	):
		tag_weight[tag_id] = TAG_EQUALS_QUERY if tag_name == normalise_tag(q) else TAG_MATCHES_QUERY
	if name_ids:
		for tag_id in db.session.scalars(
			select(interest_tags.c.tag_id).where(interest_tags.c.interest_id.in_(name_ids)).distinct()
		):
			tag_weight.setdefault(tag_id, TAG_FROM_NAME_MATCH)

	scores: dict[int, float] = {i: NAME_MATCH for i in name_ids}
	_score_by_tags(scores, tag_weight)

	if len(scores) < WIDEN_BELOW and tag_weight:
		related = _co_occurring_tags(tag_weight.keys(), limit=6)
		for tag_id in related:
			tag_weight[tag_id] = CO_OCCURRING_TAG
		_score_by_tags(scores, {t: CO_OCCURRING_TAG for t in related})

	relevant = [i for i in scores if scores[i] >= MIN_SCORE]
	top_ids = sorted(relevant, key=lambda i: -scores[i])[:MAX_RESULTS]
	interests = _load(top_ids)
	interests.sort(key=lambda i: (-scores[i.interest_id], i.interest_name))

	return {
		"query": query.strip(),
		"nameMatches": len(name_ids),
		"groups": group_interests(interests, tag_weight, scores),
		"categoryMatches": category_matches(q),
	}


def category_matches(query: str) -> list[dict]:
	"""
	Categories the query names ("science", "maths", "mus"; see
	colours.match_categories), best match first, each with ALL its interests,
	most popular first, then A-Z:
		[{"category": group key, "name", "match": "exact" | "alias" | "prefix",
		  "match_type": "category", "interests": [interest_json]}]
	"""
	matched = match_categories(query)
	if not matched:
		return []
	popularity = dict(db.session.execute(
		select(UserInterest.interest_id, func.count()).group_by(UserInterest.interest_id)
	).all())
	by_group: dict[str, list] = {key: [] for key, _how in matched}
	for interest in _load(list(db.session.scalars(select(Interest.interest_id)))):
		category = interest.category
		key = group_of(category_slug(category.category_name)) if category else None
		if key in by_group:
			by_group[key].append(interest)
	result = []
	for key, how in matched:
		members = sorted(by_group[key], key=lambda i: (-popularity.get(i.interest_id, 0), i.interest_name))
		result.append({
			"category": key,
			"name": GROUPS[key][0],
			"match": how,
			"match_type": "category",
			"interests": [{**interest_json(i), "category": i.category.category_name} for i in members],
		})
	return result


def _score_by_tags(scores: dict, tag_weight: dict) -> None:
	if not tag_weight:
		return
	rows = db.session.execute(
		select(interest_tags.c.interest_id, interest_tags.c.tag_id)
		.where(interest_tags.c.tag_id.in_(list(tag_weight)))
	)
	for interest_id, tag_id in rows:
		scores[interest_id] = scores.get(interest_id, 0) + tag_weight[tag_id]


def _co_occurring_tags(tag_ids, limit: int) -> list[int]:
	"""Tags that most often share an interest with any of `tag_ids`."""
	seed = list(tag_ids)
	a = interest_tags.alias("a")
	b = interest_tags.alias("b")
	stmt = (
		select(b.c.tag_id)
		.select_from(a.join(b, a.c.interest_id == b.c.interest_id))
		.where(a.c.tag_id.in_(seed), b.c.tag_id.not_in(seed))
		.group_by(b.c.tag_id)
		.order_by(func.count().desc())
		.limit(limit)
	)
	return list(db.session.scalars(stmt))


def _load(ids) -> list[Interest]:
	if not ids:
		return []
	stmt = (
		select(Interest)
		.where(Interest.interest_id.in_(ids))
		.options(selectinload(Interest.tags).selectinload(Tag.categories))
	)
	return list(db.session.scalars(stmt))


def initial_groups() -> list[dict]:
	"""A varied, random selection of tagged interests to explore from."""
	ids = list(db.session.scalars(
		select(Interest.interest_id)
		.where(Interest.interest_id.in_(select(interest_tags.c.interest_id)))
		.order_by(func.random())
		.limit(MAX_RESULTS)
	))
	return group_interests(_load(ids), min_size=2)


def group_interests(interests, tag_weight=None, scores=None, min_size=1) -> list[dict]:
	"""
	Greedily group interests under the tags that connect the most of them.
	Each interest appears once. With `tag_weight`, only those tags may head a
	group, and stronger tags win ties.
	"""
	weight = tag_weight or {}
	by_tag: dict[int, list] = {}
	tag_objs: dict[int, Tag] = {}
	for interest in interests:
		for tag in interest.tags:
			if tag_weight is not None and tag.tag_id not in weight:
				continue
			by_tag.setdefault(tag.tag_id, []).append(interest)
			tag_objs[tag.tag_id] = tag

	unassigned = {i.interest_id for i in interests}
	groups = []
	while unassigned and len(groups) < MAX_GROUPS:
		best, best_value = None, 0.0
		for tag_id, members in by_tag.items():
			count = sum(1 for m in members if m.interest_id in unassigned)
			if count < min_size:
				continue
			# Strongly related tags head groups first; size breaks ties among equals
			value = count * weight.get(tag_id, 1.0) ** 2
			if value > best_value or (value == best_value and best is not None
					and tag_objs[tag_id].tag_name < tag_objs[best].tag_name):
				best, best_value = tag_id, value
		if best is None:
			break
		members = [m for m in by_tag.pop(best) if m.interest_id in unassigned][:MAX_PER_GROUP]
		unassigned -= {m.interest_id for m in members}
		tag = tag_objs[best]
		groups.append({
			"key": tag.tag_name,
			"title": tag.tag_name,
			"categories": [c.category_name for c in tag.categories][:2],
			"interests": [interest_json(m, scores.get(m.interest_id) if scores else None) for m in members],
		})

	# Most relevant groups first
	if scores is not None:
		groups.sort(key=lambda g: -max(scores.get(i["id"], 0) for i in g["interests"]))

	# Name matches that no tag could place (e.g. untagged interests)
	if scores is not None:
		leftovers = [i for i in interests if i.interest_id in unassigned and scores.get(i.interest_id, 0) >= NAME_MATCH]
		if leftovers:
			groups.insert(0, {
				"key": "__matches",
				"title": "Matching names",
				"categories": [],
				"interests": [interest_json(i, scores.get(i.interest_id)) for i in leftovers[:MAX_PER_GROUP]],
			})
	return groups


def related_interests(interest: Interest, limit: int = 12) -> list[Interest]:
	"""Other interests ranked by how many tags they share with `interest`."""
	tag_ids = [t.tag_id for t in interest.tags]
	if not tag_ids:
		return []
	shared = func.count(interest_tags.c.tag_id)
	ids = [row[0] for row in db.session.execute(
		select(interest_tags.c.interest_id, shared)
		.where(interest_tags.c.tag_id.in_(tag_ids), interest_tags.c.interest_id != interest.interest_id)
		.group_by(interest_tags.c.interest_id)
		.order_by(shared.desc())
		.limit(limit)
	)]
	order = {i: n for n, i in enumerate(ids)}
	return sorted(_load(ids), key=lambda i: order[i.interest_id])


def suggested_names(limit: int = 16) -> list[str]:
	return list(db.session.scalars(
		select(Interest.interest_name)
		.where(Interest.interest_id.in_(select(interest_tags.c.interest_id)))
		.order_by(func.random())
		.limit(limit)
	))
