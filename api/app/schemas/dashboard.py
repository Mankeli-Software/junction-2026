"""Responses of the public dashboard API and its stream (#49, technical-plan.md §9.5).

Everything here is public, with no login. No model carries a confirmation token or link, a
full phone number or a full email: identities arrive masked, and every response and stream
event also goes through `app.services.dashboard.redact`.

The dashboard UI (`web/src/lib/dashboard/types.ts`) was built against these shapes. Fields
the UI added beyond #49's spec are marked "Assumed" there and here, and are optional.
Money totals are integer cents; unit prices stay in euros, as in `QuoteLine`.
"""

from datetime import date, datetime
from enum import StrEnum
from typing import Any, Literal

from .common import Exclusion, JsonDecimal, Lang, Localized, StockStatus, StrictModel
from .quote import AskedLine, NotOrdered


class Channel(StrEnum):
    """The channel a session came in through, one tile each on the overview."""

    phone = "phone"
    web_chat = "web_chat"
    webmcp = "webmcp"
    mcp = "mcp"


class SessionState(StrEnum):
    """Session states, `docs/specs/dashboard.md` §4."""

    in_conversation = "in_conversation"
    needs_clarification = "needs_clarification"
    quote_ready = "quote_ready"
    awaiting_confirmation = "awaiting_confirmation"
    link_opened = "link_opened"
    confirmed = "confirmed"
    cancelled = "cancelled"
    expired = "expired"
    rejected = "rejected"
    sms_failed = "sms_failed"
    callback_requested = "callback_requested"
    requote_needed = "requote_needed"
    abandoned = "abandoned"


class StateGroup(StrEnum):
    """The groups behind the counters and the `?state=` filter (#49, "States and totals")."""

    active = "active"
    waiting = "waiting"
    confirmed = "confirmed"
    attention = "attention"


# `cancelled` and `abandoned` are in no group: they count only in the card list.
STATE_GROUPS: dict[SessionState, StateGroup] = {
    SessionState.in_conversation: StateGroup.active,
    SessionState.needs_clarification: StateGroup.active,
    SessionState.quote_ready: StateGroup.active,
    SessionState.awaiting_confirmation: StateGroup.waiting,
    SessionState.link_opened: StateGroup.waiting,
    SessionState.confirmed: StateGroup.confirmed,
    SessionState.expired: StateGroup.attention,
    SessionState.rejected: StateGroup.attention,
    SessionState.sms_failed: StateGroup.attention,
    SessionState.callback_requested: StateGroup.attention,
    SessionState.requote_needed: StateGroup.attention,
}


# GET /api/v1/public/orders


class Totals(StrictModel):
    """Counts since `EVENT_START`, not limited by the filters or the 200-card cap."""

    active: int
    waiting: int
    confirmed: int
    attention: int
    confirmed_cents: int
    by_channel: dict[Channel, int]


class CardFlag(StrictModel):
    """A flag on a card, for "2 flags: stock not confirmed, new product"."""

    code: str
    short: Localized  # Assumed: a short label, a few words


class OrderCard(StrictModel):
    session_id: str
    order_number: str | None  # "D-1042", null until an order exists
    channel: Channel
    client: str  # `phone`, `web chat`, `browser agent`, or the OAuth `client_name`
    identity_masked: str | None  # `+358 40 *** **12` or `j***@example.com`
    state: SessionState
    state_since: datetime
    title: Localized  # first asked line plus "+ N more"
    step_text: Localized | None  # the live activity line while active
    line_count: int
    total_cents: int | None
    flags: list[CardFlag]
    next_step: Localized | None  # for attention states
    delivery_date: date | None = None  # Assumed
    recipe_count: int | None = None  # Assumed: "5 recipes, 14 lines"


class CompanyRef(StrictModel):
    name: str
    exclusions: list[Exclusion]


class CompanyGroup(CompanyRef):
    orders: list[OrderCard]  # newest activity first


class OverviewResponse(StrictModel):
    """`GET /orders` and the stream's `snapshot` event."""

    business_now: datetime  # the demo clock
    totals: Totals
    companies: list[CompanyGroup]  # newest activity first, at most 200 cards in all


# GET /api/v1/public/orders/{session_id}


class RemovedProduct(StrictModel):
    product_id: str
    name: Localized


class SummaryTraceRemoval(StrictModel):
    """`TraceRemoval` plus the products the filter removed."""

    reason_code: str
    count: int
    text: Localized
    products: list[RemovedProduct] = []  # Assumed


class RankedCandidate(StrictModel):
    rank: int
    product_id: str
    name: Localized
    price_per_base_unit: JsonDecimal | None
    stock_status: StockStatus
    chosen: bool


class SummaryTrace(StrictModel):
    """`Trace` plus the ranked candidates #49 lists for the summary."""

    found: int
    removed: list[SummaryTraceRemoval]
    left: int
    ranking_rule: Localized
    ranked: list[RankedCandidate] = []  # Assumed field name


class SummaryLine(StrictModel):
    """The fields of `QuoteLine` the summary shows, with the richer trace."""

    line_id: str
    product_id: str
    name: Localized
    image_url: str | None
    sales_unit: str
    sales_unit_label: Localized
    quantity_sales_units: int
    quantity_in_asked_unit: JsonDecimal
    unit_price_gross: JsonDecimal
    price_per_base_unit: JsonDecimal | None
    base_unit: str | None
    line_total_cents: int
    delivery_date: date
    stock_status: StockStatus
    reason_text: Localized
    trace: SummaryTrace


class SummaryRequest(StrictModel):
    """Assumed grouping: one request ("what was asked") with the lines added for it."""

    request_id: str
    asked: AskedLine
    asked_text: Localized  # "5 kg ground beef, by Monday"
    group: Localized | None  # recipe or split group name
    lines: list[SummaryLine]
    not_ordered: list[NotOrdered]


class SummaryFlag(StrictModel):
    flag_key: str
    code: str
    text: Localized
    detail: Localized | None  # Assumed: the second line ("Rapeseed oil 5 l")
    acknowledged_at: datetime | None


class QuoteRef(StrictModel):
    id: str
    version: int
    hash: str


class AgentInfo(StrictModel):
    """Assumed: the agent and prompt version that ran the session."""

    name: Localized  # "Gemini voice agent"
    prompt_version: str | None


class OrderSummary(StrictModel):
    session_id: str
    order_number: str | None
    company: CompanyRef
    channel: Channel
    client: str
    identity_masked: str | None
    state: SessionState
    state_since: datetime
    status_line: Localized | None  # Assumed: "by the buyer, after checking 3 flags"
    delivery_date: date | None  # Assumed
    total_cents: int | None
    requests: list[SummaryRequest]
    flags: list[SummaryFlag]
    quote: QuoteRef | None
    signature_valid: bool | None  # null until #40 signs quotes
    agent: AgentInfo | None = None  # Assumed


# GET /orders/{session_id}/steps, /transcript, /events


class Step(StrictModel):
    """One audit event without its payload, enough to verify the chain (§8.5)."""

    seq: int  # place in the global chain
    order_index: int  # number within the order, from 1
    # Kept as the exact string that was hashed, so the browser can recompute the hash.
    at: str
    actor: str  # buyer, agent, mcp, engine, relay, confirmation, ...
    type: str
    text: Localized
    payload_hash: str
    prev_hash: str
    session_prev_hash: str | None  # null for the session's first event
    hash: str


class TranscriptLine(StrictModel):
    at: datetime
    who: Literal["buyer", "agent"]
    text: str
    lang: Lang


class AuditEvent(Step):
    """A full redacted event, as `/events` returns it. The payload shape depends on `type`."""

    session_id: str
    channel: Channel
    identity_masked: str | None
    quote_id: str | None
    payload: dict[str, Any]


# GET /api/v1/public/audit/verify


class VerifyResult(StrictModel):
    """From #41's verify function; the global chain without `session_id`."""

    ok: bool
    checked: int
    first_bad_seq: int | None
    signature_valid: bool | None  # null until #40


# SSE /api/v1/public/stream. `snapshot` carries an `OverviewResponse`.


class OrderUpdated(StrictModel):
    """Assumed shape: the full card with its company, so a new card can be placed."""

    company: CompanyRef
    order: OrderCard
    totals: Totals | None = None  # Assumed: fresh totals; otherwise the client adjusts


class StepEvent(StrictModel):
    session_id: str
    step: Step


class TranscriptEvent(StrictModel):
    session_id: str
    line: TranscriptLine


StreamEventType = Literal["snapshot", "order_updated", "step", "transcript"]
