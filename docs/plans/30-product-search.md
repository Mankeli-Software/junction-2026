# #30 Product search: spec

Status: agreed 2026-11-14 (Miska), decisions in §7. Issue: #30. Refs: `technical-plan.md` §5.2, §5.3, §9.1; `valio-api-analysis.md` §11; `vision.md` §10.

**Goal**: deterministic local product search over the catalogue in Postgres (#29). It feeds two callers: the engine's resolve step (through the services that build `EngineInput`) and the `search_products` tool. No model and no Valio API call at search time.

**Done when**: tests show Finnish and English queries for the milk scenario, a typo and a misheard compound word all return the expected products; the same query on the same data always returns the same ids in the same order.

## 1. What the data tells us

Profiled on 2026-11-14 on a laptop database with the full product file (17,546 products).

| Fact | Consequence |
|---|---|
| Every product has `name_fi`; 17,544 have `name_en`. Names carry brand, size and attributes in one string: "Valio kevytmaito 1 l laktoositon UHT", "Valio semi skimmed milk 1 l lactose free UHT" | Search the names in both languages. English queries mostly work without a synonym list |
| **Finnish compounds are not split by the `finnish` Snowball stemmer.** `to_tsvector('finnish', 'kevytmaitojuoma')` gives `kevytmaitojuom`, so the query `maito` does **not** match it in full-text search | Full-text search alone misses most milks. Trigram matching on the name is needed for recall, not only for typos (§3.2) |
| `word_similarity('maito', 'Valio kevytmaitojuoma 1 l laktoositon')` = 0.5; the typo `laktositon` vs `laktoositon` = 0.77; the split `kevyt maito` vs `kevytmaito` = 0.64 | `pg_trgm` word similarity covers compounds, typos and split compounds with one threshold |
| The stemmer handles inflection: `maidot`, `maitoa` give `maido`, `maito` | Full-text search stays useful for inflected and English words and for ranking |
| Claims: 24 distinct `claim_id`s. `FREE_FROM_LACTOSE` 4,178; `LOW_LACTOSE` 321 (must not count); `FREE_FROM_GLUTEN` 3,047 (+2 rows with qualifier `DIET`, same `claim_id`); `VEGAN` 2,959; `VEGETARIAN` 2,358 | Map the contract's `Claim` enum to `claim_id` (§3.1) |
| Categories are flat codes (349), with Finnish and English names; `10400` "Maidot ja piimät / Milk and sour milk drinks" holds 35 lactose-free products | Category filter is an exact match. Category names go into the searchable text |
| **Spoken queries are vague.** "naudan jauheliha" matches 23 products: raw beef mince in the `Jauheliha` category (Atria 10 % 2 kg, Snellman 17 % 2 kg, …), but also cooked (`kypsä`), browned (`ruskistettu`), frozen (`pakaste`), beef and pork mixes (`nauta-sika`) and burger patties. 69 lactose-free products have "maito" in the name, including coffee milk and portion cups | Ranking must put the typical product first (§3.4), and the next hits are the options the agent offers |
| Names carry the attributes: fat % (`10%`), pack size (`2kg`, `6x400g`), brand, state (`kypsä`, `pakaste`, `UHT`). There are thousands of distinct attribute words | Attributes are not structured. A refinement ("17 %", "Snellmanin") is a new, narrower search, so numbers, percentages and brands must match exactly (§3.5) |
| Postgres 18 locally (pgvector image); `pg_trgm`, `unaccent` and `vector` are installed on both laptop and `junction_demo` | No new extension |

## 2. Scope

1. **Migration `0003_product_search`**: search columns and indexes on `products` (§4).
2. **Fill the columns** at the end of the catalogue load (#29 loader), and once in the migration for an already loaded database.
3. **Search module** `api/app/search/` with one function used by both callers (§5).
4. **Synonym list**: short, committed, reviewed by hand (§3.3).
5. **Tests**: fixture-based in CI, plus an evaluation set against the full catalogue that runs locally (§6).

Not in scope: price and availability for the hits (#31 and the services); the `search_products` tool and REST endpoint wiring (#43, #45); images (#33); a vector index on names (plan §5.3, only if tests show misses).

## 3. Matching

### 3.1 Hard filters first

Applied in SQL before any scoring:

- **Claims**: every requested claim must be present in `product_claims`:

  | `Claim` | `claim_id` |
  |---|---|
  | `lactose_free` | `FREE_FROM_LACTOSE` (never `LOW_LACTOSE`, never the name) |
  | `gluten_free` | `FREE_FROM_GLUTEN` |
  | `vegan` | `VEGAN` |
  | `vegetarian` | `VEGETARIAN` |

  The claim filter only narrows the candidates. The engine still applies the kitchen's allergen rules to every product it chooses (`policy/allergen_rules.yaml`).
- **Category**: `category_id = :category` when given.

### 3.2 Text match

The query is normalised (lower case, trimmed, numbers and units such as `1 l`, `10l`, `dl` kept as words). A product matches if **any** of these hold:

- **Full-text**: `search_fi @@ websearch_to_tsquery('finnish', q)` or `search_en @@ websearch_to_tsquery('english', q)`, with `or` between the query words, so one extra word does not drop a product.
- **Trigram**: for each query word of three or more letters, `word <% search_trgm` (word similarity above the threshold, *proposed* 0.45). This is what finds `maito` inside `kevytmaitojuoma`, and `laktositon`.

### 3.3 Synonyms

A short committed list, expanded on the query side only: `api/app/search/synonyms.yaml`, word → extra words. Examples: `milk` → `maito`; `kevari` → `kevytmaito`; `rasvaton` → `skimmed`. It exists for spoken and colloquial words that are in neither name. English kitchen words are mostly covered by `name_en` already, so the list stays small.

### 3.4 Inferring the typical product

A voice query names a kind of product, not a product. The engine picks a default from the shortlist and the agent offers the alternatives (§7.8), so the top of the list must be the product a kitchen most likely means. Two signals, both deterministic:

- **Category inference.** The query's category is the category whose Finnish or English name matches the query (`Jauheliha` for "naudan jauheliha"). When no category name matches, it is the category holding most of the strong text matches (a plurality vote over the top 20, ties broken by category id). Products in the inferred category get a boost. An explicit `category` filter replaces the inference.
- **Modifier penalty.** `api/app/search/modifiers.yaml` lists words that change what a product is: `kypsä`, `ruskistettu`, `pakaste`, `kahvi`, `kaakao`, `suklaa`, `annos`, `pihvi`, `burger`, … A product whose name contains a modifier the query does not contain is pushed down. When the buyer says "kypsä jauheliha", the cooked ones are not penalised. The list starts at about 30 words and grows only through the evaluation harness.

Refinements found while tuning (§8):

- The category name match uses the Finnish and English stemmers first (a whole-word match counts fully) and trigram similarity inside a longer word only at 0.8, and only the best-matching categories within 0.05 are boosted. Otherwise "tomaatti" boosts "Tomaattisäilykkeet" instead of "Tomaatit".
- **Brand words** (any word that is a product's brand) are left out of category inference, and a query with a brand gets no plurality guess: a brand means a specific product, not a vague kind. One category is even named "Valio kermat".
- Modifiers are checked against the category name too, so a product in "…lihapakasteet" counts as frozen even when its own name does not say so.
- When a claim is passed, the words that say the same thing ("laktoositon", "lactose", "free") are dropped from the text; they only matched noise.

The inferred category and any penalties are returned in `matched_on`, so the decision trace can say why a product came first.

### 3.5 Refinement through the names

Attributes stay in the product names; there is no structured attribute table. When the buyer answers an offer ("the 17 % one", "Snellman", "the 3 kg pack"), the agent searches again with the extra words. So:

- Numbers, percentages and units are kept as tokens and normalised (`17 %` = `17%`, `2 kg` = `2kg`, `0,5 l` = `0.5 l`), and an exact match on them weighs more than a fuzzy one.
- Brand words match exactly or by trigram (`Snellmanin` finds `Snellman`).

## 4. Columns and indexes (migration `0003_product_search`)

On `products`:

| Column | Type | Content |
|---|---|---|
| `search_fi` | `tsvector` | `setweight(to_tsvector('finnish', name_fi), 'A') ‖ setweight(to_tsvector('finnish', category name_fi), 'C')`. No brand: it is already in the name, and counting it twice made "Valio" outrank the product words |
| `search_en` | `tsvector` | The same with `name_en` and category `name_en`, config `english` |
| `search_trgm` | `text` | `immutable_unaccent(lower(name_fi ‖ ' ' ‖ name_en))` |

- Indexes: GIN on `search_fi`, GIN on `search_en`, GIN `gin_trgm_ops` on `search_trgm`, and a btree on `immutable_unaccent(lower(brand))` for the brand check.
- Each match path (full-text Finnish, full-text English, one trigram lookup per word) is its own indexed lookup, joined with `UNION`; an `OR` across them scanned every row (130 ms instead of 11 ms).
- `immutable_unaccent(text)`: an `IMMUTABLE` SQL wrapper around `unaccent('unaccent', …)`, so it can be used in the index and in the query. Full-text columns keep `ä` and `ö`, because the Finnish stemmer needs them.
- The columns are filled by one `UPDATE products … FROM categories` at the end of the catalogue load (inside the same transaction), not as generated columns, because they need the category names from another table. The migration runs the same `UPDATE` once so an existing database does not need a reload.

## 5. Interface

```python
# api/app/search/__init__.py
async def search_products(
    db: AsyncConnection | AsyncSession,
    q: str,
    *,
    claims: Sequence[Claim] = (),
    category: str | None = None,
    limit: int = 20,
) -> list[SearchHit]: ...

@dataclass(frozen=True)
class SearchHit:
    product_id: str
    score: Decimal          # rounded to 4 places, so the order never depends on float noise
    matched_on: tuple[str, ...]  # "fts_fi", "fts_en", "trigram", "synonym": for the decision trace
```

- **Score**: `W_COVERAGE × coverage + W_FTS × (ts_rank_cd(search_fi) + ts_rank_cd(search_en))`, plus `W_CATEGORY` for the inferred category, minus `W_MODIFIER` per unasked modifier (§3.4); rounded to 4 decimals. **Order by score descending, then `product_id` ascending.** Coverage is the mean over the buyer's words of the best trigram word similarity (synonyms count), with a word of 5 or more letters found inside a name word counting fully ("maito" in "kevytmaito"); amounts count as exact token matches. Current weights: coverage 1.0, full-text 0.5, category 0.3, modifier 0.3 per word. The weights live in `app/search/search.py` and are changed only through §6.2 (`--param NAME=VALUE` tries one without editing the code).
- `limit` up to 20. The services take the top 20 as the shortlist for price and availability (#31); the tool shows 10 by default (`SearchProductsRequest.limit`).
- Only product ids and scores. The services load `ProductRecord`s and offers, and build `ProductHit`s for the tool. `api/app/schemas/` is not changed.
- An empty query with a category or claims returns that filtered set ordered by `product_id`. An empty query with no filters returns nothing.

## 6. Tests and evaluation

Search quality is tuned by measurement, not by feel. Every change to matching, weights, threshold or synonyms is run against a large scenario set, and the report is compared with the last saved baseline.

### 6.1 Unit tests in CI (fixture)

Extend `api/tests/fixtures/products_sample.json` with about 10 distractors (coffee milk, chocolate milk drink, oat drink, cream, sour milk, a `LOW_LACTOSE` milk) so ranking and filters are tested for real. Cases:

- `maito` + `lactose_free` returns the lactose-free milks and never the `LOW_LACTOSE` one.
- `lactose free milk` (English) returns the same set.
- Typo `laktositon maito`, compound split `kevyt maito`, and the misheard `kevyt maitojuoma` find 464306.
- Category filter, claim filter with no text, empty query.
- Determinism: the same query twice gives identical results.

### 6.2 Evaluation harness (full catalogue, local)

`uv run python -m app.search.eval [--set NAME] [--save-baseline]` runs every scenario against the loaded catalogue and prints a report. It is not a pass/fail CI test, because the full catalogue is not in CI.

**Scenario sets** in `api/tests/search_scenarios/`, one YAML file each. A scenario is a query plus optional claims and category, and graded expectations:

- `typical`: the products a kitchen most likely means (raw beef mince for "naudan jauheliha"). Rank 1 should be one of these.
- `acceptable`: same kind, other variant (another fat %, brand or pack size). Fine as an offered option.
- `wrong_kind`: matches the words but is not what was asked (cooked, frozen, coffee milk). Must not appear in the top 5.

| Set | Size | Source | What it tests |
|---|---|---|---|
| `core` | ~60 | Hand-written: vague spoken requests as a kitchen buyer says them ("laktoositon maito", "naudan jauheliha", "kermaa", "lohifileetä"), in Finnish and English, across the main categories (dairy, meat, fish, vegetables, dry goods, frozen, bakery, cleaning), plus refinements ("naudan jauheliha 17 %", "Snellmanin jauheliha"). Includes the milk scenario | The demo and the common case. Every case must pass |
| `noisy` | ~300 | Generated from `core` by rules: one-letter typos, dropped double vowels (`laktositon`), split and joined compounds (`kevyt maito`, `kevytmaito`), missing `ä`/`ö`, inflected forms (`maitoa`, `voita`), number words (`yksi litra`). The generator is seeded, so the set is the same on every run | Speech-to-text and typing errors |
| `recipes` | ~250 product names, thousands of ingredient rows | `data/recipe-product-map.json` (only `high` and `reviewed` mappings): the recipe product name and the recipes' own ingredient texts. A scenario passes when **any** of the mapped Aimo ids (one per pack size) is found | A large, independently labelled set with real inflection and brand names |
| `negative` | ~20 | Queries that must **not** return a product: `LOW_LACTOSE` for lactose-free, sour milk for "maito", chocolate milk for "maito" in the top 5 | Precision for the cases that matter on stage |

**Metrics per set**: hit rate in the top 20 (the shortlist), hit rate in the top 5 and at rank 1, mean reciprocal rank, and query time p50 and p95. For graded scenarios also: rank 1 is `typical`, and no `wrong_kind` in the top 5. The report lists every miss with the query, the expected id and what came back instead.

**Baseline**: `--save-baseline` writes `api/tests/search_scenarios/baseline.json`. Every later run prints the difference: newly fixed and newly broken scenarios per set. A tuning change is kept only if it fixes more than it breaks, and `core` never regresses.

**Targets**: `core` 100% in the top 20 and at least 90% in the top 5, rank 1 `typical` in at least 90%, and no `wrong_kind` in the top 5 in at least 95%; `noisy` and `recipes` at least 90% in the top 20; p95 under 100 ms.

## 7. Decisions (2026-11-14, Miska)

1. **Search is neutral about the kitchen.** It applies only the claims and category it is asked for. The kitchen's allergen and diet exclusions are applied by the engine alone, so safety logic lives in one place and the decision trace shows what was blocked and why. This holds for the `search_products` tool too.
2. **Substitute candidates come from the services.** When the hits may all be blocked, the quote service (#45) adds substitute candidates to `EngineInput`: the hits' `product_substitutions` plus a second search in the same category. Search stays one plain function. Hand-off noted on #45 and #39.
3. **#30 delivers the module only**: migration, search module, synonyms and tests. The `search_products` tool and its REST twin are wired in #43 and #45, which call `app.search.search_products` and add price and availability from #31.
4. **Synonyms** live in `api/app/search/synonyms.yaml`. They are search tuning, not a business rule, so they stay out of `policy/`.
5. **Threshold and weights** start from the proposed values (§3.2, §5) and are tuned only through the evaluation harness (§6.2).
6. **Scenario sets**: the four sets in §6.2, with rule-generated errors only (no recorded speech for now). Claude drafts the `core` set from the real catalogue, with every product id checked against the database; Miska reviews it before the first baseline.
7. **Quality bar for closing #30**: the targets in §6.2.
8. **Vague requests: pick a default, offer the options.** For "naudan jauheliha 10 kg" the buyer hears the default and what else exists in one turn ("Atria naudan jauheliha 10 %, 2 kg. Also 17 % or Snellman, should I change it?"), and the confirmation page shows the assumption. The default and the options come from the top of the search ranking. This narrows `technical-plan.md` §4.2 ("ambiguous matches go to the buyer") for matches of the same kind; it is for the engine (#36, #39) and the prompt (#53) to carry out, and their owners are told on those issues.
9. **Typical-product signals**: category inference and the modifier penalty (§3.4). Recipe popularity and name length are not used.
10. **No structured attributes.** Fat %, pack size, brand and state stay in the names; there are too many to structure. Refinement is a new search with the extra words (§3.5).
11. **Vectors with Gemini embeddings: kept, at `W_VECTOR` 1.0.** Each product's Finnish and English name and its category are embedded once (`gemini-embedding-001`, 768 dimensions) into `product_embeddings` (migration `0012`, HNSW index). The 50 nearest products add candidates, and `W_VECTOR × cosine similarity` adds to the score; text matching still decides amounts, brands and claims. Query vectors are cached per query text in `query_embeddings`, so the same text always gives the same vector. `SEARCH_VECTORS`: `live` (default) embeds a query that is not cached yet, with a 2 s timeout and text-only search if that fails; `cache` never calls the API (the stage demo, with its queries embedded beforehand); `off` is text-only (the tests). Run `python -m app.search.embeddings products` after each catalogue load; it embeds only new or changed products.

## 8. Tuning log

Every change was measured on all four sets against the saved baseline (`python -m app.search.eval`). Kept changes only.

| Step | core pass / rank 1 / clean 5 | noisy top 20 | recipes pass / top 20 | p95 |
|---|---|---|---|---|
| First text-only version | 78% / 84% / 82% | 86% | 70% / 93% | 364 ms |
| Indexed `UNION` lookups | same | same | same | 56 ms |
| Stemmed category names, more modifiers, `ground` synonym, scenario fixes | 92% / 95% / 96% | 89% | 64% / 88% | 61 ms |
| No brand in full-text columns; brand words out of category inference; no plurality guess with a brand | 93% / 96% / 96% | 89% | 67% / 92% | 60 ms |
| A word of 5+ letters inside a name word counts fully | 95% / 96% / 98% | 89% | 67% / 92% | 60 ms (recipes 191 ms) |
| Spelling correction against the catalogue's words; a word naming the product's category counts at 0.6 | 97% / 99% / 98% | 97% | 68% / 92% | 51 to 223 ms |
| Pool cut by match count before scoring; no trigram lookup for brand words; tokenizer accepts any letter | 97% / 99% / 98% | 96% | 68% / 93% | under 100 ms on every set |
| Inflected known word before splitting ("kaurahiutaleet" -> "kaurahiutale") | 97% / 99% / 98% | 96% | 69% / 93% | under 100 ms |
| Gemini vectors at `W_VECTOR` 1.0 | 99% / 100% / 98% | 100% | 80% / 96% | under 100 ms |

The catalogue-wide sets added later (every category, about 2,500 scenarios) moved with vectors as follows: `categories` 87% -> 90% pass, `specific` 84% -> 89%, `vague` rank 1 90% -> 88% but top 5 95% -> 96% and top 20 98% -> 99%.

Tried and dropped: `W_VECTOR` 0.3 and 0.6 (slightly below 1.0 on every set), full-text weight 0.25 and 0.1 (noisy up, recipes down), weighting categories by their share of the top matches (broke two chicken scenarios), a modifier penalty of 0.5 or 0.8 (56 to 70 scenarios broken: real products carry incidental modifier words).

Every target in §6.2 is met. Weakest remaining: `recipes` rank 1 (80%; long product names with several pack sizes) and one-word `vague` queries at rank 1 (88%).
