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
from app.search.spelling import Vocabulary
from app.search.text import Query, name_tokens, parse_query, unasked_modifiers
from app.search.vectors import MODEL as EMBED_MODEL
from app.search.vectors import query_key
from app.settings import get_settings

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
# Query words at least this long count fully when found inside a name word (0: off).
COMPOUND_MIN_LENGTH = 5
# How much a word that names the product's category counts toward coverage (0: off).
CATEGORY_TERM_COVERAGE = 0.6
# Weight of the cosine similarity to the cached query vector (0: vectors off), and how many
# nearest products the vector adds as candidates.
W_VECTOR = 1.0
VECTOR_CANDIDATES = 50
# Correct words that are in no product name (spelling.py).
SPELLING = True
PLURALITY_POOL = 20
# The plurality category is inferred only if it holds at least this share of the pool.
PLURALITY_MIN_SHARE = 0.0
# A brand in the query means a specific product, not a vague kind: no plurality guess.
PLURALITY_WITH_BRAND = False

_WORDS = bindparam("words", type_=ARRAY(Text))


def _candidates_sql(
    trigram_paths: Sequence[int],
    has_claims: bool,
    has_category: bool,
    match_all: bool,
    has_vector: bool = False,
):
    """Each match path is its own indexed lookup (an OR across them would scan every row).
    The pool is cut by how many paths a product matched before the costly per-word
    similarities are computed, so a long query does not score thousands of rows."""
    if match_all:
        matched = "SELECT id, 0 AS hits FROM products"
    else:
        paths = [
            "SELECT id FROM products, q WHERE search_fi @@ q.qfi",
            "SELECT id FROM products, q WHERE search_en @@ q.qen",
        ] + [f"SELECT id FROM products WHERE :w{i} <% search_trgm" for i in trigram_paths]
        if has_vector:
            paths.append("SELECT id FROM products WHERE id = ANY(:vector_ids)")
        matched = (
            "SELECT id, count(*) AS hits FROM (\n            "
            + "\n            UNION ALL ".join(paths)
            + "\n        ) AS u GROUP BY id"
        )
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
    pool AS (
        SELECT p.id, p.name_fi, coalesce(p.name_en, '') AS name_en, p.category_id,
               p.search_trgm,
               ts_rank_cd(p.search_fi, q.qfi, 32) + ts_rank_cd(p.search_en, q.qen, 32) AS fts
        FROM products p JOIN matched m USING (id), q
        WHERE {where}
        ORDER BY m.hits DESC, fts DESC, p.id
        LIMIT :pool
    )
    SELECT pool.id, pool.name_fi, pool.name_en, pool.category_id,
           cat.name_fi AS category_name, pool.fts,
           ARRAY(SELECT word_similarity(w, pool.search_trgm) FROM unnest(:words) AS w) AS sims
    FROM pool JOIN categories cat ON cat.id = pool.category_id
    """
    ).bindparams(_WORDS)
    if has_claims:
        statement = statement.bindparams(bindparam("claims", type_=ARRAY(Text)))
    if has_vector:
        statement = statement.bindparams(bindparam("vector_ids", type_=ARRAY(Text)))
    return statement


# Vectors (spec §7.11): nearest products to the query vector add candidates, and the
# cosine similarity adds W_VECTOR × similarity to the score. W_VECTOR 0 turns them off.
_QUERY_VECTOR = text(
    "SELECT embedding::text FROM query_embeddings WHERE query_text = :q AND model = :model"
)
_NEAREST = text(
    """
    SELECT product_id FROM product_embeddings
    ORDER BY embedding <=> CAST(:qv AS vector), product_id
    LIMIT :n
    """
)
_VECTOR_SIMS = text(
    """
    SELECT product_id, 1 - (embedding <=> CAST(:qv AS vector)) FROM product_embeddings
    WHERE product_id = ANY(:ids)
    """
).bindparams(bindparam("ids", type_=ARRAY(Text)))


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


# The catalogue's words for spelling correction, built once per database and process.
# A catalogue reload adds words only after a restart; until then they are simply not
# corrected towards, and exact words still match.
_VOCABULARIES: dict[str, Vocabulary] = {}


async def _vocabulary(db: AsyncConnection | AsyncSession) -> Vocabulary:
    key = str(db.bind.engine.url) if isinstance(db, AsyncSession) else str(db.engine.url)
    if key not in _VOCABULARIES:
        rows = await db.execute(text("SELECT name_fi, coalesce(name_en, '') FROM products"))
        _VOCABULARIES[key] = Vocabulary.from_names(f"{fi} {en}" for fi, en in rows)
    return _VOCABULARIES[key]


async def _query_vector(db: AsyncConnection | AsyncSession, q: str) -> str | None:
    """The cached query vector; with SEARCH_VECTORS=live a missing one is embedded now."""
    mode = get_settings().search_vectors
    if mode == "off":
        return None
    cached = await db.scalar(_QUERY_VECTOR, {"q": query_key(q), "model": EMBED_MODEL})
    if cached is not None or mode != "live":
        return cached
    from app.search.embeddings import embed_query_live  # httpx and the client: only when live

    engine = db.bind.engine if isinstance(db, AsyncSession) else db.engine
    return await embed_query_live(engine, q)


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


def _coverage(
    query: Query, candidate: _Candidate, category_terms: Sequence[float] | None = None
) -> float:
    """Mean over the buyer's words of how well the name covers each (synonyms count). A word
    that names the product's category counts too, at CATEGORY_TERM_COVERAGE: "viinerit" is
    a category, not a word in the names of the pastries in it."""
    scores: list[float] = []
    sims = iter(candidate.sims)
    names = name_tokens(candidate.name)
    for i, term in enumerate(query.terms):
        best = max(next(sims) for _ in term.alternatives)
        # A word inside a compound is a full match: "maito" in "kevytmaito".
        if COMPOUND_MIN_LENGTH and any(
            len(a) >= COMPOUND_MIN_LENGTH and any(a in n for n in names) for a in term.folded
        ):
            best = 1.0
        if category_terms is not None:
            best = max(best, CATEGORY_TERM_COVERAGE * category_terms[i])
        scores.append(best)
    if query.amounts:
        scores.extend(1.0 if a in names else 0.0 for a in query.amounts)
    return sum(scores) / len(scores) if scores else 0.0


def _term_scores(query: Query, sims: Sequence[float]) -> list[float]:
    it = iter(sims)
    return [max(next(it) for _ in term.alternatives) for term in query.terms]


async def _category_terms(
    db: AsyncConnection | AsyncSession, query: Query, brands: set[str]
) -> dict[str, list[float]]:
    """Per category, how well its name matches each of the buyer's words (brand words 0)."""
    if not query.terms:
        return {}
    raw_words = [a for t in query.terms for a in t.alternatives]
    rows = (
        await db.execute(_CATEGORY_MATCHES, {"words": query.trigram_words, "raw_words": raw_words})
    ).all()
    out = {}
    for category_id, sims, whole in rows:
        per_word = [1.0 if w else CATEGORY_PARTIAL * s for s, w in zip(sims, whole, strict=True)]
        scores = _term_scores(query, per_word)
        out[category_id] = [
            0.0 if t.folded[0] in brands else v for t, v in zip(query.terms, scores, strict=True)
        ]
    return out


def _infer_categories(
    query: Query,
    brands: set[str],
    category_terms: dict[str, list[float]],
    ranked: list[_Candidate],
) -> tuple[dict[str, float], str]:
    """Categories whose name matches the query; else the plurality of the best matches."""
    kept = [i for i, t in enumerate(query.terms) if t.folded[0] not in brands]
    if kept:
        named: dict[str, float] = {}
        for category_id, all_scores in category_terms.items():
            scores = [all_scores[i] for i in kept]
            if max(scores) >= CATEGORY_NAME_THRESHOLD:
                named[category_id] = sum(scores) / len(scores)
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
    ignore = frozenset(w for c in claims for w in CLAIM_WORDS[c])
    vocabulary = await _vocabulary(db) if SPELLING else None
    query = parse_query(q, ignore=ignore, vocabulary=vocabulary)
    limit = max(1, min(limit, MAX_LIMIT))
    has_text = bool(query.terms or query.amounts)
    if not has_text and not claims and category is None:
        return []

    await db.execute(
        text("SELECT set_config('pg_trgm.word_similarity_threshold', :t, true)"),
        {"t": str(TRIGRAM_THRESHOLD)},
    )
    words = query.trigram_words
    brands = set(
        (await db.scalars(_BRAND_WORDS, {"words": [t.folded[0] for t in query.terms]})).all()
    )
    # Brand words are whole words in the names, so full-text search finds them; their
    # trigram lookup would only cost time ("valio" checks 1,600 rows).
    term_of_word = [t for t in query.terms for _ in t.alternatives]
    paths = [i for i, t in enumerate(term_of_word) if t.folded[0] not in brands]
    query_vector = await _query_vector(db, q) if W_VECTOR > 0 and query.terms else None
    statement = _candidates_sql(
        paths, bool(claims), category is not None, not query.terms, query_vector is not None
    )
    params: dict[str, object] = {"fts": query.fts, "words": words, "pool": POOL_SIZE}
    params |= {f"w{i}": words[i] for i in paths}
    if query_vector is not None:
        nearest = await db.scalars(_NEAREST, {"qv": query_vector, "n": VECTOR_CANDIDATES})
        params["vector_ids"] = list(nearest.all())
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

    category_terms = await _category_terms(db, query, brands)
    use_terms = CATEGORY_TERM_COVERAGE > 0
    base = {
        c.product_id: W_COVERAGE
        * _coverage(query, c, category_terms.get(c.category_id) if use_terms else None)
        + W_FTS * c.fts
        for c in candidates
    }
    by_base = sorted(candidates, key=lambda c: (-round(base[c.product_id], 4), c.product_id))
    if category is None:
        inferred, how = _infer_categories(query, brands, category_terms, by_base)
    else:
        inferred, how = {}, ""

    vector_sims: dict[str, float] = {}
    if query_vector is not None and candidates:
        rows = await db.execute(
            _VECTOR_SIMS, {"qv": query_vector, "ids": [c.product_id for c in candidates]}
        )
        vector_sims = {pid: float(sim) for pid, sim in rows}

    hits: list[SearchHit] = []
    for c in candidates:
        matched_on = ["fts"] if c.fts > 0 else []
        if any(s >= TRIGRAM_THRESHOLD for s in c.sims):
            matched_on.append("trigram")
        score = base[c.product_id]
        if c.category_id in inferred:
            score += W_CATEGORY * inferred[c.category_id]
            matched_on.append(f"{how}:{c.category_id}")
        if c.product_id in vector_sims:
            score += W_VECTOR * vector_sims[c.product_id]
            matched_on.append(f"vector:{vector_sims[c.product_id]:.2f}")
        mods = unasked_modifiers(f"{c.name} {c.category_name}", query)
        if mods:
            score -= W_MODIFIER * len(mods)
            matched_on.extend(f"modifier:{m}" for m in mods)
        hits.append(SearchHit(c.product_id, round(Decimal(score), 4), tuple(matched_on)))
    hits.sort(key=lambda h: (-h.score, h.product_id))
    return hits[:limit]
