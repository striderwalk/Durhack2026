"""
Home page: resting carousel and options, the 10 category cards, and search data.

Run from the project folder:   python -m unittest tests.test_home
JavaScript tests (grouping search results by category):
                               node --test tests/test_group_results.js

It only READS the database (instance/app.db), so run the app or
`python testdata.py` once first so there is data. The switch between states in
the browser is done by static/home.js; see the manual test in
docs/backend-integration.md.
"""

import re
import unittest

from app import app
from colours import GROUPS


class HomePageTest(unittest.TestCase):
	def setUp(self):
		# Every page now needs a signed-in user (moderation.gate)
		self.client = app.test_client()
		self.client.post("/login", data={"identifier": "alex", "password": "password123", "agree_terms": "yes"})

	def test_category_cards_are_the_ten_groups_in_order(self):
		html = self.client.get("/").get_data(as_text=True)
		cards = html.split('id="categories"', 1)[1].split('id="results"', 1)[0]
		keys = re.findall(r'class="cat-box" data-category="([a-z]+)"', cards)
		self.assertEqual(keys, list(GROUPS))  # all 10, in order
		# Every card shows its name (never colour alone)
		for name, *_ in GROUPS.values():
			self.assertIn(f'<span class="cat-name">{name}</span>', cards)
		# The results container starts empty and hidden
		self.assertIn('<div class="cat-grid" id="results" hidden></div>', html)

	def test_category_cards_hold_at_most_four_samples(self):
		html = self.client.get("/").get_data(as_text=True)
		for key in GROUPS:
			card = html.split(f'data-category="{key}"', 1)[1].split("</section>", 1)[0]
			self.assertLessEqual(card.count('class="cat-pill"'), 4, key)

	def test_resting_state_has_carousel_and_three_options(self):
		html = self.client.get("/").get_data(as_text=True)
		self.assertIn('class="marquee"', html)
		self.assertEqual(html.count('class="action-card"'), 3)

	def test_search_returns_interests_without_showing_tags_in_markup(self):
		data = self.client.get("/api/discover?q=music").get_json()
		self.assertTrue(data["groups"], "expected results for 'music'")
		for box in data["groups"]:
			self.assertTrue(box["interests"])
		# The page itself never renders tag names as #tags
		html = self.client.get("/").get_data(as_text=True)
		self.assertNotRegex(html, r'>#[a-z]')


if __name__ == "__main__":
	unittest.main()
