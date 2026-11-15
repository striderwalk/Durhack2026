# Legal open items

Every placeholder and [TO CONFIRM] marker in the Terms (`templates/legal/terms.html`),
the Information on Data and Security (`templates/legal/privacy.html`), the constants
(`legal.py`) and the data inventory (`docs/data-inventory.md`). A person must decide
each one before launch. Then set `SHOW_DRAFT_NOTICE = False` in `legal.py`, and only
after legal review.

## Who and how to contact

| Item | Where | Decide |
|---|---|---|
| `[OPERATOR NAME]` | `legal.py` → both pages | Who runs the service and is responsible for the data (a person, the team, a society?) |
| `[CONTACT EMAIL]` | `legal.py` → both pages | The address for questions, data requests, misuse and appeals. Also set `MODERATION_CONTACT_EMAIL` for the ban screen |
| `[ICO REGISTRATION, IF APPLICABLE]` | Privacy §1 | Whether the ICO data protection fee applies, and the registration number if so |

## Eligibility and the name

| Item | Where | Decide |
|---|---|---|
| `[MINIMUM AGE TO CONFIRM]` | Terms §2, Privacy §10 | 18+ is proposed. Some students are under 18 |
| Email ownership not verified | Terms §2 `[TO CONFIRM]`, inventory | No code is sent to prove the address. Email-code verification is planned |
| Student-address rule | Terms §2, inventory | Sign-up refuses addresses with a dot before the `@` (staff-style). Confirm this matches Durham's real student and staff formats |
| `[PERMISSION TO USE THE NAME "DURHAM" TO CONFIRM]` | Terms §3 | Permission from the university to use "Durham" in the name |
| Sign-in method | Terms §4 `[TO CONFIRM: update this if sign-in moves to one-time codes…]`, Privacy §4 | The app uses passwords; the brief describes one-time codes |
| Username = CIS code? | Inventory `[TO CONFIRM]` | Users choose their username freely. It isn't derived from the email |

## Rules, liability, law

| Item | Where | Decide |
|---|---|---|
| `[HUMAN LEGAL REVIEW REQUIRED FOR THIS SECTION]`, `[LIABILITY WORDING TO CONFIRM]` | Terms §10 | Liability wording |
| `[GOVERNING LAW TO CONFIRM]` | Terms §13 | England and Wales is proposed |
| `[APPEALS PROCESS TO CONFIRM]` | Terms §8 | Who reviews appeals, and how fast |
| `[ACCOUNT DELETION PROCESS TO CONFIRM]` | Terms §11, Privacy §7 `[REQUEST AND DELETION PROCESS TO CONFIRM]`, inventory | There's no delete button. Decide a process and timescale, or build one (and keep ban records) |

## Data protection

| Item | Where | Decide |
|---|---|---|
| `[TO CONFIRM ALL BASES]` and each "Proposed basis … [TO CONFIRM]" | Privacy §3 (5 purposes) | The lawful basis for each purpose |
| `[RETENTION PERIOD TO CONFIRM]` ×5, `[RETENTION PERIODS TO CONFIRM]` | Privacy §2 and §6; inventory ×3 | How long to keep reports, bans (including the email hash), the audit log, terms acceptances and created interests. Proposals are in `docs/moderation.md` |
| "Until your account is deleted [TO CONFIRM]" | Privacy §2 (email, connections, created interests) | Confirm, once a deletion process exists |
| `[HOSTING PROVIDER AND LOCATION TO CONFIRM]` | Privacy §5 | Host and database location |
| `[TO CONFIRM, depends on the hosting provider and jsDelivr]` | Privacy §5 | International transfers and safeguards |
| `[HTTPS AND HOSTING SECURITY TO CONFIRM]`, `[TO CONFIRM at the host]` | Privacy §9, inventory | HTTPS, secure cookies, and where request logs (with IP addresses) are kept and for how long |
| Emails `[TO CONFIRM: update this if sign-in codes or notifications are added]` | Privacy §4 | No emails are sent today |
| Waves `[TO CONFIRM when built]`, chat `[TO CONFIRM when chat is built]` | Inventory | Update the pages when these exist |
| `[TO CONFIRM: a deletion process.]` | Inventory | As above |

## Security fixes to make before launch (found during the audit, not legal text)

- **`SECRET_KEY` is hard-coded** in `app.py` (`"change-this-hackathon-secret"`). Anyone who knows it can forge a session cookie. Set it from a secret environment variable.
- Set `SESSION_COOKIE_SECURE = True` once the site is served over HTTPS.
- There are no CSRF tokens site-wide.
- **Failed sign-in limits are kept in memory,** so they reset on restart and aren't shared between servers.
- **`requirements.txt` is incomplete,** and saved as UTF-16: it lists only `flask`, while the app also needs `flask-login` and `flask-sqlalchemy`.
