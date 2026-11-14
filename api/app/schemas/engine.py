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
    """A line from a recipe (#34). Without `ingredient_index` the line is the whole recipe:
    the quote service turns it into one line per ingredient with a product link and lists
    the other ingredients in `not_ordered`.

    `order_unlinked` (#103) also orders the ingredients without a product, when the buyer
    asked for them: each one with an amount becomes a line found by the ingredient's name,
    and it leaves `not_ordered`. On an ingredient line it keeps that line ordered by name."""

    recipe_id: str
    portions: int = Field(ge=1, le=1000)
    ingredient_index: int | None = None
    order_unlinked: bool = False


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


class RecipeDraftRef(StrictModel):
    """A confirmed recipe draft that some of the lines came from (#80).

    The engine doesn't read it. The quote service stores it with the input, so the quote's
    hash and replay cover exactly what the buyer confirmed (`confirmed_hash`), and labels
    the draft's group from it. Its unticked ingredients (`not_ordered`) also go into the
    input's `not_ordered`; they are kept here so an edit of the quote keeps them.
    """

    draft_id: str
    confirmed_hash: str
    group: str
    not_ordered: list[NotOrdered] = []


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
    # Gross price per `comparison_unit` (L or KG). Unit price ÷ this = litres or kilos in one
    # sales unit, which cross-checks the sales unit (#38). None when the API has none.
    comparison_price_gross: JsonDecimal | None = None
    comparison_unit: str | None = None
    sales_unit: str | None  # from availability
    schedule: list[ScheduleLine]
    sales_block: bool
    closing_time: datetime | None
    fetched_at: datetime
    source: OfferSource


class EngineInput(StrictModel):
    lines: list[LineRequest] = Field(min_length=1, max_length=MAX_LINES)
    # The exclusions that apply to this quote: the kitchen profile's and the order's own.
    kitchen: KitchenProfile
    # The part of them the buyer asked for this order only (#102), kept apart so an
    # update can carry them on and a page can tell them from the kitchen profile.
    order_exclusions: list[Exclusion] = []
    history: HistorySummary
    # Search results per line, best first (#36). Ids refer to `products`; the quote
    # service fills it, so the engine never searches.
    candidates: dict[str, list[str]]
    # The substitute candidates among `candidates`, per line (#39): curated pairs and
    # alternatives the quote service added after the search hits. They are only used
    # when the line can't be filled from the other candidates.
    substitutes: dict[str, list[str]] = {}
    products: list[ProductRecord]
    offers: list[Offer]
    rules: RuleSet
    business_now: datetime  # business clock: cutoffs and delivery dates
    issued_at: datetime  # real clock
    lang: Lang
    # Recipe ingredients without a product link (#34). The quote service lists them and
    # the engine returns them as they are, so a stored input replays to the same output.
    not_ordered: list[NotOrdered] = []
    # Confirmed recipe drafts the lines came from; not used by the engine (#80).
    recipe_drafts: list[RecipeDraftRef] = []


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
