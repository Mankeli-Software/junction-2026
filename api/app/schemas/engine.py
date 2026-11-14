"""Engine input and output (technical-plan.md §4.1). All engine input comes in here."""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import Field

from .common import (
    Claim,
    Decision,
    Exclusion,
    JsonDecimal,
    Lang,
    Localized,
    OfferSource,
    RequestedUnit,
    StrictModel,
)
from .quote import (
    Clarification,
    DeliverySummary,
    Flag,
    GroupSubtotal,
    NotOrdered,
    QuoteLine,
    Rejection,
)
from .rules import RuleSet

# Limits from policy/policy.yaml `limits` (vision §8). Pydantic needs them when the
# classes are defined; the policy loader refuses a policy.yaml that differs from them.
MAX_LINES = 50
MAX_TEXT_LENGTH = 200
MAX_QUANTITY = Decimal("100000")


class RecipeRef(StrictModel):
    recipe_id: str
    portions: int
    ingredient_index: int


class LineRequest(StrictModel):
    """One structured line from the agent. The engine never sees raw speech."""

    line_id: str = Field(min_length=1, max_length=40)
    product_id: str | None = None  # when the agent already knows the product
    usual: bool = False  # "my usual butter"
    text: str | None = Field(default=None, max_length=MAX_TEXT_LENGTH)  # product words only
    claims: list[Claim] = []
    category: str | None = None  # code from data/valio_category_names.csv
    quantity: Annotated[JsonDecimal, Field(gt=0, le=MAX_QUANTITY)]
    unit: RequestedUnit
    package_word: str | None = None  # "laatikko", "case" when unit is `package`
    needed_by: date
    recipe_ref: RecipeRef | None = None
    group: str | None = Field(default=None, max_length=80)  # echoed back with a subtotal


class KitchenProfile(StrictModel):
    exclusions: list[Exclusion]


class HistoryLine(StrictModel):
    product_id: str
    quantity: JsonDecimal
    sales_unit: str
    ordered_at: datetime


class UsualItem(StrictModel):
    product_id: str
    name: Localized
    quantity: JsonDecimal
    unit: str


class HistorySummary(StrictModel):
    usual_items: list[UsualItem]
    recent_lines: list[HistoryLine]


class ProductAllergen(StrictModel):
    code: str  # GS1 AllergenTypeCode
    containment: Literal["CONTAINS", "MAY_CONTAIN", "FREE_FROM", "UNDECLARED"]


class UnitConversion(StrictModel):
    """One `from_unit` is `factor` `to_unit`s, e.g. KI = 10 ST, ST = 1 L, ST = 0.5 KG.
    Unit codes are upper case; volume is `L` and weight `KG`."""

    from_unit: str
    to_unit: str
    factor: JsonDecimal


class ProductRecord(StrictModel):
    product_id: str
    name: Localized
    category: str
    sales_unit: str
    base_unit: str | None
    units: list[str]
    unit_conversions: list[UnitConversion]
    allergens: list[ProductAllergen]
    allergen_listing: bool  # false when the product has no classifications
    claims: list[Claim]
    origin: str | None
    image_url: str | None
    substitutions: list[str]  # curated substitute ids


class ScheduleLine(StrictModel):
    available_date: date
    amount: JsonDecimal


class Offer(StrictModel):
    """Price and availability for one candidate, as fetched (live) or recorded (snapshot)."""

    product_id: str
    ok: bool  # false when price or availability couldn't be fetched
    unit_price_gross: JsonDecimal | None
    price_valid_to: date | None
    sales_unit: str | None  # from availability
    schedule: list[ScheduleLine]
    sales_block: bool
    closing_time: datetime | None
    fetched_at: datetime
    source: OfferSource


class EngineInput(StrictModel):
    lines: list[LineRequest] = Field(min_length=1, max_length=MAX_LINES)
    kitchen: KitchenProfile
    history: HistorySummary
    # Search results per line, best first (#36). Ids refer to `products`; the quote
    # service fills it, so the engine never searches.
    candidates: dict[str, list[str]]
    products: list[ProductRecord]
    offers: list[Offer]
    rules: RuleSet
    business_now: datetime  # business clock: cutoffs and delivery dates
    issued_at: datetime  # real clock
    lang: Lang


class EngineOutput(StrictModel):
    """The engine's decision. Quote id, hash, signature and expiry are added by the service."""

    decision: Decision
    lines: list[QuoteLine]
    groups: list[GroupSubtotal]
    flags: list[Flag]
    clarification: Clarification | None
    rejections: list[Rejection]
    not_ordered: list[NotOrdered]
    total_cents: int
    delivery: DeliverySummary | None
    speak: Localized
    rules_ref: str  # RuleSet.ref: version plus content hash
