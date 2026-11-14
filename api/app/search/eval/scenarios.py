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
from collections import Counter, defaultdict
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
from app.search.text import fold, modifiers
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
    semantic: bool = False  # rank by meaning only, as substitute searches do (#78)
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
                semantic=item.get("semantic", name == "substitutes"),
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


# Catalogue-wide sets: every category, so a change that helps milk but breaks cleaning
# products shows up. Sampling is seeded, so the sets are the same on every run.

_SPLIT_NAME = re.compile(r",\s*|\s+(?:ja|and|sekä|&)\s+|\s*/\s*")
_FILLER = {"muut", "other", "myös", "also", "etc"}
SAMPLES_PER_CATEGORY = 3
MIN_CATEGORY_PRODUCTS = 3


def _word_set(s: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", fold(s)))


async def category_set(conn: AsyncConnection) -> list[Scenario]:
    """Each part of each category name ("viinerit", "kakut") as a query. Typical: the
    products of every category whose name has that part, since several can."""
    rows = (
        await conn.execute(
            text(
                """
                SELECT c.id, c.name_fi, c.name_en FROM categories c
                WHERE (SELECT count(*) FROM products p WHERE p.category_id = c.id) >= :n
                ORDER BY c.id
                """
            ),
            {"n": MIN_CATEGORY_PRODUCTS},
        )
    ).all()
    names = [(cid, fi, en) for cid, fi, en in rows]
    # A single word found in many category names ("fresh", "dry") names no kind.
    word_spread = Counter(w for _, fi, en in names for w in _word_set(fi) | _word_set(en))
    out: dict[str, Scenario] = {}
    for cid, fi, en in names:
        for lang, name in (("fi", fi), ("en", en)):
            for part in _SPLIT_NAME.split(re.sub(r"\([^)]*\)?|\)", " ", name.lower())):
                part = part.strip(" .")
                if part.endswith("-"):  # "Sini- ja punahomejuustot": "sini-" is half a word
                    continue
                words = [w for w in part.split() if fold(w) not in _FILLER]
                part = " ".join(words).strip(" -.")
                if len(part) < 4 or fold(part) in out:
                    continue
                if len(words) == 1 and word_spread[fold(part)] >= 5:
                    continue
                wanted = _word_set(part)
                cats = [c for c, f, e in names if wanted <= _word_set(f if lang == "fi" else e)]
                out[fold(part)] = Scenario(
                    f"category:{cid}:{lang}:{fold(part)}",
                    "categories",
                    part,
                    selectors={"typical": Selector(categories=tuple(cats or [cid]))},
                )
    return list(out.values())


async def _sampled_products(conn: AsyncConnection) -> list[tuple[str, str, str | None, str]]:
    rows = (
        await conn.execute(text("SELECT id, name_fi, brand, category_id FROM products ORDER BY id"))
    ).all()
    by_category: dict[str, list[tuple[str, str, str | None, str]]] = defaultdict(list)
    for r in rows:
        by_category[r.category_id].append((r.id, r.name_fi, r.brand, r.category_id))
    out = []
    for cid in sorted(by_category):
        products = by_category[cid]
        if len(products) < MIN_CATEGORY_PRODUCTS:
            continue
        rng = random.Random(f"products:{cid}")
        out += rng.sample(products, min(SAMPLES_PER_CATEGORY, len(products)))
    return out


def _clean_name(name: str, brand: str | None) -> list[str]:
    """The name as a buyer would say it: no brand, amounts, pack counts or symbols."""
    brand_words = _word_set(brand or "")
    words = []
    for w in re.findall(r"[^\W\d_][\w-]*", name.lower()):
        w = w.strip("-")
        if len(w) >= 2 and fold(w) not in brand_words and w not in {"x", "kpl", "pss", "ltk"}:
            words.append(w)
    return words


async def specific_set(conn: AsyncConnection) -> list[Scenario]:
    """A sampled product's name without brand and amounts. Typical: products whose cleaned
    name is the same (the same product in other pack sizes)."""
    rows = (await conn.execute(text("SELECT id, name_fi, brand FROM products"))).all()
    by_clean: dict[str, list[str]] = defaultdict(list)
    for r in rows:
        by_clean[" ".join(_clean_name(r.name_fi, r.brand))].append(r.id)
    out = []
    for pid, name, brand, _ in await _sampled_products(conn):
        words = _clean_name(name, brand)
        if len(words) < 1:
            continue
        q = " ".join(words)
        out.append(
            Scenario(
                f"specific:{pid}",
                "specific",
                q,
                selectors={"typical": Selector(tuple(by_clean[q]))},
            )
        )
    return out


MIN_HEAD_SPECIFICITY = 0.3
MIN_HEAD_PRODUCTS = 3


async def vague_set(conn: AsyncConnection) -> list[Scenario]:
    """A sampled product cut to its main word: the word of its name most specific to its
    category (most of the products with that word sit there), so attributes such as
    "laktoositon" or "original" are not mistaken for a kind. Typical: products of the
    category with that word; acceptable: the whole category."""
    rows = (await conn.execute(text("SELECT name_fi, brand, category_id FROM products"))).all()
    per_word: dict[str, Counter[str]] = defaultdict(Counter)
    for r in rows:
        for w in set(_clean_name(r.name_fi, r.brand)):
            per_word[fold(w)][r.category_id] += 1
    mods = modifiers()
    out: dict[str, Scenario] = {}
    for pid, name, brand, cid in await _sampled_products(conn):
        best: tuple[float, int, str] | None = None
        for w in _clean_name(name, brand):
            counts = per_word[fold(w)]
            total = sum(counts.values())
            is_modifier = any(m in fold(w) for group in mods for m in group)
            if len(w) < 4 or total < MIN_HEAD_PRODUCTS or is_modifier:
                continue
            key = (counts[cid] / total, len(w), w)
            if best is None or key > best:
                best = key
        if best is None or best[0] < MIN_HEAD_SPECIFICITY or fold(best[2]) in out:
            continue
        head = best[2]
        # A kind can span sibling categories (eggs in "Kananmunat" and "Kananmunavalmisteet"),
        # so every category holding enough of the word's products counts, not only the sample's.
        counts = per_word[fold(head)]
        total = sum(counts.values())
        cats = tuple(sorted(c for c, n in counts.items() if n / total >= MIN_HEAD_SPECIFICITY))
        out[fold(head)] = Scenario(
            f"vague:{pid}:{fold(head)}",
            "vague",
            head,
            selectors={
                "typical": Selector(categories=cats, name=re.escape(head)),
                "acceptable": Selector(categories=cats),
            },
        )
    return list(out.values())


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
        elif name == "categories":
            out += await category_set(conn)
        elif name == "specific":
            out += await specific_set(conn)
        elif name == "vague":
            out += await vague_set(conn)
        else:
            out += load_set(name)
    return await resolve(conn, out)


def scenario_path(name: str) -> Path:
    return SCENARIO_DIR / f"{name}.yaml"
