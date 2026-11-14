"""Gemini embeddings for the search vector experiment (#30, spec §7.11).

    uv run python -m app.search.embeddings products [--limit N]
    uv run python -m app.search.embeddings queries "naudan jauheliha" "kermaa" ...

Product vectors are computed once and stored in product_embeddings; a product is embedded
again only when its text or the model changes. Query vectors are cached in
query_embeddings, so the same text always gives the same vector. Search embeds a missing
query live only when SEARCH_VECTORS=live (embed_query_live). Needs GEMINI_API_KEY.
"""

import argparse
import asyncio
import math
import sys
from collections.abc import Sequence

import httpx
from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.types import Text

from app.db import get_engine
from app.search.vectors import DIMENSIONS, MODEL, query_key, vector_literal
from app.settings import get_settings

BATCH_SIZE = 100
URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:batchEmbedContents"
MAX_TRIES = 6

PRODUCT_TEXT = """
    SELECT p.id, p.name_fi || ' | ' || coalesce(p.name_en, '') || ' | '
                 || c.name_fi || ' | ' || c.name_en AS source_text
    FROM products p JOIN categories c ON c.id = p.category_id
"""


def _normalised(values: list[float]) -> list[float]:
    # Gemini normalises only its full 3,072-dimension output; shorter ones are scaled here.
    norm = math.sqrt(sum(v * v for v in values)) or 1.0
    return [v / norm for v in values]


async def embed_texts(
    client: httpx.AsyncClient, api_key: str, texts: Sequence[str], task: str, tries: int = MAX_TRIES
) -> list[list[float]]:
    """Embed in batches. task is RETRIEVAL_DOCUMENT for products, RETRIEVAL_QUERY for
    queries. Backs off on 429 and 5xx."""
    out: list[list[float]] = []
    for start in range(0, len(texts), BATCH_SIZE):
        batch = texts[start : start + BATCH_SIZE]
        body = {
            "requests": [
                {
                    "model": f"models/{MODEL}",
                    "content": {"parts": [{"text": t}]},
                    "taskType": task,
                    "outputDimensionality": DIMENSIONS,
                }
                for t in batch
            ]
        }
        for attempt in range(tries):
            response = await client.post(URL, json=body, headers={"x-goog-api-key": api_key})
            if (response.status_code == 429 or response.status_code >= 500) and tries > 1:
                wait = min(60, 2 ** (attempt + 1))
                print(f"  {response.status_code}, waiting {wait} s", file=sys.stderr)
                await asyncio.sleep(wait)
                continue
            response.raise_for_status()
            out += [_normalised(e["values"]) for e in response.json()["embeddings"]]
            break
        else:
            raise RuntimeError(f"embedding failed after {tries} tries")
    return out


def _api_key() -> str:
    key = get_settings().gemini_api_key
    if not key:
        raise SystemExit("GEMINI_API_KEY is not set (.env on a laptop, Key Vault on the VM)")
    return key


async def embed_products(engine: AsyncEngine, limit: int | None = None) -> int:
    """Embed products that have no vector yet, or whose text or model changed."""
    api_key = _api_key()
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    f"""
                    SELECT t.id, t.source_text FROM ({PRODUCT_TEXT}) AS t
                    LEFT JOIN product_embeddings e ON e.product_id = t.id
                    WHERE e.product_id IS NULL OR e.source_text <> t.source_text
                       OR e.model <> :model
                    ORDER BY t.id
                    """
                ),
                {"model": MODEL},
            )
        ).all()
    rows = rows[:limit] if limit else rows
    print(f"{len(rows)} products to embed")
    done = 0
    async with httpx.AsyncClient(timeout=60) as client:
        for start in range(0, len(rows), BATCH_SIZE):
            batch = rows[start : start + BATCH_SIZE]
            vectors = await embed_texts(
                client, api_key, [r.source_text for r in batch], "RETRIEVAL_DOCUMENT"
            )
            # One transaction per batch, so an interrupted run keeps what it has done.
            async with engine.begin() as conn:
                await conn.execute(
                    text(
                        """
                        INSERT INTO product_embeddings (product_id, model, source_text, embedding)
                        VALUES (:id, :model, :source_text, CAST(:embedding AS vector))
                        ON CONFLICT (product_id) DO UPDATE SET model = excluded.model,
                            source_text = excluded.source_text, embedding = excluded.embedding
                        """
                    ),
                    [
                        {
                            "id": r.id,
                            "model": MODEL,
                            "source_text": r.source_text,
                            "embedding": vector_literal(v),
                        }
                        for r, v in zip(batch, vectors, strict=True)
                    ],
                )
            done += len(batch)
            print(f"  {done}/{len(rows)}")
    return done


async def ensure_query_embeddings(engine: AsyncEngine, queries: Sequence[str]) -> int:
    """Embed and cache the queries that are not cached yet. Returns how many were new."""
    keys = sorted({query_key(q) for q in queries if q.strip()})
    async with engine.connect() as conn:
        cached = set(
            (
                await conn.scalars(
                    text(
                        "SELECT query_text FROM query_embeddings "
                        "WHERE model = :model AND query_text = ANY(:keys)"
                    ).bindparams(bindparam("keys", type_=ARRAY(Text))),
                    {"model": MODEL, "keys": keys},
                )
            ).all()
        )
    missing = [k for k in keys if k not in cached]
    if not missing:
        return 0
    api_key = _api_key()
    async with httpx.AsyncClient(timeout=60) as client:
        vectors = await embed_texts(client, api_key, missing, "RETRIEVAL_QUERY")
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                INSERT INTO query_embeddings (query_text, model, embedding)
                VALUES (:q, :model, CAST(:embedding AS vector))
                ON CONFLICT DO NOTHING
                """
            ),
            [
                {"q": k, "model": MODEL, "embedding": vector_literal(v)}
                for k, v in zip(missing, vectors, strict=True)
            ],
        )
    return len(missing)


LIVE_TIMEOUT = 2.0


async def embed_query_live(engine: AsyncEngine, q: str) -> str | None:
    """Embed one query now and cache it; None if there is no key or the call fails, so
    search falls back to text. Uses its own transaction, so the cache survives the caller's
    rollback."""
    api_key = get_settings().gemini_api_key
    if not api_key:
        return None
    key = query_key(q)
    try:
        async with httpx.AsyncClient(timeout=LIVE_TIMEOUT) as client:
            [vector] = await embed_texts(client, api_key, [key], "RETRIEVAL_QUERY", tries=1)
    except (httpx.HTTPError, RuntimeError, ValueError):
        return None
    literal = vector_literal(vector)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                INSERT INTO query_embeddings (query_text, model, embedding)
                VALUES (:q, :model, CAST(:embedding AS vector)) ON CONFLICT DO NOTHING
                """
            ),
            {"q": key, "model": MODEL, "embedding": literal},
        )
    return literal


async def _main(args: argparse.Namespace) -> None:
    engine = get_engine()
    try:
        if args.what == "products":
            await embed_products(engine, args.limit)
        else:
            print(f"{await ensure_query_embeddings(engine, args.queries)} new query vectors")
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="what", required=True)
    products = sub.add_parser("products")
    products.add_argument("--limit", type=int)
    queries = sub.add_parser("queries")
    queries.add_argument("queries", nargs="+")
    asyncio.run(_main(parser.parse_args()))


if __name__ == "__main__":
    main()
