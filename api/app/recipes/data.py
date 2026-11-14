"""The recipe data files and the committed recipe vectors (#34).

- data/valio-recipes.json: 2,091 recipes scraped from the Minun Aimo portal (vision §7).
- data/recipe-product-map.json: recipe product ids to catalogue products, one per pack size.
- data/recipe-embeddings.json.gz: one Gemini vector per recipe, so every database loads them
  without calling the API. Written by `python -m app.recipes.embeddings`.

The vector file is gzipped JSON. Each vector is 768 little-endian float16 values in base64
(about 3 MB for all recipes, against 13 MB as float32 text), with a hash of the text it
was made from, so a changed recipe is noticed and embedded again.
"""

import base64
import gzip
import hashlib
import html
import json
import math
import struct
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

from app.search.vectors import DIMENSIONS, MODEL
from app.settings import REPO_ROOT

DATA_DIR = REPO_ROOT / "data"
RECIPE_FILE = DATA_DIR / "valio-recipes.json"
PRODUCT_MAP_FILE = DATA_DIR / "recipe-product-map.json"
VECTOR_FILE = DATA_DIR / "recipe-embeddings.json.gz"

ENCODING = "float16-le-base64"
_HALF = struct.Struct(f"<{DIMENSIONS}e")


@cache
def read_recipe_file(path: Path = RECIPE_FILE) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


@cache
def read_product_map(path: Path = PRODUCT_MAP_FILE) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))["mappings"]


def ingredients(recipe: dict[str, Any]) -> list[tuple[str | None, dict[str, Any]]]:
    """(segment title, ingredient) in order. The position in this list is the ingredient
    index of get_recipe and RecipeRef."""
    return [
        (segment["title"], ingredient)
        for segment in recipe["ingredientSegments"]
        for ingredient in segment["ingredients"]
    ]


def unit(portion_format: str | None) -> str | None:
    """The unit of a portion format such as "%s kg" (the data has a no-break space there)."""
    if not portion_format:
        return None
    return portion_format.replace("%s", "").replace("\xa0", " ").strip() or None


@dataclass(frozen=True)
class Tag:
    tag: str  # "erityisruokavaliot=laktoositon"
    group: str  # diet
    value: str  # laktoositon
    title: str  # Laktoositon


def tags(recipe: dict[str, Any], taxonomies: dict[str, Any]) -> list[Tag]:
    out: dict[str, Tag] = {}
    for group, values in recipe["taxonomies"].items():
        for tag in values:
            title = html.unescape(taxonomies.get(tag, {}).get("title") or tag.split("=", 1)[-1])
            out[tag] = Tag(tag, group, tag.split("=", 1)[-1], title)
    return [out[t] for t in sorted(out)]


def image_url(recipe: dict[str, Any]) -> str | None:
    image = recipe.get("image")
    return image["sizes"][0]["url"] if image and image["sizes"] else None


def source_text(recipe: dict[str, Any], taxonomies: dict[str, Any]) -> str:
    """What is embedded for one recipe (technical-plan.md §5.4): name, description,
    ingredient names and tags."""
    names = list(dict.fromkeys(i["name"] for _, i in ingredients(recipe)))
    parts = [
        recipe["name"],
        recipe.get("description") or "",
        "Ainekset: " + ", ".join(names),
        "Tagit: " + ", ".join(t.title for t in tags(recipe, taxonomies)),
    ]
    return "\n".join(p for p in parts if p)


def source_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


# --- The vector file --------------------------------------------------------------------


def encode_vector(values: Sequence[float]) -> str:
    return base64.b64encode(_HALF.pack(*values)).decode("ascii")


def decode_vector(data: str) -> list[float]:
    """Back to floats, normalised again (float16 rounding moves the length a little)."""
    values = _HALF.unpack(base64.b64decode(data))
    norm = math.sqrt(sum(v * v for v in values)) or 1.0
    return [v / norm for v in values]


@dataclass(frozen=True)
class StoredVector:
    hash: str
    vector: str  # encoded


def read_vector_file(path: Path = VECTOR_FILE) -> dict[int, StoredVector]:
    """The stored vectors by recipe id; empty when the file is missing or for another
    model or size."""
    if not path.exists():
        return {}
    with gzip.open(path, "rt", encoding="utf-8") as f:
        data = json.load(f)
    if (data.get("model"), data.get("dimensions"), data.get("encoding")) != (
        MODEL,
        DIMENSIONS,
        ENCODING,
    ):
        return {}
    return {
        int(recipe_id): StoredVector(v["hash"], v["vector"])
        for recipe_id, v in data["recipes"].items()
    }


def write_vector_file(vectors: dict[int, StoredVector], path: Path = VECTOR_FILE) -> None:
    """Sorted and with a fixed gzip time, so the same vectors give the same bytes."""
    data = {
        "model": MODEL,
        "dimensions": DIMENSIONS,
        "task": "RETRIEVAL_DOCUMENT",
        "encoding": ENCODING,
        "recipes": {
            str(recipe_id): {"hash": v.hash, "vector": v.vector}
            for recipe_id, v in sorted(vectors.items())
        },
    }
    raw = json.dumps(data, separators=(",", ":")).encode("utf-8")
    partial = path.with_suffix(".part")
    with partial.open("wb") as f, gzip.GzipFile(fileobj=f, mode="wb", mtime=0) as gz:
        gz.write(raw)
    partial.replace(path)


def recipe_texts(recipes: Iterable[dict[str, Any]], taxonomies: dict[str, Any]) -> dict[int, str]:
    return {r["id"]: source_text(r, taxonomies) for r in recipes}
