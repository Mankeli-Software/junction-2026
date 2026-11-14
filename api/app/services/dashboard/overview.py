"""The overview behind `GET /orders`, the stream's snapshot and its `order_updated` cards (#49).

Every session started since `EVENT_START` (all of them when it is unset) is one card. The
card's state is `sessions.state`, except that an MCP, WebMCP or chat session still in an
active state with no activity for 10 minutes, or a call that ended while active, shows as
`abandoned`: those channels have no hang-up, and nothing marks them in the database (no
background job). The totals count every session in scope; the filters and the 200-card cap
apply only to the cards.

Identities are masked here and everything goes through `redact()` again on the way out.
"""

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas import (
    STATE_GROUPS,
    CardFlag,
    Channel,
    CompanyGroup,
    CompanyRef,
    Exclusion,
    Localized,
    OrderCard,
    OrderUpdated,
    OverviewResponse,
    SessionState,
    StateGroup,
    Totals,
)
from app.services.phone import mask_phone
from app.services.policy import get_rule_set
from app.services.sessions import IDLE_TIMEOUT
from app.settings import get_settings

from .redact import mask_email

MAX_CARDS = 200

# `sessions.channel` (the caller's channel) to the dashboard's channel tiles.
CHANNEL_OF: dict[str, Channel] = {
    "phone": Channel.phone,
    "web_chat": Channel.web_chat,
    "web": Channel.webmcp,
    "connector": Channel.mcp,
}

ACTIVE_STATES = frozenset(s for s, g in STATE_GROUPS.items() if g == StateGroup.active)

# The next step shown on cards that need attention. `rejected` uses the engine's own.
NEXT_STEP: dict[SessionState, Localized] = {
    SessionState.expired: Localized(
        fi="Seuraavaksi: agentti voi tehdä uuden tarjouksen",
        en="Next: the agent can make a new quote",
    ),
    SessionState.rejected: Localized(
        fi="Seuraavaksi: agentti etsii toisen tuotteen",
        en="Next: the agent looks for another product",
    ),
    SessionState.sms_failed: Localized(
        fi="Seuraavaksi: vahvistus demopuhelimen viesteistä",
        en="Next: confirm from the demo phone's inbox",
    ),
    SessionState.callback_requested: Localized(
        fi="Seuraavaksi: Valio Aimon asiakaspalvelu soittaa",
        en="Next: Valio Aimo customer service calls back",
    ),
    SessionState.requote_needed: Localized(
        fi="Seuraavaksi: agentti tekee uuden tarjouksen nykyisellä saldolla",
        en="Next: the agent makes a new quote with the current stock",
    ),
}

# Short card labels for the flag codes that have none in policy/messages.yaml.
FLAG_SHORT: dict[str, Localized] = {
    "AVAILABILITY_UNVERIFIED": Localized(fi="saldo vahvistamatta", en="stock not confirmed"),
    "ALLERGEN_NO_LISTING": Localized(fi="ei allergeenitietoa", en="no allergen info"),
    "PACK_SIZE_FROM_NAME": Localized(fi="koko nimestä", en="pack size from name"),
    "ROUNDED_UP": Localized(fi="pyöristetty ylöspäin", en="rounded up"),
    "SUBSTITUTED_PACK_SIZE": Localized(fi="eri pakkauskoko", en="other pack size"),
    "SUBSTITUTED_CURATED": Localized(fi="korvaava tuote", en="substitute"),
    "QUANTITY_UNUSUAL": Localized(fi="poikkeava määrä", en="unusual quantity"),
    "DUPLICATE_ORDER": Localized(fi="mahdollinen tuplatilaus", en="possible duplicate"),
    "FIRST_TIME_PRODUCT": Localized(fi="uusi tuote", en="new product"),
}

NO_REQUEST_YET = Localized(fi="Ei vielä tilausta", en="No order yet")


# --- Loading --------------------------------------------------------------------------


@dataclass
class SessionRow:
    """One session with what its card and the totals need, as loaded."""

    id: uuid.UUID
    channel: Channel
    stored_channel: str
    client_name: str | None
    stored_state: SessionState
    state: SessionState  # after the idle rule
    state_since: datetime
    activity: datetime  # newest activity, for the order
    last_activity_at: datetime
    ended_at: datetime | None
    prompt_version: str | None
    company_name: str
    exclusions: list[Exclusion]
    identity_masked: str | None
    quote: dict[str, Any] | None = None  # the session's current quote, see _QUOTES
    order_number: str | None = None  # the confirmed order's "D-1042", see _ORDERS
    request_lines: list[dict[str, Any]] | None = None  # the latest request_received lines
    step_text: Localized | None = None


_SESSIONS = text(
    """
    SELECT s.id, s.channel, s.client_name, s.state, s.state_since, s.started_at,
           s.last_activity_at, s.ended_at, s.prompt_version,
           c.name AS company_name, k.exclusions, u.phone_e164, u.email
    FROM sessions s
    JOIN companies c ON c.id = s.company_id
    JOIN users u ON u.id = s.user_id
    LEFT JOIN kitchen_profiles k ON k.company_id = s.company_id
    WHERE (CAST(:event_start AS timestamptz) IS NULL OR s.started_at >= :event_start)
      AND (CAST(:session_ids AS uuid[]) IS NULL OR s.id = ANY(:session_ids))
      AND (CAST(:session_ids AS uuid[]) IS NOT NULL
           OR c.test_run IS NOT DISTINCT FROM CAST(:test_run AS text))
    """
).bindparams(
    bindparam("session_ids", type_=ARRAY(UUID(as_uuid=True))),
)

# The current quote of each session: the newest one that is not void, else the newest.
_QUOTES = text(
    """
    SELECT DISTINCT ON (q.session_id)
           q.session_id, q.id, q.version, q.status, q.total_cents, q.quote_hash, q.jws,
           jsonb_array_length(q.engine_output -> 'lines') AS line_count,
           q.engine_output -> 'flags' AS flags,
           q.engine_output -> 'delivery' AS delivery,
           q.engine_output -> 'rejections' AS rejections,
           q.engine_input -> 'lines' AS request_lines
    FROM quotes q
    WHERE q.session_id = ANY(:session_ids)
    ORDER BY q.session_id, (q.status = 'void'), q.issued_at DESC, q.version DESC
    """
).bindparams(bindparam("session_ids", type_=ARRAY(UUID(as_uuid=True))))

# The session's order (#47), made when the buyer confirmed one of its quotes, any version.
# One per confirmation; should a session have more, the newest one.
_ORDERS = text(
    """
    SELECT DISTINCT ON (o.session_id) o.session_id, o.order_number
    FROM orders o
    WHERE o.session_id = ANY(:session_ids)
    ORDER BY o.session_id, o.confirmed_at DESC, o.seq DESC
    """
).bindparams(bindparam("session_ids", type_=ARRAY(UUID(as_uuid=True))))

_LATEST_EVENTS = text(
    """
    SELECT DISTINCT ON (e.session_id) e.session_id, e.text_fi, e.text_en
    FROM audit_events e
    WHERE e.session_id = ANY(:session_ids)
    ORDER BY e.session_id, e.seq DESC
    """
).bindparams(bindparam("session_ids", type_=ARRAY(UUID(as_uuid=True))))

_LATEST_REQUESTS = text(
    """
    SELECT DISTINCT ON (e.session_id) e.session_id, e.payload -> 'lines' AS lines
    FROM audit_events e
    WHERE e.session_id = ANY(:session_ids) AND e.type = 'request_received'
    ORDER BY e.session_id, e.seq DESC
    """
).bindparams(bindparam("session_ids", type_=ARRAY(UUID(as_uuid=True))))


async def load_sessions(
    db: AsyncSession,
    *,
    session_ids: Sequence[uuid.UUID] | None = None,
    test_run: str | None = None,
    now: datetime | None = None,
) -> list[SessionRow]:
    """The sessions in scope (since `EVENT_START`), with their current quotes and orders.

    Without `session_ids`, the sessions of live test runs (#98) are left out; `test_run`
    gives the sessions of that run instead. A session asked for by id is always loaded.
    """
    now = now or datetime.now(UTC)
    result = await db.execute(
        _SESSIONS,
        {
            "event_start": get_settings().event_start,
            "session_ids": list(session_ids) if session_ids is not None else None,
            "test_run": test_run,
        },
    )
    rows = [_session_row(row, now) for row in result.mappings()]
    if rows:
        await _attach_quotes(db, rows, now)
    return rows


async def _attach_quotes(db: AsyncSession, rows: list[SessionRow], now: datetime) -> None:
    by_id = {row.id: row for row in rows}
    result = await db.execute(_QUOTES, {"session_ids": list(by_id)})
    for quote in result.mappings():
        by_id[quote["session_id"]].quote = dict(quote)
    for order in (await db.execute(_ORDERS, {"session_ids": list(by_id)})).mappings():
        by_id[order["session_id"]].order_number = order["order_number"]
    for row in rows:
        _apply_idle_rule(row, now)


async def attach_card_details(db: AsyncSession, rows: list[SessionRow]) -> None:
    """The live activity line and the latest request, only for the cards shown."""
    if not rows:
        return
    by_id = {row.id: row for row in rows}
    ids = {"session_ids": list(by_id)}
    for event in (await db.execute(_LATEST_EVENTS, ids)).mappings():
        row = by_id[event["session_id"]]
        if row.state in ACTIVE_STATES and (event["text_fi"] or event["text_en"]):
            row.step_text = Localized(fi=event["text_fi"] or "", en=event["text_en"] or "")
    for request in (await db.execute(_LATEST_REQUESTS, ids)).mappings():
        by_id[request["session_id"]].request_lines = request["lines"] or None


def _session_row(row: Any, now: datetime) -> SessionRow:
    stored_state = SessionState(row["state"])
    known = {e.value for e in Exclusion}
    return SessionRow(
        id=row["id"],
        channel=CHANNEL_OF[row["channel"]],
        stored_channel=row["channel"],
        client_name=row["client_name"],
        stored_state=stored_state,
        state=stored_state,
        state_since=row["state_since"],
        activity=max(row["last_activity_at"], row["state_since"]),
        last_activity_at=row["last_activity_at"],
        ended_at=row["ended_at"],
        prompt_version=row["prompt_version"],
        company_name=row["company_name"],
        exclusions=[Exclusion(e) for e in (row["exclusions"] or []) if e in known],
        identity_masked=_identity(row["channel"], row["phone_e164"], row["email"]),
    )


def _apply_idle_rule(row: SessionRow, now: datetime) -> None:
    """An active session that can no longer go on shows as `abandoned` (#49, §9.5).

    MCP, WebMCP and chat sessions have no hang-up: after 10 minutes without activity they
    are over. A call is over when the relay has ended it. None of these sessions reached a
    confirmation request (that would be a waiting state), so no order came of it.
    """
    if row.state not in ACTIVE_STATES:
        return
    ended_at = None
    if row.stored_channel == "phone":
        ended_at = row.ended_at
    elif now - row.last_activity_at > IDLE_TIMEOUT:
        ended_at = row.last_activity_at + IDLE_TIMEOUT
    if ended_at is not None:
        row.state = SessionState.abandoned
        row.state_since = max(ended_at, row.state_since)


def _identity(channel: str, phone_e164: str | None, email: str | None) -> str | None:
    """The masked email for connector accounts, otherwise the masked phone number."""
    if email and (channel == "connector" or not phone_e164):
        return mask_email(email)
    if phone_e164:
        try:
            return mask_phone(phone_e164)
        except Exception:
            return None
    return None


_TEST_SESSIONS = text(
    """
    SELECT s.id
    FROM sessions s
    JOIN companies c ON c.id = s.company_id
    WHERE s.id = ANY(:session_ids) AND c.test_run IS NOT NULL
    """
).bindparams(bindparam("session_ids", type_=ARRAY(UUID(as_uuid=True))))


async def hidden_sessions(db: AsyncSession, session_ids: Iterable[uuid.UUID]) -> set[uuid.UUID]:
    """Which of these sessions belong to a live test run (#98) and stay off the stream."""
    ids = list(session_ids)
    if not ids:
        return set()
    return set((await db.execute(_TEST_SESSIONS, {"session_ids": ids})).scalars())


# --- Building ---------------------------------------------------------------------------


def totals_of(rows: Iterable[SessionRow]) -> Totals:
    counts = dict.fromkeys(StateGroup, 0)
    by_channel = dict.fromkeys(Channel, 0)
    confirmed_cents = 0
    for row in rows:
        by_channel[row.channel] += 1
        group = STATE_GROUPS.get(row.state)
        if group is not None:
            counts[group] += 1
        if row.state == SessionState.confirmed and row.quote is not None:
            confirmed_cents += row.quote["total_cents"]
    return Totals(
        active=counts[StateGroup.active],
        waiting=counts[StateGroup.waiting],
        confirmed=counts[StateGroup.confirmed],
        attention=counts[StateGroup.attention],
        confirmed_cents=confirmed_cents,
        by_channel=by_channel,
    )


def client_label(stored_channel: str, client_name: str | None) -> str:
    if stored_channel == "phone":
        return "phone"
    if stored_channel == "web_chat":
        return "web chat"
    if stored_channel == "web":
        return "browser agent"  # WebMCP can't tell which agent is calling
    return client_name or "MCP client"


def card_of(row: SessionRow) -> OrderCard:
    quote = row.quote
    request_lines = row.request_lines or (quote["request_lines"] if quote else None) or []
    return OrderCard(
        session_id=str(row.id),
        order_number=row.order_number,
        channel=row.channel,
        client=client_label(row.stored_channel, row.client_name),
        identity_masked=row.identity_masked,
        state=row.state,
        state_since=row.state_since,
        title=title_of(request_lines),
        step_text=row.step_text if row.state in ACTIVE_STATES else None,
        line_count=(quote["line_count"] or 0) if quote else 0,
        total_cents=quote["total_cents"] if quote else None,
        flags=card_flags(quote["flags"] if quote else None),
        next_step=next_step_of(row),
        delivery_date=_delivery_date(quote),
        recipe_count=_recipe_count(request_lines),
    )


def company_of(row: SessionRow) -> CompanyRef:
    return CompanyRef(name=row.company_name, exclusions=row.exclusions)


def next_step_of(row: SessionRow) -> Localized | None:
    if STATE_GROUPS.get(row.state) != StateGroup.attention:
        return None
    if row.state == SessionState.rejected and row.quote and row.quote["rejections"]:
        step = row.quote["rejections"][0].get("next_step")
        if step and (step.get("fi") or step.get("en")):
            return Localized(
                fi=f"Seuraavaksi: {_lower_first(step['fi'])}",
                en=f"Next: {_lower_first(step['en'])}",
            )
    return NEXT_STEP.get(row.state)


def card_flags(flags: list[dict[str, Any]] | None) -> list[CardFlag]:
    messages = get_rule_set().messages
    result = []
    for flag in flags or []:
        code = flag["code"]
        short = FLAG_SHORT.get(code)
        if short is None:
            message = next((m for c, m in messages.items() if str(c) == code), None)
            label = getattr(message, "short", None)
            plain = code.replace("_", " ").lower()
            short = label or Localized(fi=plain, en=plain)
        result.append(CardFlag(code=code, short=short))
    return result


def title_of(lines: list[dict[str, Any]]) -> Localized:
    """The first asked line plus "+ N more": `1 000 l laktoositonta maitoa + 2 more`."""
    if not lines:
        return NO_REQUEST_YET
    first = asked_text(lines[0])
    more = len(lines) - 1
    if more:
        return Localized(fi=f"{first.fi} + {more} muuta", en=f"{first.en} + {more} more")
    return first


def asked_text(line: dict[str, Any]) -> Localized:
    """One asked line in words, without the date: `5 kg jauheliha`, `12 pcs usual product`."""
    quantity = format_quantity(Decimal(str(line["quantity"])))
    unit = _unit_words(line.get("unit"), line.get("package_word"))
    words = line.get("text")
    if words:
        what = Localized(fi=words, en=words)
    elif line.get("usual"):
        what = Localized(fi="tavallinen tuote", en="usual product")
    elif line.get("product_id"):
        what = Localized(fi=f"tuote {line['product_id']}", en=f"product {line['product_id']}")
    else:
        what = Localized(fi="tuote", en="product")
    return Localized(
        fi=f"{quantity.fi} {unit.fi} {what.fi}".strip(),
        en=f"{quantity.en} {unit.en} {what.en}".strip(),
    )


def format_quantity(value: Decimal) -> Localized:
    """`1 000` and `2,5` in Finnish, `1,000` and `2.5` in English."""
    plain = format(value.normalize(), "f")
    whole, _, fraction = plain.partition(".")
    grouped = f"{int(whole):,}"
    return Localized(
        fi=grouped.replace(",", " ") + (f",{fraction}" if fraction else ""),
        en=grouped + (f".{fraction}" if fraction else ""),
    )


def _unit_words(unit: str | None, package_word: str | None) -> Localized:
    if unit in ("l", "kg"):
        return Localized(fi=unit, en=unit)
    if unit == "piece":
        return Localized(fi="kpl", en="pcs")
    if unit == "package":
        word = package_word or ""
        return Localized(fi=word or "pakkausta", en=word or "packages")
    if unit == "sales_unit":
        return Localized(fi="myyntierää", en="sales units")
    return Localized(fi=unit or "", en=unit or "")


def _delivery_date(quote: dict[str, Any] | None) -> date | None:
    delivery = quote["delivery"] if quote else None
    if not delivery:
        return None
    return date.fromisoformat(delivery["latest"])


def _recipe_count(lines: list[dict[str, Any]]) -> int | None:
    recipes = {line["recipe_ref"]["recipe_id"] for line in lines if line.get("recipe_ref")}
    return len(recipes) or None


def _lower_first(value: str) -> str:
    return value[:1].lower() + value[1:]


def _matches(row: SessionRow, state: StateGroup | None, channel: Channel | None) -> bool:
    if state is not None and STATE_GROUPS.get(row.state) != state:
        return False
    return channel is None or row.channel == channel


def group_cards(rows: Sequence[SessionRow]) -> list[CompanyGroup]:
    """Companies in the order of their newest card; `rows` are newest first already."""
    groups: dict[str, CompanyGroup] = {}
    for row in rows:
        group = groups.get(row.company_name)
        if group is None:
            group = groups[row.company_name] = CompanyGroup(
                name=row.company_name, exclusions=row.exclusions, orders=[]
            )
        group.orders.append(card_of(row))
    return list(groups.values())


# --- Entry points -----------------------------------------------------------------------


async def load_overview(
    db: AsyncSession,
    state: StateGroup | None = None,
    channel: Channel | None = None,
    since: datetime | None = None,
    *,
    now: datetime | None = None,
    limit: int = MAX_CARDS,
    test_run: str | None = None,
) -> OverviewResponse:
    """`GET /orders` and the snapshot: totals over everything, then at most `limit` cards
    that match the filters, newest activity first. With `test_run`, that live test run's
    sessions instead of the public ones."""
    rows = await load_sessions(db, test_run=test_run, now=now)
    totals = totals_of(rows)
    shown = sorted(
        (r for r in rows if _matches(r, state, channel) and (since is None or r.activity >= since)),
        key=lambda r: (r.activity, str(r.id)),
        reverse=True,
    )[:limit]
    await attach_card_details(db, shown)
    return OverviewResponse(
        business_now=get_rule_set().policy.business_time,
        totals=totals,
        companies=group_cards(shown),
    )


async def load_order_updated(
    db: AsyncSession, session_id: uuid.UUID, *, now: datetime | None = None
) -> OrderUpdated | None:
    """The `order_updated` event for one session, with fresh totals, or None when the session
    is out of scope (before `EVENT_START`) or gone."""
    rows = await load_sessions(db, now=now)
    row = next((r for r in rows if r.id == session_id), None)
    if row is None:
        return None
    await attach_card_details(db, [row])
    return OrderUpdated(company=company_of(row), order=card_of(row), totals=totals_of(rows))
