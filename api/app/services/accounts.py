"""Demo accounts and web sessions (#44, `technical-plan.md` §9.2).

Typing a phone number is the login. The same number always gets the same company and
kitchen profile; each browser that types it is its own user, so its inbox and transcripts
stay its own. Nothing about the number is verified.

Connector accounts (#48) log in with an email and a password instead; they too get the
number's company. A hand-out account starts without a number and sets it on first login.

The functions take the request's `AsyncSession` and only flush: the caller commits.
"""

import re
import uuid
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Company, KitchenProfile, User, WebSession
from app.schemas.common import Exclusion, KitchenType, Lang
from app.schemas.engine import UsualItem
from app.seed import history
from app.services.policy import get_rule_set

from .company_names import company_name_candidates
from .passwords import MIN_PASSWORD_LENGTH, failed_logins, hash_password, verify_password
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
    kitchen_type: KitchenType | None = None


@dataclass(frozen=True)
class SessionUser:
    """Who a valid web session belongs to.

    `company_id` and `phone_e164` are None only for a hand-out account that hasn't set its
    number yet (#48); such a session can do nothing but `set_phone()`.
    """

    session_id: uuid.UUID
    user_id: uuid.UUID
    company_id: uuid.UUID | None
    phone_e164: str | None


@dataclass(frozen=True)
class Account:
    """What `GET /api/v1/me` shows."""

    user_id: uuid.UUID
    company_id: uuid.UUID
    company_name: str
    phone_masked: str
    exclusions: list[Exclusion]
    lang: Lang
    kitchen_type: KitchenType | None = None


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
    previous = await db.scalar(
        select(KitchenProfile.exclusions).where(KitchenProfile.company_id == company.id)
    )
    await _write_kitchen_profile(db, company.id, chosen)
    # The kitchen type and order history (#32): made on first use, and made again when the
    # exclusions change, so a blocked item is swapped for its alternative.
    kind = await history.ensure_history(
        db,
        company,
        chosen,
        get_rule_set().policy.business_time,
        regenerate=previous is not None and set(previous) != {e.value for e in chosen},
    )

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
        usual_items=await history.usual_items(db, company.id),
        new_company=new_company,
        new_user=new_user,
        kitchen_type=kind,
    )


async def usual_items(db: AsyncSession, company_id: uuid.UUID) -> list[UsualItem]:
    """The company's usual items from its order history (#32)."""
    return await history.usual_items(db, company_id)


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
    """The logged-in user's company, kitchen profile, masked number and language.

    None for an unknown user and for a hand-out account without a number yet.
    """
    row = (
        await db.execute(
            select(User, Company.name, KitchenProfile.exclusions, Company.kitchen_type)
            .join(Company, Company.id == User.company_id)
            .outerjoin(KitchenProfile, KitchenProfile.company_id == Company.id)
            .where(User.id == user_id)
        )
    ).one_or_none()
    if row is None:
        return None
    user, company_name, exclusions, kitchen_type = row
    assert user.company_id is not None and user.phone_e164 is not None  # the inner join
    return Account(
        user_id=user.id,
        company_id=user.company_id,
        company_name=company_name,
        phone_masked=mask_phone(user.phone_e164),
        exclusions=_clean_exclusions(exclusions or []),
        lang=user.lang,
        kitchen_type=KitchenType(kitchen_type) if kitchen_type else None,
    )


# --- Connector accounts: email and password (#48) ---

# A deliberately loose check: something@something.tld, no spaces. Nothing is verified.
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MAX_EMAIL_LENGTH = 254


class InvalidEmail(ValueError):
    """Not an email address."""


class WeakPassword(ValueError):
    """Shorter than MIN_PASSWORD_LENGTH."""


class EmailTaken(Exception):
    """An account with this email exists already."""


class LoginFailed(Exception):
    """Wrong email or password: one error for both, so the reply never tells which."""


class TooManyLogins(Exception):
    """Too many failed tries for this email lately."""


class PhoneAlreadySet(Exception):
    """The account has a number already; it can be set only once."""


@dataclass(frozen=True)
class LoginResult:
    session_token: str
    session_expires_at: datetime
    user_id: uuid.UUID
    phone_required: bool


def normalize_email(raw: str) -> str:
    email = raw.strip().lower()
    if len(email) > MAX_EMAIL_LENGTH or not _EMAIL.match(email):
        raise InvalidEmail("not an email address")
    return email


def _check_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise WeakPassword(f"at least {MIN_PASSWORD_LENGTH} characters")


async def _user_by_email(db: AsyncSession, email: str) -> User | None:
    return await db.scalar(select(User).where(User.email == email))


async def _replace_session(
    db: AsyncSession, user_id: uuid.UUID, current_session_token: str | None, now: datetime
) -> tuple[str, WebSession]:
    if current_session_token:
        await revoke_session(db, current_session_token, now=now)
    return await _create_session(db, user_id, now)


async def signup(
    db: AsyncSession,
    email: str,
    password: str,
    phone: str,
    current_session_token: str | None = None,
    *,
    now: datetime | None = None,
    names: Iterator[str] | None = None,
) -> LoginResult:
    """Open sign-up: a new user of the number's company, logged in.

    Raises InvalidEmail, WeakPassword, InvalidPhoneNumber or EmailTaken. The company is
    found or created like a demo account's; its kitchen profile is left as it is.
    """
    now = now or datetime.now(UTC)
    email = normalize_email(email)
    _check_password(password)
    phone_e164 = normalize_phone(phone)
    if await _user_by_email(db, email) is not None:
        raise EmailTaken(email)

    company, _ = await _find_or_create_company(db, phone_e164, names)
    user = User(
        company_id=company.id,
        phone_e164=phone_e164,
        email=email,
        password_hash=hash_password(password),
        lang="en",
    )
    try:
        async with db.begin_nested():
            db.add(user)
            await db.flush()
    except IntegrityError as error:  # the same email signed up concurrently
        raise EmailTaken(email) from error
    raw, session = await _replace_session(db, user.id, current_session_token, now)
    return LoginResult(raw, session.expires_at, user.id, phone_required=False)


async def login(
    db: AsyncSession,
    email: str,
    password: str,
    current_session_token: str | None = None,
    *,
    now: datetime | None = None,
) -> LoginResult:
    """Email and password log the browser in, replacing its previous session.

    Raises LoginFailed for a wrong email or password alike (an unknown email costs the
    same password check), and TooManyLogins after 10 failed tries for the email within
    10 minutes. A successful login clears the count.
    """
    now = now or datetime.now(UTC)
    try:
        email = normalize_email(email)
    except InvalidEmail:
        verify_password(None, password)
        raise LoginFailed() from None
    if failed_logins.blocked(email):
        raise TooManyLogins()
    user = await _user_by_email(db, email)
    matches = verify_password(user.password_hash if user else None, password)
    if user is None or not matches:
        failed_logins.record_failure(email)
        raise LoginFailed()
    failed_logins.clear(email)
    raw, session = await _replace_session(db, user.id, current_session_token, now)
    return LoginResult(raw, session.expires_at, user.id, phone_required=user.phone_e164 is None)


async def create_unclaimed_account(db: AsyncSession, email: str, password: str) -> User:
    """A hand-out account: email and password, no number and so no company yet.

    Raises InvalidEmail, WeakPassword or EmailTaken.
    """
    email = normalize_email(email)
    _check_password(password)
    if await _user_by_email(db, email) is not None:
        raise EmailTaken(email)
    user = User(email=email, password_hash=hash_password(password), lang="en")
    db.add(user)
    await db.flush()
    return user


async def set_phone(
    db: AsyncSession, user_id: uuid.UUID, phone: str, *, names: Iterator[str] | None = None
) -> Account:
    """First login of a hand-out account: set its number, once, and so its company.

    Raises InvalidPhoneNumber, or PhoneAlreadySet when the number is set already.
    """
    phone_e164 = normalize_phone(phone)
    user = await db.get(User, user_id, with_for_update=True)
    if user is None or user.phone_e164 is not None:
        raise PhoneAlreadySet()
    company, _ = await _find_or_create_company(db, phone_e164, names)
    user.phone_e164 = phone_e164
    user.company_id = company.id
    await db.flush()
    account = await me(db, user_id)
    assert account is not None
    return account


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
