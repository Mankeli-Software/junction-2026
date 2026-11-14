"""Category substitutes: where to look when every hit is blocked for the kitchen (#78).

`data/category_substitutes.csv` maps a category to categories that hold alternatives of
the same use: milk -> plant-based drinks, butter -> margarine, mince -> plant proteins.
The quote service searches those categories with the buyer's words when every search hit
may be blocked; the engine still decides what is safe.
"""

import csv
from collections import defaultdict
from functools import cache

from app.settings import REPO_ROOT

CATEGORY_SUBSTITUTES_FILE = REPO_ROOT / "data" / "category_substitutes.csv"


@cache
def category_substitutes() -> dict[str, tuple[str, ...]]:
    """from_category -> to_categories, in file order."""
    out: dict[str, list[str]] = defaultdict(list)
    with CATEGORY_SUBSTITUTES_FILE.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            out[row["from_category"]].append(row["to_category"])
    return {k: tuple(v) for k, v in out.items()}
