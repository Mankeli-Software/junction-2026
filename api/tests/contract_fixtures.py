"""Shared engine input for the contract tests."""

from datetime import date, datetime
from decimal import Decimal

from app.schemas import (
    EngineInput,
    HistorySummary,
    KitchenProfile,
    LineRequest,
    RequestedUnit,
    RuleSet,
)

RULES = RuleSet(
    version="2026-11-14.1",
    quote_ttl_seconds=None,
    enforce_closing_time=True,
    unverified_stock_threshold=999999,
    round_up_max_units=1,
    round_up_max_ratio=Decimal("0.02"),
    duplicate_window_seconds=7200,
    substitute_max_price_increase_ratio=Decimal("0.10"),
)


def line(line_id: str = "l1", text: str = "maito", quantity: str = "2", **kw) -> LineRequest:
    return LineRequest(
        line_id=line_id,
        text=text,
        quantity=Decimal(quantity),
        unit=kw.pop("unit", RequestedUnit.l),
        needed_by=kw.pop("needed_by", date(2026, 11, 16)),
        **kw,
    )


def engine_input(*lines: LineRequest) -> EngineInput:
    return EngineInput(
        lines=list(lines) or [line()],
        kitchen=KitchenProfile(exclusions=[]),
        history=HistorySummary(usual_items=[], recent_lines=[]),
        products=[],
        offers=[],
        rules=RULES,
        business_now=datetime.fromisoformat("2026-11-12T09:00:00+02:00"),
        issued_at=datetime.fromisoformat("2026-11-14T12:00:00+02:00"),
        lang="fi",
    )
