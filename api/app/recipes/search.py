"""Hybrid recipe search (#34, technical-plan.md §5.4).

Three ranked lists, merged with reciprocal rank fusion (RRF):

1. full-text search (Finnish stemming) over name, tags, ingredients and description,
2. trigram similarity of the query words to the name and ingredient names, which finds a
   word inside a Finnish compound ("pasta" in "kinkkupasta"),
3. the cosine distance between the query vector and the recipe vectors.

The query vector comes from the same cache as product search (`query_embeddings`,
SEARCH_VECTORS); without one, only the two text lists are merged. Diet tags and the
occasion are filters. Diet words in the query ("laktoositon", "gluten-free") become the
same filter, and portion counts ("50 hengelle") are dropped: they are for get_recipe.

Retrieval only finds recipes; it never takes part in an order decision (vision §7). The
recipe's diet tags are a hint, and the engine decides safety from the products' own data.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass, field

from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.types import Text

from app.search.search import query_embedding
from app.search.text import fold, parse_query

# RRF constant (Cormack et al.); each list adds 1 / (RRF_K + rank).
RRF_K = 60
LIST_SIZE = 50  # candidates taken from each list
TRIGRAM_THRESHOLD = 0.5
# Vector neighbours less similar than this are left out, so a query that matches nothing
# doesn't return the 50 least unrelated recipes.
VECTOR_MIN_SIMILARITY = 0.6
MAX_LIMIT = 20

# Diet words, folded, to the diet tag values of the data (erityisruokavaliot=<value>).
# Includes the kitchen exclusion and claim names, so an agent can pass "lactose_free".
DIET_WORDS: dict[str, str] = {
    **dict.fromkeys(
        ["laktoositon", "laktoositonta", "laktoosittomat", "laktoositonna", "lactose_free"],
        "laktoositon",
    ),
    **dict.fromkeys(
        ["gluteeniton", "gluteenitonta", "gluteenittomat", "gluten_free"], "gluteeniton"
    ),
    **dict.fromkeys(
        ["maidoton", "maidotonta", "maidottomat", "milk_free", "dairy_free"], "maidoton"
    ),
    **dict.fromkeys(["vegaaninen", "vegaanista", "vegaaniset", "vegan"], "vegaaninen"),
    **dict.fromkeys(
        ["kasvis", "kasvisruoka", "kasvisruokaa", "vegetarian", "vegetaarinen", "lakto-ovo"],
        "kasvis-lakto-ovo",
    ),
    **dict.fromkeys(
        ["kananmunaton", "kananmunatonta", "munaton", "munatonta", "egg_free"], "kananmunaton"
    ),
    **dict.fromkeys(["vahalaktoosinen", "vahalaktoosista", "low_lactose"], "vahalaktoosinen"),
}
# English words for the occasion filter, to the occasion and festivity tag values.
OCCASION_WORDS: dict[str, str] = {
    "lunch": "lounasruoka",
    "lounas": "lounasruoka",
    "breakfast": "aamiaistarjoilu",
    "aamiainen": "aamiaistarjoilu",
    "buffet": "buffet",
    "meeting": "vitriini-ja-kokoustarjoilut",
    "kokous": "vitriini-ja-kokoustarjoilut",
    "party": "juhlatarjoilu",
    "juhla": "juhlatarjoilu",
    "everyday": "arki",
    "christmas": "joulu",
    "easter": "paasiainen",
    "summer": "kesajuhlat",
    "autumn": "syksy",
    "winter": "talvi",
    "spring": "kevat",
}
# "lactose free", "gluten-free": one token, as the claim names are.
_FREE = re.compile(r"\b(lactose|gluten|milk|dairy|egg)[\s-]+free\b")
# Words about the amount or the request itself, not the dish.
IGNORED_WORDS = frozenset(
    fold(w)
    for w in (
        "hengelle henkilölle hengen henkeä henkilöä annosta annokselle annos annoksen "
        "resepti reseptiä reseptin ohje ruokaohje people persons person portions portion "
        "servings guests recipe recipes"
    ).split()
)
# Tag groups the occasion filter looks in: "lounasruoka" and "joulu" are both occasions.
OCCASION_GROUPS = ("occasion", "festivity")


@dataclass(frozen=True)
class RecipeQuery:
    text: str  # the dish words, for the full-text, trigram and vector lists
    diet: tuple[str, ...]  # diet tag values, all required
    occasion: str | None  # an occasion or festivity tag value


@dataclass(frozen=True)
class RecipeMatch:
    recipe_id: int
    score: float
    matched_on: tuple[str, ...] = field(default=())  # "fts:1", "trigram:3", "vector:2"


def split_query(q: str) -> tuple[str, list[str]]:
    """The dish words and the diet tag values said in the query."""
    normalised = _FREE.sub(r"\1_free", q.lower())
    words, diets = [], []
    for token in re.findall(r"[^\W\d][\w-]*|\d[\w.,]*", normalised):
        folded = fold(token)
        if folded in DIET_WORDS:
            diets.append(DIET_WORDS[folded])
        elif folded not in IGNORED_WORDS and not token[0].isdigit():
            words.append(token)
    return " ".join(words), list(dict.fromkeys(diets))


async def known_tags(db: AsyncSession, groups: Sequence[str]) -> dict[str, str]:
    """Folded value and folded title to the tag value, for these groups."""
    rows = await db.execute(
        text(
            "SELECT DISTINCT value, title FROM recipe_tags WHERE tag_group = ANY(:groups)"
        ).bindparams(bindparam("groups", type_=ARRAY(Text))),
        {"groups": list(groups)},
    )
    out: dict[str, str] = {}
    for value, title in rows:
        out[fold(value)] = value
        out.setdefault(fold(title), value)
    return out


def _filter_sql(query: RecipeQuery, params: dict[str, object]) -> str:
    clauses = []
    for i, value in enumerate(query.diet):
        params[f"diet{i}"] = value
        clauses.append(
            "EXISTS (SELECT 1 FROM recipe_tags t WHERE t.recipe_id = r.id "
            f"AND t.tag_group = 'diet' AND t.value = :diet{i})"
        )
    if query.occasion is not None:
        params["occasion"] = query.occasion
        groups = ", ".join(f"'{g}'" for g in OCCASION_GROUPS)
        clauses.append(
            "EXISTS (SELECT 1 FROM recipe_tags t WHERE t.recipe_id = r.id "
            f"AND t.tag_group IN ({groups}) AND t.value = :occasion)"
        )
    return " AND ".join(clauses) or "true"


async def _fts(db: AsyncSession, fts: str, where: str, params: dict) -> list[int]:
    rows = await db.execute(
        text(
            f"""
            SELECT r.id FROM recipes r, websearch_to_tsquery('finnish', :fts) q
            WHERE r.search_fi @@ q AND {where}
            ORDER BY ts_rank_cd(r.search_fi, q, 32) DESC, r.id
            LIMIT :n
            """
        ),
        {**params, "fts": fts, "n": LIST_SIZE},
    )
    return [r for (r,) in rows]


async def _trigram(
    db: AsyncSession, terms: Sequence[Sequence[str]], where: str, params: dict
) -> list[int]:
    """Mean over the query words of the best similarity of any of its alternatives."""
    words = [w for alternatives in terms for w in alternatives]
    await db.execute(
        text("SELECT set_config('pg_trgm.word_similarity_threshold', :t, true)"),
        {"t": str(TRIGRAM_THRESHOLD)},
    )
    match = " OR ".join(f":w{i} <% r.search_trgm" for i in range(len(words)))
    rows = await db.execute(
        text(
            f"""
            SELECT r.id, ARRAY(SELECT word_similarity(w, r.search_trgm)
                               FROM unnest(:words) AS w) AS sims
            FROM recipes r WHERE ({match}) AND {where}
            """
        ).bindparams(bindparam("words", type_=ARRAY(Text))),
        {**params, "words": words, **{f"w{i}": w for i, w in enumerate(words)}},
    )
    scored = []
    for recipe_id, sims in rows:
        it = iter(sims)
        per_term = [max(next(it) for _ in alternatives) for alternatives in terms]
        scored.append((round(sum(per_term) / len(per_term), 6), recipe_id))
    scored.sort(key=lambda s: (-s[0], s[1]))
    return [recipe_id for _, recipe_id in scored[:LIST_SIZE]]


async def _vector(db: AsyncSession, vector: str, where: str, params: dict) -> list[int]:
    """Exact nearest neighbours among the filtered recipes (2,091 rows: an exact scan is a
    few milliseconds, and an HNSW scan with a filter could return fewer than asked)."""
    rows = await db.execute(
        text(
            f"""
            WITH d AS MATERIALIZED (
                SELECT e.recipe_id, 1 - (e.embedding <=> CAST(:qv AS vector)) AS similarity
                FROM recipe_embeddings e JOIN recipes r ON r.id = e.recipe_id
                WHERE {where}
            )
            SELECT recipe_id FROM d WHERE similarity >= :min
            ORDER BY round(similarity::numeric, 6) DESC, recipe_id
            LIMIT :n
            """
        ),
        {**params, "qv": vector, "min": VECTOR_MIN_SIMILARITY, "n": LIST_SIZE},
    )
    return [r for (r,) in rows]


def fuse(lists: dict[str, list[int]]) -> list[RecipeMatch]:
    """Reciprocal rank fusion; ties by recipe id, so the order is deterministic."""
    scores: dict[int, float] = {}
    matched: dict[int, list[str]] = {}
    for name, ids in lists.items():
        for rank, recipe_id in enumerate(ids, start=1):
            scores[recipe_id] = scores.get(recipe_id, 0.0) + 1 / (RRF_K + rank)
            matched.setdefault(recipe_id, []).append(f"{name}:{rank}")
    ranked = sorted(scores, key=lambda i: (-round(scores[i], 9), i))
    return [RecipeMatch(i, round(scores[i], 9), tuple(matched[i])) for i in ranked]


async def search(db: AsyncSession, query: RecipeQuery, limit: int = 10) -> list[RecipeMatch]:
    limit = max(1, min(limit, MAX_LIMIT))
    params: dict[str, object] = {}
    where = _filter_sql(query, params)
    parsed = parse_query(query.text)
    if not parsed.terms:
        # Only filters: the newest recipes that pass them.
        rows = await db.execute(
            text(f"SELECT r.id FROM recipes r WHERE {where} ORDER BY r.id DESC LIMIT :n"),
            {**params, "n": limit},
        )
        return [RecipeMatch(r, 0.0, ("filter",)) for (r,) in rows]

    terms = [t.folded for t in parsed.terms]
    lists = {
        "fts": await _fts(db, parsed.fts, where, params),
        "trigram": await _trigram(db, terms, where, params),
    }
    vector = await query_embedding(db, " ".join(t.word for t in parsed.terms))
    if vector is not None:
        lists["vector"] = await _vector(db, vector, where, params)
    return fuse(lists)[:limit]
