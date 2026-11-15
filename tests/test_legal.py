"""
Terms acceptance and the legal pages (legal.py).

Run from the project folder (after `python testdata.py`):
	python -m unittest tests.test_legal

The database file is copied first and put back afterwards. Seed users: alex,
maya, priya (password123); sam is made a moderator for the ban test.
"""

import shutil
import unittest

from sqlalchemy import select

import legal
import moderation
from app import app
from models import TermsAcceptance, User, UserBan, db


def sign_in(username, agree=True):
	client = app.test_client()
	data = {"identifier": username, "password": "password123"}
	if agree:
		data["agree_terms"] = "yes"
	response = client.post("/login", data=data)
	return client, response


class LegalTest(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		with app.app_context():
			cls.db_path = db.engine.url.database
		shutil.copyfile(cls.db_path, cls.db_path + ".before-legal-tests")

	@classmethod
	def tearDownClass(cls):
		with app.app_context():
			db.session.remove()
			db.engine.dispose()
		shutil.move(cls.db_path + ".before-legal-tests", cls.db_path)

	def setUp(self):
		moderation._login_failures.clear()
		self.version = legal.VERSION
		with app.app_context():
			db.session.execute(TermsAcceptance.__table__.delete())  # nobody has accepted yet
			db.session.commit()

	def tearDown(self):
		legal.VERSION = self.version
		app.config.pop("MODERATOR_EMAILS", None)
		with app.app_context():
			db.session.execute(UserBan.__table__.delete())
			db.session.commit()

	def accepted(self, username):
		with app.app_context():
			user_id = db.session.scalar(select(User.user_id).where(User.username == username))
			return [(a.version, a.accepted_at) for a in db.session.scalars(
				select(TermsAcceptance).where(TermsAcceptance.user_id == user_id))]

	def existing_session_without_acceptance(self, username):
		"""A user already signed in before acceptance existed (their record is missing)."""
		client, _ = sign_in(username)
		with app.app_context():
			db.session.execute(TermsAcceptance.__table__.delete())
			db.session.commit()
		return client

	def test_sign_in_needs_the_box_ticked(self):
		client, response = sign_in("alex", agree=False)
		self.assertEqual(response.status_code, 400)
		self.assertIn("tick the box", response.get_data(as_text=True))
		self.assertEqual(client.get("/u/1").status_code, 302)  # not signed in
		self.assertEqual(self.accepted("alex"), [])

	def test_ticking_the_box_records_the_version_and_time(self):
		client, _ = sign_in("alex")
		[(version, when)] = self.accepted("alex")
		self.assertEqual(version, legal.VERSION)
		self.assertIsNotNone(when)
		self.assertEqual(client.get("/u/1").status_code, 200)
		self.assertFalse(client.get("/api/session").get_json()["needs_acceptance"])

	def test_registration_needs_the_box_too(self):
		client = app.test_client()
		data = {"username": "zzlegal", "email": "zz.legal@durham.ac.uk", "password": "longpassword1", "confirm_password": "longpassword1"}
		self.assertEqual(client.post("/register", data=data).status_code, 400)
		try:
			self.assertEqual(client.post("/register", data={**data, "agree_terms": "yes"}).status_code, 200)
			self.assertEqual([v for v, _ in self.accepted("zzlegal")], [legal.VERSION])
		finally:
			with app.app_context():
				db.session.execute(User.__table__.delete().where(User.username == "zzlegal"))
				db.session.commit()

	def test_without_acceptance_everything_else_answers_terms_required(self):
		client = self.existing_session_without_acceptance("alex")
		api = client.get("/api/interests?q=a")
		self.assertEqual(api.status_code, 403)
		self.assertEqual(api.get_json()["error"], "terms_required")
		page = client.get("/u/1")
		self.assertEqual(page.status_code, 302)
		self.assertIn("/accept-terms", page.location)
		self.assertTrue(client.get("/api/session").get_json()["needs_acceptance"])
		# These still work
		for url in ("/terms", "/privacy", "/accept-terms"):
			self.assertEqual(client.get(url).status_code, 200, url)
		self.assertEqual(client.get("/logout").status_code, 302)

	def test_accepting_clears_it(self):
		client = self.existing_session_without_acceptance("alex")
		self.assertEqual(client.post("/accept-terms", data={"next": "/u/1"}).status_code, 400)  # box not ticked
		response = client.post("/accept-terms", data={"agree_terms": "yes", "next": "/u/1"})
		self.assertTrue(response.location.endswith("/u/1"))
		self.assertEqual(client.get("/u/1").status_code, 200)
		self.assertEqual(len(self.accepted("alex")), 1)

	def test_accepting_by_json(self):
		client = self.existing_session_without_acceptance("maya")
		self.assertEqual(client.post("/api/terms/accept", json={"agree": True, "version": "old"}).status_code, 400)
		ok = client.post("/api/terms/accept", json={"agree": True, "version": legal.VERSION})
		self.assertEqual(ok.get_json(), {"accepted": True, "version": legal.VERSION})
		self.assertEqual(client.get("/api/interests?q=a").status_code, 200)

	def test_a_new_version_asks_again(self):
		client, _ = sign_in("alex")
		self.assertEqual(client.get("/u/1").status_code, 200)
		legal.VERSION = "2099-01-v2"
		self.assertEqual(client.get("/api/interests?q=a").get_json()["error"], "terms_required")
		client.post("/accept-terms", data={"agree_terms": "yes"})
		self.assertEqual(client.get("/u/1").status_code, 200)
		self.assertEqual([v for v, _ in self.accepted("alex")][-1], "2099-01-v2")

	def test_legal_pages_are_public_even_when_signed_out_or_banned(self):
		anonymous = app.test_client()
		for url in ("/terms", "/privacy"):
			page = anonymous.get(url)
			self.assertEqual(page.status_code, 200, url)
			html = page.get_data(as_text=True)
			self.assertIn(legal.VERSION, html)
			self.assertIn("Draft, pending review.", html)
		app.config["MODERATOR_EMAILS"] = "sam@uni.ac.uk"
		sam, _ = sign_in("sam")
		sam.post("/api/mod/users/4/ban", json={"duration": "7", "reason": "test"})
		priya, _ = sign_in("priya")
		self.assertEqual(priya.get("/u/1").status_code, 403)  # the ban screen…
		for url in ("/terms", "/privacy"):
			self.assertEqual(priya.get(url).status_code, 200, url)  # …but the legal pages open

	def test_footer_links_on_every_kind_of_page(self):
		anonymous = app.test_client()
		client, _ = sign_in("alex")
		for c, url in ((anonymous, "/login"), (anonymous, "/register"), (anonymous, "/terms"), (client, "/"), (client, "/no-such-page")):
			html = c.get(url).get_data(as_text=True)
			with self.subTest(url=url):
				self.assertIn('href="/terms">Terms and Conditions', html)
				self.assertIn('href="/privacy">Data and Security', html)


if __name__ == "__main__":
	unittest.main()
