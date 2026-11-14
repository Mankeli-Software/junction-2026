"""Recipe tables, loaded from data/valio-recipes.json and data/recipe-product-map.json (#34,
technical-plan.md §5.2, §5.4).

The search columns are filled by the recipe loader. recipe_embeddings has no model: like
product_embeddings it is read and written with SQL only (app.recipes.search, the loader).
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, SmallInteger, Text
from sqlalchemy.dialects.postgresql import TIMESTAMP, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Recipe(Base):
    __tablename__ = "recipes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    slug: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)  # Finnish, the data has no English
    description: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(Text)
    default_portions: Mapped[int] = mapped_column(Integer)
    portion_unit: Mapped[str] = mapped_column(Text)  # mostly "annosta" or "kpl"
    default_portion_weight_g: Mapped[int | None] = mapped_column(Integer)
    difficulty: Mapped[int | None] = mapped_column(SmallInteger)
    is_inhouse: Mapped[bool] = mapped_column(Boolean)
    loaded_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))
    # Name, tags, ingredients and description, weighted (loader).
    search_fi: Mapped[str | None] = mapped_column(TSVECTOR, deferred=True)
    # Folded name and ingredient names, for trigram matches inside compounds.
    search_trgm: Mapped[str | None] = mapped_column(Text, deferred=True)


class RecipeIngredient(Base):
    """One ingredient row. `position` counts across the recipe's ingredient segments, and is
    the `ingredient_index` of get_recipe and RecipeRef."""

    __tablename__ = "recipe_ingredients"

    recipe_id: Mapped[int] = mapped_column(
        ForeignKey("recipes.id", ondelete="CASCADE"), primary_key=True
    )
    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    segment: Mapped[str | None] = mapped_column(Text)  # section heading, e.g. "Taikina"
    name: Mapped[str] = mapped_column(Text)  # as written, Finnish partitive
    # Amount for one portion, in `unit` (always kg in the data); null for "to taste".
    amount_per_portion: Mapped[Decimal | None] = mapped_column(Numeric)
    unit: Mapped[str | None] = mapped_column(Text)
    suffix: Mapped[str | None] = mapped_column(Text)  # ", maun mukaan"
    # The recipe data's own product id; recipe_product_links maps it to catalogue products.
    recipe_product_id: Mapped[int | None] = mapped_column(Integer, index=True)


class RecipeTag(Base):
    """One taxonomy value: "erityisruokavaliot=laktoositon" is group diet, value laktoositon."""

    __tablename__ = "recipe_tags"

    recipe_id: Mapped[int] = mapped_column(
        ForeignKey("recipes.id", ondelete="CASCADE"), primary_key=True
    )
    tag: Mapped[str] = mapped_column(Text, primary_key=True)
    tag_group: Mapped[str] = mapped_column(Text)  # diet, occasion, dishType, ...
    value: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)  # Finnish label


class RecipeProductLink(Base):
    """A recipe product and one catalogue product (one pack size) it maps to. No foreign key
    to products: the map may name products a partial catalogue doesn't have."""

    __tablename__ = "recipe_product_links"

    recipe_product_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    product_id: Mapped[str] = mapped_column(Text, primary_key=True)
    recipe_product_name: Mapped[str] = mapped_column(Text)
    product_name: Mapped[str] = mapped_column(Text)
    sales_unit: Mapped[str] = mapped_column(Text)
    base_unit: Mapped[str] = mapped_column(Text)
    units_per_sales_unit: Mapped[Decimal] = mapped_column(Numeric)
    net_weight_kg: Mapped[Decimal | None] = mapped_column(Numeric)  # one base unit
    weight_source: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[str] = mapped_column(Text)
    pack_hint: Mapped[str | None] = mapped_column(Text)  # "sanko": the recipe means a bulk pack
