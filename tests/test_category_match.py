"""
Which categories a search query names (colours.match_categories), and that
/api/discover returns a named category's interests first.

Run from the project folder (after `python testdata.py`):
	python -m unittest tests.test_category_match
"""

import unittest

from colours import match_categories


class MatchCategoriesTest(unittest.TestCase):
	def keys(self, query, **kwargs):
		return [key for key, _how in match_categories(query, **kwargs)]

	def test_exact_names_ignore_case_and_spaces(self):
		for query in ("science", "SCIENCE", " science ", "Science"):
			with self.subTest(query=query):
				self.assertEqual(match_categories(query), [("science", "exact")])

	def test_prefix_needs_three_characters(self):
		self.assertEqual(match_categories("sci"), [("science", "prefix")])
		self.assertEqual(match_categories("mus"), [("music", "prefix")])
		self.assertEqual(match_categories("sc"), [])
		self.assertEqual(match_categories("s"), [])

	def test_aliases(self):
		self.assertEqual(match_categories("maths"), [("mathematics", "alias")])
		self.assertEqual(match_categories("tech"), [("technology", "alias")])
		self.assertEqual(match_categories("sports"), [("sport", "alias")])

	def test_no_partial_word_matches(self):
		self.assertEqual(match_categories("sciencefiction"), [])
		self.assertEqual(match_categories("chem"), [])
		self.assertEqual(match_categories(""), [])

	def test_several_matches_best_first(self):
		names = {"art": "Art", "artillery": "Artillery", "craft": "Craft"}
		aliases = {"craft": ["art"]}
		self.assertEqual(match_categories("art", names=names, aliases=aliases),
			[("art", "exact"), ("craft", "alias"), ("artillery", "prefix")])
		self.assertEqual(self.keys("art", names={"a": "Artistry", "b": "Artwork"}, aliases={}), ["a", "b"])


class CategorySearchTest(unittest.TestCase):
	def setUp(self):
		from app import app
		self.client = app.test_client()

	def test_category_name_returns_all_its_interests(self):
		import home_api
		from app import app
		with app.app_context():
			science = next(c for c in home_api.category_cards() if c["key"] == "science")
		data = self.client.get("/api/discover?q=science").get_json()
		first = data["categoryMatches"][0]
		self.assertEqual((first["category"], first["match"], first["match_type"]), ("science", "exact", "category"))
		self.assertEqual(len(first["interests"]), science["total"])  # all of them, not just top scorers

	def test_ordinary_queries_have_no_category_match(self):
		self.assertEqual(self.client.get("/api/discover?q=chem").get_json()["categoryMatches"], [])
		self.assertEqual(self.client.get("/api/discover?q=s").get_json()["categoryMatches"], [])


if __name__ == "__main__":
	unittest.main()
