"""
Interest page data layer: reads interests, who has them, and wave state from
the database (models.py), and maps them to the shapes the templates use.
ALL backend field names stay in this file.

There is no backend endpoint for an interest's users yet, so this reads the
user_interests table directly. Fallbacks are marked "TODO(backend)"; see
docs/backend-integration.md.

get_interest(interest_id, viewer) returns:

	id, name, url
	category, category_slug  short category name and slug (None if the interest is untagged)
	description              str
	tags                     [str]
	related                  [{"name", "url", "category", "category_slug"}]
	interested_count         everyone with this interest, counted on the server
	viewer_has_interest      bool
	viewer_is_creator        interests.created_by_user_id is the viewer

get_people(interest_id, viewer, page, cumulative=False) returns:

	people    [user card]: pages 1..page if cumulative, else just that page
	shown     how many cards that makes on screen so far
	has_more  bool
	next_page int

A user card has ONLY these fields (privacy: nothing else is ever loaded):

	id, url        user_id, until the backend has a public handle
	handle         None: TODO(backend) username is the CIS code, never shown
	display_name   users.display_name, else "Durham student"
	avatar_colour  users.avatar_colour, else the palette fallback (same as the profile page)
	year           users.year, only when users.show_year is on; else None
	wave_state     "none" | "sent" | "received" | "connected"
"""

from sqlalchemy import func, or_, select

import discovery
import moderation
from colours import category_slug, category_style
from models import Connection, Interest, User, UserInterest, db
from profile_api import FALLBACK_NAME, fallback_avatar

PAGE_SIZE = 12


class InterestNotFound(Exception):
	pass


# ---------- The interest ----------

def get_interest(interest_id, viewer):
	interest = db.session.get(Interest, interest_id)
	if interest is None or interest.removed_at is not None:  # removed by a moderator: 404
		raise InterestNotFound(interest_id)

	data = to_interest(interest)
	data["related"] = [to_interest_pill(i) for i in discovery.related_interests(interest, limit=10)]
	data["interested_count"] = db.session.scalar(
		select(func.count()).select_from(UserInterest).where(UserInterest.interest_id == interest_id)
	)
	data["viewer_has_interest"] = db.session.get(UserInterest, (viewer.user_id, interest_id)) is not None
	data["viewer_is_creator"] = interest.created_by_user_id == viewer.user_id
	return data


def to_interest(interest):
	"""Map a backend Interest row to the interest page shape."""
	pill = to_interest_pill(interest)
	return {
		**pill,
		"id": interest.interest_id,
		"description": interest.description or "",
		"tags": [t.tag_name for t in interest.tags],
	}


def to_interest_pill(interest):
	"""Name, link and category of an interest, for coloured pills."""
	category = interest.category  # most common category across its tags, or None
	slug = category_slug(category.category_name) if category else None
	return {
		"name": interest.interest_name,
		"url": f"/interests/{interest.interest_id}",  # TODO(backend): /interest/<slug> once slugs exist
		"category_slug": slug,
		"category": category_style(slug)[0] if category else None,
	}


# ---------- People with the interest ----------

def get_people(interest_id, viewer, page=1, cumulative=False):
	page = max(1, page)
	start = 0 if cumulative else (page - 1) * PAGE_SIZE
	wanted = page * PAGE_SIZE - start

	# Only the columns a card may show. The viewer, and anyone blocked either way,
	# are left out here, on the server (TODO(backend): skip opted-out users).
	hidden = moderation.blocked_ids(viewer.user_id) | {viewer.user_id}
	rows = db.session.execute(
		select(User.user_id, User.display_name, User.year, User.show_year, User.avatar_colour)
		.join(UserInterest, UserInterest.user_id == User.user_id)
		.where(UserInterest.interest_id == interest_id, User.user_id.not_in(hidden))
		.order_by(UserInterest.added_at.desc(), User.user_id)
		.offset(start)
		.limit(wanted + 1)  # one extra tells us whether there's another page
	).all()

	has_more = len(rows) > wanted
	rows = rows[:wanted]
	waves = _wave_states(viewer.user_id, [r.user_id for r in rows])
	return {
		"people": [to_user_card(r, waves.get(r.user_id, "none")) for r in rows],
		"shown": start + len(rows),
		"has_more": has_more,
		"next_page": page + 1,
	}


def to_user_card(row, wave_state):
	"""
	Map one row of user columns (user_id, display_name, year, show_year,
	avatar_colour) to a public user card. Never add private fields here.
	"""
	return {
		"id": row.user_id,
		"url": f"/u/{row.user_id}",
		"handle": None,  # TODO(backend): no public handle
		"display_name": (row.display_name or "").strip() or FALLBACK_NAME,
		"avatar_colour": row.avatar_colour or fallback_avatar(row.user_id),
		"year": row.year if row.show_year else None,  # only when they chose to show it
		"wave_state": wave_state,
	}


def _wave_states(viewer_id, user_ids):
	"""{user_id: "connected" | "sent" | "received"} from the connections table (one query)."""
	if not user_ids:
		return {}
	rows = db.session.scalars(
		select(Connection).where(
			or_(
				(Connection.requester_id == viewer_id) & Connection.addressee_id.in_(user_ids),
				(Connection.addressee_id == viewer_id) & Connection.requester_id.in_(user_ids),
			)
		)
	)
	states = {}
	for row in rows:
		other = row.addressee_id if row.requester_id == viewer_id else row.requester_id
		if row.status == "accepted":
			states[other] = "connected"
		elif row.status == "pending":
			states[other] = "sent" if row.requester_id == viewer_id else "received"
	return states
