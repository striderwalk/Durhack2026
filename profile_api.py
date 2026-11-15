"""
Profile data layer: reads real users from the database (models.py) and maps
them to the shape the profile templates use. ALL backend field names stay in
this file; templates only ever see the dict below.

Fields the backend can't supply yet use a fallback marked "TODO(backend)".
See docs/backend-integration.md for the full list of gaps.

get_profile(user_id, viewer, preview_as=None) returns:

	id                user_id; used in URLs until the backend adds a public handle
	handle            None: TODO(backend) no public handle exists. users.username
	                  is the CIS code and must NEVER be shown or put in a URL.
	display_name      users.display_name, else "Durham student"
	has_display_name  False when display_name is the fallback
	year, show_year   users.year, users.show_year (year removed for others when hidden)
	avatar_colour     users.avatar_colour, else picked from the palette by user_id
	interests         [{"id", "name", "url", "category", "category_slug"}] from user_interests
	bio               users.bio ("" for none; "" for others while unpublished)
	bio_published     users.bio_published
	connection_count  accepted rows in connections where the user is either side
	contacts          [{"id", "type", "value", "label"}] for self and connections (see _contacts),
	                  None for everyone else (the template shows the locked card)
	viewer_relation   "self" | "connection" | "other", worked out from connections
	wave_status       "none" | "sent" | "received", from a pending connections row
	can_preview       True when the viewer is the owner (allows "Preview as others see me")
	suggestions       owner only (else None): see get_suggestions()

Privacy rules are applied HERE, before anything reaches a template.
"""

import json

from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

import discovery
import moderation
from colours import AVATAR_COLOURS, category_slug, category_style
from models import Connection, Interest, Tag, User, UserContact, UserInterest, db

RELATIONS = ("self", "connection", "other")
BIO_MAX = 160
NAME_MAX = 30
YEARS = ["1st year", "2nd year", "3rd year",
         "4th year", "PHD", "Postgrad", "Other"]

# TODO(backend): shown when display_name is empty
FALLBACK_NAME = "Durham student"


class ProfileNotFound(Exception):
	pass


# ---------- Reading ----------

def get_profile(user_id, viewer, preview_as=None):
	"""
	The profile of `user_id` as the signed-in `viewer` may see it.
	`preview_as` lets the OWNER preview their page as "connection" or "other";
	it is ignored for anyone else, so it can never reveal more.
	Raises ProfileNotFound.
	"""
	user = db.session.scalar(
		select(User)
		.where(User.user_id == user_id)
		.options(
			selectinload(User.user_interests)
			.selectinload(UserInterest.interest)
			.selectinload(Interest.tags)
			.selectinload(Tag.categories)
		)
	)
	# Blocked either way: the profile looks as if it doesn't exist (moderation.py)
	if user is None or user.user_id in moderation.blocked_ids(viewer.user_id):
		raise ProfileNotFound(user_id)

	relation, wave_status = _relation(viewer.user_id, user.user_id)
	can_preview = relation == "self"
	if can_preview and preview_as in RELATIONS:
		relation = preview_as

	profile = to_profile(user)
	profile["viewer_relation"] = relation
	profile["wave_status"] = wave_status if relation == "other" else "none"
	profile["can_preview"] = can_preview
	profile["suggestions"] = get_suggestions(user) if relation == "self" else None

	# Privacy: only send what this viewer may see
	if relation != "self":
		if not profile["show_year"]:
			profile["year"] = None
		if not profile["bio_published"]:
			profile["bio"] = ""
	if relation == "other":
		profile["contacts"] = None
	return profile


def to_profile(user):
    """Map a backend User row to the profile shape (fields everyone may see first)."""
    contacts = _contacts(user)

    return {
        "id": user.user_id,
        # TODO(backend): no public handle; never use user.username (CIS code)
        "handle": None,
        "display_name": (user.display_name or "").strip() or FALLBACK_NAME,
        "has_display_name": bool((user.display_name or "").strip()),
        "year": user.year or None,
        "show_year": bool(user.show_year and user.year),
        "avatar_colour": user.avatar_colour or fallback_avatar(user.user_id),
        "interests": [_interest(ui.interest) for ui in moderation.visible_interests(user.user_interests)],
        "bio": user.bio or "",
        "bio_published": bool(user.bio_published),
        "connection_count": _connection_count(user.user_id),
        "contacts": contacts,
    }


def contacts_json(contacts):
	"""
	A contact list as the JSON the edit forms keep and send:
	[{"label", "type", "value"}], same key order and spacing as static/contacts.js.
	"""
	return json.dumps(
		[{"label": c["label"], "type": c["type"], "value": c["value"]} for c in (contacts or [])],
		separators=(",", ":"), ensure_ascii=False,
	)


def _contacts(user):
	"""
	[{id, type, value, label}] from user_contacts, in the user's order. A user
	with no rows yet gets their older instagram / x / email columns as entries,
	so values saved before the contact list existed still show.
	"""
	rows = db.session.scalars(
		select(UserContact).where(UserContact.user_id == user.user_id).order_by(UserContact.position)
	).all()
	if rows:
		return [{"id": r.contact_id, "type": r.contact_type, "value": r.value, "label": r.label} for r in rows]
	legacy = [("instagram", user.contact_instagram), ("x", user.contact_x), ("email", user.contact_email)]
	return [{"id": f"old-{kind}", "type": kind, "value": value, "label": None} for kind, value in legacy if value]


def _interest(interest):
	# most common category across the interest's tags, or None
	category = interest.category
	slug = category_slug(category.category_name) if category else None
	return {
		"id": interest.interest_id,
		"name": interest.interest_name,
		"url": f"/interests/{interest.interest_id}",
		"category_slug": slug,
		"category": category_style(slug)[0],
	}


def fallback_avatar(user_id):
	keys = list(AVATAR_COLOURS)
	return keys[user_id % len(keys)]


def _connection_count(user_id):
	return db.session.scalar(
		select(func.count())
		.select_from(Connection)
		.where(
			Connection.status == "accepted",
			or_(Connection.requester_id == user_id, Connection.addressee_id == user_id),
		)
	)


def _relation(viewer_id, user_id):
	"""(viewer_relation, wave_status) between the viewer and the profile owner."""
	if viewer_id == user_id:
		return "self", "none"
	row = db.session.scalar(
		select(Connection).where(
			or_(
				(Connection.requester_id == viewer_id) & (
					Connection.addressee_id == user_id),
				(Connection.requester_id == user_id) & (
					Connection.addressee_id == viewer_id),
			)
		)
	)
	if row is not None and row.status == "accepted":
		return "connection", "none"
	if row is not None and row.status == "pending":
		# Whoever asked first has "waved"
		return "other", ("sent" if row.requester_id == viewer_id else "received")
	return "other", "none"


# ---------- Suggestions (owner only) ----------

SUGGESTIONS = 3


def get_suggestions(user, exclude_ids=(), limit=SUGGESTIONS):
	"""
	Interests similar to the user's own, best first, leaving out ones they have
	and any ids in exclude_ids (cards they dismissed on this page).

	TODO(backend): there is no suggestions endpoint. This ranks the backend's own
	similarity function, discovery.related_interests() (shared tags, also used for
	"You might like" on interest pages), across all the user's interests.
	"""
	owned = [ui.interest for ui in moderation.visible_interests(user.user_interests)]
	skip = {i.interest_id for i in owned} | set(exclude_ids)
	scores = {}
	found = {}
	for interest in owned:
		for rank, other in enumerate(discovery.related_interests(interest, limit=12)):
			if other.interest_id in skip:
				continue
			# Higher when related to several of your interests, and near the top of each list
			scores[other.interest_id] = scores.get(
				other.interest_id, 0) + 1 / (rank + 1)
			found[other.interest_id] = other
	best = sorted(
		scores, key=lambda i: (-scores[i], found[i].interest_name))[:limit]
	return [{**_interest(found[i]), "description": found[i].description or ""} for i in best]


def get_suggestions_for(user_id, exclude_ids=()):
	"""get_suggestions() by user id, for the page's "Add" and dismiss refreshes."""
	user = db.session.get(User, user_id)
	if user is None:
		raise ProfileNotFound(user_id)
	return get_suggestions(user, exclude_ids)


# functions used for having added connections come up in friends

def _wave_states_for(viewer_id, user_ids):
    """Map {other_user_id: 'self' | 'connected' | 'sent' | 'received'} relative to viewer."""
    states = {}
    others = [uid for uid in user_ids if uid != viewer_id]
    if viewer_id in user_ids:
        states[viewer_id] = "self"
    if not others:
        return states

    rows = db.session.scalars(
        select(Connection).where(
            or_(
                (Connection.requester_id ==
                 viewer_id) & Connection.addressee_id.in_(others),
                (Connection.addressee_id ==
                 viewer_id) & Connection.requester_id.in_(others),
            )
        )
    )
    for row in rows:
        other = row.addressee_id if row.requester_id == viewer_id else row.requester_id
        if row.status == "accepted":
            states[other] = "connected"
        elif row.status == "pending":
            states[other] = "sent" if row.requester_id == viewer_id else "received"
    return states


def _to_connection_card(user, wave_state):
    """Public user card shape matching templates/interest/_user_card.html."""
    return {
        "id": user.user_id,
        "url": f"/u/{user.user_id}",
        "handle": None,  # Never expose user.username (CIS code)
        "display_name": (user.display_name or "").strip() or FALLBACK_NAME,
        "avatar_colour": user.avatar_colour or fallback_avatar(user.user_id),
        "year": user.year if (user.show_year and user.year) else None,
        "wave_state": wave_state,
    }


def get_connections(user_id, viewer):
    """
    Return accepted connections for `user_id` as seen by `viewer`.
    When `viewer` is `user_id`, also includes incoming and outgoing pending waves.
    """
    target = db.session.get(User, user_id)
    hidden = moderation.blocked_ids(viewer.user_id)  # blocked either way: never listed
    if target is None or target.user_id in hidden:
        raise ProfileNotFound(user_id)

    is_self = viewer.user_id == target.user_id

    accepted_rows = db.session.scalars(
        select(Connection)
        .where(
            Connection.status == "accepted",
            or_(Connection.requester_id == user_id,
                Connection.addressee_id == user_id),
        )
        .order_by(Connection.updated_at.desc())
    ).all()

    connected_ids = [
        row.addressee_id if row.requester_id == user_id else row.requester_id
        for row in accepted_rows
    ]

    incoming_ids = []
    outgoing_ids = []
    if is_self:
        pending_rows = db.session.scalars(
            select(Connection)
            .where(
                Connection.status == "pending",
                or_(Connection.requester_id == user_id,
                    Connection.addressee_id == user_id),
            )
            .order_by(Connection.created_at.desc())
        ).all()
        for row in pending_rows:
            if row.addressee_id == user_id:
                incoming_ids.append(row.requester_id)
            else:
                outgoing_ids.append(row.addressee_id)

    connected_ids = [uid for uid in connected_ids if uid not in hidden]
    incoming_ids = [uid for uid in incoming_ids if uid not in hidden]
    outgoing_ids = [uid for uid in outgoing_ids if uid not in hidden]
    all_ids = list(dict.fromkeys(connected_ids + incoming_ids + outgoing_ids))
    users_by_id = (
        {
            u.user_id: u
            for u in db.session.scalars(select(User).where(User.user_id.in_(all_ids)))
        }
        if all_ids
        else {}
    )
    waves = _wave_states_for(viewer.user_id, all_ids)

    connections = [
        _to_connection_card(users_by_id[uid], waves.get(uid, "none"))
        for uid in connected_ids
        if uid in users_by_id
    ]
    incoming_waves = [
        _to_connection_card(users_by_id[uid], "received")
        for uid in incoming_ids
        if uid in users_by_id
    ]
    outgoing_waves = [
        _to_connection_card(users_by_id[uid], "sent")
        for uid in outgoing_ids
        if uid in users_by_id
    ]

    return {
        "user": {
            "id": target.user_id,
            "display_name": (target.display_name or "").strip() or FALLBACK_NAME,
            "avatar_colour": target.avatar_colour or fallback_avatar(target.user_id),
        },
        "is_self": is_self,
        "connections": connections,
        "connection_count": len(connections),
        "incoming_waves": incoming_waves,
        "outgoing_waves": outgoing_waves,
    }
