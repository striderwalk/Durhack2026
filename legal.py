"""
The Terms and Conditions, the Information on Data and Security, and accepting them.

ONE place for the legal constants: the version people accept, the dates shown,
the operator and contact placeholders, and the draft notice. Bump VERSION when
either document changes in a way people must agree to again: everyone is then
asked to accept on their next request.

Rules (all on the server):
- /terms and /privacy are public: signed out, signed in, and banned users.
- Signing in or registering needs the "I agree" box ticked; doing so records
  acceptance of the current VERSION.
- A signed-in user who hasn't accepted the current VERSION gets the acceptance
  screen for pages, and 403 {"error": "terms_required"} for APIs, everywhere
  except sign-out, the legal pages and the acceptance endpoints.
"""

import flask
import flask_login
from sqlalchemy import select

from models import TermsAcceptance, db

# ---------- The constants (the only place to change them) ----------
VERSION = "2026-11-v1"
LAST_UPDATED = "15 November 2026"
OPERATOR_NAME = "[OPERATOR NAME]"
CONTACT_EMAIL = "[CONTACT EMAIL]"
# Shows "Draft, pending review." on both pages. Set to False ONLY after a human
# has reviewed the Terms and the data information (docs/legal-review-checklist.md).
SHOW_DRAFT_NOTICE = True

bp = flask.Blueprint("legal", __name__)

# Always reachable, whatever the user's state
OPEN_ENDPOINTS = {"legal.terms", "legal.privacy", "static"}
# Also reachable by a signed-in user who still has to accept
ACCEPTANCE_ENDPOINTS = OPEN_ENDPOINTS | {"logout", "legal.accept_page", "legal.accept_form", "legal.api_accept", "legal.api_session"}
# Forms that need the "I agree" box ticked
AGREE_FIELD = "agree_terms"


def needs_acceptance(user):
	"""True when the user hasn't accepted the current VERSION."""
	latest = db.session.scalar(
		select(TermsAcceptance.version).where(TermsAcceptance.user_id == user.user_id)
		.order_by(TermsAcceptance.accepted_at.desc(), TermsAcceptance.acceptance_id.desc()).limit(1)
	)
	return latest != VERSION


def record_acceptance(user):
	db.session.add(TermsAcceptance(user_id=user.user_id, version=VERSION))
	db.session.commit()


@bp.app_context_processor
def legal_constants():
	return {"LEGAL": {"version": VERSION, "last_updated": LAST_UPDATED, "operator": OPERATOR_NAME,
		"contact": CONTACT_EMAIL, "draft": SHOW_DRAFT_NOTICE}}


def wants_json():
	return flask.request.path.startswith("/api/") or flask.request.is_json


@bp.before_app_request
def require_terms():
	"""Runs after the sign-in and ban gate (moderation.py)."""
	endpoint = flask.request.endpoint or ""

	# Signing in or registering: the box must be ticked (checked here, not just in the page)
	if flask.request.method == "POST" and endpoint in ("login_post", "register") \
			and not flask.request.form.get(AGREE_FIELD):
		template = "login.html" if endpoint == "login_post" else "register.html"
		return flask.make_response(flask.render_template(template, terms_error=True), 400)

	user = flask_login.current_user
	if not user.is_authenticated or endpoint in ACCEPTANCE_ENDPOINTS:
		return None
	if needs_acceptance(user):
		if wants_json():
			return flask.jsonify({"error": "terms_required", "version": VERSION}), 403
		return flask.redirect(flask.url_for("legal.accept_page", next=flask.request.full_path))
	return None


@bp.after_app_request
def record_on_sign_in(response):
	"""Ticking the box when signing in or registering records acceptance of VERSION."""
	if flask.request.method == "POST" and flask.request.endpoint in ("login_post", "register") \
			and flask.request.form.get(AGREE_FIELD):
		user = flask_login.current_user
		if user.is_authenticated and needs_acceptance(user):
			record_acceptance(user)
	return response


# ---------- Pages ----------

@bp.get("/terms")
def terms():
	return flask.render_template("legal/terms.html")


@bp.get("/privacy")
def privacy():
	return flask.render_template("legal/privacy.html")


def _safe_next():
	"""Only go back to a page on this site after accepting."""
	target = flask.request.values.get("next") or "/"
	if not target.startswith("/") or target.startswith("//") or target.startswith(("/login", "/register", "/accept-terms")):
		return "/"  # never off-site, and never back to sign-in once you're in
	return target


@bp.get("/accept-terms")
def accept_page():
	if not flask_login.current_user.is_authenticated:
		return flask.redirect(flask.url_for("login_get"))
	if not needs_acceptance(flask_login.current_user):
		return flask.redirect(_safe_next())
	return flask.render_template("legal/accept.html", next=_safe_next())


@bp.post("/accept-terms")
def accept_form():
	"""The acceptance screen's Continue button (works without JavaScript)."""
	if not flask_login.current_user.is_authenticated:
		return flask.redirect(flask.url_for("login_get"))
	if not flask.request.form.get(AGREE_FIELD):
		return flask.make_response(flask.render_template("legal/accept.html", next=_safe_next(), terms_error=True), 400)
	if needs_acceptance(flask_login.current_user):
		record_acceptance(flask_login.current_user)
	return flask.redirect(_safe_next())


# ---------- JSON ----------

@bp.post("/api/terms/accept")
def api_accept():
	"""JSON: {"agree": true, "version": "<VERSION>"}. The version must be the current one."""
	data = flask.request.get_json(silent=True) or {}
	if data.get("agree") is not True or data.get("version") != VERSION:
		return flask.jsonify({"error": "Tick the box to agree to the current version.", "version": VERSION}), 400
	if needs_acceptance(flask_login.current_user):
		record_acceptance(flask_login.current_user)
	return flask.jsonify({"accepted": True, "version": VERSION})


@bp.get("/api/session")
def api_session():
	"""Who's signed in, and whether they must accept the current terms first."""
	user = flask_login.current_user
	return flask.jsonify({"user_id": user.user_id, "needs_acceptance": needs_acceptance(user), "terms_version": VERSION})


def init_app(app):
	app.register_blueprint(bp)
