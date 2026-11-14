"""One order on the public dashboard (#49): summary, steps, transcript, events and verify.

All of these read `sessions`, `quotes`, `orders`, `confirmation_acknowledgements` and
`audit_events`; the routes redact the result.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditEvent as AuditEventRow
from app.models import ConfirmationAcknowledgement, Quote
from app.schemas import (
    AgentInfo,
    AskedLine,
    AuditEvent,
    EngineOutput,
    LineRequest,
    Localized,
    NotOrdered,
    OrderSummary,
    QuoteRef,
    QuoteStatus,
    SessionState,
    Step,
    SummaryFlag,
    SummaryLine,
    SummaryRequest,
    SummaryTrace,
    SummaryTraceRemoval,
    TranscriptLine,
    VerifyResult,
)
from app.services import signing
from app.services.audit import verify_chain
from app.services.audit.chain import format_at
from app.services.confirmation_page import text_hash
from app.services.errors import NotFoundError

from .overview import (
    SessionRow,
    asked_text,
    attach_card_details,
    client_label,
    company_of,
    load_sessions,
)

TRANSCRIPT_TYPES = {"buyer_said": "buyer", "agent_said": "agent"}

AGENT_NAMES: dict[str, Localized] = {
    "phone": Localized(fi="Gemini-puheagentti", en="Gemini voice agent"),
    "web_chat": Localized(fi="Verkkokaupan chat-agentti", en="Webshop chat agent"),
}


def parse_session_id(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError:
        raise NotFoundError("order not found") from None


async def session_row(db: AsyncSession, session_id: str | uuid.UUID) -> SessionRow:
    """The session, or NotFoundError when it is unknown or before `EVENT_START`."""
    sid = session_id if isinstance(session_id, uuid.UUID) else parse_session_id(session_id)
    rows = await load_sessions(db, session_ids=[sid])
    if not rows:
        raise NotFoundError("order not found")
    return rows[0]


# --- Summary ----------------------------------------------------------------------------


async def load_summary(db: AsyncSession, session_id: str) -> OrderSummary:
    row = await session_row(db, session_id)
    await attach_card_details(db, [row])
    quote = await _current_quote(db, row.id)
    output = EngineOutput.model_validate(quote.engine_output) if quote else None
    requests = _requests(quote, output, row.request_lines) if quote or row.request_lines else []
    acknowledged = await _acknowledged(db, row.id)
    flags = [
        SummaryFlag(
            flag_key=f.flag_key,
            code=f.code,
            text=f.text,
            detail=None,
            acknowledged_at=acknowledged.get((f.flag_key, text_hash(f.text))),
        )
        for f in (output.flags if output else [])
    ]
    return OrderSummary(
        session_id=str(row.id),
        order_number=row.order_number,
        company=company_of(row),
        channel=row.channel,
        client=client_label(row.stored_channel, row.client_name),
        identity_masked=row.identity_masked,
        state=row.state,
        state_since=row.state_since,
        status_line=_status_line(row, flags),
        delivery_date=output.delivery.latest if output and output.delivery else None,
        total_cents=quote.total_cents if quote else None,
        requests=requests,
        flags=flags,
        quote=QuoteRef(id=str(quote.id), version=quote.version, hash=quote.quote_hash)
        if quote and quote.quote_hash
        else None,
        signature_valid=signature_valid(quote),
        agent=_agent(row),
    )


def _agent(row: SessionRow) -> AgentInfo:
    client = client_label(row.stored_channel, row.client_name)
    name = AGENT_NAMES.get(row.stored_channel) or Localized(fi=client, en=client)
    return AgentInfo(name=name, prompt_version=row.prompt_version)


def signature_valid(quote: Quote | None) -> bool | None:
    """Whether the quote's JWS checks against the published key and its stored hash (#40).
    Null without a signed quote (only `ready` quotes are signed)."""
    if quote is None or quote.jws is None:
        return None
    return signing.verify_quote(quote.jws, quote.quote_hash)


async def _current_quote(db: AsyncSession, session_id: uuid.UUID) -> Quote | None:
    return await db.scalar(
        select(Quote)
        .where(Quote.session_id == session_id)
        .order_by(
            (Quote.status == QuoteStatus.void.value).asc(),
            Quote.issued_at.desc(),
            Quote.version.desc(),
        )
        .limit(1)
    )


def _requests(
    quote: Quote | None, output: EngineOutput | None, request_lines: list[dict] | None
) -> list[SummaryRequest]:
    """One request per asked line, with the priced line under it (asked versus added)."""
    raw_lines = quote.engine_input["lines"] if quote else request_lines or []
    asked = [LineRequest.model_validate(line) for line in raw_lines]
    priced = {line.line_id: line for line in output.lines} if output else {}
    rejected = {r.line_id: r for r in output.rejections} if output else {}
    requests = []
    for raw, line in zip(raw_lines, asked, strict=True):
        result = priced.get(line.line_id)
        not_ordered = []
        if line.line_id in rejected:
            not_ordered.append(
                NotOrdered(
                    name=line.text or line.product_id or line.line_id,
                    quantity=line.quantity,
                    unit=line.unit.value,
                    reason=rejected[line.line_id].text,
                )
            )
        words = asked_text(raw)
        day = line.needed_by.isoformat()
        requests.append(
            SummaryRequest(
                request_id=line.line_id,
                asked=AskedLine(
                    text=line.text,
                    quantity=line.quantity,
                    unit=line.unit,
                    package_word=line.package_word,
                    needed_by=line.needed_by,
                ),
                asked_text=Localized(fi=f"{words.fi}, {day} mennessä", en=f"{words.en}, by {day}"),
                group=Localized(fi=line.group, en=line.group) if line.group else None,
                lines=[_summary_line(result)] if result else [],
                not_ordered=not_ordered,
            )
        )
    if output and output.not_ordered and requests:
        requests[0].not_ordered.extend(output.not_ordered)
    return requests


def _summary_line(line: Any) -> SummaryLine:
    trace = line.trace
    return SummaryLine(
        line_id=line.line_id,
        product_id=line.product_id,
        name=line.name,
        image_url=line.image_url,
        sales_unit=line.sales_unit,
        sales_unit_label=line.sales_unit_label,
        quantity_sales_units=line.quantity_sales_units,
        quantity_in_asked_unit=line.quantity_in_asked_unit,
        unit_price_gross=line.unit_price_gross,
        price_per_base_unit=line.price_per_base_unit,
        base_unit=line.base_unit,
        line_total_cents=line.line_total_cents,
        delivery_date=line.delivery_date,
        stock_status=line.stock_status,
        reason_text=line.reason_text,
        # The engine reports the ranked survivors and each check's removed products (#39).
        trace=SummaryTrace(
            found=trace.found,
            removed=[
                SummaryTraceRemoval(
                    reason_code=r.reason_code, count=r.count, text=r.text, products=r.products
                )
                for r in trace.removed
            ],
            left=trace.left,
            ranking_rule=trace.ranking_rule,
            ranked=trace.ranked,
        ),
    )


async def _acknowledged(db: AsyncSession, session_id: uuid.UUID) -> dict[tuple[str, str], datetime]:
    """When the buyer ticked each flag on the confirmation page, by `(flag_key, text_hash)`.

    From #47's `confirmation_acknowledgements`, over every quote of the session: a tick
    carries over to a new quote while the flag's text stays the same, as on the page.
    """
    rows = await db.execute(
        select(
            ConfirmationAcknowledgement.flag_key,
            ConfirmationAcknowledgement.text_hash,
            func.min(ConfirmationAcknowledgement.acknowledged_at),
        )
        .join(Quote, Quote.id == ConfirmationAcknowledgement.quote_id)
        .where(Quote.session_id == session_id)
        .group_by(ConfirmationAcknowledgement.flag_key, ConfirmationAcknowledgement.text_hash)
    )
    return {(key, digest): at for key, digest, at in rows}


def _status_line(row: SessionRow, flags: list[SummaryFlag]) -> Localized | None:
    if row.state != SessionState.confirmed:
        return row.step_text
    checked = sum(f.acknowledged_at is not None for f in flags)
    if checked:
        one = checked == 1
        return Localized(
            fi=f"ostajan vahvistama, {checked} {'huomio' if one else 'huomiota'} kuitattu",
            en=f"by the buyer, after checking {checked} {'flag' if one else 'flags'}",
        )
    return Localized(fi="ostajan vahvistama", en="by the buyer")


# --- Steps, transcript, events ----------------------------------------------------------


async def _events(db: AsyncSession, session_id: uuid.UUID) -> list[AuditEventRow]:
    rows = await db.scalars(
        select(AuditEventRow)
        .where(AuditEventRow.session_id == session_id)
        .order_by(AuditEventRow.seq)
    )
    return list(rows)


def step_of(event: AuditEventRow, order_index: int) -> Step:
    return Step(
        seq=event.seq,
        order_index=order_index,
        session_id=str(event.session_id),
        quote_id=None if event.quote_id is None else str(event.quote_id),
        at=format_at(event.at),
        actor=event.actor,
        type=event.type,
        text=Localized(fi=event.text_fi or "", en=event.text_en or ""),
        payload_hash=event.payload_hash,
        prev_hash=event.prev_hash,
        session_prev_hash=event.session_prev_hash,
        hash=event.hash,
    )


def transcript_line_of(event: AuditEventRow) -> TranscriptLine | None:
    """A `buyer_said` or `agent_said` event as a line; its payload holds `text` and `lang`."""
    who = TRANSCRIPT_TYPES.get(event.type)
    if who is None:
        return None
    payload = event.payload or {}
    lang = payload.get("lang") if payload.get("lang") in ("fi", "en") else "fi"
    words = payload.get("text")
    if not isinstance(words, str):
        words = (event.text_en if lang == "en" else event.text_fi) or ""
    return TranscriptLine(at=event.at, who=who, text=words, lang=lang)


async def load_steps(db: AsyncSession, session_id: str) -> list[Step]:
    row = await session_row(db, session_id)
    return [step_of(e, i) for i, e in enumerate(await _events(db, row.id), start=1)]


async def load_transcript(db: AsyncSession, session_id: str) -> list[TranscriptLine]:
    row = await session_row(db, session_id)
    lines = (transcript_line_of(e) for e in await _events(db, row.id))
    return [line for line in lines if line is not None]


async def load_events(db: AsyncSession, session_id: str) -> list[AuditEvent]:
    row = await session_row(db, session_id)
    return [
        AuditEvent(
            **dict(step_of(e, i)),
            channel=row.channel,
            identity_masked=row.identity_masked,
            payload=e.payload,
            text_fi=e.text_fi,
            text_en=e.text_en,
        )
        for i, e in enumerate(await _events(db, row.id), start=1)
    ]


async def order_index_of(db: AsyncSession, event: AuditEventRow) -> int:
    """The event's number within its session, from 1."""
    return (
        await db.scalar(
            select(func.count())
            .select_from(AuditEventRow)
            .where(AuditEventRow.session_id == event.session_id, AuditEventRow.seq <= event.seq)
        )
    ) or 1


# --- Verify -----------------------------------------------------------------------------


async def verify(db: AsyncSession, session_id: str | None) -> VerifyResult:
    """#41's chain check, globally or for one session (404 for an unknown session)."""
    if session_id is None:
        return await verify_chain(db)
    row = await session_row(db, session_id)
    result = await verify_chain(db, row.id)
    quote = await _current_quote(db, row.id)
    return result.model_copy(update={"signature_valid": signature_valid(quote)})
