"""Codes the engine emits. Every code has a Finnish and an English template in
policy/messages.yaml, and the policy loader refuses a rule set where they differ."""

from enum import StrEnum


class ReasonCode(StrEnum):
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


class KitchenChoice(StrEnum):
    """Allergen and diet exclusions a kitchen can pick (docs/specs/call-screen.md §2.2)."""

    MILK_FREE = "milk_free"
    LACTOSE_FREE = "lactose_free"
    GLUTEN_FREE = "gluten_free"
    NUT_FREE = "nut_free"
    EGG_FREE = "egg_free"
    FISH_FREE = "fish_free"
    VEGAN = "vegan"


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
