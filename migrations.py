"""
Additive database migrations, run at start-up before the schema check.

The project has no migration tool: db.create_all() makes NEW tables but never
adds columns to existing ones. Each step here only ADDS a nullable column when
it's missing, so an existing database upgrades in place. Never put a drop,
rename or type change here.
"""

from sqlalchemy import inspect, text

from models import db

# (table, column, SQL type) — all nullable, so existing rows are untouched
ADDITIVE_COLUMNS = [
	# Soft delete of interests by moderators (moderation.py)
	("interests", "removed_at", "DATETIME"),
	("interests", "removed_by", "INTEGER REFERENCES users(user_id)"),
	("interests", "removal_reason", "VARCHAR(500)"),
]


def run() -> list[str]:
	"""Add any missing columns; returns what was added (empty when up to date)."""
	inspector = inspect(db.engine)
	added = []
	for table, column, sql_type in ADDITIVE_COLUMNS:
		if not inspector.has_table(table):
			continue  # create_all() makes the whole table, column included
		if column in {c["name"] for c in inspector.get_columns(table)}:
			continue
		db.session.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {sql_type}"))
		added.append(f"{table}.{column}")
	db.session.commit()
	return added
