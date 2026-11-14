"""Shared building blocks for the agent tool and engine contract (#26)."""

from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, PlainSerializer


class StrictModel(BaseModel):
    """Base for every contract model: unknown fields are rejected (vision §8)."""

    model_config = ConfigDict(extra="forbid")


class Localized(StrictModel):
    """The same text in Finnish and English."""

    fi: str
    en: str


Lang = Literal["fi", "en"]

# Exact decimal in Python, a plain JSON number on the wire. Arithmetic stays in Decimal.
JsonDecimal = Annotated[Decimal, PlainSerializer(float, return_type=float, when_used="json")]


class Claim(StrEnum):
    """Product claims, as the product data states them.

    `lactose_free` means a lactose-free product only; a low-lactose product does not count.
    """

    lactose_free = "lactose_free"
    gluten_free = "gluten_free"
    vegan = "vegan"
    vegetarian = "vegetarian"


class Exclusion(StrEnum):
    """Kitchen exclusions: the allergens and diets the kitchen rules out."""

    milk_free = "milk_free"
    lactose_free = "lactose_free"
    gluten_free = "gluten_free"
    nut_free = "nut_free"
    egg_free = "egg_free"
    fish_free = "fish_free"
    vegan = "vegan"


class KitchenType(StrEnum):
    """The kind of kitchen a demo company is, chosen from its phone number (#32, #61)."""

    pizza_restaurant = "pizza_restaurant"
    school_kitchen = "school_kitchen"
    lunch_restaurant = "lunch_restaurant"
    bar = "bar"
    vegan_catering = "vegan_catering"
    cafe = "cafe"
    tech_office = "tech_office"


class RequestedUnit(StrEnum):
    """The unit the buyer asked in. With `package`, the word is in `package_word`."""

    l = "l"  # noqa: E741
    kg = "kg"
    piece = "piece"
    sales_unit = "sales_unit"
    package = "package"


class Decision(StrEnum):
    ready = "ready"
    needs_clarification = "needs_clarification"
    rejected = "rejected"


class StockStatus(StrEnum):
    verified = "verified"
    unverified = "unverified"  # 999999 sentinel or Terminal
    unavailable = "unavailable"


class OfferSource(StrEnum):
    live = "live"
    snapshot = "snapshot"


class QuoteStatus(StrEnum):
    """Quote lifecycle.

    A quote starts as `ready`, `needs_clarification` or `rejected`, after the engine's
    decision. Only a `ready` quote can be sent for confirmation; the other two are
    answered or changed with `update_quote`.
    """

    ready = "ready"
    needs_clarification = "needs_clarification"
    rejected = "rejected"
    pending_confirmation = "pending_confirmation"
    confirmed = "confirmed"
    cancelled = "cancelled"
    expired = "expired"
    void = "void"
