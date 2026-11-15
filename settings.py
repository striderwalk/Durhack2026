"""
Account settings page.

	GET /settings    your own settings (signed-in users only)

Saving uses the backend's own endpoints from the browser (static/settings.js):
profile details, year visibility and the bio through POST /u/<id>/edit, and
sign-out through GET /logout. Handles, discoverability and account deletion have
no backend yet, so they are shown switched off ("Coming soon"); see the gaps in
docs/backend-integration.md.

Never show users.username (the CIS code) or users.email (the sign-in address) here.
"""

import flask
import flask_login
from sqlalchemy.exc import SQLAlchemyError

import moderation
import profile_api

bp = flask.Blueprint("settings", __name__)


@bp.before_request
def require_sign_in():
	"""Send signed-out visitors to the sign-in page."""
	if not flask_login.current_user.is_authenticated:
		return flask.redirect(flask.url_for("login_get"))


@bp.get("/settings")
def page():
	user = flask_login.current_user
	try:
		profile = profile_api.get_profile(user.user_id, user)
	except SQLAlchemyError:
		flask.current_app.logger.exception("Settings lookup failed")
		return flask.make_response(flask.render_template("profile/error.html", kind="unavailable"), 503)
	return flask.render_template("settings/page.html", p=profile, blocked=moderation.my_blocked_list(user.user_id))


def init_app(app):
	app.register_blueprint(bp)
