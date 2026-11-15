"""
Interest routes: discovery APIs, creating interests, and interest pages.

Register with `interests.init_app(app)` after the database is set up.
"""

import flask
import flask_login
from sqlalchemy import func, inspect, select
from sqlalchemy.exc import SQLAlchemyError

import colours
import discovery
import home_api
import interest_api
import migrations
import taxonomy
from interest_names import to_interest_title_case
from models import Category, Interest, Tag, db

MAX_TAGS = 10

bp = flask.Blueprint("interests", __name__)


@bp.app_context_processor
def home_page_helpers():
	"""Lets index.html ask for its category cards and colours (see home_api.py, colours.py)."""
	return {
		"home_category_cards": home_api.category_cards,
		"category_palette": colours.palette_for_js,
	}


# ---------- JSON APIs used by the home page ----------

@bp.get("/api/interests")
def api_search_interests():
	q = flask.request.args.get("q", "")
	return {"results": [discovery.interest_json(i) for i in discovery.search_interests(q)]}


@bp.get("/api/discover")
def api_discover():
	return discovery.discover(flask.request.args.get("q", ""))


@bp.get("/api/tags")
def api_tags():
	q = flask.request.args.get("q", "")
	exclude = flask.request.args.getlist("exclude")
	return {"results": discovery.suggest_tags(q, exclude=exclude)}


# ---------- Creating and viewing interests ----------

@bp.post("/interests/new")
@flask_login.login_required
def create_interest():
	# Title case, the same rules as the create form (interest_names.py)
	name = to_interest_title_case(flask.request.form.get("interest_name", ""))[:120]
	description = flask.request.form.get("description", "").strip()
	tag_names = flask.request.form.getlist("tags")[:MAX_TAGS]

	if not name:
		return flask.redirect(flask.url_for("home"))

	# Don't create duplicates: send people to the existing interest instead
	existing = db.session.scalar(
		select(Interest).where(func.lower(Interest.interest_name) == name.lower())
		.execution_options(include_removed=True)  # a removed interest still holds its name
	)
	if existing and existing.removed_at is not None:
		return flask.redirect(flask.url_for("home"))  # removed by a moderator: not re-created
	if existing:
		return flask.redirect(flask.url_for("interests.view_interest", interest_id=existing.interest_id))

	user = flask_login.current_user
	interest = Interest(
		interest_name=name,
		description=description,
		created_by_user_id=user.user_id if user.is_authenticated else None,
		tags=discovery.get_or_create_tags(tag_names),  # optional: may be empty
	)
	db.session.add(interest)
	db.session.commit()
	return flask.redirect(flask.url_for("interests.view_interest", interest_id=interest.interest_id))


@bp.get("/interests/<int:interest_id>")
def view_interest(interest_id):
	"""
	Interest page: details, related interests and who has it (data from interest_api.py).
	?page=N shows the first N pages of people; with &partial=people it returns
	only page N's cards, for the "Load more" button.
	"""
	viewer = flask_login.current_user
	if not viewer.is_authenticated:
		return flask.redirect(flask.url_for("login_get"))

	page = flask.request.args.get("page", 1, type=int)
	partial = flask.request.args.get("partial") == "people"
	try:
		if partial:
			people = interest_api.get_people(interest_id, viewer, page)
			return flask.render_template("interest/_people.html", people=people, interest_id=interest_id)
		data = interest_api.get_interest(interest_id, viewer)
		people = interest_api.get_people(interest_id, viewer, page, cumulative=True)
	except interest_api.InterestNotFound:
		return flask.make_response(flask.render_template("interest/error.html", kind="missing"), 404)
	except SQLAlchemyError:
		flask.current_app.logger.exception("Interest page failed")
		return flask.make_response(flask.render_template("interest/error.html", kind="unavailable"), 503)

	return flask.render_template("interest.html", i=data, people=people)


# ---------- Setup ----------

def seed_taxonomy() -> None:
	"""Load categories, tags and starter interests from taxonomy.py (idempotent)."""
	categories = {c.category_name: c for c in db.session.scalars(select(Category))}
	tags = {t.tag_name: t for t in db.session.scalars(select(Tag))}

	def tag(name):
		if name not in tags:
			tags[name] = Tag(tag_name=name)
			db.session.add(tags[name])
		return tags[name]

	for cat_name, (description, tag_names) in taxonomy.CATEGORIES.items():
		category = categories.get(cat_name)
		if category is None:
			category = categories[cat_name] = Category(category_name=cat_name, description=description)
			db.session.add(category)
		for tag_name in tag_names:
			t = tag(tag_name)
			if category not in t.categories:
				t.categories.append(category)

	existing = set(db.session.scalars(select(func.lower(Interest.interest_name))))
	for name, description, tag_names in taxonomy.INTERESTS:
		if name.lower() not in existing:
			db.session.add(Interest(
				interest_name=name, description=description, tags=[tag(t) for t in tag_names]
			))
	db.session.commit()


def check_schema() -> None:
	"""
	Stop with a clear message if app.db is older than models.py. db.create_all()
	makes missing tables but never adds columns to existing ones, so an old file
	otherwise gives a 500 "Internal Server Error" on every page that loads a user.
	"""
	inspector = inspect(db.engine)
	interest_columns = {c["name"] for c in inspector.get_columns("interests")}
	missing = []
	for table in db.metadata.sorted_tables:
		if not inspector.has_table(table.name):
			continue  # create_all() makes it
		have = {c["name"] for c in inspector.get_columns(table.name)}
		missing += [f"{table.name}.{c.name}" for c in table.columns if c.name not in have]

	if "category_id" in interest_columns or missing:
		detail = f" (missing: {', '.join(missing)})" if missing else ""
		raise SystemExit(
			f"\nYour local database (instance/app.db) is older than models.py{detail}.\n"
			"Delete instance/app.db and start the app again; it will be rebuilt and seeded.\n"
		)


def init_app(app: flask.Flask) -> None:
	app.register_blueprint(bp)
	with app.app_context():
		db.create_all()
		migrations.run()  # additive columns for existing databases (migrations.py)
		check_schema()
		if db.session.scalar(select(Tag.tag_id).limit(1)) is None:
			seed_taxonomy()
