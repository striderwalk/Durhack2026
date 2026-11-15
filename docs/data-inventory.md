# Data inventory

**Facts found in the code** on branch `feat/legal-pages-terms-consent`, checked
15 November 2026. Anything not verifiable from the code is marked **[TO CONFIRM]**.
This is the only source for the "Information on Data and Security" page
(`templates/legal/privacy.html`). Update both together.

> **Important differences from the project brief.** The brief describes one-time
> sign-in codes, verified emails, FastAPI, Postgres and pgvector embeddings. **The code
> has none of these**:
> - it's Flask with SQLite;
> - you sign in with an email or username and a password;
> - nothing verifies the email address;
> - search is plain database text matching, with no external AI or embedding service.

## a) and b): Personal data, where it's stored, who sees it, how long it's kept

The database is one SQLite file, `instance/app.db`. Its location in production is [TO CONFIRM].

**There is no account-deletion feature.** Nothing in the code deletes a user, so every record below is **kept indefinitely** unless someone deletes it by hand. [TO CONFIRM: a deletion process.]

### Account (`users` table)

- **Email address** (`email`)
  - **What:** typed at registration and stored in lower case. Registration accepts only `@durham.ac.uk` addresses (`app.py` `register`).
  - **Not verified:** nothing proves the person owns it.
  - **Who sees it:** the user, on their own `/account` page. Moderators see it only when they choose "Show verified email" on a user's detail page, and that view is logged.
  - **Never returned to other users** by any page or API.
- **Username** (`username`)
  - **What:** chosen by the user at registration and stored in lower case. It can be used to sign in.
  - **CIS code:** the team treats it as the CIS code, but it is **not derived from the email** in the code. [TO CONFIRM]
  - **Who sees it:** the user on `/account` (Craig's page). Never shown on profiles, interest pages or search, or in the moderator panel.
- **Password** (`password_hash`)
  - **What:** stored only as a one-way scrypt hash (Werkzeug `generate_password_hash`).
  - **Who sees it:** nobody can read the password. The hash is never returned by any API.
- **Display name** (`display_name`): optional. If empty, "Durham student" is shown.
  - **Who sees it:** all signed-in users, on profiles, interest pages and connection lists. Moderators too.
- **Year** (`year`, `show_year`)
  - **Who sees it:** the user always. Other users only when "Show my year" is on.
  - **Hidden means removed:** when it's off, the server leaves the year out of other people's pages.
- **Avatar colour** (`avatar_colour`): one of 8 colours, seen by all signed-in users.
- **Bio** (`bio`, `bio_published`): up to 160 characters.
  - **Draft:** unpublished bios are seen only by the user. The server sends an empty bio to everyone else.
  - **Published:** seen by all signed-in users.
- **`avatar_url`:** a column exists but nothing in the app sets or shows it.
- **`created_at`:** the time the account was made. Not shown to others.

### Contact details

- **Where:** the `user_contacts` table (type, value, optional label, position), plus the older `users.contact_instagram`, `contact_x` and `contact_email` columns, which are kept in step.
- **What:** up to 8 entries. Types: email, phone, WhatsApp, Snapchat, Discord, Telegram, Instagram, X, LinkedIn, GitHub, website, and other (with a label).
- **Who sees them:** the user, and their **connections** only.
- **Withheld on the server:** for anyone else the server sends no contact data at all (`contacts` is `None`): no values, types or count. Moderators' pages don't show contacts.

### Interests

- **Interests added to a profile** (`user_interests`: user, interest, `added_at`)
  - **Who sees them:** all signed-in users, on the profile.
  - **Interest pages:** each one lists the people who have it, with display name, year if shown, and avatar colour. Users who have blocked each other are left out of each other's lists.
- **Interests created** (`interests`: name, description, tags, `created_by_user_id`, `created_at`)
  - **Who sees them:** all signed-in users see the name, description and tags.
  - **The creator:** only the creator sees that they made it (an "Edit" note), plus moderators.

### Connections and waves (`connections` table)

- **What:** requester, addressee, status (pending or accepted) and times.
- **No wave endpoint:** the app has no way to send or accept a wave yet. The Wave buttons send nothing; rows come only from seed data. [TO CONFIRM when built]
- **Who sees them:**
  - the two people involved;
  - other signed-in users see the connection count, and the list on `/u/<id>/connections`.
- **Blocking** deletes any connection or pending wave between the two people.

### Messages (`chat_rooms`, `room_messages`, `direct_messages` tables)

- **What:** the tables exist and hold message text, but **no page or API reads or writes them**. Only `testdata.py` fills them with seed messages.
- **Who sees them:** nobody in the app. Moderators have no access.
- **Retention:** [TO CONFIRM when chat is built]

### Blocks (`blocks` table)

- **What:** who blocked whom, and when.
- **Who sees them:** the blocker, in Settings → Blocked users. The blocked person isn't told and can't see it.
- **Retention:** kept until unblocked.

### Reports to moderators (`flags` table)

- **What:** reporter, target (user or interest), the interest's creator, reason, optional message (up to 500 characters), status, times, and the moderator's resolution note.
- **Who sees them:** moderators only. The reported person is never told and never shown who reported them.
- **Retention:** kept indefinitely. [TO CONFIRM retention period]

### Bans (`user_bans` table)

- **What:** account id, a **sha256 hash of the lower-case email**, type, end date, reason, which moderator and when, plus when and by whom it was lifted.
- **Who sees them:** moderators. The banned user sees the type and end date on the ban screen.
- **Retention:** kept indefinitely. Bans have **no database link to the account**, so they would survive the account being deleted; the email hash means re-registering with the same address stays banned. [TO CONFIRM retention period]

### Moderator audit log (`mod_actions` table)

- **What:** moderator, action, target, details (for example a reason) and time. This includes **every time a moderator views someone's email**.
- **Who sees it:** moderators.
- **Retention:** append-only, with no way to edit or delete it in the app. Kept indefinitely. [TO CONFIRM retention period]

### Terms acceptance (`terms_acceptances` table, added on this branch)

- **What:** user, version accepted and time. A new row is added for each acceptance.
- **Who sees it:** nobody in the app UI. The server checks it.
- **Retention:** kept indefinitely. [TO CONFIRM]

### Moderator list (`MODERATOR_EMAILS` setting)

Moderators' email addresses live in server configuration, not the database.

### Session, IP addresses and logs

- **Session cookie:** Flask-Login, using Flask's signed `session` cookie. It holds:
  - the user id;
  - a "fresh" flag;
  - `_id`, a **hash of the browser's IP address and user agent** (Flask-Login's default "basic" session protection).

  No "remember me" cookie is set. The cookie lasts until the browser is closed. It's signed with `SECRET_KEY`, which is currently a **hard-coded placeholder in `app.py`** (security gap, see e).
- **Failed sign-in counters:** kept **in server memory only**, keyed by IP address and by the typed email or username, for 15 minutes. They're lost when the server restarts.
- **Request logs:** the development server (Werkzeug) prints each request, with the client's IP address, to the console. Nothing writes these to a file in the code. In production, logs depend on the host. [TO CONFIRM]
- **Error logs:** two handlers log exceptions, with no personal data added (`interests.py`, `settings.py`).

## c) Third parties and services

- **Email:** none. The code sends no email of any kind: no verification codes and no notifications. There is no email library.
- **AI and embedding services:** none.
  - Interest names, tags and user text are **not sent to any external service**.
  - Search uses SQL `LIKE` text matching in `discovery.py`; there is no pgvector.
- **Content delivery network:** pages load Bootstrap CSS and JavaScript from **cdn.jsdelivr.net**, so the visitor's browser connects to jsDelivr, which sees their IP address and browser details. No user data is sent.
- **External links:** contact links (Instagram, X, WhatsApp, LinkedIn, GitHub, Snapchat, Telegram, websites) open those sites only when a person clicks them.
- **Hosting and database host:** not in the code. [TO CONFIRM]
- **International transfers:** none found in the code. Depends on hosting and jsDelivr. [TO CONFIRM]

## d) Browser storage and cookies

| Name | Kind | Set by | What for | Needed? |
|---|---|---|---|---|
| `session` | Cookie, signed, until the browser closes | Flask / Flask-Login | Keeps you signed in | Essential |
| `superposition-theme` | localStorage | `static/theme.js`, `templates/base.html` | Remembers light or dark mode | Functional; only set if you switch the theme |
| `signin-attempt` | sessionStorage, a timestamp only | `templates/login.html` | Shows "We couldn't sign you in" after a failed attempt | Functional; removed the next time the page loads |

No analytics, advertising or tracking cookies were found.

## e) Security measures actually implemented

- **Passwords** are stored only as scrypt hashes.
- **Sign-in gate (`moderation.py`):** every page and API needs a signed-in, not-banned user, except sign-in, registration, log-out and the legal pages.
- **Failed sign-ins:** 10 per IP address or per email or username in 15 minutes gives a 429. The counters are in memory only.
- **Registration** accepts only `@durham.ac.uk` addresses.
- **Server-side permission checks:**
  - contacts only to connections;
  - year and bio withheld when hidden;
  - blocks hide profiles both ways;
  - only moderators reach `/mod` and `/api/mod` (others get 404);
  - you can only edit your own profile.
- **Bans** end the session on the next request.
- **Moderators' email views are logged.**
- **The new endpoints require JSON bodies,** which stops plain cross-site form posts.

**Not implemented (don't claim these):**
- one-time sign-in codes, and email verification;
- HTTPS settings in the app [TO CONFIRM at the host];
- secure or HttpOnly cookie settings beyond Flask's defaults. Flask's session cookie is HttpOnly by default; `SESSION_COOKIE_SECURE` isn't set;
- CSRF tokens;
- a secret `SECRET_KEY` (it's hard-coded);
- encryption of the database file;
- account deletion;
- staff exclusion.
