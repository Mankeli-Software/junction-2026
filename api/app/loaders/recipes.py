"""Loads the recipes, their product links and their vectors into Postgres (#34).

    uv run python -m app.loaders.recipes [--no-embeddings]

Reads data/valio-recipes.json, data/recipe-product-map.json and the committed vectors in
data/recipe-embeddings.json.gz; never calls an API. Runs in one transaction and can be
re-run: recipes are upserted, each loaded recipe's ingredients and tags are replaced, the
product links are replaced as a whole, and recipes no longer in the file are deleted
(nothing refers to them: a quote keeps its own copy of the lines). A vector is loaded only
when it was made from the recipe's current text; the others are reported, and
`python -m app.recipes.embeddings` makes them again.

Independent of the catalogue: links name catalogue product ids without a foreign key, so
the order of the two loaders doesn't matter.
"""

import argparse
import asyncio
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from app.db import get_engine
from app.loaders.catalogue import _insert, _upsert
from app.models import Recipe, RecipeIngredient, RecipeProductLink, RecipeTag
from app.recipes import data as files
from app.search.vectors import MODEL, vector_literal

BATCH_SIZE = 500

# Name first, then tags and ingredients, then the description (technical-plan.md §5.4).
REFRESH_SEARCH = text(
    """
    UPDATE recipes r SET
        search_fi = setweight(to_tsvector('finnish', r.name), 'A')
            || setweight(to_tsvector('finnish', coalesce(t.titles, '')), 'B')
            || setweight(to_tsvector('finnish', coalesce(i.names, '')), 'B')
            || setweight(to_tsvector('finnish', coalesce(r.description, '')), 'C'),
        search_trgm = immutable_unaccent(lower(r.name || ' ' || coalesce(i.names, '')))
    FROM recipes r2
    LEFT JOIN (SELECT recipe_id, string_agg(title, ' ' ORDER BY tag) AS titles
               FROM recipe_tags GROUP BY recipe_id) t ON t.recipe_id = r2.id
    LEFT JOIN (SELECT recipe_id, string_agg(name, ' ' ORDER BY position) AS names
               FROM recipe_ingredients GROUP BY recipe_id) i ON i.recipe_id = r2.id
    WHERE r.id = r2.id
    """
)

UPSERT_EMBEDDING = text(
    """
    INSERT INTO recipe_embeddings (recipe_id, model, source_hash, embedding)
    VALUES (:recipe_id, :model, :source_hash, CAST(:embedding AS vector))
    ON CONFLICT (recipe_id) DO UPDATE SET model = excluded.model,
        source_hash = excluded.source_hash, embedding = excluded.embedding
    """
)


@dataclass
class LoadResult:
    counts: dict[str, int] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


def _amount(values: list[float]) -> Decimal | None:
    # str() keeps the float's shortest form: 0.19444444444444445, not 50 binary digits.
    return Decimal(str(values[0])) if values else None


def recipe_rows(
    recipes: list[dict[str, Any]], taxonomies: dict[str, Any], loaded_at: datetime
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    rows, ingredients, tags = [], [], []
    for r in recipes:
        rows.append(
            {
                "id": r["id"],
                "slug": r["slug"],
                "name": r["name"],
                "description": r.get("description"),
                "url": r["url"],
                "image_url": files.image_url(r),
                "default_portions": r["defaultPortions"],
                "portion_unit": r["portionUnit"],
                "default_portion_weight_g": r.get("defaultPortionWeight"),
                "difficulty": r.get("difficulty"),
                "is_inhouse": bool(r.get("isInhouse")),
                "loaded_at": loaded_at,
            }
        )
        for position, (segment, i) in enumerate(files.ingredients(r)):
            ingredients.append(
                {
                    "recipe_id": r["id"],
                    "position": position,
                    "segment": segment,
                    "name": i["name"],
                    "amount_per_portion": _amount(i["singlePortionAmounts"]),
                    "unit": files.unit(i["portionFormat"]),
                    "suffix": i.get("suffix"),
                    "recipe_product_id": i.get("productId"),
                }
            )
        tags += [
            {
                "recipe_id": r["id"],
                "tag": t.tag,
                "tag_group": t.group,
                "value": t.value,
                "title": t.title,
            }
            for t in files.tags(r, taxonomies)
        ]
    return rows, ingredients, tags


def link_rows(mappings: dict[str, Any]) -> list[dict[str, Any]]:
    """One row per recipe product and catalogue pack. not_in_catalog entries have none."""
    rows = []
    for key, m in sorted(mappings.items(), key=lambda kv: int(kv[0])):
        for p in m["aimoProducts"]:
            rows.append(
                {
                    "recipe_product_id": int(key),
                    "product_id": str(p["id"]),
                    "recipe_product_name": m["recipeProductName"],
                    "product_name": p["name"],
                    "sales_unit": p["salesUnit"],
                    "base_unit": p["baseUnit"],
                    "units_per_sales_unit": Decimal(str(p["unitsPerSalesUnit"])),
                    "net_weight_kg": (
                        Decimal(str(p["netWeightKg"])) if p.get("netWeightKg") else None
                    ),
                    "weight_source": p.get("weightSource"),
                    "confidence": m["confidence"],
                    "pack_hint": m.get("packHint"),
                }
            )
    return rows


async def _replace(conn: AsyncConnection, model: Any, ids: list[int], rows: list[dict]) -> None:
    table = model.__table__
    for start in range(0, len(ids), BATCH_SIZE):
        batch = ids[start : start + BATCH_SIZE]
        await conn.execute(delete(table).where(table.c.recipe_id.in_(batch)))
    await _insert(conn, table, rows)


async def load(
    engine: AsyncEngine,
    recipe_file: dict[str, Any],
    mappings: dict[str, Any],
    vectors: dict[int, files.StoredVector] | None,
) -> LoadResult:
    """vectors None leaves recipe_embeddings as it is."""
    result = LoadResult()
    recipes = recipe_file["recipes"]
    taxonomies = recipe_file["taxonomies"]
    rows, ingredients, tags = recipe_rows(recipes, taxonomies, datetime.now(UTC))
    links = link_rows(mappings)
    ids = sorted(r["id"] for r in rows)
    if len(ids) != len(set(ids)):
        raise ValueError("the recipe file has duplicate recipe ids")

    async with engine.begin() as conn:
        stored = set((await conn.scalars(select(Recipe.id))).all())
        stale = sorted(stored - set(ids))
        if stale:
            await conn.execute(delete(Recipe.__table__).where(Recipe.id.in_(stale)))
        await _upsert(conn, Recipe.__table__, rows)
        await _replace(conn, RecipeIngredient, ids, ingredients)
        await _replace(conn, RecipeTag, ids, tags)
        await conn.execute(delete(RecipeProductLink.__table__))
        await _insert(conn, RecipeProductLink.__table__, links)
        await conn.execute(REFRESH_SEARCH)

        loaded_vectors = 0
        if vectors is not None:
            texts = files.recipe_texts(recipes, taxonomies)
            current, outdated = [], []
            for recipe_id in ids:
                stored_vector = vectors.get(recipe_id)
                digest = files.source_hash(texts[recipe_id])
                if stored_vector is None or stored_vector.hash != digest:
                    outdated.append(recipe_id)
                    continue
                current.append(
                    {
                        "recipe_id": recipe_id,
                        "model": MODEL,
                        "source_hash": digest,
                        "embedding": vector_literal(files.decode_vector(stored_vector.vector)),
                    }
                )
            # A vector made from an older text would rank the recipe by what it used to be.
            if outdated:
                await conn.execute(
                    text("DELETE FROM recipe_embeddings WHERE recipe_id = ANY(:ids)"),
                    {"ids": outdated},
                )
                result.notes.append(
                    f"{len(outdated)} recipes have no current vector "
                    f"(e.g. {outdated[:5]}); run python -m app.recipes.embeddings"
                )
            for start in range(0, len(current), BATCH_SIZE):
                await conn.execute(UPSERT_EMBEDDING, current[start : start + BATCH_SIZE])
            loaded_vectors = len(current)

    linked = {link["recipe_product_id"] for link in links}
    with_product = [i for i in ingredients if i["recipe_product_id"] is not None]
    result.counts = {
        "recipes": len(rows),
        "ingredients": len(ingredients),
        "tags": len(tags),
        "product_links": len(links),
        "linked_ingredients": sum(i["recipe_product_id"] in linked for i in with_product),
        "embeddings": loaded_vectors,
        "deleted_recipes": len(stale),
    }
    unmapped = Counter(
        i["recipe_product_id"] for i in with_product if i["recipe_product_id"] not in linked
    )
    if unmapped:
        result.notes.append(
            f"{sum(unmapped.values())} ingredient rows name {len(unmapped)} recipe products "
            "with no catalogue product (listed as not ordered)"
        )
    return result


def report(result: LoadResult, out: Any = sys.stdout) -> None:
    print("Loaded:", file=out)
    for name, count in result.counts.items():
        print(f"  {name:<20} {count:>7}", file=out)
    for note in result.notes:
        print(f"Note: {note}", file=out)


async def _load_and_dispose(with_embeddings: bool) -> LoadResult:
    engine = get_engine()
    try:
        vectors = files.read_vector_file() if with_embeddings else None
        if with_embeddings and not vectors:
            print(f"Note: no vectors in {files.VECTOR_FILE}; search is text-only", file=sys.stderr)
        return await load(engine, files.read_recipe_file(), files.read_product_map(), vectors)
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--no-embeddings", action="store_true", help="leave recipe_embeddings as it is"
    )
    args = parser.parse_args()
    report(asyncio.run(_load_and_dispose(not args.no_embeddings)))


if __name__ == "__main__":
    main()
