"""The rule set the engine decides with (technical-plan.md §4.3).

Plain data, built by `app.services.policy` from `policy/` and two files in `data/`.
The engine never reads files: it gets a `RuleSet` through its input.
"""

from decimal import Decimal
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.engine.codes import Containment, KitchenChoice, ReasonCode


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Rounding(_Frozen):
    max_overage_units: int = Field(ge=0)
    max_overage_ratio: Decimal = Field(ge=0)


class Substitution(_Frozen):
    max_price_increase_ratio: Decimal = Field(ge=0)


class Limits(_Frozen):
    max_lines: int = Field(gt=0)
    max_text_length: int = Field(gt=0)
    max_quantity: Decimal = Field(gt=0)


class Policy(_Frozen):
    """policy/policy.yaml"""

    version: str = Field(min_length=1)
    confirmation: Literal["always"]
    quote_ttl_seconds: int | None = Field(default=None, gt=0)
    max_call_seconds: int = Field(gt=0)
    offer_cache_seconds: int = Field(gt=0)
    business_time: AwareDatetime
    timezone: str
    enforce_closing_time: bool
    unverified_stock_threshold: int = Field(gt=0)
    rounding: Rounding
    substitution: Substitution
    duplicate_window_seconds: int = Field(gt=0)
    limits: Limits
    call_language: Literal["auto", "fi", "en"]


class Label(_Frozen):
    fi: str = Field(min_length=1)
    en: str = Field(min_length=1)


class Claim(_Frozen):
    """A `nutritionalClaim` entry, e.g. LACTOSE FREE_FROM. No level means any level."""

    code: str = Field(min_length=1)
    level: str | None = None


class ClaimException(_Frozen):
    codes: tuple[str, ...] = Field(min_length=1)
    claim: tuple[Claim, ...] = Field(min_length=1)


class KitchenRule(_Frozen):
    """One kitchen choice in policy/allergen_rules.yaml."""

    label: Label
    block: tuple[str, ...] = ()
    block_unless_claim: ClaimException | None = None
    require_claim: tuple[Claim, ...] = ()


class Message(_Frozen):
    """One entry in policy/messages.yaml. Flags say whether the buyer must acknowledge."""

    kind: Literal["reason", "flag"]
    ack: bool | None = None
    fi: str = Field(min_length=1)
    en: str = Field(min_length=1)


class UnitName(_Frozen):
    """One row of policy/unit_codes.csv."""

    name_fi: str
    name_en: str
    name_fi_partitive: str
    name_en_plural: str


class AllergenName(_Frozen):
    """One row of data/gs1_allergen_codes.csv. X99 has no partitive form."""

    gs1_label: str
    eu_group: str | None
    name_fi: str
    name_fi_partitive: str | None


class ContainmentPhrase(_Frozen):
    fi: str
    en: str


class RuleSet(_Frozen):
    version: str
    # sha256 over every source file, so an edit without a version bump still changes it.
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    policy: Policy
    kitchen: dict[KitchenChoice, KitchenRule]
    messages: dict[ReasonCode, Message]
    containment: dict[Containment, ContainmentPhrase]
    units: dict[str, UnitName]
    allergens: dict[str, AllergenName]

    @property
    def ref(self) -> str:
        """The identifier that goes into every quote hash (#40)."""
        return f"{self.version}+sha256:{self.content_hash}"
