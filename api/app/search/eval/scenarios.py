"""Search scenarios: loading, generating and resolving expectations (spec §6.2).

A scenario is a query (plus optional claims and category) with graded expectations:
`typical` (what a kitchen most likely means), `acceptable` (same kind, another variant)
and `wrong_kind` (matches the words, must not be in the top 5). Each grade is a selector:
explicit `ids`, or `categories` plus a `name` regex and a `not` regex on the Finnish and
English names, resolved against the loaded catalogue.
"""

import json
import random
import re
from collections import Counter
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.asyncio import AsyncConnection
from sqlalchemy.types import Text

from app.schemas.common import Claim
from app.search.search import CLAIM_IDS
from app.search.text import fold
from app.settings import REPO_ROOT

SCENARIO_DIR = REPO_ROOT / "api" / "tests" / "search_scenarios"
RECIPES_FILE = REPO_ROOT / "data" / "valio-recipes.json"
RECIPE_MAP_FILE = REPO_ROOT / "data" / "recipe-product-map.json"
GRADES = ("typical", "acceptable", "wrong_kind")


@dataclass(frozen=True)
class Selector:
    ids: tuple[str, ...] = ()
    categories: tuple[str, ...] = ()
    name: str | None = None
    not_: str | None = None

    @classmethod
    def parse(cls, data: dict[str, Any] | list[str] | None) -> "Selector | None":
        if data is None:
            return None
        if isinstance(data, list):
            return cls(ids=tuple(str(i) for i in data))
        return cls(
            ids=tuple(str(i) for i in data.get("ids", [])),
            categories=tuple(str(c) for c in data.get("categories", [])),
            name=data.get("name"),
            not_=data.get("not"),
        )


@dataclass(frozen=True)
class Scenario:
    id: str
    set: str
    q: str
    claims: tuple[Claim, ...] = ()
    category: str | None = None
    selectors: dict[str, Selector] = field(default_factory=dict)
    note: str | None = None
    # Filled by resolve(): product ids per grade.
    expected: dict[str, frozenset[str]] = field(default_factory=dict)


def load_set(name: str) -> list[Scenario]:
    data = yaml.safe_load((SCENARIO_DIR / f"{name}.yaml").read_text(encoding="utf-8"))
    out = []
    for item in data:
        selectors = {g: s for g in GRADES if (s := Selector.parse(item.get(g))) is not None}
        out.append(
            Scenario(
                id=item["id"],
                set=name,
                q=item["q"],
                claims=tuple(Claim(c) for c in item.get("claims", [])),
                category=item.get("category"),
                selectors=selectors,
                note=item.get("note"),
            )
        )
    return out


_SELECT = text(
    """
    SELECT p.id FROM products p
    WHERE (cardinality(:ids) > 0 AND p.id = ANY(:ids))
       OR (cardinality(:ids) = 0
           AND (cardinality(:cats) = 0 OR p.category_id = ANY(:cats))
           AND (CAST(:name AS text) IS NULL
                OR p.name_fi ~* :name OR coalesce(p.name_en, '') ~* :name)
           AND (CAST(:not AS text) IS NULL
                OR NOT (p.name_fi ~* :not OR coalesce(p.name_en, '') ~* :not))
           AND (cardinality(:claims) = 0 OR p.id IN (
                SELECT product_id FROM product_claims WHERE claim_id = ANY(:claims)
                GROUP BY product_id HAVING count(DISTINCT claim_id) = cardinality(:claims))))
    """
).bindparams(*(bindparam(n, type_=ARRAY(Text)) for n in ("ids", "cats", "claims")))


async def resolve(conn: AsyncConnection, scenarios: list[Scenario]) -> list[Scenario]:
    """Turn selectors into product ids. A selector with ids and filters uses only the ids."""
    cache: dict[tuple[Selector, tuple[Claim, ...]], frozenset[str]] = {}
    out = []
    for s in scenarios:
        expected = {}
        for grade, sel in s.selectors.items():
            # wrong_kind ignores the claims: a wrong product is wrong whatever it claims.
            claims = s.claims if grade != "wrong_kind" else ()
            key = (sel, claims)
            if key not in cache:
                rows = await conn.scalars(
                    _SELECT,
                    {
                        "ids": list(sel.ids),
                        "cats": list(sel.categories),
                        "name": sel.name,
                        "not": sel.not_,
                        "claims": sorted(CLAIM_IDS[c] for c in claims),
                    },
                )
                cache[key] = frozenset(rows.all())
            expected[grade] = cache[key]
        out.append(replace(s, expected=expected))
    return out


# Generated sets -------------------------------------------------------------------------

_VOWEL_PAIRS = re.compile(r"(aa|ee|ii|oo|uu|yy|ää|öö)")


def _partitive(word: str) -> str | None:
    if not word or word[-1] not in "aeiouyäö":
        return None
    back = any(v in word for v in "aou")
    return word + ("a" if back else "ä")


def _variants(q: str, rng: random.Random, heads: set[str]) -> list[tuple[str, str]]:
    """Speech and typing errors of one query: (kind, text) pairs."""
    words = q.split()
    out: list[tuple[str, str]] = []
    longest = max(range(len(words)), key=lambda i: (len(words[i]), -i))
    w = words[longest]

    def with_word(new: str, i: int = longest) -> str:
        return " ".join(words[:i] + [new] + words[i + 1 :])

    if len(w) >= 5:
        i = rng.randrange(1, len(w) - 1)
        out.append(("typo_drop", with_word(w[:i] + w[i + 1 :])))
        j = rng.randrange(1, len(w) - 2)
        out.append(("typo_swap", with_word(w[:j] + w[j + 1] + w[j] + w[j + 2 :])))
    if m := _VOWEL_PAIRS.search(w):
        out.append(("single_vowel", with_word(w[: m.start()] + w[m.start()] + w[m.end() :])))
    if fold(q) != q.lower():
        out.append(("no_umlauts", fold(q)))
    # Split a compound where the tail is a common word in the catalogue (kevyt maito).
    for cut in range(3, len(w) - 3):
        if fold(w[cut:]) in heads:
            out.append(("split_compound", with_word(w[:cut] + " " + w[cut:])))
            break
    if len(words) >= 2:
        out.append(
            ("joined", "".join(words[:2]) + (" " + " ".join(words[2:]) if words[2:] else ""))
        )
    last = len(words) - 1
    if p := _partitive(words[last]):
        out.append(("partitive", with_word(p, last)))
    return out


async def compound_heads(conn: AsyncConnection) -> set[str]:
    """Common words in product names, used as compound tails (maito, liha, kerma)."""
    names = (await conn.scalars(text("SELECT name_fi FROM products"))).all()
    counts = Counter(t for n in names for t in re.findall(r"[a-zåäö]{4,}", fold(n)))
    return {t for t, n in counts.items() if n >= 15}


async def noisy_set(conn: AsyncConnection, core: list[Scenario]) -> list[Scenario]:
    heads = await compound_heads(conn)
    out = []
    for s in core:
        rng = random.Random(s.id)  # seeded per scenario: the same set on every run
        for kind, q in _variants(s.q, rng, heads):
            if q != s.q:
                out.append(replace(s, id=f"{s.id}~{kind}", set="noisy", q=q))
    return out


def recipe_set() -> list[Scenario]:
    """Recipe product names and the recipes' own ingredient texts, labelled by the map."""
    mappings = json.loads(RECIPE_MAP_FILE.read_text(encoding="utf-8"))["mappings"]
    good = {
        k: tuple(p["id"] for p in m["aimoProducts"])
        for k, m in mappings.items()
        if m["confidence"] in ("high", "reviewed") and m["aimoProducts"]
    }
    seen: dict[str, Scenario] = {}
    for key, ids in sorted(good.items()):
        name = mappings[key]["recipeProductName"]
        seen.setdefault(
            fold(name),
            Scenario(f"product:{key}", "recipes", name, selectors={"typical": Selector(ids)}),
        )
    recipes = json.loads(RECIPES_FILE.read_text(encoding="utf-8"))["recipes"]
    for recipe in recipes:
        for segment in recipe.get("ingredientSegments") or []:
            for ing in segment.get("ingredients") or []:
                key = str(ing.get("productId"))
                if key in good and ing.get("name"):
                    seen.setdefault(
                        fold(ing["name"]),
                        Scenario(
                            f"ingredient:{ing['id']}",
                            "recipes",
                            ing["name"],
                            selectors={"typical": Selector(good[key])},
                        ),
                    )
    return list(seen.values())


async def load_all(conn: AsyncConnection, names: list[str]) -> list[Scenario]:
    core = load_set("core")
    out: list[Scenario] = []
    for name in names:
        if name == "core":
            out += core
        elif name == "noisy":
            out += await noisy_set(conn, core)
        elif name == "recipes":
            out += recipe_set()
        else:
            out += load_set(name)
    return await resolve(conn, out)


def scenario_path(name: str) -> Path:
    return SCENARIO_DIR / f"{name}.yaml"
