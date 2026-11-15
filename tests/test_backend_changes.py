"""
Tests for the small backend fixes listed in BACKEND_CHANGES.md.

Run from the project folder (after `python testdata.py`):
	python -m unittest tests.test_backend_changes

They use the local database (instance/app.db) and remove anything they create.
"""

import json
import unittest

import profile_api
from app import app
from models import Interest, User, UserContact, db

PASSWORD = "longpassword1"


class BackendChangesTest(unittest.TestCase):
	def setUp(self):
		self.client = app.test_client()

	def tearDown(self):
		# Remove the test users and interests made below
		with app.app_context():
			for name in ("zztest01", "zztest02"):
				user = User.query.filter_by(username=name).first()
				if user:
					db.session.delete(user)
			interest = Interest.query.filter_by(interest_name="Backend Test Interest").first()
			if interest:
				db.session.delete(interest)
			db.session.commit()

	def register(self, username, email):
		return self.client.post("/register", data={
			"username": username, "email": email,
			"password": PASSWORD, "confirm_password": PASSWORD,
		})

	def test_registration_succeeds_instead_of_crashing(self):
		response = self.register("zztest01", "zztest01@durham.ac.uk")
		self.assertEqual(response.status_code, 200)
		with app.app_context():
			self.assertIsNotNone(User.query.filter_by(username="zztest01").first())

	def test_registration_refuses_non_durham_addresses(self):
		response = self.register("zztest02", "zztest02@gmail.com")
		self.assertIn(b"Durham students only", response.data)
		with app.app_context():
			self.assertIsNone(User.query.filter_by(username="zztest02").first())

	def test_update_account_cannot_change_username(self):
		self.client.post("/login", data={"identifier": "alex", "password": "password123"})
		with app.app_context():
			old_bio = db.session.get(User, 1).bio
		self.client.post("/update-account", data={"new-username": "zzhijack", "new-bio": "Test bio"})
		with app.app_context():
			user = db.session.get(User, 1)
			self.assertEqual(user.username, "alex")
			self.assertEqual(user.bio, "Test bio")  # other fields still save
			user.bio = old_bio
			db.session.commit()

	def test_creating_an_interest_needs_sign_in(self):
		self.client.post("/interests/new", data={"interest_name": "Backend Test Interest"})
		with app.app_context():
			self.assertIsNone(Interest.query.filter_by(interest_name="Backend Test Interest").first())

	def test_search_results_include_category_and_score(self):
		self.client.post("/login", data={"identifier": "alex", "password": "password123"})  # search needs sign-in
		data = self.client.get("/api/discover?q=print").get_json()
		items = [i for g in data["groups"] for i in g["interests"]]
		self.assertTrue(items)
		for item in items:
			self.assertIn("category", item)
			self.assertIsInstance(item["score"], (int, float))


class InterestTitleCaseTest(unittest.TestCase):
	"""New interest names are saved in title case, and duplicates ignore case."""

	NAMES = ("Zz Rock-Climbing Gym of the North", "Zz Typed Hobby")

	def setUp(self):
		self.client = app.test_client()
		self.client.post("/login", data={"identifier": "alex", "password": "password123"})

	def tearDown(self):
		with app.app_context():
			for interest in Interest.query.filter(Interest.interest_name.in_(self.NAMES)).all():
				db.session.delete(interest)
			db.session.commit()

	def test_create_saves_title_case(self):
		self.client.post("/interests/new", data={"interest_name": "  zz rock-climbing   gym of the north "})
		with app.app_context():
			self.assertIsNotNone(Interest.query.filter_by(interest_name="Zz Rock-Climbing Gym of the North").first())

	def test_duplicate_check_ignores_case(self):
		with app.app_context():
			existing = Interest.query.first()
			before = Interest.query.count()
		response = self.client.post("/interests/new", data={"interest_name": existing.interest_name.lower()})
		self.assertTrue(response.headers["Location"].endswith(f"/interests/{existing.interest_id}"))
		with app.app_context():
			self.assertEqual(Interest.query.count(), before)

	def test_update_account_new_name_is_title_case(self):
		self.client.post("/update-account", data={"new-interests": "zz typed hobby"})
		with app.app_context():
			self.assertIsNotNone(Interest.query.filter_by(interest_name="Zz Typed Hobby").first())


class ContactListTest(unittest.TestCase):
	"""Typed contact lists: saving, validation, old values, and privacy."""

	def setUp(self):
		self.client = app.test_client()
		self.client.post("/login", data={"identifier": "alex", "password": "password123"})
		with app.app_context():
			user = db.session.get(User, 1)
			self.saved = {c: getattr(user, c) for c in (
				"display_name", "year", "show_year", "avatar_colour", "bio", "bio_published",
				"contact_instagram", "contact_x", "contact_email")}
			self.saved_rows = [(r.contact_type, r.value, r.label, r.position)
				for r in UserContact.query.filter_by(user_id=1).all()]
			# Start every test from the old columns only (no contact rows yet)
			UserContact.query.filter_by(user_id=1).delete()
			user.contact_instagram, user.contact_x, user.contact_email = (
				"alex.mercer.durham", "alexmercer_cs", "alex.mercer@durham.ac.uk")
			db.session.commit()

	def tearDown(self):
		# Put Alex back exactly as before
		with app.app_context():
			UserContact.query.filter_by(user_id=1).delete()
			for kind, value, label, position in self.saved_rows:
				db.session.add(UserContact(user_id=1, contact_type=kind, value=value, label=label, position=position))
			user = db.session.get(User, 1)
			for column, value in self.saved.items():
				setattr(user, column, value)
			db.session.commit()

	def save(self, contacts):
		s = self.saved
		return self.client.post("/u/1/edit", data={
			"display_name": s["display_name"] or "", "year": s["year"] if s["show_year"] else "hide",
			"avatar_colour": s["avatar_colour"], "bio": s["bio"] or "", "action": "save",
			"contacts": json.dumps(contacts),
		})

	def contacts_as(self, username):
		client = app.test_client()
		client.post("/login", data={"identifier": username, "password": "password123"})
		with app.app_context():
			viewer = User.query.filter_by(username=username).first()
			return profile_api.get_profile(1, viewer)["contacts"]

	def test_old_values_still_show_as_entries(self):
		contacts = self.contacts_as("alex")
		self.assertEqual({c["type"] for c in contacts}, {"instagram", "x", "email"})

	def test_saves_a_typed_list_in_order(self):
		entries = [
			{"type": "email", "value": " alex.m@durham.ac.uk "},
			{"type": "phone", "value": "+44 7700 900123"},
			{"type": "discord", "value": "@Alex_M"},
			{"type": "instagram", "value": "@alex.m"},
			{"type": "other", "value": "Room 12, Collingwood", "label": "Find me"},
		]
		response = self.save(entries)
		self.assertEqual(response.status_code, 302)
		contacts = self.contacts_as("alex")
		self.assertEqual([c["type"] for c in contacts], ["email", "phone", "discord", "instagram", "other"])
		self.assertEqual(contacts[0]["value"], "alex.m@durham.ac.uk")  # trimmed
		self.assertEqual(contacts[2]["value"], "alex_m")  # @ removed, lower case
		self.assertEqual(contacts[4]["label"], "Find me")

	def test_rejects_unsafe_and_invalid_values(self):
		bad_lists = [
			[{"type": "website", "value": "javascript:alert(1)"}],
			[{"type": "website", "value": "data:text/html,hi"}],
			[{"type": "website", "value": "http://example.com"}],
			[{"type": "instagram", "value": "x" * 31}],
			[{"type": "other", "value": "hello" + chr(7), "label": "Bell"}],  # control character
			[{"type": "other", "value": "no label"}],
			[{"type": "email", "value": "a@b.co"}, {"type": "email", "value": "A@B.co"}],
			[{"type": "x", "value": f"user{n}"} for n in range(9)],
			[{"type": "carrier-pigeon", "value": "coo"}],
		]
		for entries in bad_lists:
			with self.subTest(entries=entries[:1]):
				self.assertEqual(self.save(entries).status_code, 400)
		# Nothing was saved by the rejected requests
		with app.app_context():
			self.assertEqual(UserContact.query.filter_by(user_id=1).count(), 0)

	def test_strangers_get_no_contact_data(self):
		self.save([{"type": "discord", "value": "alex_m"}])
		self.assertIsNone(self.contacts_as("priya"))  # not connected to Alex
		self.assertTrue(self.contacts_as("maya"))     # connected to Alex
		other = app.test_client()
		other.post("/login", data={"identifier": "priya", "password": "password123"})
		html = other.get("/u/1").get_data(as_text=True)
		self.assertNotIn("alex_m", html)
		self.assertNotIn("discord", html.lower())


if __name__ == "__main__":
	unittest.main()
