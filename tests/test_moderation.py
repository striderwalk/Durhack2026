"""
Trust and safety (moderation.py): the sign-in gate, blocks, reports, bans,
moderator-only endpoints, the audit log and removed interests.

Run from the project folder (after `python testdata.py`):
	python -m unittest tests.test_moderation

The database file is copied before these tests and put back afterwards, so
nothing they do is left behind. Seed users: alex (1), maya (2), liam (3),
priya (4), sam (5); alex and maya are connected. sam is the moderator here.
"""

import shutil
import unittest
from datetime import timedelta

from sqlalchemy import select

import moderation
from app import app
from models import Block, Connection, Flag, Interest, ModAction, User, UserBan, db

ALEX, MAYA, LIAM, PRIYA, SAM = 1, 2, 3, 4, 5


def signed_in(username, password="password123"):
	client = app.test_client()
	client.post("/login", data={"identifier": username, "password": password})
	return client


def as_json(client, method, url, body=None):
	return client.open(url, method=method, json=body if body is not None else {})


class ModerationTest(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		with app.app_context():
			cls.db_path = db.engine.url.database
		shutil.copyfile(cls.db_path, cls.db_path + ".before-moderation-tests")
		app.config["MODERATOR_EMAILS"] = "sam@uni.ac.uk"

	@classmethod
	def tearDownClass(cls):
		app.config.pop("MODERATOR_EMAILS", None)
		with app.app_context():
			db.session.remove()
			db.engine.dispose()
		shutil.move(cls.db_path + ".before-moderation-tests", cls.db_path)

	def setUp(self):
		moderation._login_failures.clear()
		with app.app_context():
			email = lambda uid: db.session.get(User, uid).email
			self.emails = {uid: email(uid) for uid in (ALEX, MAYA, LIAM, PRIYA, SAM)}

	def tearDown(self):
		# Undo what each test did, so the tests don't depend on each other
		with app.app_context():
			for model in (Block, Flag, UserBan, ModAction):
				db.session.execute(model.__table__.delete())
			for interest in db.session.execute(select(Interest).execution_options(include_removed=True)).scalars():
				interest.removed_at = interest.removed_by = interest.removal_reason = None
			if not db.session.get(Connection, (ALEX, MAYA)) and not db.session.get(Connection, (MAYA, ALEX)):
				db.session.add(Connection(requester_id=ALEX, addressee_id=MAYA, status="accepted"))
			db.session.commit()

	# ---------- Phase 0: the gate ----------

	def test_signed_out_requests_need_sign_in_everywhere(self):
		client = app.test_client()
		public = {"login_get", "login_post", "register", "logout", "static"}
		checked = 0
		for rule in app.url_map.iter_rules():
			if rule.endpoint in public:
				continue
			url = rule.rule.replace("<int:user_id>", "1").replace("<int:interest_id>", "1") \
				.replace("<int:flag_id>", "1").replace("<path:filename>", "x")
			for method in rule.methods - {"HEAD", "OPTIONS"}:
				response = client.open(url, method=method)
				with self.subTest(url=url, method=method):
					if url.startswith("/api/"):
						self.assertEqual(response.status_code, 401)
					else:
						self.assertEqual(response.status_code, 302)
						self.assertTrue(response.location.endswith("/login"))
				checked += 1
		self.assertGreater(checked, 25)

	def test_repeated_failed_sign_ins_are_slowed_down(self):
		client = app.test_client()
		for _ in range(moderation.LOGIN_FAILURES_ALLOWED):
			client.post("/login", data={"identifier": "alex", "password": "wrong"})
		blocked = client.post("/login", data={"identifier": "alex", "password": "password123"})
		self.assertEqual(blocked.status_code, 429)

	# ---------- Blocks ----------

	def test_block_hides_both_profiles_and_ends_the_connection(self):
		alex, maya = signed_in("alex"), signed_in("maya")
		self.assertEqual(maya.get("/u/1").status_code, 200)
		self.assertEqual(as_json(alex, "POST", "/api/blocks", {"user_id": MAYA}).status_code, 201)
		self.assertEqual(maya.get("/u/1").status_code, 404)        # blocked one way…
		self.assertEqual(alex.get("/u/2").status_code, 404)        # …hidden both ways
		self.assertEqual(maya.get("/u/1/connections").status_code, 404)
		with app.app_context():
			self.assertIsNone(db.session.get(Connection, (ALEX, MAYA)))
			self.assertIsNone(db.session.get(Connection, (MAYA, ALEX)))
		# Not listed on each other's interest pages, either way
		with app.app_context():
			shared = {ui.interest_id for ui in db.session.get(User, ALEX).user_interests} & \
				{ui.interest_id for ui in db.session.get(User, MAYA).user_interests}
		for interest_id in shared:
			self.assertNotIn('href="/u/2"', alex.get(f"/interests/{interest_id}").get_data(as_text=True))
			self.assertNotIn('href="/u/1"', maya.get(f"/interests/{interest_id}").get_data(as_text=True))
		# The blocked user isn't told, and can't see the blocker's list
		self.assertEqual(maya.get("/api/blocks").get_json()["blocked"], [])
		self.assertEqual([b["id"] for b in alex.get("/api/blocks").get_json()["blocked"]], [MAYA])
		# Unblock restores visibility
		self.assertEqual(as_json(alex, "DELETE", "/api/blocks/2").status_code, 200)
		self.assertEqual(maya.get("/u/1").status_code, 200)

	def test_cannot_block_yourself(self):
		self.assertEqual(as_json(signed_in("alex"), "POST", "/api/blocks", {"user_id": ALEX}).status_code, 400)

	def test_blocked_users_get_no_contact_data(self):
		alex, maya = signed_in("alex"), signed_in("maya")
		as_json(alex, "POST", "/api/blocks", {"user_id": MAYA})
		html = maya.get("/u/1").get_data(as_text=True)
		self.assertNotIn("alex.mercer", html)

	# ---------- Flags ----------

	def test_flag_rules(self):
		priya = signed_in("priya")
		ok = as_json(priya, "POST", "/api/flags", {"target_type": "user", "target_id": ALEX, "reason": "spam", "message": "x"})
		self.assertEqual(ok.status_code, 201)
		self.assertEqual(ok.get_json()["message"], "Thanks. A moderator will review this.")
		again = as_json(priya, "POST", "/api/flags", {"target_type": "user", "target_id": ALEX, "reason": "other"})
		self.assertEqual(again.status_code, 409)  # one open flag per reporter per target
		self.assertEqual(as_json(priya, "POST", "/api/flags", {"target_type": "user", "target_id": PRIYA, "reason": "spam"}).status_code, 400)
		self.assertEqual(as_json(priya, "POST", "/api/flags", {"target_type": "user", "target_id": ALEX, "reason": "nonsense"}).status_code, 400)
		self.assertEqual(as_json(priya, "POST", "/api/flags", {"target_type": "user", "target_id": MAYA, "reason": "spam", "message": "x" * 501}).status_code, 400)

	def test_flag_rate_limit(self):
		priya = signed_in("priya")
		with app.app_context():
			ids = list(db.session.scalars(select(Interest.interest_id).where(Interest.created_by_user_id.is_(None)).limit(11)))
		statuses = [as_json(priya, "POST", "/api/flags", {"target_type": "interest", "target_id": i, "reason": "spam"}).status_code for i in ids]
		self.assertEqual(statuses[:10], [201] * 10)
		self.assertEqual(statuses[10], 429)

	def test_interest_flag_records_the_creator_and_nothing_else_happens(self):
		maya, priya = signed_in("maya"), signed_in("priya")
		maya.post("/interests/new", data={"interest_name": "zz moderation test"})
		with app.app_context():
			interest = db.session.scalar(select(Interest).where(Interest.interest_name == "Zz Moderation Test"))
			interest_id = interest.interest_id
		try:
			self.assertEqual(as_json(maya, "POST", "/api/flags", {"target_type": "interest", "target_id": interest_id, "reason": "spam"}).status_code, 400)
			self.assertEqual(as_json(priya, "POST", "/api/flags", {"target_type": "interest", "target_id": interest_id, "reason": "spam"}).status_code, 201)
			with app.app_context():
				flag = db.session.scalar(select(Flag).where(Flag.target_id == interest_id))
				self.assertEqual(flag.linked_user_id, MAYA)
				self.assertIsNone(moderation.active_ban(db.session.get(User, MAYA)))
			# The reporter isn't revealed to the creator
			self.assertNotIn("priya", maya.get(f"/interests/{interest_id}").get_data(as_text=True).lower())
		finally:
			with app.app_context():
				db.session.execute(Interest.__table__.delete().where(Interest.interest_id == interest_id))
				db.session.commit()

	# ---------- Moderator endpoints ----------

	def test_non_moderators_get_404_on_every_moderator_endpoint(self):
		alex = signed_in("alex")
		checked = 0
		for rule in app.url_map.iter_rules():
			if not (rule.rule.startswith("/mod") or rule.rule.startswith("/api/mod")):
				continue
			url = rule.rule.replace("<int:user_id>", "4").replace("<int:interest_id>", "1").replace("<int:flag_id>", "1")
			for method in rule.methods - {"HEAD", "OPTIONS"}:
				with self.subTest(url=url, method=method):
					self.assertEqual(alex.open(url, method=method, json={}).status_code, 404)
				checked += 1
		self.assertGreaterEqual(checked, 15)

	def test_moderator_can_list_and_resolve_flags_and_every_action_is_logged(self):
		priya, sam = signed_in("priya"), signed_in("sam")
		as_json(priya, "POST", "/api/flags", {"target_type": "user", "target_id": ALEX, "reason": "spam", "message": "hello"})
		flags = sam.get("/api/mod/flags").get_json()["flags"]
		self.assertEqual(len(flags), 1)
		self.assertNotIn("reporter", flags[0])                       # not in the list…
		detail = sam.get(f"/api/mod/flags/{flags[0]['id']}").get_json()
		self.assertEqual(detail["reporter"]["id"], PRIYA)             # …only on the detail
		self.assertNotIn("email", detail["target"])
		as_json(sam, "POST", f"/api/mod/flags/{flags[0]['id']}/dismiss", {"note": "fine"})
		self.assertEqual(sam.get("/api/mod/flags").get_json()["flags"], [])
		self.assertEqual(sam.get("/api/mod/flags?status=resolved").get_json()["flags"][0]["status"], "dismissed")
		# Remove and restore an interest, ban and unban, view an email: all logged
		self.assertEqual(as_json(sam, "POST", "/api/mod/interests/1/remove", {}).status_code, 400)  # reason required
		as_json(sam, "POST", "/api/mod/interests/1/remove", {"reason": "spam"})
		as_json(sam, "POST", "/api/mod/interests/1/restore", {"reason": "mistake"})
		as_json(sam, "POST", "/api/mod/users/4/ban", {"duration": "1", "reason": "test"})
		as_json(sam, "POST", "/api/mod/users/4/unban", {"reason": "test over"})
		self.assertEqual(sam.get("/api/mod/users/4?email=1").get_json()["email"], self.emails[PRIYA])
		actions = [a["action"] for a in sam.get("/api/mod/audit").get_json()["actions"]]
		for action in ("flag_dismissed", "interest_remove", "interest_restore", "user_ban", "user_unban", "view_email"):
			self.assertIn(action, actions)
		# The audit log has no way to change it
		self.assertEqual(sam.delete("/api/mod/audit").status_code, 405)

	def test_moderator_lists_never_include_emails_or_passwords(self):
		sam = signed_in("sam")
		text = sam.get("/api/mod/users?q=a").get_data(as_text=True) + sam.get("/api/mod/users/1").get_data(as_text=True)
		for secret in ("password", "email", self.emails[ALEX], "alex\""):
			self.assertNotIn(secret, text)

	# ---------- Removed interests ----------

	def test_removed_interest_disappears_everywhere(self):
		sam, alex = signed_in("sam"), signed_in("alex")
		with app.app_context():
			interest = db.session.get(Interest, 1)
			name, owner_ids = interest.interest_name, [ui.user_id for ui in interest.user_interests]
		as_json(sam, "POST", "/api/mod/interests/1/remove", {"reason": "spam"})
		self.assertEqual(alex.get("/interests/1").status_code, 404)
		self.assertEqual(alex.get(f"/api/interests?q={name}").get_json()["results"], [])
		found = alex.get(f"/api/discover?q={name}").get_json()  # (the response repeats the query itself)
		self.assertNotIn(f'"name":"{name}"', str(found).replace("'", '"').replace('": "', '":"'))
		self.assertNotIn(name, alex.get("/").get_data(as_text=True))
		for uid in owner_ids:
			self.assertNotIn(name, alex.get(f"/u/{uid}").get_data(as_text=True))
		# Still there for moderators, with the reason
		self.assertTrue(sam.get("/api/mod/users/1").status_code == 200)
		as_json(sam, "POST", "/api/mod/interests/1/restore", {"reason": "back"})
		self.assertEqual(alex.get("/interests/1").status_code, 200)

	# ---------- Bans ----------

	def test_ban_ends_the_session_and_blocks_sign_in(self):
		sam, priya = signed_in("sam"), signed_in("priya")
		self.assertEqual(priya.get("/").status_code, 200)
		self.assertEqual(as_json(sam, "POST", "/api/mod/users/4/ban", {"duration": "7", "reason": "test"}).status_code, 201)
		page = priya.get("/")
		self.assertEqual(page.status_code, 403)
		self.assertIn("suspended until", page.get_data(as_text=True))
		self.assertEqual(priya.get("/u/1").status_code, 302)  # the session was ended
		again = signed_in("priya").get("/api/interests?q=a")
		self.assertEqual(again.status_code, 403)
		body = again.get_json()
		self.assertEqual((body["error"], body["type"]), ("banned", "temporary"))
		self.assertTrue(body["expires_at"])
		self.assertIn("Contact", body["contact"])

	def test_temporary_ban_expires(self):
		as_json(signed_in("sam"), "POST", "/api/mod/users/4/ban", {"duration": "1", "reason": "test"})
		with app.app_context():
			ban = db.session.scalar(select(UserBan))
			ban.expires_at = moderation.now() - timedelta(minutes=1)
			db.session.commit()
		self.assertEqual(signed_in("priya").get("/").status_code, 200)

	def test_moderators_cannot_ban_themselves_or_each_other(self):
		app.config["MODERATOR_EMAILS"] = "sam@uni.ac.uk, liam@uni.ac.uk"
		try:
			sam = signed_in("sam")
			self.assertEqual(as_json(sam, "POST", "/api/mod/users/5/ban", {"reason": "x"}).status_code, 400)
			self.assertEqual(as_json(sam, "POST", "/api/mod/users/3/ban", {"reason": "x"}).status_code, 400)
		finally:
			app.config["MODERATOR_EMAILS"] = "sam@uni.ac.uk"

	def test_permanent_ban_survives_the_account_being_deleted(self):
		sam = signed_in("sam")
		client = app.test_client()
		client.post("/register", data={"username": "zzbanned", "email": "zz.banned@durham.ac.uk",
			"password": "longpassword1", "confirm_password": "longpassword1"})
		with app.app_context():
			user_id = db.session.scalar(select(User.user_id).where(User.username == "zzbanned"))
		as_json(sam, "POST", f"/api/mod/users/{user_id}/ban", {"duration": "permanent", "reason": "test"})
		with app.app_context():  # the account is deleted…
			db.session.execute(User.__table__.delete().where(User.user_id == user_id))
			db.session.commit()
		again = app.test_client()  # …and registered again with the same address
		again.post("/register", data={"username": "zzbanned2", "email": "ZZ.Banned@durham.ac.uk",
			"password": "longpassword1", "confirm_password": "longpassword1"})
		try:
			self.assertEqual(again.get("/").status_code, 403)
			self.assertIn("permanently banned", signed_in("zzbanned2", "longpassword1").get("/").get_data(as_text=True))
		finally:
			with app.app_context():
				db.session.execute(User.__table__.delete().where(User.username.in_(["zzbanned", "zzbanned2"])))
				db.session.commit()


if __name__ == "__main__":
	unittest.main()
