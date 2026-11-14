"""The engine rule set (technical-plan.md §4.3, #35).

Built by `app.services.policy` from `policy/` and two files in `data/`, and handed
to the engine in `EngineInput.rules`. The engine never reads the files itself.
"""

from enum import StrEnum
from typing import Literal

from pydantic import AwareDatetime, ConfigDict, Field

from .common import Exclusion, JsonDecimal, Localized, StrictModel


class ReasonCode(StrEnum):
    """Codes the engine emits. Each has a Finnish and an English template in
    policy/messages.yaml; the loader refuses a rule set where the two differ."""

    # Validate and resolve
    INPUT_INVALID = "INPUT_INVALID"
    PRODUCT_NOT_FOUND = "PRODUCT_NOT_FOUND"
    NO_MATCH = "NO_MATCH"
    AMBIGUOUS_MATCH = "AMBIGUOUS_MATCH"
    USUAL_NOT_FOUND = "USUAL_NOT_FOUND"
    # Allergens and diet
    ALLERGEN_CONFLICT = "ALLERGEN_CONFLICT"
    DIET_CLAIM_MISSING = "DIET_CLAIM_MISSING"
    ALLERGEN_NO_LISTING = "ALLERGEN_NO_LISTING"
    # Availability and dates
    UNAVAILABLE = "UNAVAILABLE"
    DELIVERY_DATE_UNREACHABLE = "DELIVERY_DATE_UNREACHABLE"
    PAST_CLOSING_TIME = "PAST_CLOSING_TIME"
    PARTIAL_STOCK = "PARTIAL_STOCK"
    AVAILABILITY_UNVERIFIED = "AVAILABILITY_UNVERIFIED"
    OFFER_UNAVAILABLE = "OFFER_UNAVAILABLE"
    PRICE_NOT_VALID = "PRICE_NOT_VALID"
    # Units and rounding
    UNIT_UNKNOWN = "UNIT_UNKNOWN"
    UNIT_CONVERSION_UNKNOWN = "UNIT_CONVERSION_UNKNOWN"
    PACKAGING_AMBIGUOUS = "PACKAGING_AMBIGUOUS"
    PACK_SIZE_FROM_NAME = "PACK_SIZE_FROM_NAME"
    ROUNDED_UP = "ROUNDED_UP"
    EXACT_FIT_ALTERNATIVE = "EXACT_FIT_ALTERNATIVE"
    # Substitution
    SUBSTITUTED_PACK_SIZE = "SUBSTITUTED_PACK_SIZE"
    SUBSTITUTED_CURATED = "SUBSTITUTED_CURATED"
    SUBSTITUTE_SUGGESTED = "SUBSTITUTE_SUGGESTED"
    SUBSTITUTE_PRICE_TOO_HIGH = "SUBSTITUTE_PRICE_TOO_HIGH"
    CALLBACK_REQUESTED = "CALLBACK_REQUESTED"
    # Sanity checks (P1, never blocking)
    QUANTITY_UNUSUAL = "QUANTITY_UNUSUAL"
    DUPLICATE_ORDER = "DUPLICATE_ORDER"
    FIRST_TIME_PRODUCT = "FIRST_TIME_PRODUCT"


class Containment(StrEnum):
    """How a product lists an allergen (data/allergen_containment_levels.csv)."""

    CONTAINS = "CONTAINS"
    MAY_CONTAIN = "MAY_CONTAIN"
    FREE_FROM = "FREE_FROM"
    UNDECLARED = "UNDECLARED"
    NO_LISTING = "NO_LISTING"


# Placeholders a message template may use. The loader rejects any other name.
TEMPLATE_FIELDS = frozenset(
    {
        "product",
        "products",
        "quantity",
        "unit",
        "available",
        "date",
        "allergen",
        "allergen_fi",
        "containment_en",
        "containment_fi",
        "choice",
        "substitute",
        "percent",
    }
)


class _Frozen(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Rounding(_Frozen):
    max_overage_units: int = Field(ge=0)
    max_overage_ratio: JsonDecimal = Field(ge=0)


class Substitution(_Frozen):
    max_price_increase_ratio: JsonDecimal = Field(ge=0)


class Limits(_Frozen):
    max_lines: int = Field(gt=0)
    max_text_length: int = Field(gt=0)
    max_quantity: JsonDecimal = Field(gt=0)


class Policy(_Frozen):
    """policy/policy.yaml, with the same names and units."""

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


class ClaimRule(_Frozen):
    """A `nutritionalClaim` entry, e.g. LACTOSE FREE_FROM. No level means any level."""

    code: str = Field(min_length=1)
    level: str | None = None


class ClaimException(_Frozen):
    codes: tuple[str, ...] = Field(min_length=1)
    claim: tuple[ClaimRule, ...] = Field(min_length=1)


class KitchenRule(_Frozen):
    """One kitchen choice in policy/allergen_rules.yaml."""

    label: Localized
    block: tuple[str, ...] = ()
    block_unless_claim: ClaimException | None = None
    require_claim: tuple[ClaimRule, ...] = ()


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


class RuleSet(_Frozen):
    version: str
    # sha256 over every source file, so an edit without a version bump still changes it.
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    policy: Policy
    kitchen: dict[Exclusion, KitchenRule]
    messages: dict[ReasonCode, Message]
    containment: dict[Containment, Localized]
    units: dict[str, UnitName]
    allergens: dict[str, AllergenName]

    @property
    def ref(self) -> str:
        """The identifier stored with every quote and included in its hash (#40)."""
        return f"{self.version}+sha256:{self.content_hash}"
