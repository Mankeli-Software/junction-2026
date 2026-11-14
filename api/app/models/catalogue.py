"""Catalogue tables, loaded from the static product file (#29, technical-plan.md §5.2).

The search columns are filled by the SQL function refresh_product_search() (#30).
Product images come from our portal crawl, data/product_images.json.gz (#108).
"""

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Numeric, SmallInteger, Text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

CONTAINMENTS = ("CONTAINS", "MAY_CONTAIN", "FREE_FROM", "UNDECLARED")
IMAGE_MATCHES = ("gtin", "name")


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name_en: Mapped[str] = mapped_column(Text)
    name_fi: Mapped[str] = mapped_column(Text)
    name_fi_source: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    shop_path_fi: Mapped[str | None] = mapped_column(Text)
    mandate_group: Mapped[str] = mapped_column(Text)


class AllergenCode(Base):
    __tablename__ = "allergen_codes"

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    gs1_label: Mapped[str] = mapped_column(Text)
    gs1_uri: Mapped[str] = mapped_column(Text)
    eu_group: Mapped[str | None] = mapped_column(Text)
    name_fi: Mapped[str | None] = mapped_column(Text)
    name_fi_partitive: Mapped[str | None] = mapped_column(Text)
    voice_note_fi: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)


class Product(Base):
    __tablename__ = "products"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name_fi: Mapped[str] = mapped_column(Text)
    name_en: Mapped[str | None] = mapped_column(Text)
    name_sv: Mapped[str | None] = mapped_column(Text)
    category_id: Mapped[str] = mapped_column(ForeignKey("categories.id"), index=True)
    # As in the file. The availability response wins where they differ (#31).
    sales_unit: Mapped[str] = mapped_column(Text)
    base_unit: Mapped[str] = mapped_column(Text)
    sales_unit_gtin: Mapped[str | None] = mapped_column(Text)
    synkka_gtin: Mapped[str | None] = mapped_column(Text)
    allowed_lot_size: Mapped[Decimal] = mapped_column(Numeric)
    temperature_condition: Mapped[int | None] = mapped_column(SmallInteger)
    min_temperature: Mapped[Decimal | None] = mapped_column(Numeric)
    max_temperature: Mapped[Decimal | None] = mapped_column(Numeric)
    variable_unit: Mapped[bool | None] = mapped_column(Boolean)
    vendor_name: Mapped[str] = mapped_column(Text)
    brand: Mapped[str | None] = mapped_column(Text)
    country_of_origin: Mapped[str | None] = mapped_column(Text)
    # False for products with no classifications at all: no allergen listing.
    has_classifications: Mapped[bool] = mapped_column(Boolean)
    source_updated_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    raw: Mapped[dict[str, Any]] = mapped_column(JSONB)
    loaded_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))
    # Filled by refresh_product_search() at the end of every catalogue load (#30).
    search_fi: Mapped[str | None] = mapped_column(TSVECTOR, deferred=True)
    search_en: Mapped[str | None] = mapped_column(TSVECTOR, deferred=True)
    search_trgm: Mapped[str | None] = mapped_column(Text, deferred=True)


def _product_fk() -> Any:
    return mapped_column(ForeignKey("products.id", ondelete="CASCADE"), primary_key=True)


class ProductUnit(Base):
    __tablename__ = "product_units"

    product_id: Mapped[str] = _product_fk()
    unit_id: Mapped[str] = mapped_column(Text, primary_key=True)
    size_in_base_units: Mapped[Decimal] = mapped_column(Numeric)
    gtin: Mapped[str | None] = mapped_column(Text)
    is_sales_unit: Mapped[bool] = mapped_column(Boolean)
    is_base_unit: Mapped[bool] = mapped_column(Boolean)


class ProductUnitConversion(Base):
    """Weight, volume and size of one packaging level. The file has at most one per product."""

    __tablename__ = "product_unit_conversions"

    product_id: Mapped[str] = _product_fk()
    packaging_type: Mapped[str] = mapped_column(Text, primary_key=True)
    # The unit this row describes; null when the loader could not tell.
    unit_id: Mapped[str | None] = mapped_column(Text)
    net_weight_g: Mapped[Decimal | None] = mapped_column(Numeric)
    gross_weight_g: Mapped[Decimal | None] = mapped_column(Numeric)
    # Synkka's `volume` is the net content: millilitres, grams or pieces by its unit.
    volume_ml: Mapped[Decimal | None] = mapped_column(Numeric)
    content_weight_g: Mapped[Decimal | None] = mapped_column(Numeric)
    content_pieces: Mapped[Decimal | None] = mapped_column(Numeric)
    width_mm: Mapped[Decimal | None] = mapped_column(Numeric)
    length_mm: Mapped[Decimal | None] = mapped_column(Numeric)
    height_mm: Mapped[Decimal | None] = mapped_column(Numeric)
    raw: Mapped[dict[str, Any]] = mapped_column(JSONB)


class ProductAllergen(Base):
    __tablename__ = "product_allergens"
    __table_args__ = (
        CheckConstraint(
            "containment IN ('CONTAINS', 'MAY_CONTAIN', 'FREE_FROM', 'UNDECLARED')",
            name="containment",
        ),
    )

    product_id: Mapped[str] = _product_fk()
    code: Mapped[str] = mapped_column(
        ForeignKey("allergen_codes.code"), primary_key=True, index=True
    )
    containment: Mapped[str] = mapped_column(Text, primary_key=True)


class ProductClaim(Base):
    __tablename__ = "product_claims"

    product_id: Mapped[str] = _product_fk()
    claim_id: Mapped[str] = mapped_column(Text, primary_key=True, index=True)  # FREE_FROM_LACTOSE
    qualifier: Mapped[str] = mapped_column(Text, primary_key=True)  # FREE_FROM, DIET, LOW, …
    synkka_id: Mapped[str | None] = mapped_column(Text)  # LACTOSE


class ProductLabel(Base):
    __tablename__ = "product_labels"
    __table_args__ = (CheckConstraint("kind IN ('temperature', 'certificate')", name="kind"),)

    product_id: Mapped[str] = _product_fk()
    label_id: Mapped[str] = mapped_column(Text, primary_key=True)
    kind: Mapped[str] = mapped_column(Text)


class ProductSubstitution(Base):
    __tablename__ = "product_substitutions"

    product_id: Mapped[str] = _product_fk()
    substitute_product_id: Mapped[str] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    position: Mapped[int] = mapped_column(SmallInteger)


class ProductImage(Base):
    """Valio's own main image URL for a product, hotlinked (#108, technical-plan.md §5.5).

    Its own table because it comes from another source than the product file (our portal
    crawl joined by barcode) and is refreshed on its own (app.loaders.images). A product
    with no row has no image and the clients show the placeholder.
    """

    __tablename__ = "product_images"
    __table_args__ = (CheckConstraint("image_match IN ('gtin', 'name')", name="image_match"),)

    product_id: Mapped[str] = _product_fk()
    image_url: Mapped[str] = mapped_column(Text)
    # gtin: joined by barcode; name: by the exact normalised Finnish name (166 products).
    image_match: Mapped[str] = mapped_column(Text)
