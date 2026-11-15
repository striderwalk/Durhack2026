# Legal review checklist

For the person reviewing the Terms and the Information on Data and Security before
launch. **These are points to check, not legal conclusions.** The facts behind the
pages are in `docs/data-inventory.md`; open decisions are in `docs/legal-open-items.md`.

## Before switching off the draft notice

- [ ] All items in `docs/legal-open-items.md` are decided, and the placeholders replaced (search the pages for `[`).
- [ ] Every statement on `/privacy` still matches `docs/data-inventory.md` and the code.
- [ ] `SHOW_DRAFT_NOTICE = False` in `legal.py`. Bump `VERSION` if the text changed after people accepted it.

## UK GDPR privacy information

- [ ] The notice covers what UK GDPR requires, including:
  - who the controller is, and their contact details;
  - the purposes and lawful bases;
  - recipients;
  - international transfers;
  - retention periods;
  - users' rights, including complaining to the ICO;
  - whether giving the data is required.
- [ ] A lawful basis is confirmed for each purpose in Privacy §3. Check whether legitimate-interests assessments are needed, for example for moderation and the ban email hash.
- [ ] Keeping a hashed email after account deletion, to enforce bans: the basis, the period, and how it's explained.
- [ ] Whether the moderator audit log, reports and terms acceptances need set retention periods and deletion.
- [ ] How access, correction, deletion and objection requests are handled, and by whom.

## ICO data protection fee

- [ ] Whether the operator must pay the ICO data protection fee, or is exempt, given who the operator is and what processing happens.

## Online Safety Act (user-to-user service)

- [ ] Whether the service is in scope as a user-to-user service, and which duties apply to a small service.
- [ ] An illegal content risk assessment, and whether a children's access assessment is needed. The service is proposed as 18+, but age isn't checked.
- [ ] Reporting and complaints: users can report people and interests, and appeal through `[CONTACT EMAIL]`. Is that enough?
- [ ] The terms explain how users are protected, and how moderation and bans work.
- [ ] Ofcom's guidance and codes of practice for small or low-risk services, and record-keeping.

## Name, eligibility and age

- [ ] Permission to use "Durham" in the name. The "not affiliated" wording.
- [ ] The minimum age (18+ proposed). How it's checked. What happens for under-18 students.
- [ ] How student status is verified. Staff exclusion: sign-up accepts only student-style `@durham.ac.uk` addresses (no dot before the `@`) and doesn't verify ownership; email-code verification is planned.

## Terms

- [ ] The liability clause (Terms §10): it must not try to exclude liability that can't be excluded in the UK, and should be fair for a consumer service.
- [ ] Governing law and jurisdiction (England and Wales proposed).
- [ ] The user content licence wording (Terms §6).
- [ ] The safety note on meeting people (Terms §7): advice, not a promise.
- [ ] Whether accepting by ticking a box at sign-in, recorded with version and time, is enough, and how changes are notified (re-acceptance on a new version).

## Providers and transfers

- [ ] The hosting provider and database location, and any processor agreement.
- [ ] jsDelivr (Bootstrap CDN) receives visitors' IP addresses: whether to self-host Bootstrap instead, or mention it.
- [ ] Confirm that no AI or embedding provider is used. The code has none; search is local text matching. Re-check if pgvector or embeddings are added later.
- [ ] International transfers and safeguards, if any.

## Who and where

- [ ] Who the operator is (a person, the team, a club or society?), and who is accountable.
- [ ] The moderation appeals route, and response times.
- [ ] Whether Durham University and/or Durham Students' Union should be consulted or informed.
