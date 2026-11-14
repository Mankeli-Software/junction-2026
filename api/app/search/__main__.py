"""Try one search against the loaded catalogue and see why each product ranked where it did.

uv run python -m app.search "naudan jauheliha" [--claim lactose_free] [--category ID]
"""

import argparse
import asyncio

from sqlalchemy import text

from app.db import get_engine
from app.schemas.common import Claim
from app.search import search_products


async def run(q: str, claims: list[Claim], category: str | None, limit: int) -> None:
    engine = get_engine()
    async with engine.connect() as conn:
        hits = await search_products(conn, q, claims=claims, category=category, limit=limit)
        names = dict(
            (
                await conn.execute(
                    text("SELECT id, name_fi FROM products WHERE id = ANY(:ids)"),
                    {"ids": [h.product_id for h in hits]},
                )
            ).all()
        )
    await engine.dispose()
    for rank, h in enumerate(hits, 1):
        print(f"{rank:>2} {h.score:>7} {h.product_id} {names[h.product_id]}")
        print(f"{'':>18}{', '.join(h.matched_on)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("q")
    parser.add_argument("--claim", action="append", default=[], type=Claim)
    parser.add_argument("--category")
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()
    asyncio.run(run(args.q, args.claim, args.category, args.limit))


if __name__ == "__main__":
    main()
