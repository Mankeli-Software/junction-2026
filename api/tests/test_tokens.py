from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.models import AccessToken, Company, User
from app.services.tokens import (
    CALLER_TOKEN_TTL,
    hash_token,
    issue_caller_token,
    new_token,
    resolve_access_token,
)


def test_new_tokens_are_long_and_random():
    tokens = {new_token() for _ in range(100)}
    assert len(tokens) == 100
    assert all(len(token) >= 43 for token in tokens)  # 32 bytes in base64url


def test_hash_token_is_sha256_hex():
    assert hash_token("abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


async def _user(db) -> User:
    company = Company(name="Testi Tikka Oy", phone_e164="+358401110001")
    db.add(company)
    await db.flush()
    user = User(company_id=company.id, phone_e164=company.phone_e164, lang="fi")
    db.add(user)
    await db.flush()
    return user


async def test_caller_token_resolves_to_its_user_and_company(db):
    user = await _user(db)

    raw = await issue_caller_token(db, user.id, "phone", "S.I.MO phone")
    caller = await resolve_access_token(db, raw)

    assert caller is not None
    assert caller.user_id == user.id
    assert caller.company_id == user.company_id
    assert caller.channel == "phone"
    assert caller.client_name == "S.I.MO phone"


async def test_only_the_hash_is_stored(db):
    user = await _user(db)

    raw = await issue_caller_token(db, user.id, "web_chat", "S.I.MO chat")

    stored = (await db.scalars(select(AccessToken.token_hash))).all()
    assert stored == [hash_token(raw)]


async def test_caller_token_expires_after_15_minutes(db):
    user = await _user(db)
    now = datetime.now(UTC)
    raw = await issue_caller_token(db, user.id, "phone", "S.I.MO phone", now=now)

    almost = now + CALLER_TOKEN_TTL - timedelta(seconds=1)
    assert await resolve_access_token(db, raw, now=almost) is not None
    assert await resolve_access_token(db, raw, now=now + CALLER_TOKEN_TTL) is None


async def test_unknown_token_resolves_to_none(db):
    assert await resolve_access_token(db, new_token()) is None


async def test_a_token_of_an_unclaimed_account_resolves_to_none(db):
    # A hand-out account has no number and so no company until its first login (#48).
    user = User(email="unclaimed.token@example.com", password_hash="x", lang="en")
    db.add(user)
    await db.flush()

    raw = await issue_caller_token(db, user.id, "phone", "S.I.MO phone")

    assert await resolve_access_token(db, raw) is None
