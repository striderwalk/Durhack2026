# Backend integration: what actually exists

Written 14 Nov 2026 from `main` at `c348189`, after reading every Python file and template
on `main` and on the `craig`, `PeterDatabase`, `owen` and `owen2` branches.

## Summary

The integration brief assumed a **FastAPI + Postgres/pgvector** backend and a **React +
Tailwind** frontend. Neither exists. On every branch, the backend is one **Flask** app:

- **App:** Flask 3 with Jinja templates, in `app.py`, plus blueprints.
- **Database:** SQLite at `instance/app.db`, accessed through Flask-SQLAlchemy (`models.py`).
- **Auth:** Flask-Login with a session cookie (see section a.1).
- **Not present:** pgvector, embeddings, semantic search, OpenAPI docs (`/docs`), `.env`,
  `.env.example`, migrations (tables are made by `db.create_all()`), `package.json`.
- **Seed script:** `testdata.py` (5 users, 6 interests, connections, rooms). It drops every
  table when run.
- **Dependencies:** `requirements.txt` lists only `flask` and is UTF-16 encoded.
  Flask-Login and Flask-SQLAlchemy are not listed.

Pages are rendered on the server by Flask. There is no separate frontend, so in this doc
"frontend" means the templates plus the small data layers that feed them (`profile_api.py`,
`discovery.py`).

## ⚠️ Security and privacy problems found (verified by running the app)

1. **Any password signs in.** `auth.load_user()` takes a `password` argument but never
   checks it, and `POST /login` calls it and signs the user in.
   - Signing in as `alex` with the password `WRONG` redirected to `/account` and showed
     Alex's details.
   - Fix: call `user.check_password(password)` in `load_user()`, or in `login_post()`.
2. **Anyone can read any user's email**, even when not signed in. `GET /view/<username>`
   renders `other_user.email`.
   - `/view/maya` showed `maya@uni.ac.uk` to a signed-out visitor.
3. **The CIS code is public.** `User.username` is the CIS code (comment in `login_post`,
   and the sign-in label says "CIS code or username").
   - `/view/<username>` puts it in the URL and prints it on the page.
   - `account.html` prints it too.
4. **No Durham or student check.** `POST /register` accepts any email domain and any
   username, with no verification.
   - Registering `someone@gmail.com` created an account and signed it in.
   - Nothing distinguishes students from staff.
5. **Unknown users don't give a 404.** `/view/<anything>` returns 200 and renders an empty
   profile.

## a) Endpoints

Auth for all of these is the Flask-Login **session cookie** set by `POST /login`. It is
not a bearer token. Unless stated, routes don't require sign-in. "HTML" means a page,
not JSON.

### a.1 Auth (`app.py`, `auth.py`)

| Method | Path | Request | Response | Auth |
|---|---|---|---|---|
| GET | `/login` | – | HTML sign-in form | none |
| POST | `/login` | form: `identifier` (username/CIS code **or** email), `password` | 302 to `/account` on match, else 302 to `/login`. **Password not checked (problem 1).** | none |
| GET | `/logout` | – | 302 to `/login` | none |
| GET/POST | `/register` | form: `username`, `email`, `password`, `confirm_password` | Creates a user and signs them in. Renders `success.html`, or re-renders the form with no message on error. | none |
| – | (unauthorised handler) | – | Routes marked `login_required` render `unauthorized.html` (status 200) | – |

### a.2 Users and profiles

| Method | Path | Request | Response | Auth |
|---|---|---|---|---|
| GET | `/account` | – | HTML: the signed-in user's username, email, interests, categories and bio. Has a form posting to `/update-account`, **which doesn't exist (404)**. | login |
| GET | `/view/<username>` | username or email in the URL | HTML: that user's **username, email**, interests and bio | none (problem 2) |
| GET/POST | `/search` | form: `search` | HTML: users with an interest whose name contains the text (`search.find_users_by_interest`) | none |
| GET | `/find-new-interest` | – | 302 to a recommended `/interests/<id>` | login |
| GET | `/u/`, `/u/<handle>`, `/u/<handle>/edit` | – | Profile page. **Mock data only** (`profile_api.py`), not connected to the database. | none |

There is **no JSON profile endpoint**, **no profile update endpoint**, and **no wave or
connection endpoints** (send, accept or list).

### a.3 Interests, categories, tags and search (`interests.py`, `discovery.py`)

| Method | Path | Request | Response (JSON) | Auth |
|---|---|---|---|---|
| GET | `/api/interests` | `q` | `[{id, name, url, tags[]}]`: up to 8 interests whose name contains `q` | none |
| GET | `/api/discover` | `q` (empty means random) | `{query, nameMatches, groups: [{key, title, categories[], interests: [{id, name, url, tags[]}]}]}` | none |
| GET | `/api/tags` | `q`, `exclude` (repeatable) | `[{name, count, categories[]}]` | none |
| POST | `/interests/new` | form: `interest_name`, `description`, `tags` (repeatable) | 302 to `/interests/<id>` | none |
| GET | `/interests/<id>` | – | HTML interest page with related interests | none |
| GET | `/` | – | HTML home page with search, using `/api/discover` | none |

Search is **tag-based keyword matching**, not semantic. Groups are sorted by relevance,
but `discover()` keeps the scores internally and doesn't return them. There is **no
categories endpoint**: categories reach the page only as names inside `groups[].categories`
and `/api/tags`.

## b) Database tables (`models.py`)

| Table | Columns | Relations |
|---|---|---|
| `users` | `user_id` PK, `username` unique (**CIS code**), `display_name` nullable, `email` unique, `password_hash`, `bio` text, `avatar_url`, `created_at` | `user_interests`, `sent_connections`, `received_connections`, `created_interests`, rooms, messages |
| `categories` | `category_id` PK, `category_name` unique, `description` | many-to-many with `tags` through `tag_categories` |
| `tags` | `tag_id` PK, `tag_name` unique (lower case), `created_at` | many-to-many with `categories` and with `interests` (`interest_tags`) |
| `interests` | `interest_id` PK, `interest_name` unique, `description`, `cover_image_url`, `created_by_user_id` FK nullable, `created_at` | `tags`; `categories` and `category` are derived from the tags (Python properties, not columns) |
| `user_interests` | `user_id` + `interest_id` PK, `experience_level`, `personal_note`, `added_at` | joins users and interests |
| `connections` | `requester_id` + `addressee_id` PK, `status` (`"pending"`/`"accepted"`, default `"pending"`), `created_at`, `updated_at` | two FKs to `users` |
| `chat_rooms`, `room_messages`, `direct_messages` | (not relevant here) | |

The chain is Category → Tags → Interests. An interest has **no category column**: it gets
its categories through its tags, and `Interest.category` is the most common one. There are
**20 categories** (seeded from `taxonomy.py`), not 10.

## c) Field mapping

| Frontend needs | Comes from | Status |
|---|---|---|
| `handle` | Nothing public. `users.username` is the CIS code, so it **must not** be used. | **MISSING** |
| `display_name` | `users.display_name` (nullable) | ✓ (read only: no update endpoint) |
| `year` | – | **MISSING** |
| `avatar_colour` | – (`users.avatar_url` exists but holds an image URL, not a palette key) | **MISSING** |
| `bio` | `users.bio` | ✓ (read only) |
| `bio_published` | – | **MISSING**: today every bio is public |
| `connection_count` | `connections` rows with `status = "accepted"` where the user is `requester_id` or `addressee_id` | Derivable, no endpoint |
| `contacts` | – (only `users.email`, which `/view` leaks) | **MISSING** |
| `viewer_relation` | Derivable: signed-in `user_id` equal to the profile's means `self`; an accepted `connections` row means `connection`; otherwise `other` | Derivable, no endpoint |
| wave state (sent/received) | Derivable from `connections` with `status = "pending"` and its direction | Derivable; **no endpoints to send or accept** |
| interests with category | `user_interests` → `interests` → `tags` → `categories` (`Interest.category`) | Derivable (an interest may have no category) |
| categories (10) with sample interests | `categories` → `tags` → `interests` (20 categories) | Derivable, **no endpoint**; the count is 20 |
| tag-grouped results `[{tag, score, interests[]}]` | `GET /api/discover`: `groups[].title` is the tag, `groups[].interests`. Groups come back already sorted. | ✓ but **no `score`** and **not semantic** |
| category slug (for colours) | – (`category_name` only, e.g. "Science and Technology") | **MISSING** (slug derivable from the name) |

## Gaps for Craig and Peter

**Security (fix first)**
1. Check the password at sign-in (problem 1).
2. Stop `/view/<username>` showing the email to anyone, and return 404 for unknown users
   (problems 2 and 5).
3. Stop using the CIS code as a public identifier: add a separate public `handle` column
   (lowercase a-z, 0-9 and `_`, 3–20 characters) and use it in URLs (problem 3).

**Durham-only sign-in**
4. Accept only student `@durham.ac.uk` addresses, verify them by email link or code, and
   decide how staff are told apart from students (problem 4). The backend should be the
   only source for the allowed email format.

**New profile fields**
5. Add `year`, `show_year`, `avatar_colour`, `bio_published` and contact fields
   (`contact_instagram`, `contact_x`, `contact_email`). Default `bio_published` to false.

**New endpoints**
6. A profile read endpoint (JSON, or keep it server-rendered) that applies the privacy
   rules **on the server**:
   - contacts only for self and connections;
   - unpublished bios and hidden years only for self.
7. A profile update endpoint, with publish and unpublish for the bio.
   `account.html` already posts to `/update-account`, which doesn't exist.
8. Wave endpoints:
   - send a wave (creates a pending `connections` row);
   - accept a wave (sets the status to `accepted`);
   - optionally list waves received.

**Data and search**
9. A categories endpoint (slug, name, sample interests), if the home page should show a
   category grid.
10. Semantic search (pgvector) if it's still planned. Today search is keyword plus tag
    relations, and it doesn't return scores.

**Setup and running**
11. `requirements.txt`: save it as UTF-8 and add `flask-login` and `flask-sqlalchemy`.
12. Login is required on almost nothing. `/`, `/search`, `/view`, `/api/*`, `/interests/*`
    and `/u/*` are all public.
13. CORS: not needed while everything is served by Flask on one origin.
14. The secret key is hard-coded in `app.py` (`change-this-hackathon-secret`).

## Privacy check (current state)

- **Contacts withheld server-side?** There are no contact fields. The only contact detail
  is `users.email`, and it is **not** withheld: `/view/<username>` shows it to anyone.
- **CIS code withheld?** **No.** It is in `/view/<username>` URLs, printed on `/view` and
  `/account`, and asked for on the sign-in form.
- The mock profile page (`/u/…`) withholds contacts, drafts and hidden years on the
  server, but it uses made-up data and no real user records.

## What the frontend does with each gap (temporary fallbacks)

All of these are marked `TODO(backend)` in the code.

| Missing | Fallback | Where |
|---|---|---|
| public `handle` | Profiles live at `/u/<user_id>`. No @handle is shown. | `profiles.py`, `profile_api.py` |
| `display_name` empty | "Durham student" (never the username) | `profile_api.FALLBACK_NAME` |
| `year` | Not shown | `profile_api.to_profile` |
| `avatar_colour` | Picked from the palette by `user_id` | `profile_api.fallback_avatar` |
| `bio_published` | Treated as published, because bios are already public on `/view` | `profile_api.to_profile` |
| contacts | Empty for self and connections ("No contact details added yet"). `None`, so locked, for everyone else. | `profile_api.to_profile` and `get_profile` |
| update endpoint | Edit page previews changes, but its save and publish buttons are disabled | `templates/profile/edit.html` |
| wave endpoints | `sendWave` and `acceptWave` are stubs that send nothing and say so | `static/profile.js` |
| categories endpoint | The idle home page shows random tag groups from `/api/discover` | `static/home.js` |
| category slug | Made from `category_name` | `colours.category_slug` |

`viewer_relation`, `wave_status` and `connection_count` are **derived** from the real
`connections` table (they are not fallbacks).

## Running it locally

There's no separate frontend server, `.env` or CORS setup: Flask serves everything on
one origin.

```bash
pip install flask flask-login flask-sqlalchemy
rm -f instance/app.db          # only if your database predates the tags change
python testdata.py             # optional: 5 seeded users (drops all tables first)
python app.py                  # http://127.0.0.1:5000
```

- **Mac:** port 5000 is taken by AirPlay, so change the port in the last line of
  `app.py`, or turn off AirPlay Receiver.
- **Preview as:** only appears when the app runs with `app.run(debug=True)`.
- **Seeded accounts:** sign in with the user's email and `password123`.
  - Seen from `alex@uni.ac.uk`:
    - **self:** `/u/1`
    - **connection:** `/u/2` (maya), `/u/3` (liam)
    - **other, and has waved at you:** `/u/4` (priya)
    - **other:** `/u/5` (sam)
  - Until problem 1 is fixed, any password works.

---

# Interests ↔ users (added 14 Nov 2026, `main` at `c376fad`)

The backend is still Flask + SQLite. There is still no FastAPI, Postgres, pgvector or
OpenAPI, and nothing has been added for interests and users since the first part of
this doc.

## ⚠️ Privacy problem 6: `/search` gives out emails

`GET/POST /search` (`app.py`, `search.find_users_by_interest`, `templates/search.html`)
lists every user who has a matching interest. For each one, it renders:
- `person.email`;
- `person.id`, `person.name` and `person.phone` (not real `User` fields, so they're blank).

It needs no sign-in. Searching "mycology" while signed out showed all three seeded users'
email addresses. It also `print`s the user list to the server log on every search.

## a) Does a user ↔ interest relationship exist?

**Yes:** the `user_interests` table (`models.UserInterest`):

| Column | Type | Notes |
|---|---|---|
| `user_id` | FK → `users.user_id` | part of the primary key |
| `interest_id` | FK → `interests.interest_id` | part of the primary key |
| `experience_level` | string, default `"Curious"` | |
| `personal_note` | string | |
| `added_at` | datetime | |

It's exposed only through HTML pages, never JSON:

| Where | What it shows |
|---|---|
| `/account` | the signed-in user's own interests |
| `/view/<username>` | another user's interests, plus their email (problem 2) |
| `/search` | users whose interest name contains the text, with emails (problem 6) |
| `/u/<user_id>` (our profile page) | a user's interests, read directly from the table by `profile_api.py` |

## b) Endpoints for an interest's details, an interest's users, or a user's interests

| Method | Path | Gives | Auth |
|---|---|---|---|
| GET | `/interests/<interest_id>` | HTML interest page: name, categories (through tags), description, tags, and related interests (`discovery.related_interests`, ranked by shared tags) | none |
| GET | `/api/interests?q=`, `/api/discover?q=` | `{id, name, url, tags[]}` per interest; no users, no counts | none |
| POST | `/search` | users with an interest whose **name contains** the text (not by ID), as HTML with emails | none |

There is **no endpoint** that returns an interest's users or user count, and no way to add
or remove an interest for the signed-in user (`account.html` posts to `/update-account`,
which doesn't exist). There are no wave endpoints, and no discoverability or opt-out
setting.

## c) Field mapping for the interest page

| Frontend needs | Comes from | Status |
|---|---|---|
| `slug` | – (interests are addressed by `interest_id`) | **MISSING**: page stays at `/interests/<id>` |
| `name` | `interests.interest_name` | ✓ |
| `category` | `Interest.category`: most common category across its tags, or none if untagged | ✓ (derived) |
| `description` | `interests.description` | ✓ |
| `tags[]` | `interests` → `interest_tags` → `tags.tag_name` | ✓ |
| `related_interests[]` | `discovery.related_interests(interest)` | ✓ |
| `interested_count` | count of `user_interests` rows for the interest | Derivable, no endpoint |
| `viewer_has_interest` | a `user_interests` row for (viewer, interest) | Derivable, no endpoint |
| users `[]`, paginated | `user_interests` → `users`, newest first | Derivable, **no endpoint, no cursor** |
| user `handle` | – (`username` is the CIS code) | **MISSING**: cards link to `/u/<user_id>` |
| user `display_name` | `users.display_name` (else "Durham student") | ✓ |
| user `avatar_colour` | – | **MISSING**: same palette fallback as the profile page |
| user `year` | – | **MISSING**: never shown |
| user `wave_state` | `connections`: `accepted` → connected; `pending` → sent or received, depending on direction | Derivable |
| add / remove interest | – | **MISSING** |
| discoverability opt-out | – | **MISSING** |

### What the interest page does with each gap (temporary, marked `TODO(backend)`)

| Gap | What happens |
|---|---|
| The user list and count have no endpoint | `interest_api.py` reads `user_interests` directly and selects **only** `user_id` and `display_name` for cards. It never loads emails, usernames or bios into a card. |
| No pagination endpoint | "Load more" asks the same page for the next 12 (`?page=N&partial=people`), counted on the server. |
| The backend doesn't exclude the viewer | `interest_api.py` excludes the signed-in user on the server, not in the browser. |
| No add/remove endpoint | The "+" button shows the real state (added or not) but is disabled, with a "coming soon" message. |
| No wave endpoints | Card Wave buttons reuse the profile page's `sendWave`/`acceptWave` stubs in `static/profile.js`. They send nothing and say so. |
| No discoverability setting | Everyone with the interest is listed and counted. |

## Gaps for Craig and Peter (interest ↔ users)

1. **Fix `/search` (problem 6).** Stop rendering emails, require sign-in, and remove the
   `print` calls.
2. **Interest users endpoint.** Return only public fields (handle, display name, avatar
   colour, year if shown, wave state), paginated with a cursor, excluding the viewer and
   anyone who opted out. Include the total count.
3. **Add/remove interest endpoints** for the signed-in user (fixing the broken
   `/update-account` would also do).
4. **Discoverability setting:** a `users` column, respected by search, interest user lists
   and counts.
5. **Interest slugs:** a unique slug column, if the URLs should be `/interest/<slug>`.
6. The earlier gaps still apply: handle, year, avatar colour, wave endpoints, and the
   password check.

### Testing the interest page locally

After `python testdata.py`, sign in as `alex@uni.ac.uk` with the password `password123`.

| Interest | What it shows |
|---|---|
| **Urban Mycology & Spore Printing** | 3 interested, including you. Maya and Liam show as **Connected**. |
| **Cyanotype Sun Printing** | Maya and Liam are connected, and Priya shows **Accept wave** because she waved at you. You don't have this interest. |
| Any taxonomy interest, e.g. `/interests/1` | The empty state |

Find an interest's ID from its link on the home page, or in the profile pills.
`/interests/99999` shows the not-found page.

"Load more" appears once more than 12 people have an interest. The seed data has at most
3, so add users for testing, but only in a copy of the database, not in `testdata.py`.

---

# Login, own profile, creating interests and the category home page (14 Nov 2026, `main` at `5fe703e`)

The backend is still Flask + SQLite. **New since the last section:** Peter's
`POST /update-account` (`app.py`, `user_account.py`).

## ⚠️ Security gaps (verified)

1. **Any password still signs in** (problem 1): `alex@uni.ac.uk` with the password `WRONG` reaches `/account`.
2. **`/update-account` can change `users.username`, which is the CIS code**, to any unused value.
   - Someone could take another person's CIS code before that person registers.
   - The frontend never sends `new-username`, but the server accepts it.
3. **`POST /interests/new` needs no sign-in.** Signed-out visitors can create interests, with no creator recorded. The home page only shows the form to signed-in users, but that is not protection.
4. **Typos create interests.** `/update-account` silently *creates* an interest when `new-interests` doesn't match one exactly.
   - The frontend only sends exact names taken from search results.
5. **Interest editing:** there is no endpoint to edit an interest, so the server enforces nothing about who may edit.
   - `interests.created_by_user_id` exists, and the page uses it to show the creator a (disabled) Edit button.
   - When an edit endpoint is added, it **must** check the creator on the server.
6. **No CSRF protection** on any POST (`/login`, `/update-account`, `/interests/new`).
   - Modern browsers' default `SameSite=Lax` cookies limit this, but nothing in the app sets it.

## LOGIN STATUS

Tested with Flask's test client and the in-app browser against a seeded copy of the database.

| Case | Status | Notes |
|---|---|---|
| Student email → verification email/link/code → signed in | **CANNOT TEST** | There is no verification step and no email service. Sign-in is email (or username) plus password. |
| Sign in with correct email + password | **WORKS** | Redirects to `/account`. |
| Refresh keeps the session | **WORKS** | Flask-Login session cookie. It lasts until the browser closes (no "remember me"). |
| Sign out | **WORKS** | `/logout` → `/login`. Protected pages then need sign-in again. |
| Wrong password | **BROKEN (backend)** | Signs in anyway (security gap 1). |
| Wrong or expired code | **CANNOT TEST** | There are no codes. |
| Non-Durham address (e.g. `@gmail.com`) | **BROKEN (backend)** | `/register` accepts any domain. Signing in with an unknown address correctly fails, and now shows the Durham-only message (fixed). |
| Staff-style address (e.g. `j.smith@durham.ac.uk`) | **BROKEN (backend)** | Nothing tells students from staff. A staff-style address registered and signed in. |
| Empty fields | **WORKS** | The browser blocks empty fields. The server also rejects them and returns to `/login`. |
| Protected page while signed out | **WORKS (fixed)** | `/u/*` and `/interests/*` redirect to `/login`. Backend routes with `login_required` showed a page whose link opened a new tab; it now redirects to `/login`. Routes without `login_required` (`/`, `/search`, `/view/*`, `/api/*`, `POST /interests/new`) stay public. |
| CIS code handling | **PARTLY** | Since `4654f08` (Craig), sign-in asks for "Email or username" again, so the CIS code can be typed in. The backend still shows usernames on `/account` and `/view`, and the register form still asks for "Username". |

**Frontend fixes made:**
- the sign-in page shows the Durham-only message after a failed attempt;
- `unauthorized.html` now redirects to sign-in.

The message never reveals whether an address has an account.

## Endpoints used by this work

| Method | Path | Request | Response | Auth |
|---|---|---|---|---|
| POST | `/update-account` | form: `new-username`, `new-bio`, `new-interests` (comma-separated names), `remove-interests` (comma-separated names) | 302 → `/account` | login |
| POST | `/interests/new` | form: `interest_name`, `description`, `tags` (repeatable) | 302 → `/interests/<id>`, or to the existing interest if the name matches | **none** |
| GET | `/api/interests?q=` | – | `{results: [{id, name, url, tags[]}]}`: name contains `q` (keyword, not semantic) | none |
| GET | `/api/tags?q=&exclude=` | – | `{results: [{name, count, categories[]}]}` | none |
| GET | `/api/discover?q=` | – | `{query, nameMatches, groups: [{key, title, categories[], interests[]}]}` | none |
| GET | `/find-new-interest` | – | 302 to **one** recommended interest | login |

**How `/update-account` behaves:**
- `new-bio` is ignored when blank, so a bio can't be cleared;
- it has no length limit and no draft state;
- it can't set the display name, year, avatar colour or contacts.

**Not found:**
- no endpoint to edit or delete an interest;
- no categories endpoint;
- no suggestions endpoint beyond the single `/find-new-interest` redirect;
- no re-embed endpoint (there are no embeddings at all).

## Field mapping

| Frontend needs | Comes from | Status |
|---|---|---|
| save bio | `POST /update-account` `new-bio` | ✓, but only as **published** (no drafts) and can't be cleared |
| `bio_published` / drafts | – | **MISSING**: only "Publish bio" saves |
| save display name, year, avatar colour, contacts | – | **MISSING**: inputs shown disabled |
| add / remove an interest | `POST /update-account` `new-interests` / `remove-interests`, by exact name | ✓ |
| suggestions (3, similar, excluding owned) | `discovery.related_interests()` per owned interest, ranked by `profile_api.get_suggestions` | Derived (no endpoint). Dismissals aren't stored. |
| create interest: name, description, tags | `POST /interests/new` | ✓ |
| create interest: **category** | – (categories come only from tags) | **MISSING**: the form says the category comes from tags |
| auto-add a created interest | `POST /update-account` `new-interests` right after creating | ✓ (two requests) |
| duplicate check | `GET /api/interests?q=` (name contains) | ✓, keyword not semantic |
| `viewer_is_creator` | `interests.created_by_user_id` | ✓ |
| edit interest | – | **MISSING** |
| interest `slug` | – | **MISSING**: URLs stay `/interests/<id>` |
| categories (10) with samples | `categories` → `tags` → `interests`, read by `home_api.py` | Derived (no endpoint). The backend has **20** categories; `colours.py` groups them into the 10 shown. |
| a tag-box interest's own category | – (`/api/discover` returns categories per box, not per interest) | **MISSING**: pills use their box's colour |

## Gaps for Craig and Peter (this round)

1. **Security first:** check passwords; stop `/update-account` changing the CIS-code username; require sign-in for `POST /interests/new`; add CSRF protection.
2. **Durham-only sign-in:** email verification (link or code), student-only addresses, and a way to exclude staff.
3. **Profile fields and drafts:** `display_name`, `year`, `show_year`, `avatar_colour`, `bio_published` and contact columns, with an update endpoint that accepts them. Allow clearing the bio.
4. **Interest editing:** an update endpoint (name, description, tags) that checks `created_by_user_id` on the server, plus slugs that stay the same after a rename.
5. **Category on create:** a field, if interests should have a category of their own rather than one taken from their tags.
6. **Suggestions endpoint:** returns N similar interests excluding the user's own, with a way to dismiss one permanently.
7. **Categories endpoint**, and **each interest's category** in `/api/discover` results.
8. **JSON errors:** `/update-account` and `/interests/new` should return 4xx with a message, so the page can show it (for example, for a duplicate name). Today they only redirect.
9. **If semantic search arrives:** creating or editing an interest will need a re-embed step on the server.

## Privacy check (this round)

- **Contacts:** withheld on the server for non-connections. There are no contact fields at all; for strangers `profile_api` sets `contacts` to `None`.
- **Public cards and profiles:** responses for `/u/<id>` (other students), `/interests/<id>` and the partials contain no email or username. This was checked by fetching the HTML the pages receive.
- **The owner's own page** contains only their own data.
- **Still showing private data (backend):** `/account` shows your own email and username (CIS code) to you.
- **Fixed on `main` (Craig):** `/search` was removed (`182f6bb`), so problem 6 (emails on `/search`) is gone. `/view/<username>` was removed (`690a79a`), so problems 2, 3 and 5 (emails and CIS codes on `/view`) are gone too.
- **Two ways to create an interest now exist:** the home page's "Create it?" form (with tag chips, duplicate check and auto-add) and Craig's separate `/create_interest` page (`690a79a`). His page loads no script, so its tag field can't add tags yet. The team should pick one.

## Home page: categories before typing (manual test)

Automated part: `python -m unittest tests.test_home`. It checks that the page renders exactly the 10 category cards and that the tag-box container starts empty and hidden, and that a typed query returns tag boxes.

In the browser:
1. Open `/`. You should see exactly 10 cards (Science … Recreation), each with its name on a coloured header and 3–4 interests.
2. Type `music`. The cards disappear and tag boxes (`#music` …) appear, labelled with their category.
3. Clear the box (or press Escape). The 10 category cards come back straight away.
4. Reload the page. The sample interests change. They don't change while you type.

## Testing this round locally

```bash
python testdata.py
```

```bash
python app.py
```

Sign in as `alex@uni.ac.uk` with the password `password123`.

| Test | Steps |
|---|---|
| Own profile | Open `/u/` → **Edit profile**. Publish a bio, remove an interest with ×, add one through "Add an interest", and use **Add** and × on the suggestions. |
| Preview | **Preview as others see me** shows the public view. |
| Create | Search for something that doesn't exist → **Create it?** Try the name `Astrophotography` first to see "Did you mean…". You land on the new interest, already added. |
| Creator vs others | The creator sees a disabled **Edit**. Sign in as `maya@uni.ac.uk`: no Edit button. |
| Home | See the manual test above. |

---

# Account settings, homepage states and category search (15 Nov 2026, `main` at `c979f1c`)

The backend is still Flask + SQLite (there is no FastAPI, Postgres, pgvector or
`/openapi.json`). **New since the last section (Peter, `a6b3d08`):** user columns
`year`, `show_year`, `avatar_colour`, `bio_published`, `contact_instagram`,
`contact_x`, `contact_email`, and `POST /u/<id>/edit` in `profiles.py`.

## Endpoints found

| Method | Path | Request | Response | Auth | Used for |
|---|---|---|---|---|---|
| POST | `/u/<id>/edit` | form: `display_name`, `year` (one of the years, or `hide`), `avatar_colour`, `bio`, `instagram`, `x`, `email`, `action` (`save` / `publish` / `unpublish`) | 302 → `/u/<id>` (save) or → `/u/<id>?edit=1` (publish/unpublish); 403 if not yours | login (via the blueprint) | Settings → Profile details and Privacy; profile edit mode |
| GET | `/logout` | – | 302 → `/login` | – | Settings → Sign out |
| GET | `/api/discover?q=` | – | `{query, nameMatches, groups: [{key, title, categories[], interests: [{id, name, url, tags[]}]}]}`: grouped **by tag** | none | Homepage results (regrouped by category in the browser) |
| GET | `/api/interests?q=` | – | `{results: [{id, name, url, tags[]}]}`: name contains `q` | none | Name dropdown under the search box |

**How `POST /u/<id>/edit` behaves (important):**
- It sets **every** field from the form each time. A missing field is saved as empty, so the frontend always sends all saved values (`static/account.js`).
- Saving a *changed* bio with `action=save` turns it into an unpublished draft. Settings and profile edit mode always send the last saved bio, so they never unpublish it by accident.
- `year=hide` keeps the stored year but sets `show_year` false.
- There is **no** handle field, change limit or availability check.
- It returns a redirect, never a JSON error.

**Not found:**
- a public handle, or an availability check for one;
- a "verified Durham student" flag;
- a discoverability ("Show me on interest pages") setting;
- account deletion;
- a search endpoint that returns each interest's **own category** or a **score**;
- any Discover or recommendation endpoint other than the one-result `/find-new-interest` redirect.

## Field mapping

| Field needed | Endpoint + field | Status |
|---|---|---|
| display name (1–30, optional) | `POST /u/<id>/edit` `display_name` | ✓ (server trims to 30) |
| year, incl. "Don't show" | `year` (`hide` hides it) | ✓ |
| avatar colour | `avatar_colour` (keys in `colours.AVATAR_COLOURS`) | ✓ |
| contacts (Instagram, X, email) | `instagram`, `x`, `email` | ✓ (no format check on the server) |
| "Show my year" toggle | `year` = stored year, or `hide` | ✓ (shares the field with the year dropdown) |
| bio published / draft | `action=publish` / `unpublish`; `users.bio_published` | ✓ |
| handle (`a-z 0-9 _`, 3–20) | – | **MISSING**: field shown disabled, "Coming soon" |
| handle availability check | – | **MISSING** |
| handle change limit | – | **MISSING** |
| "Verified Durham student" badge | – | **MISSING**: not shown, because nothing records verification |
| discoverability toggle | – | **MISSING**: switch shown on and disabled, "Coming soon" |
| delete account | – | **MISSING**: button disabled, "Coming soon" |
| sign out | `GET /logout` | ✓ |
| search: each interest's own category | – (`/api/discover` gives categories per **tag group**) | **MISSING**: temporary fallback (below) |
| search: score per interest | – | **MISSING**: temporary fallback uses the order of the response |
| homepage carousel | `discovery.suggested_names(16)`, passed by `app.py` `home()` as `chips` | ✓ (restored) |

## What the frontend does with each gap (temporary, marked `TODO(backend)` in code)

- **Handle, verification, discoverability, deletion:** shown on `/settings` but switched off, each labelled "Coming soon". No fake data, and nothing is sent.
- **Search categories and scores:** `flattenTagGroups()` in `static/groupResults.js` (clearly marked as a fallback):
  - It turns the tag groups into a flat list. It ranks by **position** (earlier group, then earlier in the group), which follows the backend's own ordering.
  - It gives each interest the category of the **tag group it arrived in**, not its own category. So an interest can land in the wrong box (for example, "print" puts some printing interests under Recreation).
  - It **cannot** rank name matches above tag matches by itself.
  - `groupByCategory()` then builds the boxes. That part is final and unit-tested.
- **"Matching names" box:** the backend still sends a `__matches` group for name matches that no tag could place. The frontend no longer shows it as its own box: those interests are regrouped like any other, so untagged ones land in a grey "Other" box.

## Gaps for Craig and Peter (this round)

1. **Search response by category** (`docs/search-ranking-spec.md`): each interest's own category and a score, ideally already grouped and sorted. Then delete `flattenTagGroups()`.
2. **Handle:** a `handle` column (unique, `a-z 0-9 _`, 3–20), an availability check (`GET /api/handles/<handle>` → `{available}`), and an update with any change limit returning a readable error. Profile URLs could then use it instead of the user id.
3. **Verification flag**, so the "Verified Durham student" badge can be shown truthfully.
4. **Discoverability:** a `discoverable` column, applied **on the server** when listing an interest's people (`interest_api.get_people`).
5. **Account deletion** endpoint (with cascade rules for connections, interests list and messages; decide what happens to interests the user created).
6. **`POST /u/<id>/edit`:**
   - accept partial updates (only the fields sent), or document that every field is required;
   - validate contact formats;
   - return JSON errors instead of only redirecting.
7. Still open from earlier rounds:
   - any password signs in;
   - `/update-account` can change the CIS-code username;
   - `POST /interests/new` needs no sign-in;
   - no CSRF protection, which now also covers `POST /u/<id>/edit`.

## PRIVACY CHECK (this round, verified on a seeded copy)

- **Contacts:** withheld **by the server** for non-connections. As Maya and Liam (connections), Alex's profile HTML contains his contacts. As Priya and Sam (not connected), it doesn't. Pages are server-rendered, so the HTML response is what the Network tab shows.
- **Hidden year:** not in the HTML for other students when "Show my year" is off.
- **Owner-only data:** the `profile-saved` JSON (used for saving) is only on your own profile and `/settings`.
- **CIS code and sign-in email:** neither appears on `/settings`, profiles or search responses.
- **Search JSON:** `/api/discover` and `/api/interests` still send `tags[]`. The page never shows them, but they're visible in the Network tab. Tags aren't personal data.
- No PRIVACY BUG found this round.

## SECURITY GAPS (this round)

- **`POST /u/<id>/edit`** checks the owner on the server. Good. But it has no CSRF protection.
- Everything in `static/account.js` and `static/settings.js` is only for friendly messages; the server is the authority.
- Earlier gaps 1–6 above are unchanged.

## Testing this round locally

```bash
python testdata.py
```

```bash
python app.py
```

```bash
python -m unittest tests.test_home
```

```bash
node --test tests/test_group_results.js
```

Sign in as `alex` / `password123` (seed data).

| Test | Steps | Expected |
|---|---|---|
| Resting | Open `/` | Heading, two scrolling rows of interests, and Browse / Add an interest / Sign in (or Your profile) |
| Search mode | Click the search box | The 10 category cards, each with 3–4 random interests |
| Pills still work | Click a pill in a card | Opens that interest (the view doesn't collapse first) |
| Typing | Type `club` | Boxes by category, best match first; "N interests in M categories" is announced |
| Tag-only match | Type `botany` | Interests whose names don't say botany (e.g. Foraging and Mycology); no tags visible |
| Empty | Type `zzqxv` | "No matches yet. Try a broader word." with "Create a new interest" (pre-filled) |
| Clear by typing | Delete the text | Back to the category cards |
| Escape / clear button / click outside | With an empty box | Back to resting |
| Settings | Menu → Settings | Change name, colour or contacts → Save profile details → "Saved."; turn off "Show my year" → Save privacy; reload to confirm |
| Profile edit | `/u/` → Edit profile → change year → Done | Saved and shown; Unpublish / Publish bio work |

---

# Trust and safety (moderation.py)

Full rules, roles and retention are in [docs/moderation.md](moderation.md); that's also where the list of every endpoint with its access level lives. New endpoints:

| Method | Path | Body / query | Answer | Who |
|---|---|---|---|---|
| POST | `/api/blocks` | JSON `{user_id}` | 201 `{blocked: true}`; 400 for yourself | signed in |
| DELETE | `/api/blocks/<user_id>` | – | `{blocked: false}` | signed in |
| GET | `/api/blocks` | – | `{blocked: [{id, display_name}]}`: people you blocked | signed in |
| POST | `/api/flags` | JSON `{target_type: "user"\|"interest", target_id, reason, message?}` | 201 `{message}`; 400 bad input or self; 409 already open; 429 more than 10 an hour | signed in |
| GET | `/api/mod/flags?status=open\|resolved` | – | `{flags: […]}` | moderators (others: 404) |
| GET | `/api/mod/flags/<id>` | – | flag plus target, linked creator and reporter | moderators |
| POST | `/api/mod/flags/<id>/dismiss` or `/action` | JSON `{note?}` | the flag | moderators |
| POST | `/api/mod/interests/<id>/remove` or `/restore` | JSON `{reason}` (required) | the interest | moderators |
| POST | `/api/mod/users/<id>/ban` | JSON `{duration: "1"\|"7"\|"30"\|"permanent", reason}` | the user; 400 for yourself or another moderator | moderators |
| POST | `/api/mod/users/<id>/unban` | JSON `{reason?}` | the user | moderators |
| GET | `/api/mod/users?q=` | display name or id | `{users: […]}`: no emails | moderators |
| GET | `/api/mod/users/<id>?email=1` | – | status, bans, reports; `email` only with `email=1` (logged) | moderators |
| GET | `/api/mod/audit?action=` | – | `{actions: […]}` | moderators |

Pages: `/mod`, `/mod/flags/<id>`, `/mod/users`, `/mod/users/<id>`, `/mod/audit` (moderators only).

**Errors** every page and API can now return:
- `401 {"error": "signin_required"}` when signed out;
- `403 {"error": "banned", "type", "expires_at", "contact"}` when banned;
- `429` after too many failed sign-ins.
