"""
Trust and safety: the sign-in gate, bans, blocks, reports (flags), moderators
and the moderator audit log. Every rule here is enforced on the SERVER; the
pages only show or hide buttons. See docs/moderation.md.

Moderators are the signed-in users whose email is listed in the MODERATOR_EMAILS
setting (comma-separated; app config or environment variable), checked on every
moderator request. Clear the setting to remove all moderators.
"""

import hashlib
import json
import os
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

import flask
import flask_login
from sqlalchemy import event, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, with_loader_criteria

from models import Block, Connection, Flag, Interest, ModAction, User, UserBan, db

bp = flask.Blueprint("moderation", __name__)

FLAG_REASONS = ("spam", "harassment", "inappropriate", "impersonation", "other")
FLAG_MESSAGE_MAX = 500
FLAGS_PER_HOUR = 10
BAN_DAYS = {"1": 1, "7": 7, "30": 30}  # "permanent" has no expiry
DEFAULT_BAN_DAYS = "7"
LOGIN_FAILURES_ALLOWED = 10  # per address and per IP, in LOGIN_WINDOW
LOGIN_WINDOW = 15 * 60  # seconds

# Pages and endpoints a signed-out person may reach
PUBLIC_ENDPOINTS = {"login_get", "login_post", "register", "logout", "static"}


def now():
	return datetime.now(timezone.utc).replace(tzinfo=None)  # the database stores naive UTC


def email_hash(email):
	"""Ban key that survives account deletion: sha256 of the lower-case email."""
	return hashlib.sha256((email or "").strip().lower().encode()).hexdigest()


# ---------- Removed interests are hidden everywhere ----------
# Any ORM SELECT that involves Interest gets "removed_at IS NULL", unless it
# asks for include_removed=True (only the moderator views do). Relationship
# loads (user_interest.interest) aren't filtered, so existing code never gets
# None: places that list a user's interests skip removed ones (visible_interests()).

@event.listens_for(Session, "do_orm_execute")
def _hide_removed_interests(state):
	if state.is_select and not state.is_relationship_load \
			and not state.execution_options.get("include_removed", False):
		state.statement = state.statement.options(
			with_loader_criteria(Interest, lambda cls: cls.removed_at.is_(None),
				include_aliases=True, propagate_to_loaders=False)
		)


def visible_interests(user_interests):
	"""A user's UserInterest rows without removed interests."""
	return [ui for ui in user_interests if ui.interest is not None and ui.interest.removed_at is None]


# ---------- Moderators ----------

def moderator_emails():
	raw = flask.current_app.config.get("MODERATOR_EMAILS") or os.environ.get("MODERATOR_EMAILS", "")
	return {e.strip().lower() for e in raw.split(",") if e.strip()}


def is_moderator(user):
	return bool(user and user.is_authenticated and (user.email or "").lower() in moderator_emails())


def contact_line():
	email = flask.current_app.config.get("MODERATION_CONTACT_EMAIL") or os.environ.get("MODERATION_CONTACT_EMAIL", "")
	# TODO(NEEDS INPUT): no contact address configured yet
	return f"Questions? Contact {email}." if email else "Questions? Contact the moderators (contact address to be confirmed)."


# ---------- Bans ----------

def active_ban(user):
	"""The ban that applies to this user (by account or by email), or None."""
	if user is None:
		return None
	return db.session.scalar(
		select(UserBan).where(
			or_(UserBan.user_id == user.user_id, UserBan.email_hash == email_hash(user.email)),
			UserBan.lifted_at.is_(None),
			or_(UserBan.expires_at.is_(None), UserBan.expires_at > now()),
		).order_by(UserBan.expires_at.is_(None).desc(), UserBan.expires_at.desc())
	)


def ban_info(ban):
	return {
		"error": "banned",
		"type": ban.ban_type,
		"expires_at": ban.expires_at.isoformat() + "Z" if ban.expires_at else None,
		"contact": contact_line(),
	}


# ---------- Login attempt limits (in memory: one server process, dev only) ----------

_login_failures = defaultdict(deque)


def _recent_failures(key):
	q = _login_failures[key]
	while q and q[0] < time.time() - LOGIN_WINDOW:
		q.popleft()
	return len(q)


def _login_keys():
	identifier = (flask.request.form.get("identifier") or "").strip().lower()
	return [f"ip:{flask.request.remote_addr}", f"id:{identifier}"]


# ---------- The gate: every request ----------

def wants_json():
	return flask.request.path.startswith("/api/") or flask.request.is_json


@bp.before_app_request
def gate():
	"""
	Signed-out visitors may only reach sign-in and registration. Banned users are
	signed out (ending their session) and see the ban screen. Repeated failed
	sign-ins are slowed down.
	"""
	endpoint = flask.request.endpoint or ""
	if endpoint == "login_post" and any(_recent_failures(k) >= LOGIN_FAILURES_ALLOWED for k in _login_keys()):
		return flask.make_response(flask.render_template(
			"login.html", too_many=True), 429)

	user = flask_login.current_user
	if user.is_authenticated:
		ban = active_ban(user)
		if ban is not None:
			flask_login.logout_user()
			flask.session.clear()
			if wants_json():
				return flask.jsonify(ban_info(ban)), 403
			return flask.make_response(flask.render_template("banned.html", ban=ban, contact=contact_line()), 403)
		return None

	if endpoint in PUBLIC_ENDPOINTS or endpoint == "":
		return None  # endpoint "" is a 404, which the error page handles
	if wants_json():
		return flask.jsonify({"error": "signin_required"}), 401
	return flask.redirect(flask.url_for("login_get"))


@bp.after_app_request
def count_failed_logins(response):
	"""The backend answers a failed sign-in by sending you back to /login."""
	if flask.request.endpoint == "login_post" and response.status_code in (301, 302, 303) \
			and response.location and response.location.rstrip("/").endswith("/login"):
		for key in _login_keys():
			_login_failures[key].append(time.time())
	return response


@bp.app_context_processor
def safety_helpers():
	return {"is_moderator": lambda: is_moderator(flask_login.current_user)}


# ---------- Blocks ----------

def blocked_ids(user_id):
	"""Everyone this user has blocked or been blocked by (blocks work both ways)."""
	rows = db.session.execute(
		select(Block.blocker_id, Block.blocked_id).where(
			or_(Block.blocker_id == user_id, Block.blocked_id == user_id))
	).all()
	return {b if a == user_id else a for a, b in rows}


def is_blocked(a, b):
	return b in blocked_ids(a)


def _json():
	"""The request's JSON body. Requiring JSON also stops plain cross-site form posts."""
	return flask.request.get_json(silent=True) or {}


def _user_or_404(user_id):
	user = db.session.get(User, user_id)
	if user is None:
		flask.abort(404)
	return user


@bp.post("/api/blocks")
def block_user():
	me = flask_login.current_user
	target_id = _json().get("user_id")
	if not isinstance(target_id, int) or target_id == me.user_id:
		return flask.jsonify({"error": "You can't block that account."}), 400
	_user_or_404(target_id)
	if db.session.scalar(select(Block).where(Block.blocker_id == me.user_id, Block.blocked_id == target_id)):
		return flask.jsonify({"blocked": True}), 200
	db.session.add(Block(blocker_id=me.user_id, blocked_id=target_id))
	# Blocking ends any connection or pending wave between the two
	db.session.execute(Connection.__table__.delete().where(or_(
		(Connection.requester_id == me.user_id) & (Connection.addressee_id == target_id),
		(Connection.requester_id == target_id) & (Connection.addressee_id == me.user_id),
	)))
	db.session.commit()
	return flask.jsonify({"blocked": True}), 201


@bp.delete("/api/blocks/<int:user_id>")
def unblock_user(user_id):
	me = flask_login.current_user
	db.session.execute(Block.__table__.delete().where(Block.blocker_id == me.user_id, Block.blocked_id == user_id))
	db.session.commit()
	return flask.jsonify({"blocked": False})


def my_blocked_list(user_id):
	"""People this user blocked (not the ones who blocked them: that's never shown)."""
	rows = db.session.execute(
		select(User.user_id, User.display_name)
		.join(Block, Block.blocked_id == User.user_id)
		.where(Block.blocker_id == user_id)
		.order_by(Block.created_at.desc())
	).all()
	return [{"id": r.user_id, "display_name": (r.display_name or "").strip() or "Durham student"} for r in rows]


@bp.get("/api/blocks")
def list_blocks():
	return flask.jsonify({"blocked": my_blocked_list(flask_login.current_user.user_id)})


# ---------- Flags (reports) ----------

@bp.post("/api/flags")
def create_flag():
	me = flask_login.current_user
	data = _json()
	target_type, target_id = data.get("target_type"), data.get("target_id")
	reason = data.get("reason")
	message = (data.get("message") or "").strip()
	if target_type not in ("user", "interest") or not isinstance(target_id, int):
		return flask.jsonify({"error": "Choose what you're reporting."}), 400
	if reason not in FLAG_REASONS:
		return flask.jsonify({"error": "Choose a reason."}), 400
	if len(message) > FLAG_MESSAGE_MAX:
		return flask.jsonify({"error": f"Keep the message to {FLAG_MESSAGE_MAX} characters."}), 400

	linked = None
	if target_type == "user":
		if target_id == me.user_id:
			return flask.jsonify({"error": "You can't report yourself."}), 400
		if is_blocked(me.user_id, target_id):
			pass  # still allowed: you may report someone you blocked
		_user_or_404(target_id)
	else:
		interest = db.session.get(Interest, target_id)
		if interest is None or interest.removed_at is not None:
			flask.abort(404)
		if interest.created_by_user_id == me.user_id:
			return flask.jsonify({"error": "You can't report your own interest."}), 400
		linked = interest.created_by_user_id  # moderators see the creator too; nothing happens to them

	hour_ago = now() - timedelta(hours=1)
	recent = db.session.scalar(select(func.count()).select_from(Flag).where(
		Flag.reporter_id == me.user_id, Flag.created_at > hour_ago))
	if recent >= FLAGS_PER_HOUR:
		return flask.jsonify({"error": "You've sent a lot of reports. Please try again later."}), 429

	db.session.add(Flag(reporter_id=me.user_id, target_type=target_type, target_id=target_id,
		linked_user_id=linked, reason=reason, message=message or None, created_at=now()))
	try:
		db.session.commit()
	except IntegrityError:
		db.session.rollback()
		return flask.jsonify({"error": "You've already reported this. A moderator will review it."}), 409
	return flask.jsonify({"ok": True, "message": "Thanks. A moderator will review this."}), 201


# ---------- Moderator endpoints ----------

def require_moderator():
	"""Every moderator endpoint calls this first. Non-moderators get a 404."""
	if not is_moderator(flask_login.current_user):
		flask.abort(404)


def log_action(action, target_type, target_id, details=None):
	db.session.add(ModAction(moderator_id=flask_login.current_user.user_id, action=action,
		target_type=target_type, target_id=target_id, details=json.dumps(details or {}), created_at=now()))


def user_summary(user_id):
	"""What a moderator sees about a user in lists: never the email, CIS code or password."""
	user = db.session.get(User, user_id) if user_id else None
	if user is None:
		return None
	ban = active_ban(user)
	return {"id": user.user_id, "display_name": (user.display_name or "").strip() or "Durham student",
		"url": f"/u/{user.user_id}", "banned": bool(ban),
		"ban_expires_at": ban.expires_at.isoformat() + "Z" if ban and ban.expires_at else None}


def interest_summary(interest_id):
	interest = db.session.execute(
		select(Interest).where(Interest.interest_id == interest_id).execution_options(include_removed=True)
	).scalar()
	if interest is None:
		return None
	return {"id": interest.interest_id, "name": interest.interest_name, "description": interest.description or "",
		"url": f"/interests/{interest.interest_id}", "removed": interest.removed_at is not None,
		"removal_reason": interest.removal_reason, "creator": user_summary(interest.created_by_user_id)}


def flag_json(flag, detail=False):
	"""A flag for moderators. The reporter is shown as an id only on the detail view."""
	data = {"id": flag.flag_id, "target_type": flag.target_type, "target_id": flag.target_id,
		"reason": flag.reason, "message": flag.message, "status": flag.status,
		"created_at": flag.created_at.isoformat() + "Z",
		"resolved_at": flag.resolved_at.isoformat() + "Z" if flag.resolved_at else None,
		"resolution_note": flag.resolution_note,
		"target": user_summary(flag.target_id) if flag.target_type == "user" else interest_summary(flag.target_id),
		"linked_user": user_summary(flag.linked_user_id)}
	if detail:
		data["reporter"] = user_summary(flag.reporter_id)
	return data


def list_flags(status="open"):
	query = select(Flag).order_by(Flag.created_at.desc())
	query = query.where(Flag.status == "open") if status == "open" else query.where(Flag.status != "open")
	return [flag_json(f) for f in db.session.scalars(query)]


@bp.get("/api/mod/flags")
def api_list_flags():
	require_moderator()
	return flask.jsonify({"flags": list_flags(flask.request.args.get("status", "open"))})


def get_flag_or_404(flag_id):
	flag = db.session.get(Flag, flag_id)
	if flag is None:
		flask.abort(404)
	return flag


@bp.get("/api/mod/flags/<int:flag_id>")
def api_flag(flag_id):
	require_moderator()
	return flask.jsonify(flag_json(get_flag_or_404(flag_id), detail=True))


def _resolve(flag_id, status):
	require_moderator()
	flag = get_flag_or_404(flag_id)
	note = (_json().get("note") or "").strip()[:500]
	flag.status, flag.resolved_by, flag.resolved_at, flag.resolution_note = status, flask_login.current_user.user_id, now(), note or None
	log_action("flag_" + status, "flag", flag_id, {"note": note})
	db.session.commit()
	return flask.jsonify(flag_json(flag, detail=True))


@bp.post("/api/mod/flags/<int:flag_id>/dismiss")
def api_dismiss_flag(flag_id):
	return _resolve(flag_id, "dismissed")


@bp.post("/api/mod/flags/<int:flag_id>/action")
def api_action_flag(flag_id):
	return _resolve(flag_id, "actioned")


def _interest_including_removed(interest_id):
	interest = db.session.execute(
		select(Interest).where(Interest.interest_id == interest_id).execution_options(include_removed=True)
	).scalar()
	if interest is None:
		flask.abort(404)
	return interest


@bp.post("/api/mod/interests/<int:interest_id>/remove")
def api_remove_interest(interest_id):
	require_moderator()
	reason = (_json().get("reason") or "").strip()
	if not reason:
		return flask.jsonify({"error": "Give a reason for removing it."}), 400
	interest = _interest_including_removed(interest_id)
	interest.removed_at, interest.removed_by, interest.removal_reason = now(), flask_login.current_user.user_id, reason[:500]
	log_action("interest_remove", "interest", interest_id, {"reason": reason[:500], "name": interest.interest_name})
	db.session.commit()
	return flask.jsonify(interest_summary(interest_id))


@bp.post("/api/mod/interests/<int:interest_id>/restore")
def api_restore_interest(interest_id):
	require_moderator()
	reason = (_json().get("reason") or "").strip()
	if not reason:
		return flask.jsonify({"error": "Give a reason for restoring it."}), 400
	interest = _interest_including_removed(interest_id)
	interest.removed_at = interest.removed_by = interest.removal_reason = None
	log_action("interest_restore", "interest", interest_id, {"reason": reason[:500]})
	db.session.commit()
	return flask.jsonify(interest_summary(interest_id))


@bp.post("/api/mod/users/<int:user_id>/ban")
def api_ban_user(user_id):
	require_moderator()
	me = flask_login.current_user
	data = _json()
	duration = str(data.get("duration") or DEFAULT_BAN_DAYS)
	reason = (data.get("reason") or "").strip()
	target = _user_or_404(user_id)
	if target.user_id == me.user_id:
		return flask.jsonify({"error": "You can't ban yourself."}), 400
	if is_moderator(target):
		return flask.jsonify({"error": "Moderators can't ban other moderators."}), 400
	if duration != "permanent" and duration not in BAN_DAYS:
		return flask.jsonify({"error": "Choose 1 day, 7 days, 30 days or permanent."}), 400
	if not reason:
		return flask.jsonify({"error": "Give a reason for the ban."}), 400
	permanent = duration == "permanent"
	ban = UserBan(user_id=target.user_id, email_hash=email_hash(target.email),
		ban_type="permanent" if permanent else "temporary",
		expires_at=None if permanent else now() + timedelta(days=BAN_DAYS[duration]),
		reason=reason[:500], created_by=me.user_id, created_at=now())
	db.session.add(ban)
	db.session.flush()
	log_action("user_ban", "user", target.user_id, {"duration": duration, "reason": reason[:500], "ban_id": ban.ban_id})
	db.session.commit()
	return flask.jsonify(user_summary(target.user_id)), 201


@bp.post("/api/mod/users/<int:user_id>/unban")
def api_unban_user(user_id):
	require_moderator()
	target = _user_or_404(user_id)
	reason = (_json().get("reason") or "").strip()[:500]
	lifted = 0
	for ban in db.session.scalars(select(UserBan).where(
			or_(UserBan.user_id == target.user_id, UserBan.email_hash == email_hash(target.email)),
			UserBan.lifted_at.is_(None))):
		ban.lifted_at, ban.lifted_by = now(), flask_login.current_user.user_id
		lifted += 1
	log_action("user_unban", "user", target.user_id, {"reason": reason, "bans_lifted": lifted})
	db.session.commit()
	return flask.jsonify(user_summary(target.user_id))


def find_users(q):
	"""Look up by display name (contains) or user id. There are no public handles yet."""
	q = (q or "").strip()
	if not q:
		return []
	query = select(User.user_id)
	query = query.where(User.user_id == int(q)) if q.isdigit() else query.where(
		func.lower(User.display_name).contains(q.lower(), autoescape=True))
	return [user_summary(uid) for uid in db.session.scalars(query.limit(20))]


@bp.get("/api/mod/users")
def api_find_users():
	require_moderator()
	return flask.jsonify({"users": find_users(flask.request.args.get("q"))})


def user_detail(user_id, show_email=False):
	"""Status, bans and past flags for one user. The email only when asked, and that's logged."""
	data = user_summary(user_id)
	if data is None:
		flask.abort(404)
	user = db.session.get(User, user_id)
	bans = db.session.scalars(select(UserBan).where(
		or_(UserBan.user_id == user_id, UserBan.email_hash == email_hash(user.email))).order_by(UserBan.created_at.desc()))
	data["bans"] = [{"id": b.ban_id, "type": b.ban_type, "reason": b.reason,
		"created_at": b.created_at.isoformat() + "Z", "expires_at": b.expires_at.isoformat() + "Z" if b.expires_at else None,
		"lifted_at": b.lifted_at.isoformat() + "Z" if b.lifted_at else None} for b in bans]
	flags = db.session.scalars(select(Flag).where(or_(
		(Flag.target_type == "user") & (Flag.target_id == user_id), Flag.linked_user_id == user_id)).order_by(Flag.created_at.desc()))
	data["flags"] = [flag_json(f) for f in flags]
	data["is_moderator"] = is_moderator(user)
	if show_email:
		data["email"] = user.email
		log_action("view_email", "user", user_id)
		db.session.commit()
	return data


@bp.get("/api/mod/users/<int:user_id>")
def api_user(user_id):
	require_moderator()
	return flask.jsonify(user_detail(user_id, show_email=flask.request.args.get("email") == "1"))


def audit_log(action=None, limit=200):
	query = select(ModAction).order_by(ModAction.created_at.desc()).limit(limit)
	if action:
		query = query.where(ModAction.action == action)
	return [{"id": a.action_id, "moderator": user_summary(a.moderator_id), "action": a.action,
		"target_type": a.target_type, "target_id": a.target_id, "details": json.loads(a.details or "{}"),
		"created_at": a.created_at.isoformat() + "Z"} for a in db.session.scalars(query)]


@bp.get("/api/mod/audit")
def api_audit():
	require_moderator()
	return flask.jsonify({"actions": audit_log(flask.request.args.get("action") or None)})


# ---------- Moderator pages (/mod): the same checks, rendered on the server ----------

@bp.get("/mod")
def mod_queue():
	require_moderator()
	status = "resolved" if flask.request.args.get("status") == "resolved" else "open"
	return flask.render_template("mod/queue.html", flags=list_flags(status), status=status)


@bp.get("/mod/flags/<int:flag_id>")
def mod_flag(flag_id):
	require_moderator()
	return flask.render_template("mod/flag.html", f=flag_json(get_flag_or_404(flag_id), detail=True),
		ban_days=BAN_DAYS, default_days=DEFAULT_BAN_DAYS)


@bp.get("/mod/users")
def mod_users():
	require_moderator()
	q = flask.request.args.get("q", "")
	return flask.render_template("mod/users.html", users=find_users(q), q=q)


@bp.get("/mod/users/<int:user_id>")
def mod_user(user_id):
	require_moderator()
	return flask.render_template("mod/user.html", u=user_detail(user_id, show_email=flask.request.args.get("email") == "1"),
		ban_days=BAN_DAYS, default_days=DEFAULT_BAN_DAYS)


@bp.get("/mod/audit")
def mod_audit():
	require_moderator()
	action = flask.request.args.get("action") or None
	actions = sorted({a for (a,) in db.session.execute(select(ModAction.action).distinct())})
	return flask.render_template("mod/audit.html", entries=audit_log(action), action=action, actions=actions)


def init_app(app):
	app.register_blueprint(bp)
