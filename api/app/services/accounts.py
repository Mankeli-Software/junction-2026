"""Demo accounts and web sessions (#44, `technical-plan.md` §9.2).

Typing a phone number is the login. The same number always gets the same company and
kitchen profile; each browser that types it is its own user, so its inbox and transcripts
stay its own. Nothing about the number is verified.

The functions take the request's `AsyncSession` and only flush: the caller commits.
"""

import uuid
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Company, KitchenProfile, User, WebSession
from app.schemas.common import Exclusion, Lang
from app.schemas.engine import UsualItem

from .company_names import company_name_candidates
from .phone import mask_phone, normalize_phone
from .tokens import hash_token, new_token

SESSION_TTL = timedelta(days=14)
# last_seen_at is written at most this often, so most requests stay read-only.
LAST_SEEN_INTERVAL = timedelta(minutes=1)
# A guard against a bug looping forever; numbered names make a clash very unlikely.
MAX_NAME_TRIES = 50


@dataclass(frozen=True)
class DemoAccount:
    """The result of entering a number. `session_token` is the raw `simo_session` cookie."""

    session_token: str
    session_expires_at: datetime
    user_id: uuid.UUID
    company_id: uuid.UUID
    company_name: str
    phone_masked: str
    exclusions: list[Exclusion]
    usual_items: list[UsualItem]
    new_company: bool
    new_user: bool


@dataclass(frozen=True)
class SessionUser:
    """Who a valid web session belongs to."""

    session_id: uuid.UUID
    user_id: uuid.UUID
    company_id: uuid.UUID
    phone_e164: str


@dataclass(frozen=True)
class Account:
    """What `GET /api/v1/me` shows."""

    user_id: uuid.UUID
    company_id: uuid.UUID
    company_name: str
    phone_masked: str
    exclusions: list[Exclusion]
    lang: Lang


def _clean_exclusions(exclusions: Iterable[Exclusion | str]) -> list[Exclusion]:
    """Unique, in the order of the Exclusion enum. An unknown key raises ValueError."""
    chosen = {Exclusion(e) for e in exclusions}
    return [e for e in Exclusion if e in chosen]


async def create_demo_account(
    db: AsyncSession,
    phone: str,
    exclusions: Iterable[Exclusion | str],
    lang: Lang,
    current_session_token: str | None = None,
    *,
    now: datetime | None = None,
    names: Iterator[str] | None = None,
) -> DemoAccount:
    """Log this browser in as a user of the number's company (the demo-account flow).

    1. Normalise the number (raises InvalidPhoneNumber).
    2. Find or create the company for it, and write `exclusions` to its kitchen profile.
    3. Reuse this browser's user if its current session is for the same number; otherwise
       create a new user.
    4. Create a web session, replacing the browser's previous one.
    """
    now = now or datetime.now(UTC)
    phone_e164 = normalize_phone(phone)
    chosen = _clean_exclusions(exclusions)

    company, new_company = await _find_or_create_company(db, phone_e164, names)
    await _write_kitchen_profile(db, company.id, chosen)

    user: User | None = None
    if current_session_token:
        previous = await resolve_session(db, current_session_token, now=now)
        if previous is not None:
            if previous.phone_e164 == phone_e164:
                user = await db.get(User, previous.user_id)
            await revoke_session(db, current_session_token, now=now)

    new_user = user is None
    if user is None:
        user = User(company_id=company.id, phone_e164=phone_e164, lang=lang)
        db.add(user)
    else:
        user.lang = lang
    await db.flush()

    raw, session = await _create_session(db, user.id, now)
    return DemoAccount(
        session_token=raw,
        session_expires_at=session.expires_at,
        user_id=user.id,
        company_id=company.id,
        company_name=company.name,
        phone_masked=mask_phone(phone_e164),
        exclusions=chosen,
        usual_items=await usual_items(db, company.id),
        new_company=new_company,
        new_user=new_user,
    )


async def usual_items(db: AsyncSession, company_id: uuid.UUID) -> list[UsualItem]:
    """The company's usual items from its order history.

    Empty until `order_history_lines` exists (#32, #61), which fills this in.
    """
    return []


async def resolve_session(
    db: AsyncSession, raw_token: str, *, now: datetime | None = None
) -> SessionUser | None:
    """The user of a live session cookie, or None if unknown, expired or revoked.

    Bumps `last_seen_at` when it is more than LAST_SEEN_INTERVAL old.
    """
    now = now or datetime.now(UTC)
    row = (
        await db.execute(
            select(WebSession, User.company_id, User.phone_e164)
            .join(User, User.id == WebSession.user_id)
            .where(
                WebSession.token_hash == hash_token(raw_token),
                WebSession.revoked_at.is_(None),
                WebSession.expires_at > now,
            )
        )
    ).one_or_none()
    if row is None:
        return None
    session, company_id, phone_e164 = row
    if now - session.last_seen_at >= LAST_SEEN_INTERVAL:
        session.last_seen_at = now
        await db.flush()
    return SessionUser(
        session_id=session.id,
        user_id=session.user_id,
        company_id=company_id,
        phone_e164=phone_e164,
    )


async def revoke_session(db: AsyncSession, raw_token: str, *, now: datetime | None = None) -> bool:
    """Log out. Returns whether a live session was revoked."""
    now = now or datetime.now(UTC)
    result = await db.execute(
        update(WebSession)
        .where(WebSession.token_hash == hash_token(raw_token), WebSession.revoked_at.is_(None))
        .values(revoked_at=now)
        .execution_options(synchronize_session=False)
    )
    return result.rowcount > 0


async def me(db: AsyncSession, user_id: uuid.UUID) -> Account | None:
    """The logged-in user's company, kitchen profile, masked number and language."""
    row = (
        await db.execute(
            select(User, Company.name, KitchenProfile.exclusions)
            .join(Company, Company.id == User.company_id)
            .outerjoin(KitchenProfile, KitchenProfile.company_id == Company.id)
            .where(User.id == user_id)
        )
    ).one_or_none()
    if row is None:
        return None
    user, company_name, exclusions = row
    return Account(
        user_id=user.id,
        company_id=user.company_id,
        company_name=company_name,
        phone_masked=mask_phone(user.phone_e164),
        exclusions=_clean_exclusions(exclusions or []),
        lang=user.lang,
    )


async def _find_or_create_company(
    db: AsyncSession, phone_e164: str, names: Iterator[str] | None
) -> tuple[Company, bool]:
    company = await _company_by_phone(db, phone_e164)
    if company is not None:
        return company, False

    names = names or company_name_candidates()
    for _, name in zip(range(MAX_NAME_TRIES), names, strict=False):
        # DO NOTHING covers both a taken name and the same number created concurrently.
        company_id = await db.scalar(
            insert(Company)
            .values(name=name, phone_e164=phone_e164)
            .on_conflict_do_nothing()
            .returning(Company.id)
        )
        if company_id is not None:
            return await db.get_one(Company, company_id), True
        company = await _company_by_phone(db, phone_e164)
        if company is not None:
            return company, False
    raise RuntimeError(f"no free company name after {MAX_NAME_TRIES} tries")


async def _company_by_phone(db: AsyncSession, phone_e164: str) -> Company | None:
    return await db.scalar(select(Company).where(Company.phone_e164 == phone_e164))


async def _write_kitchen_profile(
    db: AsyncSession, company_id: uuid.UUID, exclusions: list[Exclusion]
) -> None:
    """Last write wins; a change applies from the next call (`call-screen.md` §2.2)."""
    values = [e.value for e in exclusions]
    await db.execute(
        insert(KitchenProfile)
        .values(company_id=company_id, exclusions=values)
        .on_conflict_do_update(
            index_elements=[KitchenProfile.company_id],
            set_={"exclusions": values, "updated_at": func.now()},
        )
    )


async def _create_session(
    db: AsyncSession, user_id: uuid.UUID, now: datetime
) -> tuple[str, WebSession]:
    raw = new_token()
    session = WebSession(
        token_hash=hash_token(raw),
        user_id=user_id,
        created_at=now,
        last_seen_at=now,
        expires_at=now + SESSION_TTL,
    )
    db.add(session)
    await db.flush()
    return raw, session
