# Search ranking: grouped by category, ranked by match

**Status: a proposal for the team (Craig, Peter) to agree.** Nothing in the backend
has been changed. Until something like this exists, the homepage uses a temporary
client-side fallback (`flattenTagGroups()` in `static/groupResults.js`).

## Behaviour

1. The query is compared **first** with interest names, **second** with the hidden tags attached to interests.
2. Each interest gets **one** score: its best match through its name or any tag. Name matches are slightly preferred:

   ```
   final = max(name_score, 0.9 * best_tag_score)
   ```

   Each score is between 0 and 1. Today `discovery.discover()` **adds** weights together (name 3.0, tag 2.0–2.5, co-occurring tag 0.5), so an interest with several matching tags can outrank an exact name match.
3. Matched interests are grouped into the **10 display categories** (`colours.GROUPS`, which maps the backend's 20 categories). Each interest appears in exactly **one** box: its own main category (`Interest.category`).
4. Inside a box, interests are sorted by score, best first. Boxes are sorted by their best interest's score, best first. Categories with no matches are left out.
5. **Tags are never shown** to people: not as box titles, labels or hints. Scores aren't shown either.

## Proposed response

`GET /api/search?q=` (or a new shape for `/api/discover`):

```json
[
  {
    "category": "science-and-the-natural-world",
    "best_score": 0.94,
    "interests": [
      { "id": 12, "slug": "foraging-and-mycology", "name": "Foraging and Mycology", "url": "/interests/12", "score": 0.94 },
      { "id": 31, "slug": "allotment-gardening", "name": "Allotment Gardening", "url": "/interests/31", "score": 0.81 }
    ]
  }
]
```

- `category` is the backend category slug. The frontend maps it to one of the 10 display groups and their colours with `colours.py`.
- Already grouped and sorted is ideal. If the backend sends a flat list of `{id, name, url, category, score}` instead, the frontend's `groupByCategory()` will group and sort it (it's unit-tested).
- No `tags` in the response, so they can't leak into the page.
- `slug` is optional until interests have slugs.

## Matching short queries

Plain substring matching misses things, and pure semantic search (pgvector, if the team moves to Postgres) is weak on short, partial words like `chem`. Suggestion:

- **Name score:** combine
  - prefix matching (`name ILIKE 'chem%'` or word-start), scored highest;
  - trigram similarity (`pg_trgm` `similarity(name, q)`) for typos and partial words;
  - when embeddings exist, cosine similarity between the query and the interest name or description.
- **Tag score:** the same prefix and trigram matching against tag names, and optionally the embedding similarity of the query to each tag.
- Take the **best** of each, then apply the rule above.
- On SQLite today, prefix + substring with `LIKE`, plus a small trigram score in Python over the top candidates, would be enough for this data size.

## What the frontend does now (to remove later)

- `flattenTagGroups()` gives each interest its tag group's category, and a score from its position in the response.
- It can put an interest in the wrong category box, and it can't rank name matches above tag matches by itself.
- Once the backend sends the shape above, delete `flattenTagGroups()` and pass the response (mapped in `home.js` `runSearch()`) straight to `groupByCategory()`.

## Category match (implemented in `4bd9b72`; rules NOT YET AGREED)

When the query names one of the 10 display categories, that category's interests are shown even if no name or tag contains the word. For example, "science" shows Astrophotography, Observational Astronomy and the rest.

**Matching** (`colours.match_categories`). Normalise the query: trim, lowercase, collapse spaces. A category matches by:

1. **exact** name: "science", "SPORT", " music ";
2. **alias** (exact): words in `colours.CATEGORY_ALIASES`:
   - mathematics: maths, math
   - technology: tech
   - arts: art
   - sport: sports
   - science: sciences
   - humanities: humanity

   To extend it, add lowercase words to a list. The page receives the same list.
3. **prefix** of the name, only for queries of 3 or more characters: "mus" → Music. "s" or "sc" never prefix-match.

More than one category can match. They're ordered exact, then alias, then prefix.

**Response** (`/api/discover`, added alongside the unchanged `groups`):

```json
"categoryMatches": [
  { "category": "science", "name": "Science", "match": "exact", "match_type": "category",
    "interests": [{ "id": 4, "name": "Space Exploration Society", "url": "/interests/4", "category": "Science and the natural world" }] }
]
```

- Each match lists **all** interests in that category: those whose main category maps to it through `colours.CATEGORY_GROUP`.
- They're sorted by how many students have each interest (most first), then A–Z.

**Page:**
- Category-match boxes come first, in the order above, with a small "Category" label.
- They show 8 interests plus "Show all N", which expands in place.
- The normal ranked boxes follow. Any interest already in a category box is removed from them, so each interest appears once (`GroupResults.withCategoryMatches`).
- A named category with no interests shows "No interests here yet. Create a new interest".

**For the team to decide:** whether prefix matching is wanted at all, which aliases to keep, and whether category matches should also feed the ranking score.
