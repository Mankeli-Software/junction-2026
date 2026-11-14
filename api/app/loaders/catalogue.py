"""Loads the catalogue into Postgres from the static product file (#29).

    uv run python -m app.loaders.catalogue [--download] [--force] [--file PATH]

Runs in one transaction and can be re-run: categories, allergen codes and products are
upserted, and each loaded product's child rows are replaced. Products that are no longer
in the file are kept (quotes and orders may point at them) and reported.
"""

import argparse
import asyncio
import json
import sys
import urllib.request
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Table, delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from app.db import get_engine
from app.loaders.product_file import (
    Anomaly,
    parse_product,
    read_allergen_codes,
    read_categories,
)
from app.models import (
    AllergenCode,
    Category,
    Product,
    ProductAllergen,
    ProductClaim,
    ProductLabel,
    ProductSubstitution,
    ProductUnit,
    ProductUnitConversion,
)
from app.settings import REPO_ROOT, get_settings

DATA_DIR = REPO_ROOT / "data"
DEFAULT_PRODUCT_FILE = DATA_DIR / "valio-products.json"
CATEGORY_FILE = DATA_DIR / "valio_category_names.csv"
ALLERGEN_CODE_FILE = DATA_DIR / "gs1_allergen_codes.csv"
DOWNLOAD_URL = "https://junction26.valioaimo.fi/api/products/download"

BATCH_SIZE = 2000

CHILD_TABLES: dict[str, Table] = {
    "units": ProductUnit.__table__,
    "conversions": ProductUnitConversion.__table__,
    "allergens": ProductAllergen.__table__,
    "claims": ProductClaim.__table__,
    "labels": ProductLabel.__table__,
    "substitutions": ProductSubstitution.__table__,
}


@dataclass
class LoadResult:
    counts: dict[str, int] = field(default_factory=dict)
    anomalies: list[Anomaly] = field(default_factory=list)


def download(path: Path, api_key: str) -> None:
    """Fetches the product file once. Never call the API for the catalogue otherwise."""
    if not api_key:
        raise SystemExit("VALIO_API_KEY is not set")
    request = urllib.request.Request(
        DOWNLOAD_URL,
        # Cloudflare blocks Python's default User-Agent.
        headers={"X-API-Key": api_key, "User-Agent": "curl/8.4.0"},
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(".part")
    with urllib.request.urlopen(request, timeout=300) as response, partial.open("wb") as f:
        while chunk := response.read(1 << 20):
            f.write(chunk)
    partial.replace(path)


def _batches(rows: Sequence[dict[str, Any]]) -> Iterable[Sequence[dict[str, Any]]]:
    for start in range(0, len(rows), BATCH_SIZE):
        yield rows[start : start + BATCH_SIZE]


async def _upsert(conn: AsyncConnection, table: Table, rows: list[dict[str, Any]]) -> None:
    keys = [c.name for c in table.primary_key.columns]
    for batch in _batches(rows):
        statement = insert(table)
        statement = statement.on_conflict_do_update(
            index_elements=keys,
            set_={c.name: statement.excluded[c.name] for c in table.columns if c.name not in keys},
        )
        await conn.execute(statement, batch)


async def _insert(conn: AsyncConnection, table: Table, rows: list[dict[str, Any]]) -> None:
    for batch in _batches(rows):
        await conn.execute(insert(table), batch)


async def load(
    engine: AsyncEngine,
    products: list[dict[str, Any]],
    categories: list[dict[str, Any]],
    allergen_codes: list[dict[str, Any]],
) -> LoadResult:
    result = LoadResult()
    loaded_at = datetime.now(UTC)

    product_rows: list[dict[str, Any]] = []
    child_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for raw in products:
        parsed = parse_product(raw, loaded_at)
        product_rows.append(parsed.product)
        for name in CHILD_TABLES:
            child_rows[name].extend(getattr(parsed, name))
        result.anomalies.extend(parsed.anomalies)

    # Codes the foreign keys would reject: fail with a readable message instead.
    category_ids = {c["id"] for c in categories}
    codes = {c["code"] for c in allergen_codes}
    product_ids = {p["id"] for p in product_rows}
    unknown = [
        Anomaly("unknown_category", p["id"], p["category_id"])
        for p in product_rows
        if p["category_id"] not in category_ids
    ] + [
        Anomaly("unknown_allergen_code", a["product_id"], a["code"])
        for a in child_rows["allergens"]
        if a["code"] not in codes
    ]
    missing_targets = [
        s for s in child_rows["substitutions"] if s["substitute_product_id"] not in product_ids
    ]
    if unknown:
        raise ValueError(f"product file has codes the CSVs don't know: {unknown[:10]}")
    for s in missing_targets:
        result.anomalies.append(
            Anomaly("substitute_not_in_file", s["product_id"], s["substitute_product_id"])
        )
        child_rows["substitutions"].remove(s)

    async with engine.begin() as conn:
        await _upsert(conn, Category.__table__, categories)
        await _upsert(conn, AllergenCode.__table__, allergen_codes)
        await _upsert(conn, Product.__table__, product_rows)

        ids = sorted(product_ids)
        for table in CHILD_TABLES.values():
            for batch_start in range(0, len(ids), BATCH_SIZE):
                batch = ids[batch_start : batch_start + BATCH_SIZE]
                await conn.execute(delete(table).where(table.c.product_id.in_(batch)))
        for name, table in CHILD_TABLES.items():
            await _insert(conn, table, child_rows[name])

        stored = set((await conn.scalars(select(Product.id))).all())
        for stale in sorted(stored - product_ids):
            result.anomalies.append(Anomaly("product_not_in_file", stale))

    result.counts = {
        "categories": len(categories),
        "allergen_codes": len(allergen_codes),
        "products": len(product_rows),
        **{name: len(rows) for name, rows in child_rows.items()},
    }
    return result


def report(result: LoadResult, out: Any = sys.stdout) -> None:
    print("Loaded:", file=out)
    for name, count in result.counts.items():
        print(f"  {name:<16} {count:>7}", file=out)
    by_kind: dict[str, list[Anomaly]] = defaultdict(list)
    for anomaly in result.anomalies:
        by_kind[anomaly.kind].append(anomaly)
    print(f"Anomalies: {len(result.anomalies)}", file=out)
    for kind, items in sorted(by_kind.items()):
        details = Counter(a.detail for a in items if a.detail)
        examples = ", ".join(f"{a.product_id} {a.detail}".strip() for a in items[:10])
        print(f"  {kind}: {len(items)}", file=out)
        if details and len(details) > 1:
            print(f"    by detail: {dict(details.most_common(8))}", file=out)
        print(f"    e.g. {examples}", file=out)


async def _load_and_dispose(products: list[dict[str, Any]]) -> LoadResult:
    engine = get_engine()
    try:
        return await load(
            engine,
            products,
            read_categories(CATEGORY_FILE),
            read_allergen_codes(ALLERGEN_CODE_FILE),
        )
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--file", type=Path, default=DEFAULT_PRODUCT_FILE)
    parser.add_argument("--download", action="store_true", help="fetch the file if missing")
    parser.add_argument("--force", action="store_true", help="download even if the file exists")
    args = parser.parse_args()

    path: Path = args.file
    if args.download and (args.force or not path.exists()):
        print(f"Downloading the product file to {path}")
        download(path, get_settings().valio_api_key)
    if not path.exists():
        raise SystemExit(f"{path} not found. Run with --download (needs VALIO_API_KEY).")
    with path.open(encoding="utf-8") as f:
        products = json.load(f)

    report(asyncio.run(_load_and_dispose(products)))


if __name__ == "__main__":
    main()
