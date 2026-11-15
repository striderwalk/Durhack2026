"""
Profile page routes. Every route needs a signed-in user.

	GET /u/                     your own profile
	GET /u/<user_id>            a profile
	GET /u/<user_id>?as=other   owner-only preview as another student sees it
	GET /u/<user_id>?edit=1     your own profile, opened in edit mode
	GET /u/<user_id>/edit       redirects to ?edit=1

Profiles are addressed by user_id for now. TODO(backend): switch to a public
handle once one exists. Never use users.username here: it is the CIS code.
All data comes from profile_api.py.
"""

import flask
import flask_login
from sqlalchemy.exc import SQLAlchemyError

import colours
import contact_types
import profile_api
from models import User, UserContact, db

bp = flask.Blueprint("profiles", __name__)


def _template_helpers():
	return {
		"category_style": colours.category_style,
		"category_vars": colours.category_vars,
		"avatar_colour": colours.avatar_colour,
		"contacts_json": profile_api.contacts_json,
		"category_theme_css": colours.theme_css,
		"AVATAR_COLOURS": colours.AVATAR_COLOURS,
		"YEARS": profile_api.YEARS,
		"BIO_MAX": profile_api.BIO_MAX,
		"NAME_MAX": profile_api.NAME_MAX,
	}


bp.app_context_processor(_template_helpers)


@bp.before_request
def require_sign_in():
	"""Send signed-out visitors to the sign-in page."""
	if not flask_login.current_user.is_authenticated:
		return flask.redirect(flask.url_for("login_get"))


def _error(kind, status):
	return flask.make_response(flask.render_template("profile/error.html", kind=kind), status)


def _load(user_id, preview_as=None):
	"""get_profile(), turning failures into the right error page."""
	try:
		return profile_api.get_profile(user_id, flask_login.current_user, preview_as), None
	except profile_api.ProfileNotFound:
		return None, _error("missing", 404)
	except SQLAlchemyError:
		flask.current_app.logger.exception("Profile lookup failed")
		return None, _error("unavailable", 503)


@bp.get("/u/")
def mine():
	return flask.redirect(flask.url_for("profiles.show", user_id=flask_login.current_user.user_id))


@bp.get("/u/<int:user_id>")
def show(user_id):
	"""
	A profile. The owner sees it editable in place (?edit=1 opens edit mode).
	?as=other or ?as=connection: the owner previews their page as others see it
	(get_profile ignores this for anyone else, so it can never reveal more).
	?partial=body|interests|suggestions returns just that part, for in-page updates.
	"""
	profile, error = _load(user_id, flask.request.args.get("as"))
	if error:
		return error

	partial = flask.request.args.get("partial")
	if partial == "interests":
		return flask.render_template("profile/_interest_tags.html", p=profile)
	if partial == "suggestions":
		if profile["viewer_relation"] != "self":
			return _error("forbidden", 403)
		exclude = [int(x) for x in flask.request.args.get("exclude", "").split(",") if x.isdigit()]
		profile["suggestions"] = profile_api.get_suggestions_for(user_id, exclude)
		return flask.render_template("profile/_suggestions.html", p=profile)
	if partial:
		return flask.render_template("profile/_body.html", p=profile)

	return flask.render_template(
		"profile/page.html",
		p=profile,
		# The three-way "Preview as" switch is a developer tool: debug mode only
		view_as_enabled=flask.current_app.debug and profile["can_preview"],
	)

@bp.post("/u/<int:user_id>/edit")
def edit_post(user_id):
    if flask_login.current_user.user_id != user_id:
        return _error("forbidden", 403)

    user = db.session.get(User, user_id)
    if user is None:
        return _error("missing", 404)

    action = flask.request.form.get("action", "save")

    # Contact list (sent by the current profile and settings forms as JSON).
    # Checked before anything changes, so a bad entry saves nothing.
    contacts = None
    if "contacts" in flask.request.form:
        contacts, problem = contact_types.validate_contacts(flask.request.form["contacts"])
        if problem:
            return flask.make_response(problem, 400)

    # Basics
    display_name = " ".join(flask.request.form.get("display_name", "").split())[:profile_api.NAME_MAX]
    user.display_name = display_name or None

    year_val = flask.request.form.get("year", "hide")
    if year_val in profile_api.YEARS:
        user.year = year_val
        user.show_year = True
    else:
        user.show_year = False

    colour = flask.request.form.get("avatar_colour", "")
    if colour in colours.AVATAR_COLOURS:
        user.avatar_colour = colour

    # Bio & publish state
    new_bio = flask.request.form.get("bio", "").strip()[:profile_api.BIO_MAX]
    bio_changed = new_bio != (user.bio or "").strip()
    user.bio = new_bio

    if not new_bio:
        user.bio_published = False
    elif action == "publish":
        user.bio_published = True
    elif action == "unpublish":
        user.bio_published = False
    elif bio_changed:
        # Saving edited text keeps changes as a private draft until "Publish bio" is clicked
        user.bio_published = False

    if contacts is None:
        # Older forms: the three fixed fields (strip leading '@' if typed)
        user.contact_instagram = flask.request.form.get("instagram", "").strip().lstrip("@")[:60]
        user.contact_x = flask.request.form.get("x", "").strip().lstrip("@")[:60]
        user.contact_email = flask.request.form.get("email", "").strip()[:120]
    else:
        # Replace the user's contact rows with the new list, in order
        UserContact.query.filter_by(user_id=user_id).delete()
        for position, entry in enumerate(contacts):
            db.session.add(UserContact(
                user_id=user_id, contact_type=entry["type"], value=entry["value"],
                label=entry["label"], position=position,
            ))
        # Keep the old columns in step (first entry of each kind, or empty), so they
        # never resurface once the list is in use and older code still sees them
        first = lambda kind: next((e["value"] for e in contacts if e["type"] == kind), "")
        user.contact_instagram = first("instagram")[:60]
        user.contact_x = first("x")[:60]
        user.contact_email = first("email")[:120]

    db.session.commit()

    if action in ("publish", "unpublish"):
        return flask.redirect(flask.url_for("profiles.edit", user_id=user_id))
    return flask.redirect(flask.url_for("profiles.show", user_id=user_id))

@bp.get("/u/<int:user_id>/edit")
def edit(user_id):
	"""Old address of the edit page: editing now happens on the profile itself."""
	if user_id != flask_login.current_user.user_id:
		return _error("forbidden", 403)
	return flask.redirect(flask.url_for("profiles.show", user_id=user_id, edit=1))


def init_app(app):
	app.register_blueprint(bp)
	# Account settings live in settings.py; registered here so app.py doesn't need changing
	import settings
	settings.init_app(app)
	# Site-wide 404/500 pages in the shared layout (site_pages.py)
	import site_pages
	site_pages.init_app(app)
	# Trust and safety: sign-in gate, bans, blocks, reports, moderators (moderation.py)
	import moderation
	moderation.init_app(app)


# Add to profiles.py

@bp.get("/connections")
def my_connections():
    return flask.redirect(
        flask.url_for("profiles.connections", user_id=flask_login.current_user.user_id)
    )


@bp.get("/u/<int:user_id>/connections")
def connections(user_id):
    try:
        data = profile_api.get_connections(user_id, flask_login.current_user)
    except profile_api.ProfileNotFound:
        return _error("missing", 404)
    except SQLAlchemyError:
        flask.current_app.logger.exception("Connections lookup failed")
        return _error("unavailable", 503)

    return flask.render_template("profile/connections.html", c=data)