"""Stub engine (#26): a fixed milk quote so web, voice and platform can build against the contract.

Deterministic and pure. Magic words in a line's `text`:
- "unclear" returns `needs_clarification` with two milk options.
- "reject" returns `rejected` for that line; the other lines are still priced.
Anything else is priced as 464306 Valio Arki semi skimmed 1 l.
"""

import math
from decimal import Decimal

from app.schemas import (
    Alternative,
    AskedLine,
    Clarification,
    Decision,
    DeliverySummary,
    EngineInput,
    EngineOutput,
    Flag,
    GroupSubtotal,
    LineRequest,
    Localized,
    QuoteLine,
    Rejection,
    StockStatus,
    Trace,
    TraceRemoval,
)

MILK_ID = "464306"
MILK_NAME = Localized(fi="Valio Arki kevytmaito 1 l", en="Valio Arki semi skimmed milk 1 l")
MILK_PRICE = Decimal("1.15")

WHOLE_MILK_ID = "464073"
WHOLE_MILK_NAME = Localized(fi="Valio täysmaito 1 l UHT", en="Valio whole milk 1 l UHT")
WHOLE_MILK_PRICE = Decimal("1.86")

PIECE = Localized(fi="kappale", en="piece")


def _cents(units: int, price: Decimal) -> int:
    """Line total in cents, rounded up to the next cent."""
    return math.ceil(Decimal(units) * price * 100)


def _euros(cents: int, lang: str) -> str:
    whole, rest = divmod(cents, 100)
    return f"{whole},{rest:02d} €" if lang == "fi" else f"€{whole}.{rest:02d}"


def _alternative(product_id: str, name: Localized, price: Decimal, units: int) -> Alternative:
    return Alternative(
        product_id=product_id,
        label=name,
        quantity_sales_units=units,
        line_total_cents=_cents(units, price),
    )


def _trace() -> Trace:
    return Trace(
        found=7,
        removed=[
            TraceRemoval(
                reason_code="EMPTY_SCHEDULE",
                count=1,
                text=Localized(fi="ei saatavilla", en="not available"),
            ),
            TraceRemoval(
                reason_code="TERMINAL",
                count=1,
                text=Localized(fi="poistumassa valikoimasta", en="being discontinued"),
            ),
        ],
        left=5,
        ranking_rule=Localized(fi="halvin litrahinta", en="lowest price per litre"),
    )


def _price_line(line: LineRequest) -> QuoteLine:
    units = math.ceil(line.quantity)
    return QuoteLine(
        line_id=line.line_id,
        group=line.group,
        asked=AskedLine(
            text=line.text,
            quantity=line.quantity,
            unit=line.unit,
            package_word=line.package_word,
            needed_by=line.needed_by,
        ),
        product_id=MILK_ID,
        name=MILK_NAME,
        image_url=None,
        sales_unit="ST",
        sales_unit_label=PIECE,
        quantity_sales_units=units,
        quantity_in_asked_unit=Decimal(units),
        unit_price_gross=MILK_PRICE,
        price_per_base_unit=MILK_PRICE,
        base_unit="l",
        line_total_cents=_cents(units, MILK_PRICE),
        delivery_date=line.needed_by,
        stock_status=StockStatus.unverified,
        origin="FI",
        reason_codes=["CHEAPEST", "LACTOSE_FREE"],
        reason_text=Localized(
            fi="Halvin laktoositon maito, joka ehtii ajoissa.",
            en="The cheapest lactose-free milk that arrives in time.",
        ),
        trace=_trace(),
        alternatives=[_alternative(WHOLE_MILK_ID, WHOLE_MILK_NAME, WHOLE_MILK_PRICE, units)],
    )


def _has(line: LineRequest, word: str) -> bool:
    return word in (line.text or "").lower()


def decide(data: EngineInput) -> EngineOutput:
    unclear = next((line for line in data.lines if _has(line, "unclear")), None)
    if unclear is not None:
        units = math.ceil(unclear.quantity)
        return EngineOutput(
            decision=Decision.needs_clarification,
            lines=[],
            groups=[],
            flags=[],
            clarification=Clarification(
                line_id=unclear.line_id,
                question=Localized(fi="Mitä maitoa tarkoitat?", en="Which milk do you mean?"),
                options=[
                    _alternative(MILK_ID, MILK_NAME, MILK_PRICE, units),
                    _alternative(WHOLE_MILK_ID, WHOLE_MILK_NAME, WHOLE_MILK_PRICE, units),
                ],
            ),
            rejections=[],
            not_ordered=[],
            total_cents=0,
            delivery=None,
            speak=Localized(fi="Mitä maitoa tarkoitat?", en="Which milk do you mean?"),
            rules_ref=data.rules.ref,
        )

    rejections = [
        Rejection(
            line_id=line.line_id,
            reason_code="UNAVAILABLE",
            text=Localized(fi="Tuote ei ole saatavilla.", en="The product is not available."),
            next_step=Localized(fi="Pyydä soittopyyntö", en="Ask for a callback"),
        )
        for line in data.lines
        if _has(line, "reject")
    ]
    rejected_ids = {r.line_id for r in rejections}
    lines = [_price_line(line) for line in data.lines if line.line_id not in rejected_ids]

    groups: dict[str, list[QuoteLine]] = {}
    for line in lines:
        if line.group is not None:
            groups.setdefault(line.group, []).append(line)

    total = sum(line.line_total_cents for line in lines)
    dates = [line.delivery_date for line in lines]

    if rejections:
        speak = Localized(
            fi="Kaikkia tuotteita ei voi tilata. Voin pyytää soittopyynnön.",
            en="Not every product can be ordered. I can ask for a callback.",
        )
    else:
        speak = Localized(
            fi=f"Tilauksen summa on {_euros(total, 'fi')}.",
            en=f"The order total is {_euros(total, 'en')}.",
        )

    return EngineOutput(
        decision=Decision.rejected if rejections else Decision.ready,
        lines=lines,
        groups=[
            GroupSubtotal(
                group=name,
                line_ids=[line.line_id for line in members],
                subtotal_cents=sum(line.line_total_cents for line in members),
            )
            for name, members in groups.items()
        ],
        flags=[
            Flag(
                flag_key=f"stock_unverified:{line.line_id}",
                code="STOCK_UNVERIFIED",
                line_ids=[line.line_id],
                kind="acknowledge",
                text=Localized(
                    fi="Varastosaldoa ei voitu varmistaa.",
                    en="The stock level could not be verified.",
                ),
            )
            for line in lines
        ],
        clarification=None,
        rejections=rejections,
        not_ordered=[],
        total_cents=total,
        delivery=DeliverySummary(earliest=min(dates), latest=max(dates)) if dates else None,
        speak=speak,
        rules_ref=data.rules.ref,
    )
