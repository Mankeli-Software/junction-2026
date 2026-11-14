import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import Company, KitchenProfile, WebSession
from app.schemas.common import Exclusion
from app.services.accounts import (
    LAST_SEEN_INTERVAL,
    SESSION_TTL,
    create_demo_account,
    me,
    resolve_session,
    revoke_session,
)
from app.services.phone import InvalidPhoneNumber
from app.services.tokens import hash_token

NUMBER = "+358401234512"
OTHER_NUMBER = "+358409876543"


async def test_same_number_in_two_browsers_shares_the_company_not_the_user(db):
    first = await create_demo_account(db, NUMBER, [], "fi")
    second = await create_demo_account(db, NUMBER, [], "en")  # another cookie jar

    assert first.company_id == second.company_id
    assert first.company_name == second.company_name
    assert first.user_id != second.user_id
    assert first.new_company and not second.new_company
    assert first.new_user and second.new_user


async def test_same_browser_same_number_keeps_the_user(db):
    first = await create_demo_account(db, NUMBER, [], "fi")
    again = await create_demo_account(db, "040 123 4512", [], "en", first.session_token)

    assert again.user_id == first.user_id
    assert not again.new_user
    assert again.session_token != first.session_token
    # The old cookie no longer works.
    assert await resolve_session(db, first.session_token) is None
    assert (await me(db, again.user_id)).lang == "en"


async def test_same_browser_other_number_gets_a_new_user_and_company(db):
    first = await create_demo_account(db, NUMBER, [], "fi")
    other = await create_demo_account(db, OTHER_NUMBER, [], "fi", first.session_token)

    assert other.user_id != first.user_id
    assert other.company_id != first.company_id
    assert other.new_user and other.new_company


async def test_unknown_session_token_creates_a_new_user(db):
    first = await create_demo_account(db, NUMBER, [], "fi")
    other = await create_demo_account(db, NUMBER, [], "fi", "not-a-real-token")

    assert other.user_id != first.user_id


async def test_new_exclusions_overwrite_the_kitchen_profile(db):
    first = await create_demo_account(db, NUMBER, ["vegan", "milk_free"], "fi")
    second = await create_demo_account(db, NUMBER, [Exclusion.gluten_free], "fi")

    assert first.exclusions == [Exclusion.milk_free, Exclusion.vegan]
    assert second.exclusions == [Exclusion.gluten_free]
    profile = await db.get(KitchenProfile, first.company_id)
    await db.refresh(profile)
    assert profile.exclusions == ["gluten_free"]
    assert (await me(db, first.user_id)).exclusions == [Exclusion.gluten_free]


async def test_invalid_number_is_rejected(db):
    with pytest.raises(InvalidPhoneNumber):
        await create_demo_account(db, "12", [], "fi")


async def test_unknown_exclusion_is_rejected(db):
    with pytest.raises(ValueError):
        await create_demo_account(db, NUMBER, ["no_carrots"], "fi")


async def test_account_shows_only_the_masked_number(db):
    account = await create_demo_account(db, NUMBER, [], "fi")

    assert account.phone_masked == "+358 40 *** **12"
    assert account.company_name.endswith(" Oy")
    assert account.usual_items == []
    assert (await me(db, account.user_id)).phone_masked == "+358 40 *** **12"


async def test_taken_name_is_retried(db):
    db.add(Company(name="Hassu Hauki Oy", phone_e164="+358401110002"))
    await db.flush()

    names = iter(["Hassu Hauki Oy", "Hassu Hauki Oy", "Pirteä Peura Oy"])
    account = await create_demo_account(db, NUMBER, [], "fi", names=names)

    assert account.company_name == "Pirteä Peura Oy"


async def test_session_resolves_and_is_stored_hashed(db):
    account = await create_demo_account(db, NUMBER, [], "fi")

    resolved = await resolve_session(db, account.session_token)
    assert resolved is not None
    assert resolved.user_id == account.user_id
    assert resolved.company_id == account.company_id

    hashes = (await db.scalars(select(WebSession.token_hash))).all()
    assert hashes == [hash_token(account.session_token)]


async def test_session_expires_after_14_days(db):
    now = datetime.now(UTC)
    account = await create_demo_account(db, NUMBER, [], "fi", now=now)

    assert account.session_expires_at == now + SESSION_TTL
    assert await resolve_session(db, account.session_token, now=now + SESSION_TTL) is None


async def test_revoked_session_no_longer_resolves(db):
    account = await create_demo_account(db, NUMBER, [], "fi")

    assert await revoke_session(db, account.session_token)
    assert await resolve_session(db, account.session_token) is None
    assert not await revoke_session(db, account.session_token)


async def test_last_seen_updates_at_most_once_a_minute(db):
    now = datetime.now(UTC)
    account = await create_demo_account(db, NUMBER, [], "fi", now=now)
    session = await db.scalar(select(WebSession))

    await resolve_session(db, account.session_token, now=now + timedelta(seconds=30))
    assert session.last_seen_at == now

    later = now + LAST_SEEN_INTERVAL
    await resolve_session(db, account.session_token, now=later)
    assert session.last_seen_at == later


async def test_me_for_unknown_user_is_none(db):
    assert await me(db, uuid.uuid4()) is None
