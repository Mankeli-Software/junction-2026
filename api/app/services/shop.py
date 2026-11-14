"""The webshop's public catalogue (#118): the category tree and each leaf's top products.

The tree is the Valio Aimo shop path of each category (`categories.shop_path_fi`): its first
two steps are the section and the group, and the category itself is the leaf. English names
for the sections and groups come from `data/shop_sections.csv`, whose row order is the
shop's order. A category without a shop path goes under "Other products".

Only products with a Valio image are listed, at most `TOP` per category. "Top" is
deterministic, because the product file has no sales data: products in more of the seeded
order histories first, then those more recipes link to, then Valio's own, then by name.
"""

import csv
import re
from dataclasses import dataclass
from functools import cache

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Category,
    Product,
    ProductImage,
    ProductUnit,
    RecipeIngredient,
    RecipeProductLink,
)
from app.schemas import (
    Localized,
    ShopCatalogue,
    ShopCategory,
    ShopGroup,
    ShopProduct,
    ShopProducts,
    ShopSection,
)
from app.seed.history import kitchen_types
from app.services.errors import NotFoundError
from app.settings import REPO_ROOT

SECTIONS_FILE = REPO_ROOT / "data" / "shop_sections.csv"
TOP = 20
OTHER = "Muut tuotteet"
SEPARATOR = " > "
# A pack size in a Finnish product name: "1 l", "1,5 kg", "e5 kg" (each 5 kg).
PACK_SIZE = re.compile(r"(?<![\w,])e?(\d+(?:,\d+)?)\s?(kg|g|dl|l)\b")


@cache
def _section_names() -> dict[str, str]:
    """English name of each section and group path, in the shop's order."""
    with SECTIONS_FILE.open(encoding="utf-8") as f:
        return {row["path_fi"]: row["name_en"] for row in csv.DictReader(f)}


def _localized(path: str) -> Localized:
    return Localized(fi=path.split(SEPARATOR)[-1], en=_section_names().get(path, path))


@dataclass(frozen=True)
class _Place:
    section: str  # Finnish path of the section
    group: str  # Finnish path of the group


def _place(shop_path_fi: str | None) -> _Place:
    steps = shop_path_fi.split(SEPARATOR) if shop_path_fi else []
    if len(steps) < 2:
        return _Place(OTHER, f"{OTHER}{SEPARATOR}{OTHER}")
    return _Place(steps[0], SEPARATOR.join(steps[:2]))


def _order(path: str) -> tuple[int, str]:
    """The shop's order: the file's row order, unknown paths last by name."""
    names = list(_section_names())
    return (names.index(path), "") if path in names else (len(names), path)


async def _counts(db: AsyncSession) -> dict[str, int]:
    rows = await db.execute(
        select(Product.category_id, func.count())
        .join(ProductImage, ProductImage.product_id == Product.id)
        .group_by(Product.category_id)
    )
    return {category_id: min(n, TOP) for category_id, n in rows.all()}


def _category(row: Category, count: int) -> ShopCategory:
    return ShopCategory(
        id=row.id, name=Localized(fi=row.name_fi, en=row.name_en), product_count=count
    )


async def load_catalogue(db: AsyncSession) -> ShopCatalogue:
    """Every section, group and category with at least one product to show."""
    counts = await _counts(db)
    tree: dict[str, dict[str, list[ShopCategory]]] = {}
    for row in await db.scalars(select(Category).order_by(Category.id)):
        if not counts.get(row.id):
            continue
        place = _place(row.shop_path_fi)
        groups = tree.setdefault(place.section, {})
        groups.setdefault(place.group, []).append(_category(row, counts[row.id]))
    return ShopCatalogue(
        sections=[
            ShopSection(
                name=_localized(section),
                groups=[
                    ShopGroup(name=_localized(group), categories=categories)
                    for group, categories in sorted(groups.items(), key=lambda g: _order(g[0]))
                ],
            )
            for section, groups in sorted(tree.items(), key=lambda s: _order(s[0]))
        ]
    )


@cache
def _history_counts() -> dict[str, int]:
    """In how many kitchen types' seeded order history each product is."""
    counts: dict[str, int] = {}
    for spec in kitchen_types().values():
        for product_id in {item.product_id for item in spec.items}:
            counts[product_id] = counts.get(product_id, 0) + 1
    return counts


def _is_valio(brand: str | None, vendor: str) -> bool:
    return any((name or "").casefold().startswith("valio") for name in (brand, vendor))


def _pack_size(name_fi: str) -> str | None:
    size = PACK_SIZE.search(name_fi)
    return f"{size.group(1)} {size.group(2)}" if size else None


def _recipe_uses():
    """How many recipes link to each product."""
    return (
        select(
            RecipeProductLink.product_id,
            func.count(func.distinct(RecipeIngredient.recipe_id)).label("n"),
        )
        .join(
            RecipeIngredient,
            RecipeIngredient.recipe_product_id == RecipeProductLink.recipe_product_id,
        )
        .group_by(RecipeProductLink.product_id)
        .subquery()
    )


async def load_products(db: AsyncSession, category_id: str) -> ShopProducts:
    """The category's top products with an image, best first. Unknown id: NotFoundError."""
    category = await db.get(Category, category_id)
    if category is None:
        raise NotFoundError(f"No category {category_id}.")
    recipe_uses = _recipe_uses()
    rows = (
        await db.execute(
            select(
                Product.id,
                Product.name_fi,
                Product.name_en,
                Product.brand,
                Product.vendor_name,
                Product.sales_unit,
                ProductImage.image_url,
                ProductUnit.size_in_base_units,
                func.coalesce(recipe_uses.c.n, 0),
            )
            .join(ProductImage, ProductImage.product_id == Product.id)
            .outerjoin(
                ProductUnit,
                and_(
                    ProductUnit.product_id == Product.id,
                    ProductUnit.unit_id == Product.sales_unit,
                ),
            )
            .outerjoin(recipe_uses, recipe_uses.c.product_id == Product.id)
            .where(Product.category_id == category_id)
        )
    ).all()
    history = _history_counts()
    rows = sorted(
        rows,
        key=lambda r: (
            -history.get(r.id, 0),
            -r[-1],
            not _is_valio(r.brand, r.vendor_name),
            r.name_fi.casefold(),
            r.id,
        ),
    )[:TOP]
    place = _place(category.shop_path_fi)
    return ShopProducts(
        section=_localized(place.section),
        group=_localized(place.group),
        category=_category(category, len(rows)),
        products=[
            ShopProduct(
                product_id=r.id,
                name=Localized(fi=r.name_fi, en=r.name_en or r.name_fi),
                brand=r.brand,
                pack_size=_pack_size(r.name_fi),
                sales_unit=r.sales_unit,
                units_per_sales_unit=int(r.size_in_base_units or 1),
                image_url=r.image_url,
            )
            for r in rows
        ],
    )
