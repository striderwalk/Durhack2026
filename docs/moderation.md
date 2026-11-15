# Moderation and trust and safety

How Durham Superposition keeps people safe: who can do what, what is stored and
for how long, and what moderators can and can't see. Written plainly so it can
feed the Terms and the privacy information. (Code: `moderation.py`.)

> **Not yet decided by the team** (see the end): the sign-in method, email
> verification, how long reports and bans are kept, and the moderators' contact address.

## Roles

| Role | Who | Can |
|---|---|---|
| **Student** | A signed-in, not-banned account | Use the site; block people; report people and interests |
| **Moderator** | A signed-in account whose email is in the `MODERATOR_EMAILS` setting | Everything a student can, plus the moderator panel at `/mod` |

There is no shared moderator account and no shared code: each moderator signs in as
themselves, and every action is recorded under their name.

### Adding or removing moderators

- Set `MODERATOR_EMAILS` to their verified email addresses, comma-separated, either in the server's environment or in the app config (see `.env.example`).
- It's checked on **every** moderator request, so a change applies as soon as the server sees the new setting.
- To remove all moderators, clear the setting.
- Never commit real addresses to the code.

## Signing in (Phase 0 audit)

**The app today signs in with an email or username and a password.** It doesn't use one-time codes. The one-time-code design (single-use, 10-minute expiry, hashed, rate-limited) doesn't exist yet, so it isn't built here; see NEEDS INPUT.

What is enforced now, on the server, for every request:

- **Signed out:** only the sign-in, registration and log-out pages can be reached.
  - Every other page sends you to sign-in.
  - Every `/api/…` request answers `401 {"error": "signin_required"}`.
- **Banned:**
  - The session is ended on the next request.
  - Pages show the ban screen (HTTP 403).
  - APIs answer `403 {"error": "banned", "type", "expires_at", "contact"}`.
- **Repeated failed sign-ins:** 10 failures per address or per IP address in 15 minutes gives `429` for 15 minutes.
  - This is kept in the server's memory, so it resets on restart and isn't shared across processes. It's enough for development, not for production.
- **Registration** accepts only `@durham.ac.uk` addresses.
  - Nothing yet tells students from staff.
  - Nothing proves you own the address: there's no verification email.

### Every endpoint and who can use it

| Method | Path | Who |
|---|---|---|
| GET | `/` | Signed in and not banned |
| GET | `/account` | Signed in and not banned |
| POST | `/api/blocks` | Signed in and not banned |
| GET | `/api/blocks` | Signed in and not banned |
| DELETE | `/api/blocks/<int:user_id>` | Signed in and not banned |
| GET | `/api/discover` | Signed in and not banned |
| POST | `/api/flags` | Signed in and not banned |
| GET | `/api/interests` | Signed in and not banned |
| GET | `/api/mod/audit` | Moderators only (others get 404) |
| GET | `/api/mod/flags` | Moderators only (others get 404) |
| GET | `/api/mod/flags/<int:flag_id>` | Moderators only (others get 404) |
| POST | `/api/mod/flags/<int:flag_id>/action` | Moderators only (others get 404) |
| POST | `/api/mod/flags/<int:flag_id>/dismiss` | Moderators only (others get 404) |
| POST | `/api/mod/interests/<int:interest_id>/remove` | Moderators only (others get 404) |
| POST | `/api/mod/interests/<int:interest_id>/restore` | Moderators only (others get 404) |
| GET | `/api/mod/users` | Moderators only (others get 404) |
| GET | `/api/mod/users/<int:user_id>` | Moderators only (others get 404) |
| POST | `/api/mod/users/<int:user_id>/ban` | Moderators only (others get 404) |
| POST | `/api/mod/users/<int:user_id>/unban` | Moderators only (others get 404) |
| GET | `/api/tags` | Signed in and not banned |
| GET | `/connections` | Signed in and not banned |
| GET | `/find-new-interest` | Signed in and not banned |
| GET | `/interests/<int:interest_id>` | Signed in and not banned |
| POST | `/interests/new` | Signed in and not banned |
| GET | `/login` | Public (sign-in pages) |
| POST | `/login` | Public (sign-in pages) |
| GET | `/logout` | Public (sign-in pages) |
| GET | `/mod` | Moderators only (others get 404) |
| GET | `/mod/audit` | Moderators only (others get 404) |
| GET | `/mod/flags/<int:flag_id>` | Moderators only (others get 404) |
| GET | `/mod/users` | Moderators only (others get 404) |
| GET | `/mod/users/<int:user_id>` | Moderators only (others get 404) |
| GET, POST | `/register` | Public (sign-in pages) |
| GET | `/settings` | Signed in and not banned |
| GET | `/static/<path:filename>` | Public (sign-in pages) |
| GET | `/u/` | Signed in and not banned |
| GET | `/u/<int:user_id>` | Signed in and not banned |
| GET | `/u/<int:user_id>/connections` | Signed in and not banned |
| POST | `/u/<int:user_id>/edit` | Signed in and not banned |
| GET | `/u/<int:user_id>/edit` | Signed in and not banned |
| POST | `/update-account` | Signed in and not banned |

Moderator endpoints answer **404** to everyone else, as if they didn't exist.

## Blocking

- **Who:** any student can block another account (`POST /api/blocks`), see their own list (`GET /api/blocks`, or Settings → Blocked users) and unblock (`DELETE /api/blocks/<id>`).
- **Blocks work both ways.** Neither person can:
  - see the other's profile or connections page (they get a "not found" page, as if it didn't exist);
  - appear in the other's lists of people on interest pages, or in connection lists.
- **Ends existing ties:** blocking deletes any connection or pending wave between the two.
- **Silent:** the blocked person **isn't told**. They can't see who blocked them.
- **Stored:** who blocked whom, and when (`blocks` table), until the block is removed.

## Reports (flags)

- **What can be reported:** a person (⋯ → Report user on their profile) or an interest ("Report this interest" on its page).
- **Not allowed:** you can't report yourself or your own interest.
- **What a report holds:** a reason (spam, harassment, inappropriate, impersonation, other), plus an optional message of up to 500 characters.
- **Limits:**
  - one open report per person per target;
  - at most 10 reports an hour.
- **Interest reports:** these also record the interest's **creator**, so moderators see both. That doesn't penalise or mark the creator.
- **Reporter privacy:** the reported person **isn't told**, and is never shown who reported them.
- **Stored** (`flags` table): who reported, what, why, the message, when, and how a moderator resolved it.

## Removed interests

- **Soft removal:** moderators can remove an interest, with a required reason. It's **soft-deleted** (`interests.removed_at`, `removed_by`, `removal_reason`): never actually deleted.
- **Effect:** it disappears from search, pages (its page shows "not found") and profiles.
- **Moderator view:** moderators still see it, with the reason, and can restore it.

## Bans

- **Length:** temporary bans are 1 day, 7 days (default) or 30 days; permanent bans never expire.
- **Reason:** moderators must give one.
- **Effect:**
  - a banned person is signed out straight away, and can't sign in until the ban ends or is lifted;
  - they see when a temporary ban ends, and the contact line (`MODERATION_CONTACT_EMAIL`; a placeholder until it's set).
- **Who can be banned:** moderators can't ban themselves or another moderator.
- **Survives account deletion:** each ban is stored with a **hash of the verified email address** (sha256 of the lower-case address) as well as the account number, and has no link that would delete it with the account. Re-registering with the same address stays banned. **The privacy notice must say this:** "If your account is banned, we keep a one-way fingerprint of your email address so the ban still applies if you register again."
- **Stored** (`user_bans` table): account number, email fingerprint, type, end date, reason, who and when; plus when and by whom it was lifted.

## The audit log

- **What's recorded:** every moderator action writes a row to `mod_actions`, including dismissing or actioning a report, removing or restoring an interest, banning or unbanning, and **viewing someone's email**.
- **Each row has:** who, what, which target, details, and when.
- **Append-only:** there's no way in the app to change or delete it. Moderators can read and filter it at `/mod/audit`.

## What moderators can and can't see

**Can:**
- reports, with the reporter's display name (only on the report's detail page);
- the reported profile or interest, and the interest's creator;
- a user's ban history, and reports about them or their interests;
- a user's verified email address, only on that user's detail page, when they choose "Show verified email". That view is logged.

**Can't:**
- passwords;
- CIS codes (not shown in the moderator panel);
- sign-in tokens;
- private messages: chat doesn't exist, and no chat access is built.

## How long things are kept (to be decided)

Nothing is deleted automatically yet. Proposed for the team to agree:
- open and resolved reports: 12 months after resolution;
- the audit log: 2 years;
- bans: while active, and permanent-ban fingerprints for as long as the service runs;
- blocks: until removed.

## For the team (NEEDS INPUT)

- **Sign-in:** the brief describes one-time codes to an `@durham.ac.uk` address with no passwords. The app uses passwords. Moving to codes is an auth redesign, so it isn't done here.
- **Verification:** there's no "verified" flag or email check. "Verified Durham students only" can't be enforced until there is.
- **Staff:** nothing tells students from staff.
- **Contact address:** `MODERATION_CONTACT_EMAIL` isn't set, so banned users see a placeholder.
- **Retention periods:** above.
- **Handles:** there are no public handles, so blocks and moderator lookups use account numbers and display names.
- **CSRF:** the new endpoints require JSON bodies, which stops simple cross-site form posts. Full CSRF tokens are still missing site-wide.
