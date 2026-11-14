"""Deterministic product search over the catalogue (#30, docs/plans/30-product-search.md).

Postgres finds the candidates (claim and category filters, full-text and trigram match)
and returns their match scores; the ranking below is plain arithmetic on those scores, so
the same query on the same data always gives the same ids in the same order.
"""

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession
from sqlalchemy.types import Text

from app.schemas.common import Claim
from app.search.text import Query, name_tokens, parse_query, unasked_modifiers

CLAIM_IDS: dict[Claim, str] = {
    Claim.lactose_free: "FREE_FROM_LACTOSE",  # never LOW_LACTOSE, never the name
    Claim.gluten_free: "FREE_FROM_GLUTEN",
    Claim.vegan: "VEGAN",
    Claim.vegetarian: "VEGETARIAN",
}

# Words that say the same as a claim, dropped from the text when the claim is given.
CLAIM_WORDS: dict[Claim, tuple[str, ...]] = {
    Claim.lactose_free: ("laktoositon", "laktoositonta", "lactose", "free", "lactose-free"),
    Claim.gluten_free: ("gluteeniton", "gluteenitonta", "gluten", "free", "gluten-free"),
    Claim.vegan: ("vegaaninen", "vegaanista", "vegan"),
    Claim.vegetarian: ("kasvis", "vegetarian", "vegetaarinen"),
}

MAX_LIMIT = 20
# How many text matches are ranked in Python; the category boost can't lift others.
POOL_SIZE = 400
# Starting weights (§3.2, §5). Change only through python -m app.search.eval.
TRIGRAM_THRESHOLD = 0.45
W_COVERAGE = 1.0
W_FTS = 0.5
W_CATEGORY = 0.3
W_MODIFIER = 0.3
# A whole-word (stemmed) match on a category name counts fully, a trigram match inside a
# longer word only partly. Categories within CATEGORY_MARGIN of the best are inferred.
CATEGORY_PARTIAL = 0.8
CATEGORY_NAME_THRESHOLD = 0.6
CATEGORY_MARGIN = 0.05
# Weight of "share of the top matches in this category" next to the name match.
CATEGORY_SHARE_WEIGHT = 0.0
# Query words at least this long count fully when found inside a name word (0: off).
COMPOUND_MIN_LENGTH = 5
PLURALITY_POOL = 20
# The plurality category is inferred only if it holds at least this share of the pool.
PLURALITY_MIN_SHARE = 0.0
# A brand in the query means a specific product, not a vague kind: no plurality guess.
PLURALITY_WITH_BRAND = False

_WORDS = bindparam("words", type_=ARRAY(Text))


def _candidates_sql(n_words: int, has_claims: bool, has_category: bool, match_all: bool):
    """Each match path is its own indexed lookup (an OR across them would scan every row)."""
    if match_all:
        matched = "SELECT id FROM products"
    else:
        paths = [
            "SELECT id FROM products, q WHERE search_fi @@ q.qfi",
            "SELECT id FROM products, q WHERE search_en @@ q.qen",
        ] + [f"SELECT id FROM products WHERE :w{i} <% search_trgm" for i in range(n_words)]
        matched = "\n        UNION ".join(paths)
    filters = []
    if has_claims:
        filters.append(
            """p.id IN (SELECT product_id FROM product_claims WHERE claim_id = ANY(:claims)
                    GROUP BY product_id HAVING count(DISTINCT claim_id) = cardinality(:claims))"""
        )
    if has_category:
        filters.append("p.category_id = :category")
    where = " AND ".join(filters) or "true"
    statement = text(
        f"""
    WITH q AS (
        SELECT websearch_to_tsquery('finnish', :fts) AS qfi,
               websearch_to_tsquery('english', :fts) AS qen
    ),
    matched AS (
        {matched}
    ),
    scored AS (
        SELECT p.id, p.name_fi, coalesce(p.name_en, '') AS name_en, p.category_id,
               cat.name_fi AS category_name,
               ts_rank_cd(p.search_fi, q.qfi, 32) + ts_rank_cd(p.search_en, q.qen, 32) AS fts,
               ARRAY(SELECT word_similarity(w, p.search_trgm) FROM unnest(:words) AS w) AS sims
        FROM products p JOIN matched USING (id) JOIN categories cat ON cat.id = p.category_id, q
        WHERE {where}
    )
    SELECT * FROM scored
    ORDER BY fts + (SELECT coalesce(avg(s), 0) FROM unnest(sims) AS s) DESC, id
    LIMIT :pool
    """
    ).bindparams(_WORDS)
    if has_claims:
        statement = statement.bindparams(bindparam("claims", type_=ARRAY(Text)))
    return statement


# Per query word: trigram similarity to the category name, and whether the stemmed word
# matches a whole word of it ("tomaatti" stems like "Tomaatit", not "Tomaattisäilykkeet").
_CATEGORY_MATCHES = text(
    """
    SELECT c.id,
           ARRAY(SELECT word_similarity(w, immutable_unaccent(lower(c.name_fi || ' ' || c.name_en)))
                 FROM unnest(:words) AS w) AS sims,
           ARRAY(SELECT to_tsvector('finnish', c.name_fi) @@ plainto_tsquery('finnish', w)
                        OR to_tsvector('english', c.name_en) @@ plainto_tsquery('english', w)
                 FROM unnest(:raw_words) AS w) AS whole
    FROM categories c
    """
).bindparams(_WORDS, bindparam("raw_words", type_=ARRAY(Text)))


# Brand words ("Valio") say nothing about the kind of product, and one category is even
# named "Valio kermat", so they are left out of category inference.
_BRAND_WORDS = text(
    """
    SELECT w FROM unnest(:words) AS w
    WHERE EXISTS (SELECT 1 FROM products WHERE immutable_unaccent(lower(brand)) = w)
    """
).bindparams(_WORDS)


@dataclass(frozen=True)
class SearchHit:
    product_id: str
    score: Decimal  # rounded to 4 places, so the order never depends on float noise
    matched_on: tuple[str, ...]  # for the decision trace: what made this product match


@dataclass(frozen=True)
class _Candidate:
    product_id: str
    name: str  # Finnish and English, for amounts and modifiers
    category_id: str
    category_name: str  # modifiers count here too: "...lihapakasteet" is frozen
    fts: float
    sims: tuple[float, ...]


def _coverage(query: Query, candidate: _Candidate) -> float:
    """Mean over the buyer's words of how well the name covers each (synonyms count)."""
    scores: list[float] = []
    sims = iter(candidate.sims)
    names = name_tokens(candidate.name)
    for term in query.terms:
        best = max(next(sims) for _ in term.alternatives)
        # A word inside a compound is a full match: "maito" in "kevytmaito".
        if COMPOUND_MIN_LENGTH and any(
            len(a) >= COMPOUND_MIN_LENGTH and any(a in n for n in names) for a in term.folded
        ):
            best = 1.0
        scores.append(best)
    if query.amounts:
        scores.extend(1.0 if a in names else 0.0 for a in query.amounts)
    return sum(scores) / len(scores) if scores else 0.0


def _term_scores(query: Query, sims: Sequence[float]) -> list[float]:
    it = iter(sims)
    return [max(next(it) for _ in term.alternatives) for term in query.terms]


async def _infer_categories(
    db: AsyncConnection | AsyncSession, query: Query, ranked: list[_Candidate]
) -> tuple[dict[str, float], str]:
    """Categories whose name matches the query; else the plurality of the best matches."""
    brands = set(
        (await db.scalars(_BRAND_WORDS, {"words": [t.folded[0] for t in query.terms]})).all()
    )
    query = Query(
        tuple(t for t in query.terms if t.folded[0] not in brands), query.amounts, query.folded_text
    )
    if query.terms:
        raw_words = [a for t in query.terms for a in t.alternatives]
        rows = (
            await db.execute(
                _CATEGORY_MATCHES, {"words": query.trigram_words, "raw_words": raw_words}
            )
        ).all()
        named: dict[str, float] = {}  # above the name threshold
        all_named: dict[str, float] = {}  # every category, for the share-weighted choice
        for category_id, sims, whole in rows:
            per_word = [
                1.0 if w else CATEGORY_PARTIAL * s for s, w in zip(sims, whole, strict=True)
            ]
            scores = _term_scores(query, per_word)
            all_named[category_id] = sum(scores) / len(scores)
            if max(scores) >= CATEGORY_NAME_THRESHOLD:
                named[category_id] = all_named[category_id]
        if named and CATEGORY_SHARE_WEIGHT > 0 and not brands:
            # A name match counts more when the strongest matches actually sit there:
            # "maito" names "Maito- ja kermajauheet", but the milks are in "Maidot ja piimät".
            top = ranked[:PLURALITY_POOL]
            share = Counter(c.category_id for c in top)
            combined = {
                c: all_named.get(c, 0.0) + CATEGORY_SHARE_WEIGHT * n / len(top)
                for c, n in share.items()
            } | {c: v for c, v in named.items() if c not in share}
            best = max(combined.values())
            return {
                c: 1.0 for c, v in combined.items() if v >= best - CATEGORY_MARGIN
            }, "category_name_and_matches"
        if named:
            best = max(named.values())
            return {c: v for c, v in named.items() if v >= best - CATEGORY_MARGIN}, "category_name"
    if brands and not PLURALITY_WITH_BRAND:
        return {}, ""
    counts = Counter(c.category_id for c in ranked[:PLURALITY_POOL])
    if not counts:
        return {}, ""
    top = max(counts.values())
    if top < PLURALITY_MIN_SHARE * min(len(ranked), PLURALITY_POOL):
        return {}, ""
    winner = min(c for c, n in counts.items() if n == top)
    return {winner: 1.0}, "category_plurality"


async def search_products(
    db: AsyncConnection | AsyncSession,
    q: str,
    *,
    claims: Sequence[Claim] = (),
    category: str | None = None,
    limit: int = MAX_LIMIT,
) -> list[SearchHit]:
    """Search the catalogue. Neutral about the kitchen: only the given claims and category
    filter (§7.1). An empty query with filters returns the filtered set by product id."""
    # Once the claim is a filter, its words in the text only match noise ("free").
    query = parse_query(q, ignore=frozenset(w for c in claims for w in CLAIM_WORDS[c]))
    limit = max(1, min(limit, MAX_LIMIT))
    has_text = bool(query.terms or query.amounts)
    if not has_text and not claims and category is None:
        return []

    await db.execute(
        text("SELECT set_config('pg_trgm.word_similarity_threshold', :t, true)"),
        {"t": str(TRIGRAM_THRESHOLD)},
    )
    words = query.trigram_words
    statement = _candidates_sql(len(words), bool(claims), category is not None, not query.terms)
    params: dict[str, object] = {"fts": query.fts, "words": words, "pool": POOL_SIZE}
    params |= {f"w{i}": w for i, w in enumerate(words)}
    if claims:
        params["claims"] = sorted({CLAIM_IDS[c] for c in claims})
    if category is not None:
        params["category"] = category
    rows = (await db.execute(statement, params)).all()
    candidates = [
        _Candidate(
            r.id,
            f"{r.name_fi} {r.name_en}",
            r.category_id,
            r.category_name,
            float(r.fts),
            tuple(r.sims),
        )
        for r in rows
    ]
    if not has_text:
        return [
            SearchHit(c.product_id, Decimal(0), ("filter",))
            for c in sorted(candidates, key=lambda c: c.product_id)
        ][:limit]

    base = {c.product_id: W_COVERAGE * _coverage(query, c) + W_FTS * c.fts for c in candidates}
    by_base = sorted(candidates, key=lambda c: (-round(base[c.product_id], 4), c.product_id))
    if category is None:
        inferred, how = await _infer_categories(db, query, by_base)
    else:
        inferred, how = {}, ""

    hits: list[SearchHit] = []
    for c in candidates:
        matched_on = ["fts"] if c.fts > 0 else []
        if any(s >= TRIGRAM_THRESHOLD for s in c.sims):
            matched_on.append("trigram")
        score = base[c.product_id]
        if c.category_id in inferred:
            score += W_CATEGORY * inferred[c.category_id]
            matched_on.append(f"{how}:{c.category_id}")
        mods = unasked_modifiers(f"{c.name} {c.category_name}", query)
        if mods:
            score -= W_MODIFIER * len(mods)
            matched_on.extend(f"modifier:{m}" for m in mods)
        hits.append(SearchHit(c.product_id, round(Decimal(score), 4), tuple(matched_on)))
    hits.sort(key=lambda h: (-h.score, h.product_id))
    return hits[:limit]
