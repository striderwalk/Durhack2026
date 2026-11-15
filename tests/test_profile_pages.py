"""
Profile and settings pages render for the owner, and other people see the right
parts: suggestions only for the owner, contacts only for connections, and never
a Wave button for yourself.

Run from the project folder (after `python testdata.py`):
	python -m unittest tests.test_profile_pages
"""

import re
import unittest

from app import app


def signed_in(username):
	client = app.test_client()
	client.post("/login", data={"identifier": username, "password": "password123", "agree_terms": "yes"})
	return client


class ProfilePagesTest(unittest.TestCase):
	def test_owner_pages_render_with_the_contact_editor(self):
		alex = signed_in("alex")
		for url in ("/u/1", "/u/1?edit=1", "/settings"):
			with self.subTest(url=url):
				response = alex.get(url)
				self.assertEqual(response.status_code, 200)
				self.assertIn("data-contact-editor", response.get_data(as_text=True))

	def test_suggestions_row_only_on_your_own_profile(self):
		html = signed_in("alex").get("/u/1").get_data(as_text=True)
		self.assertIn('id="suggested-card"', html)
		# Below the two columns, not inside them
		self.assertLess(html.index('class="profile-columns"'), html.index('id="suggested-card"'))
		self.assertNotIn('id="suggested-card"', signed_in("alex").get("/u/2").get_data(as_text=True))

	def test_no_wave_button_for_yourself(self):
		alex = signed_in("alex")
		for url in ("/u/1", "/u/1?as=other", "/u/1?as=connection", "/connections"):
			with self.subTest(url=url):
				html = alex.get(url).get_data(as_text=True)
				self.assertIsNone(re.search(r'class="wave" data-user="1"', html))

	def test_strangers_see_the_locked_card_only(self):
		html = signed_in("priya").get("/u/1").get_data(as_text=True)  # not connected to Alex
		self.assertIn("Wave to connect", html)
		self.assertNotIn("contact-row", html)
		self.assertNotIn("contact-editor", html)


if __name__ == "__main__":
	unittest.main()
