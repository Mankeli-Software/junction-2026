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


class RemovedProduct(StrictModel):
    product_id: str
    name: Localized


class TraceRemoval(StrictModel):
    reason_code: str
    count: int
    text: Localized
    products: list[RemovedProduct] = []  # the candidates this check removed


class RankedCandidate(StrictModel):
    """One candidate that passed every check, in ranking order (`rank` 1 is the best)."""

    rank: int
    product_id: str
    name: Localized
    price_per_base_unit: JsonDecimal | None
    stock_status: StockStatus
    chosen: bool


class Trace(StrictModel):
    """Candidates found, removed per reason and left.

    Each candidate is counted once, at the first check it fails, in the order the checks run.
    """

    found: int
    removed: list[TraceRemoval]
    left: int
    ranking_rule: Localized
    ranked: list[RankedCandidate] = []


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
    """A notice on the quote. The buyer acknowledges it on the confirmation page."""

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
    # "photo" when the group's lines came from a confirmed recipe draft (#80), which the
    # confirmation page shows as "From your recipe photo".
    source: Literal["photo"] | None = None
    recipe_draft_id: str | None = None
    # The recipe's image for a group from one of our recipes, or from the recipe a dish photo
    # matched (#57): the recipe data's own URL, never built. Null for other groups.
    image_url: str | None = None


class DeliverySummary(StrictModel):
    earliest: date
    latest: date
