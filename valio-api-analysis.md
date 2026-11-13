# Valio Aimo mock API: analysis and spec implications

Date: 2026-11-13. Based on the resource portal (`https://junction26.valioaimo.fi/`), the OpenAPI document, the downloadable data files and live calls with the team API key. Companion to issue #1 (Policy / Ordering Engine Model).

## 1. What exists

Everything under `/api` needs an `X-API-Key` header. Cloudflare blocks Python's default User-Agent (error 1010), so set a custom one such as `curl/8.4.0`.

| Resource | What it is |
|---|---|
| `POST /api/availability` | Stock, closing time and earliest date for 1-1000 product codes |
| `POST /api/price` | Price per sales unit for 1-1000 product codes |
| `GET /api/ping` | Health check, returns `{"status":"ok"}` |
| Product data JSON (87 MB) | 17,546 products, schema provided as JSON Schema |
| Carbon footprint CSV | 11,033 products, `AVG kg CO2-eq/kg` (product group average, not per product) |
| Delivery reliability CSV | 4,425 products, value 0-1 |

Download links also exist under `/api/*/download` (redirect, use `curl -L`). The files are static during the challenge.

**There are no search, quote, order, customer, mandate or history endpoints.** Those are all ours to build or mock.

Both live endpoints take `{customer, requestedDate, products[]}`. The `customer` value does not affect results (verified: different customer ids gave identical responses). The API docs say undisclosed rate limits apply and that solutions must not poll all products. Narrow down from the static product file first, then query.

Observed: about 0.3-1.5 s per call, 40 sequential pings in 23 s with no 429.

## 2. Decisions taken

- **Prices come from the API as-is.** Customer-specific pricing is out of scope. Customer profiles, mandates and order history are mocked by us.
- **Search is local.** Load the product JSON once into an index and call price and availability only for a shortlist.
- **Demo is voice only**, with an SMS link to a plain HTML confirmation page. No chat, no A2UI.

## 3. Price API

Response per product (all `catalogPrice`, `priceWithTax`, `comparisonPrice`, `listPrice` and `tax` may be null):

- `catalogPrice.value` / `valueWithTax`: per sales unit, decimal euros, before / after tax.
- `listPrice`: price before discount.
- `comparisonPrice` + `comparisonUnit` (`KG` or `L`): price per kg or litre. Missing for about 20% of sampled products (79 of 400).
- `tax.taxRate` (for example 13.5) and `taxValue`.
- `netPriceFound`: true for 7 of 400 sampled products, otherwise the catalog price was used. Catalog is about 76-85% of list for most products.
- `error: true` means no price found. The HTTP status is still 200.
- Validity: `validTo` is `9999-12-31` for nearly all; prices did not vary with the requested date in testing (2026-11-16 vs 2026-12-31 identical).
- `quantity` is always 1.0. Totals are quantity x unit price and we compute them.

Implications:

- Convert to integer cents on ingest. Keep decimal arithmetic. Decide whether quotes are net of VAT, gross, or both. The API exposes both.
- Per-unit price of a sales unit (for example a case `KI` of 10) is not per litre. Use `comparisonPrice` only for comparing products, and compute order lines from the sales unit price.
- Fixed-price quotes are our own construct. The API gives only the current price.

## 4. Availability API

Response per product: `productId`, `closingTime`, `salesBlock`, `logisticModel`, `scheduleLines[]`.

- `logisticModel`: `Stock` (real quantities) or `Terminal` (supplier warehouse, quantity unknown, reported as 999999). In a 400-product sample: 151 Stock, 173 Terminal, 76 no model at all.
- **Empty `scheduleLines` (19% of sample):** product cannot be delivered on any date. No `closingTime` or `logisticModel` either. Treat as `UNAVAILABLE` with no restock date.
- `availableAmount` is in `salesUnit`. 0 means not available, and then `availableDate` is absent. Stock items can have tiny quantities (0, 1, 2, 3). Some report sentinel values (9,999,999,999, 999,999,999, 4,999,999,999), so cap or treat as "unbounded".
- `availableDate` is the earliest date the amount is available and **does not depend on `requestedDate`**. In every sample (600 products, requested dates from 2026-11-13 to 2027-03-01) it was `2026-11-16` (the coming Monday) for all products that had a date. Rule: deliverable by `needed_by` if `availableDate <= needed_by`, but note the date is constant, so the API cannot tell us about any other delivery day. Items with amount 0 have no `availableDate`.
- `closingTime` is documented as "the order cut-off time (= order by closingTime at the latest to receive goods on availableDate)". So it is tied to `availableDate`, not to `requestedDate`, and is identical for every requested date. Observed in 600 products (server time was Fri 2026-11-13 22:27):
  - Stock, 245 of the sample: Sun 11-15 17:00 (1 day before delivery), or Fri 11-13 13:00 (3 days before, already passed).
  - Terminal, about 250 of the sample: Thu 11-12, between 10:30 and 16:00 (4 days before delivery, already passed).
  - **Every Terminal product and every Fri-13:00 Stock product is past its own cutoff at the time of the call, yet the API still returns an orderable schedule line for 11-16.** See question 1 below.
  - Per-product times exist (10:30, 12:00, 12:30, 13:00, 13:30, 14:00, 14:30, 15:00, 16:00, 17:00), so cutoff is a per-product field, which is the part we can use.
- `salesBlock` was false everywhere in the sample, but must still be honoured (top level and per schedule line).
- Unknown product ids return 200 with an empty schedule. Past dates are accepted.
- `salesUnit` in availability differed from the product file's `salesUnit` for 4 of 314 sampled products. Validate and fail closed on mismatch.

## 5. Product data

17,546 products, all non-deleted, all with `synkkaData` (manufacturer data, quality varies by product type).

Top-level fields: `id`, `salesUnit`, `baseUnit`, `salesUnitGtin`, `category`, `allowedLotSize`, `temperatureCondition`, `vendorName`, `countryOfOrigin`, `units[]`, `deposits[]`, `substitutions[]`, `synkkaData`.

Coverage notes:

- **Units:** codes are technical (`KI`, `ST`, `KG`, `PAK`, `BAG`, `RAS`...) with no translations. `units[]` gives the packaging hierarchy with `sizeInBaseUnits` (for example `KI` = 12 `ST`). `unitConversions` gives weights and volumes per level and exists for 14,474 products. Converting "1,000 L" to an order quantity requires parsing these plus the name.
- **`allowedLotSize`:** 0.01 for 96% of products, so it is almost never a real pack constraint. Real pack size comes from the units hierarchy.
- **Categories:** 349 numeric codes, no names. Mandate categories like `dairy` need a mapping we create, or we use the codes directly.
- **Origin:** `countryOfOrigin` (lowercase ISO alpha-2) missing for only 9 products.
- **Names:** fi, sv and en in `synkkaData.names`. Marketing text, ingredients (3,746 products) and nutrition (12,251) are partial.
- **Temperature class:** `temperatureCondition` integer (8 = ambient is the most common, no legend). Closest thing we have to "fresh". **No shelf life data anywhere.**
- **Allergens:** `classifications` group `allergen` lists codes with `CONTAINS` or `MAY_CONTAIN`. Group `nonAllergen` lists `FREE_FROM`. Codes are Synkka codes with no legend (AM, AW, UW, AE, AN, AY...). About 11 products have no classifications at all. Fail closed: treat missing data and `MAY_CONTAIN` as unsafe for strict exclusions. We must build the code-to-allergen mapping (for example nuts).
- **Diet and claims:** group `nutritionalClaim` has `LACTOSE FREE_FROM` (4,178 products), `GLUTEN FREE_FROM`, `VEGAN`, `VEGETARIAN` and so on. "Lactose-free" must be matched on the claim, not just the name (name search alone matched many non-milk products, such as pastries and chocolate).
- **Labels:** group `packagingMarkedLabel` includes Blue Swan, Finnish heart, EU organic, Swan, Rainforest Alliance, MSC, Fair Trade and others. These are the "certificates and sustainability labels" in the optional criteria.
- **VAT:** `vatCode` is dirty (`STANDARD`, `MEDIUM`, `MEDIUM MEDIUM`, empty, `NOT_APPLICABLE`) and missing for about 3,000 products. Use `tax.taxRate` from the price API instead.
- **Substitutions:** only 189 products have entries (250 pairs, all targets exist, 230 in the same category). Use as high-trust seed pairs; our R1-R3 ladder needs its own similarity logic for everything else.
- **Fish:** `fishingReports` exists for 353 products (species, production method, areas).
- **Free text** (marketing text, descriptions) is untrusted data. The prompt-injection rules in the issue apply.

## 6. Carbon and reliability

- Carbon is an average per product group in kg CO2-eq per **kg**. Not per unit, so using it for ranking needs the product weight from `unitConversions`. Missing for about 37% of products. Keep as a soft stretch signal.
- Reliability is a 0-1 value (1 = delivered as ordered), present for only about 25% of products, median 1.0, 291 products below 0.9. Usable as a soft ranking and explainability signal. Missing means unknown, not good.

## 7. What this changes in the engine spec

| Issue assumption | Reality | Action |
|---|---|---|
| Customer-specific price record | Not available, customer ignored | Drop; use API price; report `netPriceFound` for info only |
| `list_price_cents` and price in cents | Decimal euros per sales unit, net and gross | Convert to cents at the adapter |
| Customer, mandate, history from the platform | None exist | Mock in our own seed data and DB |
| Stock quantity | Only for Stock products; Terminal unknown; some sentinels | Add `AVAILABILITY_UNVERIFIED` style flag for Terminal |
| Cutoff and delivery days per product | One static `closingTime`, no delivery calendar, no date dependence | Do not build T14, T15, T19 on this field until clarified; our own delivery calendar in policy config |
| Shelf life | Not provided | Drop stage 4 shelf life check and T20, or mock |
| `pack_size`, `sell_unit`, `unit_volume_l` | `units[]`, `unitConversions`, names | Build a normalising adapter with `UNIT_UNKNOWN` fail-closed |
| `allergens` list and `allergen_data_complete` | Coded CONTAINS / MAY_CONTAIN / FREE_FROM, no legend | Build mapping; completeness = group present |
| `carbon_g_per_unit` | Group average per kg | Derive from weight, soft only |
| Season table | None | Our own table, soft only |
| Quotes and order placement | None | Entirely ours |
| Product search | None | Local index over the product JSON |

## 8. Answers to the issue's open questions

- Customer-specific prices and order history per customer: no. Mocked by us.
- Allergen and diet fields: yes, coded and fairly complete (17,535 of 17,546), no legend.
- Origin, carbon, season: origin yes, carbon group average only, season no.
- Stock, shelf life, cutoff, delivery days: stock partial, shelf life none, cutoff one static field, delivery days none.
- Quotes and expiry: not supported, ours.
- Sandbox customer list: none. Webshop test accounts were promised "separately" in the brief; ask mentors.
- SMS and phone numbers: not part of the API. We use a separate SMS sender and invented numbers.

## 9. Open questions for the mentors

1. **`closingTime` vs `availableDate`.** The spec says `closingTime` is the latest time to order to receive goods on `availableDate`. In the mock, `availableDate` is always 2026-11-16 whatever date we request, and for all Terminal products (and some Stock products) `closingTime` was already in the past when we queried (Thu 11-12 and Fri 11-13 13:00 vs server time Fri 22:27). Should we treat those as no longer orderable for 11-16 (and then which date is the next valid one, since the API will not tell us), or is the mock's `closingTime` just an unreliable snapshot? Is `availableDate` computed from the server clock (it should then move over the weekend) or is it fixed for the whole event?
2. What does an empty `scheduleLines` mean for a product, and how common is it in the real system?
3. Is `Terminal` stock ever confirmable, or should agents always treat it as unverified?
4. Legend for the Synkka allergen codes, category codes, `temperatureCondition` and unit codes (or confirmation that we should infer them).
5. Should quotes be net or gross of VAT in the demo?
6. Are webshop test accounts or sample customers coming?

## 10. Suggested demo data to prepare

Before writing the seed data, pick a small set of real product ids that cover:

- Stock product with plenty of quantity (the main happy path, for example a 1 L lactose-free milk).
- Stock product with 0 or very low quantity (partial stock, substitute).
- Terminal product (unverified stock).
- Product with empty schedule (unorderable).
- A product with a known `substitutions` entry.
- A nut-containing product and a product with missing allergen data.
- A fish product (category minimum tier, fishing report).

A script that scans the product file and live availability for these cases is worth writing before the customer seed data.

## 11. Second pass: additional findings

Checked against the full OpenAPI document (12.5 KB, five top-level keys, no servers or extensions, every operation secured by `APIKeyHeader`) and about 1,000 sampled products.

### API behaviour
- Limits and validation: more than 1000 products or an empty list gives 422. Product ids must be strings. Duplicate ids return duplicate entries. Extra request fields (for example `quantity`) are accepted and ignored, so **there is no quantity-based pricing**. Unknown paths (`/api/order`, `/search`, `/products`...) return 404. A wrong key gives 401.
- Speed: 1000 products take about 1.3 s for availability and about 4.7 s for price.
- **Availability is deterministic.** Three runs two seconds apart on 1000 products gave identical results, so the same request gives the same stock picture. Good for reproducible quotes and tests, but it also means stock-outs are fixed, not random.
- **Price does not check validity.** Requesting a delivery date after `validTo` still returns the expired price. The engine must compare `validTo` with the delivery date itself.
- The `netPriceFound = true` products (12 of 1000) all share validity 2026-06-01 to 2026-12-31. A quote for a delivery after 2026-12-31 would use a price that has expired.
- **Price is not orderability.** All 176 empty-schedule products in the 1000 sample still returned a price. About 18% of the sample has an empty schedule, spread across categories and vendors (not a pattern we can pre-filter).

### Unit mismatch: price follows availability, not the product file
For about 1.2% of products the product file's `salesUnit` differs from the unit in the availability response (for example file `KI`, availability `ST`). For all 6 cases checked, dividing `catalogPrice` by `comparisonPrice` gave the weight or volume of the **availability unit**:

| Product | File unit | Availability unit | price / comparison | Matches |
|---|---|---|---|---|
| 474756 (120 g) | KI (3 ST) | ST | 0.12 kg | ST |
| 476980 (520 g) | KI (2 ST) | ST | 0.52 kg | ST |
| 476475 (1.5 kg) | BAG | KI (3 BAG) | 4.5 kg | KI |
| 465244 (0.5 L) | ST | KI (6 ST) | 3.0 L | KI |

So the two live APIs agree with each other and the product file's `salesUnit` is stale for these. The adapter should take the sales unit from the availability response, flag the mismatch, and fail closed on products where it cannot be resolved.

### Stock numbers (Stock products only, 426 in the sample)
- Median 62 units, 10th percentile 4, 18 products at 0, no fractional quantities.
- 99 products (23%) report a sentinel of at least 1,000,000 (9,999,999,999 is the common one). Treat as unbounded but unverified.
- Real finite quantities are small, so partial-stock cases are easy to demo with real data.

### Headline scenario: "1,000 litres of lactose-free milk"
Category `10400` is milk drinks (it also contains sour milk and coffee drinks). 35 products there carry the lactose-free claim. Real examples (prices net of VAT, delivery 2026-11-16):

| Product | Sale unit | Availability | Price | Per litre |
|---|---|---|---|---|
| 464073 Valio whole milk 1 l UHT | ST (10 per case) | Stock, sentinel (unbounded) | 1.64 | 1.64 |
| 464201 Valio semi skimmed 1 l UHT | ST | Stock, sentinel | 1.56 | 1.56 |
| 464306 Valio Arki semi skimmed 1 l | ST (20 per case) | Stock, sentinel | 1.01 | 1.01 |
| 462775 Arla fat free 1 L | ST (12 per case) | Stock, **51** | 2.57 | 2.57 |
| 463380 Arla Café 1 L | ST (12 per case) | Stock, **698** | 2.65 | 2.65 |
| 464119 Valio skimmed 1 l UHT | KI (10 ST) | Terminal, unknown | 13.32 | 1.33 |
| 464440 Valio semi skimmed 0.5 l | ST | **empty schedule** | 0.88 | 1.76 |

This one query already covers unbounded stock, partial stock (Arla 51 ST vs 1,000 L), Terminal (unverified) and unorderable cases. Cheapest unbounded option is 464306 at 1.01 per litre. The "lactose-free" decision should use the `LACTOSE FREE_FROM` claim, and note `LACTOSE LOW` exists too (321 products) and should not count as lactose-free.

### Inferred legends (not provided, verify with the mentors)
Allergen codes, inferred by correlating `CONTAINS` codes with ingredient text and product names (they look like GS1 allergen codes):

| Code | Likely meaning | Code | Likely meaning |
|---|---|---|---|
| AM | milk | AW | cereals containing gluten |
| ML | lactose (probable) | UW | wheat |
| AE | egg | NR / GB / GO | rye / barley / oats |
| AF | fish | AY | soy |
| AC / UM | crustaceans / molluscs | AS | sesame |
| AP | peanut | BM | mustard |
| AN | tree nuts (general) | BC | celery |
| SA / SH / SC / SW | almond / hazelnut / cashew / walnut | AU | sulphites (probable) |

**Nut exclusion must union several codes.** Of 58 products with "almond" in the name, 44 carry `SA` and only 26 carry `AN`. A nut-free rule that checks only `AN` would miss nuts. Use `AN`, `SA`, `SH`, `SC`, `SW` and probably `AP`, plus unknown codes (`ST`, `NC`) until clarified, and treat `MAY_CONTAIN` as unsafe.

`temperatureCondition` (inferred from `minTemperature` / `maxTemperature` and labels): 8 = ambient (about 18-22 °C), 7 = frozen (-18 to -25 °C), 1-4 = chilled (1: 0-3, 2: 2-4, 3: 2-6, 4: 5-8 °C), 5, 6 and 9 are rare special classes. This is the only way to approximate "fresh". Category codes have no clean legend (top categories mix many unrelated brands), so mandate categories need our own mapping from keywords or specific codes.

### Other data observations
- **Variable weight:** 35 of 1000 sampled products are `variableUnit` and sold by `KG`. The ordered quantity and the delivered weight differ, so totals are estimates.
- **Deposits:** 33 of 1000 have deposit items (`deposits[]`, for example one piece per unit). The price API does not mention deposits, so we don't know if they are in the price. Ask.
- **Comparison price:** missing for about 20% (mostly `KI` and `ST` products). It can be derived from `unitConversions` weights, which themselves are missing for some products (`CASE` rows often have null weight).
- **Reliability:** mean 0.988 for Stock and 0.946 for Terminal products, minimum 0.47. Coverage is only 18-37% depending on model, so missing is unknown, not good.
- **Carbon coverage** is about 62-68% in this sample (not 37% missing as estimated earlier from the file alone).

### Extra questions for the mentors
7. Do deposits get added to the invoice on top of the API price?
8. Which unit does the price apply to when the product file and availability disagree on `salesUnit`? (Our test says availability, please confirm.)
9. Meaning of the allergen codes (especially `AN`, `ML`, `ST`, `NC`, `UW`) and of `temperatureCondition`.

## 12. Delivery date handling: status, decision and recheck plan

### What we can and cannot answer today
- **"What can I order so it arrives before Friday 2026-11-20?" works.** A product qualifies if it has a schedule line, `availableAmount > 0`, `salesBlock` is false (top level and line) and `availableDate <= needed_by`. In every sample `availableDate` was Monday 2026-11-16, so everything orderable qualifies for Monday and later, and nothing qualifies for Saturday 11-14 or Sunday 11-15.
- **We cannot learn the next delivery day after Monday.** The API returns exactly one `availableDate` per product and never a second one. We cannot ask "what Tuesday or Wednesday options exist", and we do not know the delivery calendar (days per week, per product, per region).
- **`closingTime` cannot be taken at face value.** It is documented as the latest time to order to get delivery on `availableDate`. At 22:27-22:40 on Fri 2026-11-13 the cutoff had already passed for about 280 of 600 sampled products (all Terminal products, Thursday 11-12 10:30-16:00, and Stock products with Friday 11-13 13:00), and the API still returned an orderable schedule line. If a past `closingTime` meant "not orderable", almost nothing would be orderable for Monday and the API would give no next date.

### Decision for now (revisit after the recheck and the mentor answer)
1. The deliverability rule is `availableDate <= needed_by` plus the stock and block checks above.
2. `closingTime` is shown and logged but does **not** block an order. It is also stored per product in the quote so a stricter rule can be switched on with one config flag (`enforce_closing_time`).
3. The delivery calendar (delivery days, our own cutoff, alternative dates to offer) lives in our policy config. Tests T14, T15 and T19 run against that config, not against the API.
4. If `needed_by` is earlier than `availableDate`, the engine says so (`DELIVERY_DATE_UNREACHABLE`) and offers `availableDate` as the nearest option. It never moves the date silently.

### Baseline recorded Fri 2026-11-13, about 22:27-22:40 (Europe/Helsinki)
600 products (random sample, seed 7), requested dates 2026-11-13 to 2027-03-01:

| Class | Products | `availableDate` | `closingTime` |
|---|---|---|---|
| Stock | 206 | 2026-11-16 | Sun 2026-11-15 17:00 |
| Stock | 39 | 2026-11-16 | Fri 2026-11-13 13:00 |
| Terminal | 165 | 2026-11-16 | Thu 2026-11-12 15:00 |
| Terminal | about 85 | 2026-11-16 | Thu 2026-11-12, 10:30 to 16:00 (other times) |
| Empty schedule | 95 | none | none |

Identical for every requested date. `availableDate` is absent when `availableAmount` is 0 (11 of the Stock products). Repeated calls returned identical data.

### Recheck plan (Sat 2026-11-14 and again Mon 2026-11-16 morning)
Run `scripts/recheck_availability_dates.py` (needs `VALIO_API_KEY` and the product JSON path, see the file header). Compare against the baseline above.

| If we see | It means |
|---|---|
| `availableDate` still 2026-11-16 and `closingTime` values unchanged | The mock is a frozen snapshot. Keep the decision above. Ask the mentors anyway. |
| `availableDate` moves (for example to Tue 2026-11-17 on Sat, or Mon 11-16 stays until its cutoff) | It is computed from the server clock. We can read the real delivery rhythm and the next-date logic from the API. Update the date section. |
| `closingTime` values shift forward with the clock | The cutoff is a live rule. Consider enforcing `closingTime` (flip `enforce_closing_time`) and re-derive T14, T15 and T19 from it. |
| Products start returning an empty schedule after their cutoff | A past cutoff really does make a product unorderable. Enforce it. |
| Nothing is orderable on Monday | We must not demo "Monday" after the cutoff. Demo dates must be chosen after checking. |

Also note for the demo: the demo "today" in the issue's test cases (Fri 2026-11-13, 10:00) is fixed by us. The API uses the real server clock (`timeNow`), so any demo after the weekend will see different values than our fixtures assume. Fixtures should stub the API or record responses.

### Open question for the mentors (question 1 above, in short)
Is `closingTime` meant to make a product unorderable once it has passed, and is `availableDate` computed from the real clock or fixed for the whole event? If it is computed, what is the delivery calendar?
