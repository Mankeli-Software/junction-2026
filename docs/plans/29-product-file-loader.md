# #29 Product file loader and catalogue tables: spec

Status: draft for review, 2026-11-14 (Miska). Issue: #29. Refs: `technical-plan.md` §5.1, §5.2, `valio-api-analysis.md` §5, §11, §13.

**Goal**: the whole catalogue in Postgres, loaded from the static product file, never from the live API. Every laptop database and `junction_demo` hold the same 17,546 products with units, allergens, claims and labels.

**Done when**: a fresh laptop database and `junction_demo` both hold every product with units, allergens and claims; the loader can be re-run and gives the same counts; CI tests the loader on a small committed sample.

## 1. What the product file actually contains

Profiled on 2026-11-14 from a fresh download (`/api/products/download`, 87,077,467 bytes, one JSON array).

| Fact | Count | Consequence |
|---|---|---|
| Products | 17,546, ids unique, all numeric strings, none `deleted` | `products.id` is `text`, matching `product_id: str` in the contract (§4.1) and the API |
| Categories used | 349, all present in `data/valio_category_names.csv` | Foreign key from `products.category_id` holds |
| Names | `fi` 17,546, `en` 17,544, `sv` 16,100, a few `es`/`nl` | `name_fi` not null; `name_en`, `name_sv` nullable. Two products lack English |
| `salesUnit` / `baseUnit` | Always present in `units[]`; base unit always has `sizeInBaseUnits` 1; 6,622 products sell in a unit other than the base | Units table holds the whole hierarchy with both flags |
| `units[]` | 44,357 rows, 23 unit codes (`KI`, `ST`, `PAL`, `KRS`, `PAK`, …), `gtin` on 35,881 | |
| `unitConversions` | 14,474 products, **at most one row each**, typed `BASE_UNIT_OR_EACH` (8,215), `CASE` (6,249), `PALLET` (10). Not keyed by unit code | The loader must resolve which unit the row describes (§3.3) |
| Measure units in conversions | `GRM`, `KGM`, `LTR`, `MLT`, `CLT`, plus `H87` (piece), `PTN`, `MTR` and dirty values like `KGM H87` | Normalise to grams and millilitres where known; the rest is an anomaly |
| `classifications` | Missing on 11 products. Groups: `allergen`, `nonAllergen`, `nutritionalClaim`, `packagingMarkedLabel`, `packaging` (always empty), nutrition groups | |
| Allergens | `CONTAINS` 15,610, `MAY_CONTAIN` 9,956, `UNDECLARED` 303, `FREE_FROM` 68,597. Every code is in `data/gs1_allergen_codes.csv` | 2 products list a code as both contained and free-from (468044 `AM`; 469429 `AM`, `AN`) |
| Claims | `{id, synkkaId, unit}`, e.g. `FREE_FROM_LACTOSE` / `LACTOSE` / `FREE_FROM` (4,178), `VEGAN` / `VEGAN` / `DIET` (2,959). 24 distinct | Store all three fields; `id` is the stable key |
| Labels | 19 ids. Three are temperature markers (`warmTemperature`, `coolTemperature`, `freezeTemperature`), the rest are certificates (Blue Swan, Finnish heart, EU organic, MSC, …) | Store all; mark the three temperature markers as `kind = 'temperature'` |
| Substitutions | 196 products, 250 pairs, all targets exist | |
| `salesUnitGtin` | Missing on 159; differs from `synkkaData.gtin` on 9,788 (Synkka's GTIN is usually the base unit's) | Store both |
| Other | `temperatureCondition` missing on 61; `variableUnit` null on 3,068; `vatCode` dirty (don't use, analysis §5); `deposits[]` 576 rows | |

## 2. Scope

1. **Download command**: fetch `/api/products/download` once with `curl -L` semantics (follow redirects, `X-API-Key` from `VALIO_API_KEY`, User-Agent `curl/8.4.0`) to `data/valio-products.json`, which is git-ignored. Skips the download when the file exists unless `--force`.
2. **Migration `0002_catalogue`**: the tables in §3.
3. **Loader** for the product file, `valio_category_names.csv` and `gs1_allergen_codes.csv`, in one transaction, re-runnable, printing counts and anomalies (§4).
4. **Tests** on a small committed sample (§5).
5. **Run on `junction_demo`** once #28 has the VM up (§6).

Not in scope: search columns and indexes (`tsvector`, trigram) belong to #30; `product_images` to #33 (done in #108, which fills it from the catalogue loader); recipes to #34; nutrition, ingredients and marketing text stay in `raw` only.

## 3. Tables (migration `0002_catalogue`)

SQLAlchemy 2 models in `api/app/models/catalogue.py`, so #30, #31 and the services import one definition. `api/app/schemas/` (Pydantic, #26) is not touched.

### 3.1 Reference tables

`categories`

| Column | Type | From |
|---|---|---|
| `id` | text PK | `category` |
| `name_en`, `name_fi` | text not null | CSV |
| `name_fi_source`, `confidence`, `note`, `shop_path_fi` | text | CSV |
| `mandate_group` | text not null | CSV (`dairy`, `non_food`, …; 15 values) |

`allergen_codes`

| Column | Type | From |
|---|---|---|
| `code` | text PK | `code` |
| `gs1_label`, `gs1_uri` | text not null | CSV |
| `eu_group` | text | `eu_1169_2011_group` (null for non-EU codes) |
| `name_fi`, `name_fi_partitive`, `voice_note_fi`, `note` | text | CSV |

The CSV's count columns (`contains`, `may_contain`, …) are statistics, not loaded.

### 3.2 `products`

| Column | Type | From |
|---|---|---|
| `id` | text PK | `id` |
| `name_fi` | text not null | `synkkaData.names[fi]` |
| `name_en`, `name_sv` | text | `synkkaData.names` |
| `category_id` | text not null FK `categories` | `category` |
| `sales_unit`, `base_unit` | text not null | `salesUnit`, `baseUnit` |
| `sales_unit_gtin` | text | `salesUnitGtin` |
| `synkka_gtin` | text | `synkkaData.gtin` |
| `allowed_lot_size` | numeric not null | `allowedLotSize` |
| `temperature_condition` | smallint | `temperatureCondition` |
| `min_temperature`, `max_temperature` | numeric | `synkkaData` |
| `variable_unit` | boolean | `synkkaData.variableUnit` (null kept as null) |
| `vendor_name` | text not null | `vendorName` |
| `brand` | text | `synkkaData.brand` |
| `country_of_origin` | text | `countryOfOrigin` |
| `has_classifications` | boolean not null | false for the 11 products without them |
| `source_updated_at` | timestamptz | `synkkaData.lastUpdated` |
| `raw` | jsonb not null | the whole product object |
| `loaded_at` | timestamptz not null | load time |

The analysis notes that `salesUnit` is stale for about 1.2% of products. The loader stores the file's value as it is; the Valio adapter (#31) takes the sales unit from the availability response.

### 3.3 Child tables

All have `product_id` FK `products` `ON DELETE CASCADE`.

`product_units`: PK (`product_id`, `unit_id`); `size_in_base_units` numeric not null; `gtin` text; `is_sales_unit`, `is_base_unit` boolean not null.

`product_unit_conversions`: PK (`product_id`, `packaging_type`); `packaging_type` text (`BASE_UNIT_OR_EACH`, `CASE`, `PALLET`); `unit_id` text, nullable, the unit the row describes; `net_weight_g`, `gross_weight_g`, `width_mm`, `length_mm`, `height_mm` numeric; `volume_ml`, `content_weight_g`, `content_pieces` numeric; `raw` jsonb (the original row, so dirty units stay inspectable).

Synkka's `volume` is really the **net content**, in the unit that fits the product: litres or millilitres for liquids, grams or kilos for solids (equal to `netWeight` in 5,977 of 6,373 cases), `H87` pieces for countable goods. The loader splits it into `volume_ml`, `content_weight_g` or `content_pieces` by its unit.

How `unit_id` is resolved, in order:
1. the unit in `units[]` whose `gtin` equals `synkkaData.gtin`;
2. the only unit, when the product has just one;
3. `BASE_UNIT_OR_EACH` → `baseUnit`; `PALLET` → `PAL` if present; `CASE` → `salesUnit` if it is not the base unit;
4. otherwise null, reported as an anomaly (89 products in the full file).

Measures are normalised: `GRM` ×1 and `KGM` ×1000 to grams; `MLT` ×1, `CLT` ×10 and `LTR` ×1000 to millilitres; `MMT`, `CMT`, `MTR` to millimetres; `H87` to pieces. Any other unit (`PTN`, `PR`, `MTR` as content, `KGM H87`) gives null plus an anomaly: 26 rows in the full file.

`product_allergens`: PK (`product_id`, `code`, `containment`); `code` FK `allergen_codes`; `containment` text with check `CONTAINS | MAY_CONTAIN | FREE_FROM | UNDECLARED`. Rows from both the `allergen` and `nonAllergen` groups. A code listed as both contained and free-from keeps both rows (the engine fails closed, #37), and is reported. "No listing" means no rows for the product; no column stores it, so nothing can drift.

`product_claims`: PK (`product_id`, `claim_id`, `qualifier`); `claim_id` text (`FREE_FROM_LACTOSE`); `synkka_id` text (`LACTOSE`); `qualifier` text (`FREE_FROM`, `DIET`, `LOW`, `HIGH`, `NO_ADDED`). Lactose-free is `claim_id = 'FREE_FROM_LACTOSE'` (§5.3).

`product_labels`: PK (`product_id`, `label_id`); `kind` text, `temperature` for the three temperature markers, otherwise `certificate`.

`product_substitutions`: PK (`product_id`, `substitute_product_id`); `substitute_product_id` FK `products`; `position` smallint (order in the file).

Plain B-tree indexes: `products(category_id)`, `product_claims(claim_id)`, `product_allergens(code)`, `product_substitutions(substitute_product_id)`.

## 4. Loader

`uv run python -m app.loaders.catalogue [--file data/valio-products.json] [--download] [--force]` from `api/`. In the container: `docker compose exec api python -m app.loaders.catalogue --download`.

It lives in the API package, not `scripts/`: it needs the models and the settings loader, and on the VM it must run inside the `api` container, because laptops never connect to `junction_demo` (CLAUDE.md).

**One transaction**, in this order:
1. Upsert `categories` and `allergen_codes` from the CSVs.
2. Upsert `products` (`INSERT … ON CONFLICT (id) DO UPDATE`).
3. Delete every row of the five child tables, then insert them again from the file.
4. Products in the database but not in the file are **not deleted**, because quotes, orders and recipe links will point at them later. They are reported.
5. On any error: roll back and exit with a non-zero status, so the old catalogue stays.

Why not `TRUNCATE products CASCADE`: it would also wipe quotes and orders once those tables reference `products`.

Inserts use the async engine with batched `executemany`. The full file loads in about 6 s on a laptop.

The `api` image is built from the repository root, so it holds `data/` (the CSVs) and `policy/`. The product file itself is excluded and downloaded inside the container.

**Output**: counts per table, then anomalies grouped by kind, with up to 10 product ids each:

- products without classifications;
- allergen code listed as both contained and free-from;
- unit conversion not resolved to a unit, or measure unit not normalised;
- missing `name_en`;
- missing `temperatureCondition`;
- category or allergen code not in the CSVs (the load fails on these, since they break foreign keys);
- products in the database but no longer in the file.

## 5. Tests

- **Sample fixture**: `api/tests/fixtures/products_sample.json`, about 15 products picked from the real file, a few hundred kB at most. It covers:
  - the milk shortlist (464073, 464201, 464306, 462775, 463380, 464119, 464440);
  - a product without classifications (461963);
  - the double-listed allergen (468044);
  - a variable-weight `KG` product;
  - a `CASE` conversion;
  - a substitution pair.
- **Loader tests** (need Postgres, as in #27):
  - Loading the sample gives the expected counts.
  - Loading it twice gives the same counts and no duplicates.
  - 464073 has `FREE_FROM_LACTOSE`, unit `KI` = 10 `ST`, and a conversion with `volume_ml` 1000.
  - The anomalies list includes 461963 and 468044.
- **Pure unit tests** (no database) for unit resolution and measure normalisation.
- **CI** runs these after `alembic upgrade head`. CI never downloads the full file.

## 6. Running it on each database

- **Laptop**: `cp .env.example .env`, start `db`, `uv run alembic upgrade head`, then `uv run python -m app.loaders.catalogue --download`. `VALIO_API_KEY` must be set in `.env`.
- **`junction_demo`**: after #28, on the VM, run `docker compose exec api python -m app.loaders.catalogue --download`. The key comes from Key Vault.

The loader goes into the CLAUDE.md Commands section.

## 7. Decisions (2026-11-14, Miska)

1. **The loader lives in the API package** (`api/app/loaders/`), not `scripts/`, so it runs inside the `api` container on the VM. `technical-plan.md` §11 is updated to match.
2. **A ~15-product sample of the product file is committed** as a test fixture (`api/tests/fixtures/products_sample.json`). The full file stays out of git.
3. **Search columns belong to #30**: `tsvector` and trigram indexes come in #30's migration.
4. **Deposits stay in `raw` only** until the engine needs them (vision §10: deposits are not added to totals).
5. **Stale products are kept and reported**, not deleted.
6. **ORM models in `api/app/models/`** (*proposed*, Juho to confirm): a new package next to `schemas/`, shared by #30, #31 and the platform services.
