"""Request and response models for the agent tools (vision §8, technical-plan.md §9.1).

No tool response ever carries the confirmation token or link (technical-plan.md §9).
"""

from datetime import date, datetime
from typing import Literal

from pydantic import Field, model_validator

from .common import (
    Claim,
    Exclusion,
    JsonDecimal,
    KitchenType,
    Lang,
    Localized,
    QuoteStatus,
    StockStatus,
    StrictModel,
)
from .engine import MAX_LINES, EngineOutput, LineRequest, UsualItem

# search_products


class SearchProductsRequest(StrictModel):
    q: str
    claims: list[Claim] = []
    category: str | None = None
    needed_by: date | None = None
    limit: int = Field(default=10, ge=1, le=20)


class ProductHit(StrictModel):
    product_id: str
    name: Localized
    category: str
    sales_unit: str
    sales_unit_label: Localized
    image_url: str | None
    unit_price_gross: JsonDecimal | None
    price_per_base_unit: JsonDecimal | None
    base_unit: str | None
    stock_status: StockStatus
    available_date: date | None
    origin: str | None


class SearchProductsResponse(StrictModel):
    results: list[ProductHit]


# get_customer_context (no request arguments)


class ExclusionLabel(StrictModel):
    key: Exclusion
    label: Localized


class CustomerContext(StrictModel):
    company_name: str
    phone_masked: str  # "+358 40 *** **12"
    exclusions: list[ExclusionLabel]
    usual_items: list[UsualItem]
    lang: Lang
    kitchen_type: KitchenType | None = None  # what kind of kitchen this is (#32)
    last_order: list[UsualItem] = []  # the latest order, for "the same as last time"


# search_recipes


class SearchRecipesRequest(StrictModel):
    q: str
    diet: list[str] = []
    occasion: str | None = None
    limit: int = Field(default=10, ge=1, le=20)


class RecipeHit(StrictModel):
    recipe_id: str
    name: str  # Finnish, the recipe data has no English
    image_url: str | None
    default_portions: int
    diet_tags: list[str]


class SearchRecipesResponse(StrictModel):
    results: list[RecipeHit]


# get_recipe


class GetRecipeRequest(StrictModel):
    recipe_id: str
    portions: int = Field(ge=1, le=1000)


class RecipeIngredient(StrictModel):
    index: int
    name: str
    quantity: JsonDecimal | None
    unit: str | None
    product_id: str | None  # only when recipe-product-map.json links it


class Recipe(StrictModel):
    recipe_id: str
    name: str
    image_url: str | None
    portions: int
    ingredients: list[RecipeIngredient]


# build_quote and update_quote


class BuildQuoteRequest(StrictModel):
    """The order's lines. With `recipe_draft_id`, a confirmed recipe draft's ingredients
    are added as lines too, so `lines` may then be empty."""

    lines: list[LineRequest] = Field(default=[], max_length=MAX_LINES)
    recipe_draft_id: str | None = None
    # When the draft's lines are needed by. Default: the earliest needed_by of `lines`,
    # or else the next weekday.
    needed_by: date | None = None

    @model_validator(mode="after")
    def _lines_or_draft(self) -> "BuildQuoteRequest":
        if not self.lines and self.recipe_draft_id is None:
            raise ValueError("give at least one line or a recipe_draft_id")
        return self


class UpdateQuoteRequest(StrictModel):
    """The full new line list. Keep `line_id`s for unchanged lines.

    Answering a clarification is sending the line again with the chosen `product_id`.
    """

    quote_id: str
    lines: list[LineRequest] = Field(min_length=1, max_length=MAX_LINES)


class QuoteResponse(EngineOutput):
    """The engine's decision plus the quote id, version, status, expiry and hash."""

    quote_id: str
    version: int
    parent_quote_id: str | None
    status: QuoteStatus
    expires_at: datetime | None  # null during the event
    quote_hash: str | None  # only when `ready`


# request_confirmation


class RequestConfirmationRequest(StrictModel):
    """No recipient argument: the confirmation link goes to the account's own phone."""

    quote_id: str


class ConfirmationRequestResponse(StrictModel):
    sent_to_masked: str
    delivery_status: Literal["held", "sent", "failed", "off"]  # held on the phone until hang-up
    inbox: bool


# get_order_status


class GetOrderStatusRequest(StrictModel):
    quote_id: str


class OrderStatusResponse(StrictModel):
    quote_id: str
    status: QuoteStatus
    order_number: str | None
    replaced_by_quote_id: str | None
