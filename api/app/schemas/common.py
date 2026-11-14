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
    """Product claims, from the product file's `nutritionalClaim` group.

    lactose_free is `LACTOSE FREE_FROM` only; `LACTOSE LOW` does not count.
    """

    lactose_free = "lactose_free"
    gluten_free = "gluten_free"
    vegan = "vegan"
    vegetarian = "vegetarian"


class Exclusion(StrEnum):
    """Kitchen exclusions: the keys of `policy/allergen_rules.yaml`."""

    milk_free = "milk_free"
    lactose_free = "lactose_free"
    gluten_free = "gluten_free"
    nut_free = "nut_free"
    egg_free = "egg_free"
    fish_free = "fish_free"
    vegan = "vegan"


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
    """Quote lifecycle (technical-plan.md §8.1).

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
