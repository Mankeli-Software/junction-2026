"""Phone calls for the voice relay (#52, technical-plan.md §7.1): the call's session, its
caller token, its audit events and the end of the call.

The relay in `app.interfaces.voice` owns the audio and Gemini; this module owns what goes
into the database. Like the other services, the functions take an `AsyncSession` and only
flush: the relay commits. The caller token must be committed before the relay uses it on
`/mcp` (#44).
"""

import logging
import re
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import OrderSession, Product, Quote
from app.schemas import CustomerContext, Lang, Localized
from app.services import accounts, audit, confirmations, customers, sessions, sms, tokens
from app.services.caller import Caller
from app.services.dashboard.redact import redact_text
from app.services.policy import get_rule_set

log = logging.getLogger(__name__)

CLIENT_NAME = "S.I.MO phone"

EndedBy = str  # visitor, agent, time_limit or dropped (technical-plan.md §9.3)


@dataclass(frozen=True)
class CallStart:
    caller: Caller
    session_id: uuid.UUID
    call_id: str
    token: str
    context: CustomerContext


@dataclass(frozen=True)
class CallEnd:
    released_quote_ids: list[str]
    quote_id: str | None
    total_cents: int | None


def business_date() -> date:
    """Today on the business clock that quotes use for `needed_by` (policy.yaml)."""
    policy = get_rule_set().policy
    return policy.business_time.astimezone(ZoneInfo(policy.timezone)).date()


async def start_call(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    prompt_version: str,
    now: datetime | None = None,
) -> CallStart | None:
    """The call's caller token and session, and `customer_identified`. None when the user
    has no account with a number. Commit before using the token."""
    now = now or datetime.now(UTC)
    account = await accounts.me(db, user_id)
    if account is None:
        return None
    caller = Caller(
        user_id=account.user_id,
        company_id=account.company_id,
        company_name=account.company_name,
        phone_masked=account.phone_masked,
        exclusions=account.exclusions,
        lang=account.lang,
        channel="phone",
        client_name=CLIENT_NAME,
    )
    token = await tokens.issue_caller_token(db, user_id, channel="phone", client_name=CLIENT_NAME)
    call_id = uuid.uuid4().hex
    session = await sessions.start_call_session(
        db, caller, call_id=call_id, prompt_version=prompt_version, now=now
    )
    await audit.record(
        db,
        type="customer_identified",
        actor="service",
        session_id=session.id,
        payload={
            "company_name": caller.company_name,
            "phone_masked": caller.phone_masked,
            "exclusions": [e.value for e in caller.exclusions],
            "lang": caller.lang,
        },
        text=Localized(
            fi=f"Soittaja tunnistettiin: {caller.company_name}",
            en=f"Caller identified: {caller.company_name}",
        ),
    )
    return CallStart(
        caller=caller,
        session_id=session.id,
        call_id=call_id,
        token=token,
        context=await customers.get_customer_context(db, caller),
    )


async def record_said(
    db: AsyncSession,
    session_id: uuid.UUID,
    who: str,
    text: str,
    *,
    lang: Lang | None = None,
    filler: bool = False,
) -> None:
    """`buyer_said` or `agent_said`: a voice transcript, public on the dashboard and never
    engine input (technical-plan.md §9.3). Phone numbers and emails in it are masked."""
    buyer = who == "buyer"
    # A caller may read out a phone number or an email; the log keeps only masked ones.
    text = redact_text(text)
    payload: dict[str, object] = {"text": text, "lang": lang, "transcript": True}
    if filler:
        payload["filler"] = True
    await audit.record(
        db,
        type="buyer_said" if buyer else "agent_said",
        actor="buyer" if buyer else "agent",
        session_id=session_id,
        payload=payload,
        text=Localized(fi=text, en=text),
    )


async def record_local_tool(
    db: AsyncSession,
    session_id: uuid.UUID,
    name: str,
    arguments: dict[str, object],
    response: dict[str, object],
) -> None:
    """`tool_called` and `tool_returned` for a call the relay answers itself (`end_call`, or
    a refused `request_confirmation`), which never reaches MCP and its own audit events."""
    await audit.record(
        db,
        type="tool_called",
        actor="agent",
        session_id=session_id,
        payload={"tool": name, "arguments": arguments, "answered_by": "relay"},
        text=Localized(fi=f"Agentti kutsui: {name}", en=f"The agent called {name}"),
    )
    if "error" in response:
        text = Localized(
            fi=f"{name}: puhelu ei sallinut: {response['error']}",
            en=f"{name} refused by the call: {response['error']}",
        )
        payload = {"tool": name, "error": response["error"], "answered_by": "relay"}
    else:
        text = Localized(fi=f"{name} vastasi", en=f"{name} returned")
        payload = {"tool": name, "response": response, "answered_by": "relay"}
    await audit.record(
        db, type="tool_returned", actor="service", session_id=session_id, payload=payload, text=text
    )


async def end_call(
    db: AsyncSession,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
    *,
    ended_by: EndedBy,
    duration_s: int,
    now: datetime | None = None,
) -> CallEnd:
    """Release the call's held confirmation link (#46), end the session and write
    `inbox_delivered` and `session_ended`. A held SMS goes out once this commits; then
    `sms_delivery()` tells how it went. Safe to call twice: the second call releases
    nothing and leaves the session as it is."""
    now = now or datetime.now(UTC)
    # The session first (#88): a request_confirmation still running holds this lock until
    # it commits, so the release below sees its held message. One that starts later finds
    # the call ended and delivers at once (`confirmations.call_in_progress`).
    session = await db.get(OrderSession, session_id, with_for_update=True)
    released = await confirmations.release_held_messages(db, user_id, now=now)
    for quote_id in released:
        await confirmations.record_inbox_delivered(db, session_id, quote_id)
    quote_id: str | None = None
    total_cents: int | None = None
    if released:
        quote = await db.get(Quote, uuid.UUID(str(released[-1])))
        if quote is not None:
            quote_id, total_cents = str(quote.id), quote.total_cents

    if session is not None and session.ended_at is None:
        session.ended_at = now
        session.ended_by = ended_by
        sessions.touch(session, now)
        await db.flush()
        await audit.record(
            db,
            type="session_ended",
            actor="service",
            session_id=session_id,
            quote_id=quote_id,
            payload={
                "ended_by": ended_by,
                "duration_s": duration_s,
                "call_id": session.call_id,
                "released_quote_ids": [str(q) for q in released],
            },
            text=Localized(
                fi=f"Puhelu päättyi ({_ENDED_BY_FI.get(ended_by, ended_by)}), "
                f"kesto {_duration(duration_s)}",
                en=f"Call ended ({_ENDED_BY_EN.get(ended_by, ended_by)}), "
                f"{_duration(duration_s)} long",
            ),
        )
    return CallEnd(
        released_quote_ids=[str(q) for q in released], quote_id=quote_id, total_cents=total_cents
    )


async def sms_delivery(end: CallEnd) -> str:
    """After `end_call()` has committed: how the released link went by SMS, for the relay's
    `ended` message. `sent` (or queued), `failed` when Twilio refused it, `off` when no
    SMS goes out for it (Twilio off, a number not on the allowlist, or over the limit)."""
    if end.quote_id is None:
        return "off"
    return await sms.delivery_status_for_quote(end.quote_id)


_ENDED_BY_FI = {
    "visitor": "soittaja lopetti",
    "agent": "S.I.MO lopetti",
    "time_limit": "aikaraja",
    "dropped": "yhteys katkesi",
}
_ENDED_BY_EN = {
    "visitor": "the caller hung up",
    "agent": "S.I.MO hung up",
    "time_limit": "time limit",
    "dropped": "the connection dropped",
}


def _duration(seconds: int) -> str:
    return f"{seconds // 60}:{seconds % 60:02d}"


# --- Custom vocabulary (#51: always send it) --------------------------------------------

# Always in the list: our own names and words the spike found the recogniser mishears.
# Not "S.I.MO": callers rarely say it, and the recogniser wrote it in place of speech it
# was unsure of, such as the first Finnish words after an English opening (#85). What
# the recogniser hears is also what the model acts on (#51), so the call lost its thread.
BASE_VOCABULARY = (
    "Valio",
    "Valio Aimo",
    "laktoositon",
    "vispikerma",
    "ruokakerma",
    "kermaviili",
    "kevytmaito",
    "rasvaton maito",
    "kaurajuoma",
)
MAX_VOCABULARY = 100
MAX_BRANDS = 30
_WORD = re.compile(r"[a-zåäö]+")
_MIN_COMPOUND = 9  # letters; shorter words are rarely the compounds the recogniser misses

_vocabulary: list[str] | None = None


async def custom_vocabulary(db: AsyncSession) -> list[str]:
    """Up to about 100 terms for the input transcription: the base list, the catalogue's
    most common brands and its most common long Finnish words (mostly compounds such as
    "kevytmaitojuoma"). Read from the catalogue tables once per process, never from the
    live API."""
    global _vocabulary
    if _vocabulary is not None:
        return _vocabulary
    terms = list(BASE_VOCABULARY)
    rows = (await db.execute(select(Product.brand, Product.name_fi))).all()
    brands = Counter(_brand(b) for b, _ in rows if b)
    words: Counter[str] = Counter()
    for _, name in rows:
        for word in set(_WORD.findall((name or "").lower())):
            if len(word) >= _MIN_COMPOUND:
                words[word] += 1
    seen = {t.lower() for t in terms}

    def add(term: str) -> None:
        if term and term.lower() not in seen and len(terms) < MAX_VOCABULARY:
            seen.add(term.lower())
            terms.append(term)

    for brand, _ in brands.most_common(MAX_BRANDS):
        add(brand)
    for word, count in words.most_common():
        if count < 2:
            break
        add(word)
    if rows:  # an empty catalogue (tests, a fresh laptop) is read again next time
        _vocabulary = terms
    return terms


def _brand(raw: str) -> str:
    """`VALIO` -> `Valio`; mixed case is kept (`Oddlygood`)."""
    raw = raw.strip()
    return raw.title() if raw.isupper() else raw
