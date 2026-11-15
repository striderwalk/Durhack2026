# Backend changes (for Craig and Peter)

Small, targeted backend edits made from the frontend side. Each is its own
commit, so it can be undone on its own with `git revert <commit>`.

(An earlier version of this file was removed from `main` in 93910d9. The changes it
listed are in git history: a610551, f7bd510, a0b0b3d, 2b46eca and 4120c14.)


## SECURITY-RELEVANT: sign-up only for student-style @durham.ac.uk addresses (b7936ef)

- **File:** `app.py`, `register()`.
- **What changed:**
  - Sign-up now refuses any address that isn't exactly `…@durham.ac.uk` with **no dot before the `@`**, because staff addresses are `firstname.lastname@`.
  - Look-alike domains and sub-domains are refused too.
  - The message is generic: "Please use your student @durham.ac.uk address."
- **Not changed:** login for existing accounts, including any staff-style ones.
- **This restricts sign-up but does NOT verify that the person owns the inbox.** Email-code verification is planned.
- **Rule source:** there was no student-format rule in the code or docs, so this uses the no-dots rule. NEEDS INPUT: confirm it matches Durham's real formats.
- **Schema:** none.
- **Tested:** `tests/test_backend_changes.py`:
  - staff-style addresses, look-alike domains and sub-domains are refused;
  - a capitalised student address is accepted;
  - an existing staff-style account still signs in.
- **Undo:** `git revert b7936ef`.

## SCHEMA + SECURITY-RELEVANT: terms acceptance (8d7efd0, tests 36c0d73)

- **Files:** `models.py` (new `TermsAcceptance`); new `legal.py`; `moderation.py` (`ALWAYS_OPEN_ENDPOINTS`: legal pages open even to banned users); `profiles.py` (registers `legal` after `moderation`).
- **Schema (additive):** new table `terms_acceptances` (`acceptance_id`, `user_id`, `version`, `accepted_at`), one row per acceptance, created by `db.create_all()`. Nothing existing is changed.
- **What changed (tightens access):**
  - `legal.VERSION` is the single required version (one combined version for both documents).
  - A signed-in user without it gets the acceptance screen, or `403 {"error": "terms_required", "version"}` from APIs. This applies everywhere except sign-out, `/terms`, `/privacy`, `/accept-terms`, `/api/terms/accept` and `/api/session`.
  - `POST /login` and `POST /register` answer **400** without the `agree_terms` box, and record acceptance when it's ticked.
  - Existing users have no record, so they're asked on their next request.
- **New endpoints:**
  - `GET /terms`, `GET /privacy` (public);
  - `GET`/`POST /accept-terms`;
  - `POST /api/terms/accept` (JSON `{agree: true, version}`);
  - `GET /api/session` (`{user_id, needs_acceptance, terms_version}`).
- **Why:** clickwrap acceptance of the Terms and the data information, recorded on the server.
- **Tested:** `tests/test_legal.py`:
  - the box is required;
  - acceptance is recorded with version and time;
  - terms_required everywhere else, and acceptance clears it;
  - a new version asks again;
  - legal pages work signed out and while banned;
  - footer links appear on every kind of page.
- **Undo:** `git revert 36c0d73 8d7efd0`, and the legal-pages frontend commit. The table can stay or be dropped by hand.

## SCHEMA: trust and safety tables and soft-delete columns (84bd248)

- **New tables** (created by `db.create_all()`; additive):
  - `blocks`: unique pair, `CHECK (blocker_id <> blocked_id)`;
  - `flags`: partial unique index for one OPEN flag per reporter per target;
  - `user_bans`: user id **and** a sha256 of the email, with no foreign key, so a ban outlives the account;
  - `mod_actions`: the append-only audit log.
- **New nullable columns** on `interests`: `removed_at`, `removed_by`, `removal_reason` (soft delete).
  - New `migrations.py` adds them to existing databases at start-up with `ALTER TABLE … ADD COLUMN`, only when missing.
  - No column is dropped, renamed or retyped, and no data is changed.
- `Interest.creator` and `User.created_interests` now name their foreign key, because `interests` now has two user keys. Behaviour is unchanged.
- **Undo:** `git revert 84bd248`. The new tables and columns can stay, or be dropped by hand.

## SECURITY-RELEVANT: sign-in gate, bans, blocks, reports, moderators (796d583, tests a2c31c4)

- **Files:** new `moderation.py`; `profiles.py` (registers it); `profile_api.py` and `interest_api.py` (blocks enforced, removed interests skipped); `user_account.py` (won't add or re-create a removed interest).
- **Gate on every request (tightens access):**
  - signed-out users can reach only sign-in, registration and log-out; APIs answer **401**;
  - banned users are signed out, and see the ban screen or get **403 banned**;
  - 10 failed sign-ins per address or IP in 15 minutes give **429**.
- **Effect on existing behaviour:** the homepage, search and tag APIs are **no longer public**.
- **Blocks:** mutual in effect. Profiles and connection pages answer 404, people lists leave the users out, and connections and pending waves between them are deleted.
- **Reports:** for users and interests, with limits. The reporter is never shown to the reported user.
- **Moderators:** `MODERATOR_EMAILS`, checked on every call; everyone else gets **404**.
  - Moderators can't ban themselves or another moderator.
  - Every action writes `mod_actions`.
  - Emails show only on a user's detail page, on request, and that view is logged.
- **Removed interests:** hidden from every ORM query, through one session hook in `moderation.py`, except moderator views.
- **Privacy:** contact withholding and the "CIS codes and emails never returned to other users" rule are unchanged. Moderator lists contain no email, CIS code or password.
- **Tested:** `tests/test_moderation.py` (16 tests).
- **Undo:** `git revert a2c31c4 796d583`. The pages that use these then stop working, so revert the frontend commits too.

## Search: category names (`/api/discover`)

- **Files:**
  - `colours.py`: new `CATEGORY_ALIASES` and `match_categories()`, next to the existing category names, which both server and page already use, so the list isn't duplicated;
  - `discovery.py`: `discover()` adds `categoryMatches`, built by the new `category_matches()`.
- **What changed:** when the query is a category's name, an alias, or the start of a name (3 or more characters), the response also lists **all** that category's interests (most popular first, then A–Z), flagged `match_type: "category"`. The existing `groups` results are unchanged.
- **Why:** typing "science" should show Science's interests even though their names and tags don't contain the word.
- **Needed for:** "Homepage search: category names".
- **Schema:** no. **Security:** no new data. Interest names and links were already public in search.
- **Cost:** only when a category matches: one query for all interests (with their tags' categories) and one grouped count from `user_interests`.
- **Tested** (`tests/test_category_match.py`): exact, any letter case, extra spaces, prefix of 3+ characters, nothing under 3, aliases, no partial words ("sciencefiction"), several matches ordered best first, "science" returns every Science interest, and "chem" or "s" return none.
- **Undo:** `git revert 4bd9b72`. The page then simply gets no `categoryMatches`.

## SCHEMA: contacts as a typed list (new table `user_contacts`)

- **Files:**
  - `models.py`: new `UserContact` model;
  - new `contact_types.py`: validation;
  - `profiles.py`: `POST /u/<id>/edit`;
  - `profile_api.py`: reading contacts.
- **Schema change (additive only):** new table `user_contacts`:

  | Column | Type |
  |---|---|
  | `contact_id` | integer, primary key |
  | `user_id` | foreign key to `users`, indexed |
  | `contact_type` | varchar(20) |
  | `value` | varchar(200) |
  | `label` | varchar(24), nullable, only for "other" |
  | `position` | integer |

  - `db.create_all()` creates it on start-up; there's no migration tool in this project.
  - No existing table or column is changed, renamed or dropped.
- **What changed:**
  - `POST /u/<id>/edit` accepts a `contacts` field: a JSON list `[{"type", "value", "label"}]`. It replaces the user's rows, in order.
  - Forms that still send `instagram` / `x` / `email` work exactly as before.
- **Validation** (`contact_types.py`, every value checked on the server):
  - 12 types: email, phone, whatsapp, snapchat, discord, telegram, instagram, x, linkedin, github, website, other;
  - per-type patterns and length limits;
  - values are trimmed, and a leading `@` is removed from handles;
  - websites must start with `https://`, so `javascript:`, `data:` and `http:` are rejected;
  - control characters are rejected;
  - no duplicates of the same type and value;
  - at most 8 entries;
  - "other" needs a label of 2 to 24 characters.

  A bad list returns **400 with a readable message and saves nothing**.
- **Old data kept (MIGRATE, DO NOT LOSE):**
  - `users.contact_instagram`, `contact_x` and `contact_email` are kept and never cleared by the migration.
  - A user with no rows in `user_contacts` gets those values back as entries (ids `old-instagram` and so on). Values saved before this change still show and still work.
  - When a user saves a list, the old columns are set to the first entry of each kind (or empty), so they stay in step and never resurface after the user removes them.
  - No data was rewritten.
- **Security (privacy unchanged):**
  - `contacts` is still `None` for anyone who isn't the owner or a connection.
  - Their page has no contact values, types or count; it shows only the locked state.
- **Needed for:** "Contact: many kinds of contact method".
- **Tested** (`tests/test_backend_changes.py` `ContactListTest`, `tests/test_profile_pages.py`):
  - old values show;
  - a typed list saves in order;
  - `javascript:`, `data:`, `http:`, over-long, control characters, a missing label, duplicates, 9 entries and unknown types are all rejected with nothing saved;
  - strangers get `None` and no contact data in the page.
- **Undo:** `git revert ba85605 74981e5`
  - The table can stay or be dropped by hand.
  - The old columns still hold the first entry of each kind.

## Title case for new interest names

- **Files:** new `interest_names.py`; `interests.py` (`POST /interests/new`); `user_account.py` (where `/update-account` creates an interest from a name it doesn't know)
- **What changed:** before a **new** interest is saved, its name goes through `to_interest_title_case()`:
  - spaces are trimmed and collapsed;
  - each word gets a capital first letter;
  - words typed in capitals (CS, DNA, D&D) are kept;
  - small words (of, the, and…) stay lowercase inside a name;
  - hyphen, `&` and `/` parts are each capitalised;
  - a word starting with a digit ("1970s", "3d") is kept as typed.

  The browser uses the same rules (`static/titleCase.js`); `tests/title_case_cases.json` is the shared list both are tested against.
- **Why:** so names are consistent, and a direct request can't skip what the create form does.
- **Needed for:** create-interest title case.
- **Duplicate check:** unchanged. It was already case-insensitive (`func.lower`), so "astronomy" finds "Astronomy".
- **Schema:** no. **Data:** no. Existing interests are not renamed.
- **Security:** no.
- **Tested:** `tests/test_title_case.py` (27 shared cases) and `tests/test_backend_changes.py`:
  - a created name is saved in title case;
  - a lowercase duplicate goes to the existing interest and nothing new is created;
  - `/update-account` creates new names in title case.
- **Undo:** `git revert 5975efe 243502d`

## Not changed: Gaps for Craig and Peter

| Gap | Proposal |
|---|---|
| **Sign-in by one-time code** | The brief describes one-time codes (single-use, 10-minute expiry, hashed, rate-limited per address and IP) with no passwords. The app still uses passwords. Replacing that is an auth redesign: not done. |
| **Email verification and staff** | There's no "verified" flag and no way to tell staff from students, so "verified Durham students only" can't be enforced yet. |
| **Login limits are in memory** | Fine for one dev server; production needs a shared store, such as a table or Redis. |
| **CSRF tokens** | The new endpoints require JSON bodies, which stops plain cross-site form posts. Full CSRF protection is still missing site-wide. |
| **Retention** | How long flags, bans and audit rows are kept isn't decided. See `docs/moderation.md`. |
| **Category-match rules not yet agreed** | Prefix matching and the alias list (`colours.CATEGORY_ALIASES`) are a proposal; see `docs/search-ranking-spec.md`, "Category match". |
| **No wave / connection-request endpoint exists** | Waves are front-end placeholders (`sendWave` / `acceptWave` in `static/profile.js` send nothing). So there was no server check to add for "you can't wave to yourself". When the endpoint is built: reject `sender == target` with **400 "You can't wave to yourself"**, and make "accept wave" refuse a pending row whose requester and addressee are the same. |
| **Proposed CHECK constraint (Peter)** | `ALTER TABLE connections ADD CONSTRAINT no_self_connection CHECK (requester_id <> addressee_id);` — not added here, since it's a schema change. |
| **Contacts API shape not yet agreed** | The list shape `[{id, type, value, label}]` and the 12 types are a proposal. They're implemented on the existing `POST /u/<id>/edit`, not a new endpoint. |
| **Old contact columns** | Once everyone has saved a list, `users.contact_*` could be retired. Not now: they're the fallback. |
| **No edit-interest endpoint** | So there's no rename to apply title case to. When one is added, run the new name through `to_interest_title_case()` and keep the case-insensitive duplicate check. |
| **Existing names that differ from the rules** | Only "Medieval Re-enactment" in the seed data (the rules give "Re-Enactment"). Not renamed; fix it in `taxonomy.py` if wanted. |
| **Search is case-insensitive already** | `discovery.search_interests` lowercases both sides. No change needed. |
| **No interest slugs yet** | When slugs are added, build them from the title-cased name. |
