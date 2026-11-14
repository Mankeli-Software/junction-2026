"""Loads the product image URLs into Postgres from data/product_images.json.gz (#108).

    uv run python -m app.loaders.images [--file PATH]

The file is our crawl of the Minun Aimo portal joined to the product file by barcode
(scripts/build_image_map.py): {product_id: {image, ean, match}}. The URLs are Valio's own
and are hotlinked (technical-plan.md §5.5). The catalogue loader runs the same refresh at
the end of every load; this command refreshes the images alone.

Runs in one transaction and can be re-run: every row of product_images is replaced by the
file's entries for the products in the catalogue. Entries for products that aren't in the
catalogue are skipped and reported, as are the products with no image.
"""

import argparse
import asyncio
import gzip
import json
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from app.db import get_engine
from app.loaders.product_file import Anomaly
from app.models import Product, ProductImage
from app.models.catalogue import IMAGE_MATCHES
from app.settings import REPO_ROOT

IMAGE_FILE = REPO_ROOT / "data" / "product_images.json.gz"
BATCH_SIZE = 2000


@dataclass(frozen=True)
class ImageEntry:
    url: str
    match: str  # gtin or name


@dataclass
class ImageResult:
    counts: dict[str, int] = field(default_factory=dict)
    anomalies: list[Anomaly] = field(default_factory=list)


def read_image_file(path: Path = IMAGE_FILE) -> dict[str, ImageEntry]:
    """The image map, gzipped or plain JSON. Fails on an entry the table would reject."""
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as f:
        data: dict[str, dict[str, Any]] = json.load(f)
    images = {}
    for product_id, entry in data.items():
        url, match = entry.get("image"), entry.get("match")
        if not isinstance(url, str) or not url.startswith("https://"):
            raise ValueError(f"{path}: product {product_id} has no https image URL: {url!r}")
        if match not in IMAGE_MATCHES:
            raise ValueError(f"{path}: product {product_id} has an unknown match {match!r}")
        images[product_id] = ImageEntry(url=url, match=match)
    return images


async def replace_images(conn: AsyncConnection, images: Mapping[str, ImageEntry]) -> ImageResult:
    """Replace product_images in the caller's transaction, for the products stored now."""
    stored = set((await conn.scalars(select(Product.id))).all())
    rows = [
        {"product_id": product_id, "image_url": entry.url, "image_match": entry.match}
        for product_id, entry in sorted(images.items())
        if product_id in stored
    ]
    await conn.execute(delete(ProductImage.__table__))
    for start in range(0, len(rows), BATCH_SIZE):
        await conn.execute(insert(ProductImage.__table__), rows[start : start + BATCH_SIZE])

    with_image = {r["product_id"] for r in rows}
    result = ImageResult()
    result.anomalies += [
        Anomaly("image_not_in_catalogue", product_id) for product_id in sorted(set(images) - stored)
    ]
    result.anomalies += [
        Anomaly("product_without_image", product_id) for product_id in sorted(stored - with_image)
    ]
    result.counts = {
        "images": len(rows),
        "images_by_gtin": sum(r["image_match"] == "gtin" for r in rows),
        "images_by_name": sum(r["image_match"] == "name" for r in rows),
    }
    return result


async def load(engine: AsyncEngine, images: Mapping[str, ImageEntry]) -> ImageResult:
    async with engine.begin() as conn:
        return await replace_images(conn, images)


def report(result: ImageResult, out: Any = sys.stdout) -> None:
    print("Loaded:", file=out)
    for name, count in result.counts.items():
        print(f"  {name:<16} {count:>7}", file=out)
    print(f"Anomalies: {len(result.anomalies)}", file=out)
    for kind in sorted({a.kind for a in result.anomalies}):
        items = [a for a in result.anomalies if a.kind == kind]
        print(f"  {kind}: {len(items)}", file=out)
        print(f"    e.g. {', '.join(a.product_id for a in items[:10])}", file=out)


async def _load_and_dispose(images: Mapping[str, ImageEntry]) -> ImageResult:
    engine = get_engine()
    try:
        return await load(engine, images)
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--file", type=Path, default=IMAGE_FILE)
    args = parser.parse_args()
    report(asyncio.run(_load_and_dispose(read_image_file(args.file))))


if __name__ == "__main__":
    main()
