from sqlalchemy import func, select
from interest_names import to_interest_title_case
from models import Interest, User, UserInterest, db


def _parse_interest_names(raw: str) -> list[str]:
    """Splits comma-separated interest names and normalises whitespace."""
    if not raw:
        return []
    names = []
    for item in raw.split(","):
        cleaned = " ".join(item.split())[:120]
        if cleaned:
            names.append(cleaned)
    return names


def update_user_account(
    user: User,
    new_username: str = "",
    new_bio: str = "",
    new_interests: str = "",
    remove_interests: str = "",
) -> None:
    """Updates a user's username, bio, and UserInterest links in SQLite."""
    # 1. The username is the CIS code people sign in with, so it can't be changed
    #    here (new_username is ignored). Display names are edited on the profile.

    # 2. Update bio only if the user typed something (leaves current bio intact if blank)
    clean_bio = (new_bio or "").strip()
    if clean_bio:
        user.bio = clean_bio

    # 3. Add new interests (supports single or comma-separated names)
    current_interest_ids = {ui.interest_id for ui in user.user_interests}
    for name in _parse_interest_names(new_interests):
        interest = db.session.scalar(
            select(Interest).where(func.lower(Interest.interest_name) == name.lower())
            .execution_options(include_removed=True)
        )
        if interest is not None and interest.removed_at is not None:
            continue  # removed by a moderator: can't be added or re-created
        if interest is None:
            interest = Interest(
                interest_name=to_interest_title_case(name),  # same rules as the create form
                created_by_user_id=user.user_id,
            )
            db.session.add(interest)
            db.session.flush()  # Populates interest.interest_id before linking

        if interest.interest_id not in current_interest_ids:
            db.session.add(
                UserInterest(
                    user_id=user.user_id,
                    interest_id=interest.interest_id,
                )
            )
            current_interest_ids.add(interest.interest_id)

    # 4. Remove interests (case-insensitive match against user's current interests)
    to_remove = {name.lower() for name in _parse_interest_names(remove_interests)}
    if to_remove:
        for ui in list(user.user_interests):
            if ui.interest.interest_name.lower() in to_remove:
                db.session.delete(ui)

    db.session.commit()