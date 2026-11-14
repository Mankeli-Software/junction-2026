"""Quote parts shared by the engine output and the tool responses (technical-plan.md §9.1)."""

from datetime import date
from typing import Literal

from .common import JsonDecimal, Localized, RequestedUnit, StockStatus, StrictModel


class AskedLine(StrictModel):
    """Echo of what the buyer asked for."""

    text: str | None
    quantity: JsonDecimal
    unit: RequestedUnit
    package_word: str | None
    needed_by: date


class TraceRemoval(StrictModel):
    reason_code: str
    count: int
    text: Localized


class Trace(StrictModel):
    """Candidates found, removed per reason and left.

    Each candidate is counted once, at the first step it fails, in §4.2 order.
    """

    found: int
    removed: list[TraceRemoval]
    left: int
    ranking_rule: Localized


class Alternative(StrictModel):
    product_id: str
    label: Localized
    quantity_sales_units: int
    line_total_cents: int


class QuoteLine(StrictModel):
    line_id: str
    group: str | None
    asked: AskedLine
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
    origin: str | None
    reason_codes: list[str]
    reason_text: Localized
    trace: Trace
    alternatives: list[Alternative]


class FlagOption(StrictModel):
    option_id: str
    label: Localized
    line_total_cents: int


class Flag(StrictModel):
    """A notice on the quote. `acknowledged_at` belongs to the confirmation view (#47)."""

    flag_key: str  # stable across re-quotes
    code: str
    line_ids: list[str]  # empty for order-wide flags
    kind: Literal["acknowledge", "choose"]
    text: Localized
    options: list[FlagOption] = []  # only for `choose`


class Clarification(StrictModel):
    """The single question back to the buyer. `options` may be empty for an open question."""

    line_id: str
    question: Localized
    options: list[Alternative]


class Rejection(StrictModel):
    line_id: str
    reason_code: str
    text: Localized
    next_step: Localized


class NotOrdered(StrictModel):
    """A recipe ingredient without a product link. The recipe data is Finnish only."""

    name: str
    quantity: JsonDecimal | None
    unit: str | None
    reason: Localized


class GroupSubtotal(StrictModel):
    group: str
    line_ids: list[str]
    subtotal_cents: int


class DeliverySummary(StrictModel):
    earliest: date
    latest: date
