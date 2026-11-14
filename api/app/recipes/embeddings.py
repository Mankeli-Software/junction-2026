"""Regenerate the recipe vectors file (#34, technical-plan.md §5.4).

    uv run python -m app.recipes.embeddings [--limit N] [--dry-run]

Embeds each recipe (name, description, ingredient names, tags) once with the product
search's Gemini model and settings (app.search.vectors, #30) and writes
data/recipe-embeddings.json.gz. Only recipes without a vector, or whose text changed, are
embedded, 100 texts per request; the file is saved after every request. It stops at the
first 429 or error instead of retrying, because the hackathon key has abuse limits: run it
again later to continue. Needs GEMINI_API_KEY. Databases load the file with
`python -m app.loaders.recipes`, never calling the API.
"""

import argparse
import asyncio
import sys

import httpx

from app.recipes.data import (
    VECTOR_FILE,
    StoredVector,
    encode_vector,
    read_recipe_file,
    read_vector_file,
    recipe_texts,
    source_hash,
    write_vector_file,
)
from app.search.embeddings import BATCH_SIZE, embed_texts
from app.settings import get_settings


async def regenerate(limit: int | None = None, dry_run: bool = False) -> int:
    """Embed what is missing or stale; returns how many requests were sent."""
    data = read_recipe_file()
    texts = recipe_texts(data["recipes"], data["taxonomies"])
    stored = read_vector_file()
    # Recipes no longer in the file are dropped.
    vectors = {i: v for i, v in stored.items() if i in texts}
    todo = [
        i for i in sorted(texts) if i not in vectors or vectors[i].hash != source_hash(texts[i])
    ]
    todo = todo[:limit] if limit else todo
    print(f"{len(texts)} recipes, {len(vectors)} stored vectors, {len(todo)} to embed")
    if dry_run or not todo:
        if not dry_run and len(vectors) != len(stored):
            write_vector_file(vectors)
        return 0

    api_key = get_settings().gemini_api_key
    if not api_key:
        raise SystemExit("GEMINI_API_KEY is not set (.env on a laptop)")
    requests = 0
    async with httpx.AsyncClient(timeout=120) as client:
        for start in range(0, len(todo), BATCH_SIZE):
            batch = todo[start : start + BATCH_SIZE]
            requests += 1
            try:
                embedded = await embed_texts(
                    client, api_key, [texts[i] for i in batch], "RETRIEVAL_DOCUMENT", tries=1
                )
            except httpx.HTTPStatusError as error:
                print(
                    f"stopped: HTTP {error.response.status_code} on request {requests}; "
                    "the file keeps what was done, run again later",
                    file=sys.stderr,
                )
                break
            for recipe_id, vector in zip(batch, embedded, strict=True):
                vectors[recipe_id] = StoredVector(
                    source_hash(texts[recipe_id]), encode_vector(vector)
                )
            write_vector_file(vectors)
            print(f"  {min(start + BATCH_SIZE, len(todo))}/{len(todo)}")
    size = VECTOR_FILE.stat().st_size / 1e6
    print(f"{requests} requests, {len(vectors)} vectors in {VECTOR_FILE.name} ({size:.1f} MB)")
    return requests


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--limit", type=int, help="embed at most this many recipes")
    parser.add_argument("--dry-run", action="store_true", help="only count what is missing")
    args = parser.parse_args()
    asyncio.run(regenerate(args.limit, args.dry_run))


if __name__ == "__main__":
    main()
