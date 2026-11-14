# Technical implementation plan

Status: draft v3, 2026-11-14, after two review rounds and a check against the UI design. Built on `vision.md` (source of truth), `valio-api-analysis.md`, the files in `data/` and the team answers recorded in section 1. **The existing GitHub issues (#1 to #21) are not a source for this plan.** New issues will be created from this spec and should reference it. Where the plan suggests something vision.md does not settle, it is marked *proposed*. Section 14 lists what moves to follow-up issues.

## 1. Decisions this plan builds on

Taken on 2026-11-14, in addition to vision.md:

| Topic | Decision |
|---|---|
| Backend | Python, FastAPI |
| Frontend | SvelteKit |
| Cloud | Azure (we have credits). The app containers (Caddy, FastAPI, SvelteKit) run on one VM with Docker Compose. Not Container Apps or Web Apps, because their 240-second request limit may cut voice calls and the dashboard stream (section 10) |
| Database | The deployed app on the VM uses the existing Azure Database for PostgreSQL instance (`junction_demo`). `vector`, `pg_trgm` and `unaccent` are allowed on the server. Development uses Postgres with pgvector in Docker on each laptop. We revisit this once we know how many developers change database data or schema at the same time (section 10.1) |
| Voice path | Our server relays audio between the browser and Gemini Live. The server is an ordinary MCP client |
| SMS | Twilio |
| Product images | The image file's `code` is the product file's `id`. Images are hotlinked from their `img` URL |
| Connector login | Our own OAuth 2.1 authorization server, built on the MCP Python SDK's auth routes, with our own email and password page |
| Recipe embeddings | Gemini embeddings, stored in pgvector |
| Clock | A business clock frozen at Thu 2026-11-12 09:00 for cutoffs and delivery dates. The real clock for link and quote expiry, the duplicate check and audit timestamps |
| SMS after a call | When the call ends, the voice relay calls `request_confirmation` for the call's latest ready quote |
| Secrets | Azure Key Vault in production, with no `.env` on the VM. A local `.env` only on laptops for development (section 10.2) |
| Token after an edit | The token belongs to a confirmation that points to the current quote. Confirm must send the hash of the quote on screen |
| Substitute price limit | An automatic swap may be at most 10% more expensive. The value is configurable in `policy.yaml` |
| Rounding | Line total = quantity × gross unit price, rounded up to the next cent. Nothing is rounded before that |
| Missing price or availability | The agent explains that the price or stock could not be checked and asks whether to try again |
| Call language | The agent follows the caller's language. A setting can force Finnish or English |
| Connector accounts | Both: self sign-up, and accounts we create and hand out |
| Demo login | Typing a phone number (real or fake) on the demo page creates a demo user and logs that browser in. That browser session is the login; these users have no password |
| Dashboard access | General data is public, with no login. Chat logs, phone numbers, emails and raw event data are private: each user sees only their own, operators see everything (vision §11). This extends vision §11, where buyers see only their own company's orders |
| Confirmation messages | Every message goes to the simulated phone inbox, which is shown on the phone page only. Real SMS through Twilio sits behind a feature flag that is off by default. Even with the flag on, only phone numbers on an allowlist get a real SMS. Production would use SMS only |

Constraints from vision.md that shape the architecture:

- Deterministic engine, no LLM inside. Same input and policy version give the same decision and quote hash (§3).
- No agent tool can confirm. The only place to confirm is the page behind the SMS link (§3, §6, §8).
- One MCP server over Streamable HTTP, with the same operations documented as OpenAPI (§8).
- Product search runs locally on the product file loaded into Postgres. Price and availability are fetched only for a shortlist and cached for about five minutes. A 429 means wait 30 seconds (§10).
- Injectable clock, demo clock Thu 2026-11-12 09:00, `closingTime` enforced (§10). This overrides section 12 of `valio-api-analysis.md`.
- Live API or recorded snapshot, behind a switch (§10).
- Gross totals in integer cents, decimal arithmetic, deposits not added (§10).
- Hash-chained append-only audit, dashboard updated by push (§11).
- Quotes signed as JWS with a published key (§12).

## 2. Architecture

```mermaid
flowchart LR
    subgraph Clients
        PhonePage["Virtual phone page"]
        Shop["Mock Aimo webshop<br/>(registers WebMCP tools)"]
        ChatGPT["ChatGPT desktop browser"]
        Claude["Claude connector"]
        ConfirmPage["Confirmation page"]
        DashPage["Dashboard"]
    end

    subgraph VM["Azure VM, Docker Compose"]
        Caddy["Caddy: HTTPS and routing"]
        subgraph API["FastAPI (one process)"]
            Relay["Voice relay"]
            MCP["MCP server /mcp"]
            REST["REST /api/v1 (OpenAPI)"]
            Auth["OAuth server, web sessions"]
            SSE["SSE stream"]
            Svc["Services (IO)"]
            Engine["Engine (pure functions)"]
        end
        Web["SvelteKit (adapter-node)"]
    end

    PG[("Azure Database for PostgreSQL (existing)<br/>pgvector, pg_trgm, unaccent")]

    ChatGPT -. "uses tools on" .-> Shop
    PhonePage -- "WebSocket audio" --> Relay
    Relay -- "MCP client" --> MCP
    Relay <-- "Live API" --> Gemini["Gemini Live"]
    Claude -- "MCP + OAuth" --> MCP
    Shop -- "fetch + session cookie" --> REST
    ConfirmPage --> Web --> REST
    DashPage -- "EventSource" --> SSE
    MCP --> Svc
    REST --> Svc
    Svc --> Engine
    Svc -- "direct, port 5432, TLS" --> PG
    Svc --> Valio["Valio mock API"]
    Svc --> Twilio["Twilio SMS"]
    Svc --> Emb["Gemini embeddings"]
    API -. "secrets at startup" .-> KV["Azure Key Vault"]
```

Three layers inside FastAPI:

1. **Interfaces**: MCP tools, REST routes, the voice relay, the Twilio webhook, OAuth and the SSE stream. They parse, authenticate and call a service. No business logic.
2. **Services**: gather the inputs (products and history from Postgres, price and availability from the Valio adapter, the kitchen profile, the clock), call the engine, store the quote, write audit and status events, send SMS.
3. **Engine**: `decide(EngineInput) -> EngineOutput`. No database, no HTTP, no clock reads, no randomness. Everything it uses is in its input.

Because the engine is pure and the full `EngineInput` is stored in the audit event, any decision can be replayed. That makes the determinism principle a test (section 11), not a promise.

REST and MCP share one set of Pydantic models and one service layer. FastAPI turns the models into the OpenAPI document. The MCP tools use the same models for their input schemas, so the two surfaces cannot drift apart.

## 3. Build or use out of the box

| Component | Use out of the box | We build | Priority (vision §13) |
|---|---|---|---|
| HTTP API and OpenAPI | FastAPI generates OpenAPI 3.1 from Pydantic v2 models. `extra="forbid"` rejects unknown fields (vision §8) | Routes under `/api/v1`, request and response models | P0 |
| MCP server | MCP Python SDK (`FastMCP`), Streamable HTTP, mounted into FastAPI at `/mcp`. MCP Inspector for manual testing | The seven tools of vision §8 as thin wrappers over services. Tool descriptions written for a voice agent | P0 |
| Ordering engine | Python `decimal`, `zoneinfo` | All of it: resolve, allergen and diet filter, units, availability and dates, ranking, substitution, price, sanity checks, decision, explanation text | P0 (sanity checks, tuned ranking and exact-fit are P1) |
| Rules and texts | YAML and CSV loaders | Versioned rule files, reason-code templates in Finnish and English, a name table for unit codes (`KI`, `ST`, `PAK`, ...) | P0 |
| Product search | Postgres full-text search (`finnish` and `english` configs), `pg_trgm` for typos, `unaccent` | Loader for the product file, search SQL, a short synonym list, deterministic ranking | P0 |
| Recipe search | pgvector (HNSW index), Gemini embeddings, Postgres full-text search | Embedding script, hybrid query, scaling to portions | P1 |
| Valio API client | `httpx` (async) | Rate limiter, 429 back-off, 5-minute cache, snapshot record and replay, sales-unit cross-check | P0 |
| Quote hash and signature | `rfc8785` (canonical JSON), `joserfc` (JWS with EdDSA), `cryptography` | Quote model, hash, JWKS endpoint | P0 |
| Confirmation token | `secrets.token_urlsafe(32)` (256 bits), SHA-256 | Token table, single-use and expiry rules | P0 |
| SMS | Twilio Messages API, `twilio` SDK, delivery status callbacks | SMS service that delivers every message to the simulated phone inbox, and through Twilio to allowlisted numbers when the flag is on. Message text, status webhook | P0 |
| Confirmation page | SvelteKit server rendering, Svelte's default escaping | Odd things first with acknowledgements, asked-and-added lines, edit and re-quote, confirm, cancel, "order received" | P0 |
| Voice agent | Gemini Live API (`google-genai` SDK, function calling), browser `getUserMedia` and `AudioWorklet` | Audio relay, MCP-to-Gemini tool bridge, system prompt, call screen, demo account on number entry, SMS after hang-up | P0 |
| Webshop with WebMCP | The `modelContext` API in the ChatGPT desktop app's browser. The MCP-B polyfill or Chrome's testing flag for ordinary Chrome | Mock Aimo shop (login, search, product cards, cart) and tool registration calling `/api/v1` | P0 |
| Claude connector | Claude custom connectors (remote MCP URL plus OAuth). MCP Python SDK auth routes (metadata, client registration, authorize, token, PKCE). `argon2-cffi` for password hashes | Users table, the SDK's authorization-server provider backed by Postgres, login and sign-up pages | P1 |
| OpenAI connector | ChatGPT custom MCP connectors | Testing only | P1 |
| Live dashboard | Server-Sent Events (`sse-starlette`), Postgres `LISTEN/NOTIFY`. The listener needs a direct connection on port 5432, because PgBouncer in transaction mode drops notifications | Status events, plain-language step texts, operator and buyer views | P0 |
| Audit trail | Postgres, SHA-256 | Append-only hash-chained table, database privileges, chain checker | P0 |
| Database | Deployed: the existing Azure Database for PostgreSQL instance, with `vector`, `pg_trgm` and `unaccent` allowed in `azure.extensions` (done 2026-11-14). Development: the `pgvector/pgvector` image in Docker. SQLAlchemy 2, Alembic | Schema, migrations (the first one runs `CREATE EXTENSION`), loaders, seed data | P0 |
| Hosting | Azure VM, Docker Compose, Caddy (automatic HTTPS), Azure Key Vault with a managed identity, `azure-identity` and `azure-keyvault-secrets` | Compose file for the app containers, a development override with the database, Caddyfile, deploy script, a settings loader for `.env` or Key Vault | P0 |

In short: protocols, transport, crypto, search primitives, speech and SMS come off the shelf. The engine, the data loaders, the confirmation flow, the relay and the four web pages are ours.

## 4. Engine

### 4.1 Contracts (proposed)

Input to `build_quote`, one call with all lines (vision §8). The agent sends structured lines and the engine never sees raw speech (vision §5):

```python
class LineRequest(BaseModel, extra="forbid"):
    line_id: str
    product_id: str | None = None   # when the agent already knows the product
    usual: bool = False             # "my usual butter"
    text: str | None = None         # product words only, e.g. "maito" or "milk"
    claims: list[Claim] = []        # lactose_free, gluten_free, vegan, ...
    category: str | None = None     # category code from data/valio_category_names.csv
    quantity: Decimal
    unit: RequestedUnit             # litre, kg, piece, sales unit, or a packaging word
    needed_by: date
    recipe_ref: RecipeRef | None = None
```

`EngineInput` = the lines, the kitchen profile (allergen and diet exclusions), a history summary, the candidate product records, one offer per candidate (price and availability, with fetch time and source live or snapshot), the rule set with its version, business "now" and the quote issue time.

`EngineOutput` = a decision (`ready`, `needs_clarification` or `rejected`), priced lines (asked, chosen, quantity in sales units and in the asked unit, gross unit price as an exact decimal and line total in cents, delivery date, reason codes, trace), flags (code, whether the buyer must acknowledge it, Finnish and English text), alternatives, at most one clarification question, a next step for every rejection, text to speak in Finnish and English, and the quote when the decision is `ready`.

### 4.2 Pipeline per line

| Step | Rule | Source |
|---|---|---|
| Validate | Strict schema, limits on line count, string length and quantity | vision §8 |
| Resolve | A named product id must exist (otherwise stop). "My usual" comes from history. Otherwise run local search. Ambiguous matches go to the buyer | vision §3, §6 |
| Allergen and diet filter | A listed `CONTAINS` or `MAY_CONTAIN` for an excluded code blocks. No listing or `UNDECLARED`: orderable, flagged once per order. `X99` never blocks. Milk-free is decided on `AM`, lactose-free on `ML` plus the `LACTOSE` claim, nut-free on `AN` plus the specific nuts, gluten-free on the `GLUTEN` claim together with `AW`. Codes come from `data/gs1_allergen_codes.csv`. The same filter runs on every substitute. A conflict is a hard stop | vision §6, §10; analysis §11, §13 |
| Availability and date | Schedule line exists, amount above 0, `salesBlock` false at both levels, `availableDate` on or before needed-by, business "now" before `closingTime`. 999999 or more: orderable, flagged as unverified. Empty schedule: not available | vision §10 |
| Units | Sales unit comes from availability, checked against `units[]` and the price ratio. Disagreement is `UNIT_UNKNOWN`, a hard stop. Conversion uses `unitConversions`. A pack size read from the name is allowed and flagged. An unknown conversion, or a packaging word that could mean two sizes, goes to the buyer | vision §6, §10 |
| Rounding | Whole sales units (`allowedLotSize` 0.01 counts as 1). Rounding up is automatic when the overage is at most one unit and 2%, and is flagged. Above that, the buyer gets an exact-fit product as the alternative | vision §6, §10 |
| Rank | Price, stock certainty, history, origin. Ties broken by product id (*proposed*, keeps ranking deterministic) | vision §6 |
| Substitute | Only when the line cannot be filled. Order of tries: same product in another pack, then a curated `substitutions[]` pair, then a similar product, then a callback request. Automatic only for the first two, and only if no allergen is added and the substitute is at most 10% more expensive (configurable). The price is compared per kg or litre where known, since pack sizes differ; when it can't be compared, there is no automatic swap (*proposed*). Splitting on partial stock is the buyer's choice | vision §4, §6; review |
| Price | Gross unit price from `valueWithTax`, kept as an exact decimal. Line total = quantity × unit price, rounded up to the next cent. Order total = sum of line totals. `validTo` must cover the delivery date. If price or availability can't be fetched (`error: true`, API down, no snapshot), the line isn't quoted: the agent explains and asks whether to try again (returned as `needs_clarification`, *proposed*) | vision §10; analysis §3, §11; review |
| Sanity checks (P1) | Normal quantity range per product from history, the same order within two hours, a product never ordered before. These flags need an acknowledgement and never block | vision §6 |

Then for the whole order: one notice that lists every product without allergen information (customers with an exclusion only, analysis §13), the decision, and the quote.

### 4.3 Rules as data (`policy/`)

- `policy.yaml`: version, confirmation `always`, quote lifetime 30 minutes, cache lifetime 300 seconds, rounding limits (1 unit, 2%), duplicate window 2 hours, `enforce_closing_time: true`, demo business time, substitute price limit (10% more expensive), call language (`auto`, `fi` or `en`, default `auto`).
- `allergen_rules.yaml`: each exclusion as a set of GS1 codes, built from `data/gs1_allergen_codes.csv`. Whether pine nut, coconut and peanut belong to nut-free is decided in a follow-up issue (section 14). It is a one-line change in this file.
- `messages.yaml`: one Finnish and one English template per reason code and flag. Uses `data/allergen_containment_levels.csv` and the partitive allergen names for Finnish sentences.
- `unit_codes.csv`: display names for unit codes in Finnish and English.

The rule-set version goes into every quote hash.

Two clocks (decided 2026-11-14). A business clock, frozen at the demo time, gives the engine its business "now" for cutoffs and delivery dates. The real clock is used for link and quote expiry, the two-hour duplicate window and audit timestamps. Without this split, a frozen clock would stop links from ever expiring and break "same order 20 minutes ago".

## 5. Data and storage

### 5.1 Sources

| Source | How we get it | Loaded into |
|---|---|---|
| Product file (87 MB JSON) | `curl -L` once from `/api/products/download` (CLAUDE.md). Not committed | `products` and child tables |
| Category names | `data/valio_category_names.csv`, the 11-column version in the category brief. The file in the repo still has the older 6 columns | `categories` |
| Allergen codes and phrases | `data/gs1_allergen_codes.csv`, `data/allergen_containment_levels.csv` | `allergen_codes`, message templates |
| Recipes | `data/valio-recipes.json` (2,091 recipes) | `recipes`, `recipe_ingredients`, `recipe_tags` |
| Recipe-to-product links | `data/recipe-product-map.json` | `recipe_product_links` |
| Product images | The image file still to come (`code`, `name`, `img`) | `product_images`, joined on `code` = product `id` |
| Carbon and reliability CSVs | API downloads | Stretch |
| Customers, kitchen profiles, phone numbers, order history | Our seed script. No real people (vision §10) | `companies`, `users`, `kitchen_profiles`, `order_history_lines` |

Every loader can be re-run: it reloads in one transaction and prints counts and anomalies (for example image codes with no matching product).

### 5.2 Tables

- **Catalogue**: `products` (id, names fi/sv/en, category, sales unit from the file, base unit, GTINs, temperature class, vendor, origin, variable unit, raw JSON), `product_units`, `product_unit_conversions`, `product_allergens` (code, containment), `product_claims`, `product_labels`, `product_substitutions`, `categories`, `product_images`, plus search columns (`tsvector` in Finnish and English, trigram index).
- **Recipes**: `recipes`, `recipe_ingredients`, `recipe_tags`, `recipe_embeddings` (`vector(768)`), `recipe_product_links`.
- **Customers**: `companies`, `users` (name, phone in E.164, email, password hash, company), `kitchen_profiles`, `order_history_lines`.
- **Ordering**: `sessions` (channel, user, call id), `quotes` (hash, JWS, status, expiry, engine input and output as JSON), `quote_lines`, `confirmations` (token hash, quote, recipient, expiry, used at), `orders`, `order_lines`, `callback_requests`, `sms_messages` (Twilio id, delivery status).
- **Valio data**: `api_cache` (endpoint, product id, requested date, response, fetched at), `api_snapshots`.
- **Audit and live view**: `audit_events`, `status_events`.
- **Auth**: `oauth_clients`, `oauth_codes`, `oauth_tokens`, `web_sessions`.

### 5.3 Product search

Deterministic, no model at request time:

1. Hard filters first: requested claims from `product_claims` (lactose-free is the `LACTOSE FREE_FROM` claim, never the name; analysis §11), category if given.
2. Text match on product names in Finnish and English, the category names in both languages and a short synonym list (`milk` → `maito`), using `websearch_to_tsquery` in the `finnish` and `english` configs. The Finnish Snowball stemmer handles common inflections. Trigram similarity catches typos and transcription errors.
3. Order by score, then product id. The top 20 (*proposed*) become the shortlist for price and availability.

If tests show that this misses too often, a vector index on product names is the next step (vision §7 allows more indexes). It would only add candidates, so the engine's choice stays deterministic.

### 5.4 Recipes (P1, Juho owns the data and the linking, vision §7)

- Embed each recipe once (name, description, ingredient names, tags) with the Gemini embedding model at `output_dimensionality` 768. pgvector's HNSW index takes at most 2,000 dimensions for the `vector` type. The script saves the vectors to a file, so `junction_demo` and every laptop database load them without calling the API again (*proposed*).
- Search: embed the query at request time, rank by vector and by full-text search, merge with reciprocal rank fusion, filter by taxonomy. Diet tags are only a search hint (vision §7).
- `get_recipe` scales `singlePortionAmounts` to the portion count. In `build_quote`, ingredients with a product link go through `recipe-product-map.json`, the rest through normal resolution, and anything that cannot be resolved safely becomes a clarification.

### 5.5 Images and category names

- `<img src={img} loading="lazy" referrerpolicy="no-referrer">` with a placeholder when the image is missing or fails to load. Only pages that are actually rendered fetch from Valio's media server. We never prefetch the catalogue's images.
- `name_fi` and `name_en` are used for voice and display. `mandate_group` is a coarse grouping for search filters and the dashboard. It is never used for allergens and never as "chilled" or "fresh" (category brief).

## 6. Valio API adapter

- `httpx.AsyncClient` with `X-API-Key` from `VALIO_API_KEY` and `User-Agent: curl/8.4.0` (Cloudflare blocks Python's default).
- One batched call per endpoint per shortlist. Price and availability run in parallel.
- A token bucket at 5 requests per second (*proposed*, below our reading of a roughly 10 per second burst limit). On 429: wait 30 seconds, retry once.
- Cache in Postgres for 300 seconds, keyed by endpoint, product id and requested date.
- `VALIO_SOURCE=live | record | snapshot`. `record` calls live and stores every response. `snapshot` reads only stored responses, and a missing one is logged loudly. Snapshots live in `data/snapshots/` (no key inside, safe to commit).
- Normalisation at the edge: prices as exact decimals (totals become cents in the engine), sentinels to "unverified", empty schedule to "not available", the sales-unit cross-check from section 4.2.
- Availability is called again at confirmation, for the quote's products only (vision §10).

## 7. Channels

### 7.1 Phone (P0, main stage demo)

```mermaid
sequenceDiagram
    actor V as Visitor
    participant P as Phone page
    participant R as Voice relay
    participant G as Gemini Live
    participant M as MCP server
    participant T as Twilio
    V->>P: Types own phone number
    P->>R: Create demo account, start call session
    P->>R: WebSocket, microphone audio (PCM 16 kHz)
    R->>M: tools/list as this caller (channel phone)
    R->>G: Connect: system prompt and function declarations
    loop Conversation
        R->>G: Audio in
        G-->>R: Audio out, or a tool call
        R->>M: tools/call
        M-->>R: Result with text to speak
        R->>G: Tool response
        R-->>P: Agent audio (PCM 24 kHz)
    end
    V->>P: Hangs up
    R->>M: request_confirmation for the call's latest ready quote
    M-->>P: Message with link in the simulated phone
    opt Twilio flag on and number on the allowlist
        M->>T: Send link to the account's number
        T-->>V: SMS with link
    end
```

- **Browser**: `getUserMedia`, an `AudioWorklet` that downsamples to 16 kHz 16-bit mono, binary WebSocket frames. Playback through a second worklet. When Gemini reports an interruption, the playback buffer is flushed so the caller can talk over the agent.
- **Relay**: `google-genai` `client.aio.live.connect`, one asyncio task per direction. Sessions are held in memory, which is why the API runs as one process (section 10).
- **After hang-up** (decided 2026-11-14): when the call ends, the relay calls `request_confirmation` for the call's latest ready quote. If there is no ready quote, no SMS goes out and the dashboard shows that the call ended without one. The agent never has to remember to send the link.
- **Tool bridge**: at call start the relay lists the MCP tools and turns their JSON Schemas into Gemini function declarations. It authenticates to MCP as the identified caller with a short-lived token from our own auth server, so MCP treats the phone like any other client (vision §2: no client is special).
- **Model and platform**: a 3.x Live model through the Gemini API (AI Studio key), not Vertex AI. Finnish is listed only for the 3.x audio models, and the Vertex "Configure language and voice" page does not list it. `gemini-3.8-live` is the candidate. Google's docs list synchronous and asynchronous function calling for it, and asynchronous calls let the agent keep talking while `build_quote` runs. Pick after the spike in M0.
- **Finnish** (researched 2026-11-14): Finnish (`fi`) is in Google's table of additional languages for 3.x audio models, not in the base 24 that every audio model supports. The native audio models detect the language themselves and take no `language_code`. By default the agent follows the caller. The `call_language` setting can force Finnish or English, which becomes one line in the system prompt ("Always respond in Finnish"). Any of the 30 HD voices should work. Quality is not tested: recognition of product names and Finnish compound words may be weaker than for the major languages. Two existing parts of the design soften this: search tolerates typos (trigram), and the confirmation page shows what we understood next to what we added, so a misheard word is easy to spot (vision §6).
- **System prompt** (ours): collect all lines, then one `build_quote`. One clarification per turn. Speak the top pick and at most one alternative (vision §5). Give the no-allergen-listing notice once, at the end. Never say the order is placed. Say the link comes by SMS after hanging up. When a decision cannot be overridden, say so and move on.
- **Call screen**: dial-pad look, timer, mute, hang-up. No proximity sensor (vision §9).

### 7.2 Webshop with WebMCP (P0)

- SvelteKit route `/shop`: login (same users as the connector), search, product cards with images, cart.
- After login the page registers the same operations as the MCP tools through `document.modelContext`, falling back to `navigator.modelContext` (the API moved between the two in 2026). Each tool calls `/api/v1` with the session cookie.
- OpenAI side: OpenAI announced WebMCP support in the ChatGPT desktop app's built-in browser in August 2026. Check this on day one with our own page. For ordinary Chrome, use the MCP-B polyfill or Chrome's testing flag.
- TypeScript types are generated from the OpenAPI document (`openapi-typescript`), so the web tools follow the backend schemas.

### 7.3 Claude connector (P1)

- The connector URL is `https://<host>/mcp`. FastAPI serves the OAuth protected-resource metadata (RFC 9728) and authorization-server metadata. The MCP SDK's auth routes handle client registration, authorize with PKCE and token. Our provider stores clients, codes and tokens in Postgres. Authorize redirects to the SvelteKit `/login` page (email and password) and back.
- Claude lets you add a custom connector with auth turned off, so the tools can be tested before login works.
- Accounts (decided): both self sign-up (email, password and phone number) and accounts we create and hand out to judges and peers. A handed-out account gets the recipient's own phone number, because the confirmation SMS goes there.
- Tool results carry structured fields and product names only. Marketing text is never sent to an agent (*proposed*; vision §8 treats all product free text as data).

### 7.4 OpenAI connector (P1)

The same MCP URL as a custom connector in ChatGPT. Check its auth requirements when we get there.

## 8. Quote, confirmation, order, audit and dashboard

### 8.1 Quote

- Hash: SHA-256 over RFC 8785 canonical JSON of customer, lines, totals, delivery dates, issue time, expiry and rule-set version.
- Signature: compact JWS with Ed25519 (EdDSA) and a `kid`. The public key is published at `/.well-known/jwks.json` (vision §12).
- Each line carries labelled claims: stock verified or unverified, price from the API, origin from product data (vision §12).
- Status: `ready` → `pending_confirmation` → `confirmed`, `cancelled`, `expired` or `void` (replaced by an edit or by worse availability).

### 8.2 SMS link

- `request_confirmation(quote_id)` has no recipient argument. The recipient is the identified user's registered number (vision §6).
- Delivery (decided 2026-11-14):
  - **Simulated phone inbox**: every message lands in the inbox of the account that made the order. It is shown on the phone page only. This is our own path, so the demo never depends on an SMS provider.
  - **Real SMS**: Twilio sends only when the feature flag `SMS_TWILIO_ENABLED` is on (default off) and the number is on the allowlist `SMS_ALLOWLIST`. Every other number gets the inbox message only, so a made-up number that belongs to a stranger never gets our SMS.
  - **Allowlist**: holds real phone numbers, so it lives in Azure Key Vault (comma-separated E.164 numbers), never in the repo (section 10.2).
  - **Vision**: this deviates from vision §6, where the SMS is the only path. The inbox is a demo setting (`demo_inbox`, on for the event). Production would use SMS only.
- The token is 256 random bits, stored as SHA-256. It belongs to a confirmation that holds the recipient and points to the current quote (decided). It expires with the current quote.
- Link `https://<host>/c/<token>`. *Proposed*: opening the link never uses it up, so SMS link previews and repeated opens do no harm. Confirm or Cancel uses it up.
- Twilio sends with a status callback to `/api/v1/twilio/status` (Twilio signature checked). A failed delivery appears on the dashboard. The simulated inbox still has the message, so the buyer can confirm from there. With the inbox off, nothing is ordered and a resend can be offered (vision §6).
- Twilio setup: a trial account only sends to verified numbers. With the allowlist that may be enough: verify each allowlisted number in Twilio, and upgrade only if the trial's limits get in the way. Check the sender-id rules for Finland at the same time.

### 8.3 Confirmation page (`/c/[token]`)

- Rendered on the server by SvelteKit from FastAPI data only (vision §6).
- Odd things first, each with an acknowledge box. Confirm stays disabled until every box is ticked.
- Asked and added side by side, grouped by request. Quantities in sales units and in the asked unit, delivery date, gross total, and a readable trace.
- Edits (quantity, remove a line, pick an alternative) run the engine again and produce a new quote on the same page. The old quote becomes void and the confirmation points to the new one. Confirm must send the hash of the quote on screen, so a stale tab cannot confirm an old version.
- Confirm re-checks availability. If it got worse, the quote is void and a new one is shown. Otherwise the order is created and the page shows "order received".
- Product text is escaped (Svelte's default, never `{@html}`). `Referrer-Policy: no-referrer` keeps the token out of Referer headers, including towards the hotlinked image host.

### 8.4 Order record

`orders` and `order_lines` in our database (vision §10). `get_order_status` returns pending confirmation, confirmed, cancelled or expired. Peppol export is a stretch goal.

### 8.5 Audit

- `audit_events(seq, at, type, actor, session_id, quote_id, payload, payload_hash, prev_hash, hash)`, with `payload_hash = SHA-256(canonical payload)` and `hash = SHA-256(prev_hash + payload_hash + seq, at, type)`. Chaining over `payload_hash` (*proposed*) lets the dashboard verify the chain without the payloads, so personal data in a payload can be hidden or redacted without breaking it.
- The writer takes a transaction-level advisory lock (`pg_advisory_xact_lock`) so the chain stays linear. It is released at commit, so it would also work through transaction pooling, but the app connects directly anyway (section 10.1). The application's database role has only `INSERT` and `SELECT` on the table.
- Events: request, candidates considered, filters applied, choice and reason codes, quote, SMS sent or failed, confirmation (vision §11). The full engine input is stored so any decision can be replayed.
- `scripts/verify_audit_chain.py` checks the chain, for the pitch.

### 8.6 Dashboard

- A `status_events` row is written in the same transaction as each audit event. A trigger calls `pg_notify`. A FastAPI listener on its own direct connection (port 5432, not PgBouncer) pushes the events over two SSE streams: a public one with the public part of each event, and a private one filtered to the logged-in user's own orders (operators get all).
- `/dashboard`: orders grouped by company. Open one to see the steps in plain words, rejected candidates, flags and confirmation state. Failures too: rejected, link expired, SMS failed, callback requested. Large type, readable from a distance.
- The relay emits call events (started, tool called, ended), so a call shows up while it is still going on.
- A periodic job marks expired quotes and emits the event, because expiry does not happen on its own.
- Public and private views (decided 2026-11-14): anyone can see general data without logging in, and only the owner sees chat logs and contact details (section 9.5). Each status event carries a public part (step, status, counts, totals, timestamps, generated company name, no phone numbers or personal names) next to the private detail.
- Private endpoints accept web sessions only, never MCP tokens, so no agent can read the log (vision §8). Public endpoints carry no audit payloads, tool arguments or transcripts.
- How operators log in is a follow-up issue (section 14).

## 9. Endpoints and messages

Checked against the UI design (18 screens: landing, call, confirmation, dashboard, shop) on 2026-11-14. Everything under `/api/v1` is in the OpenAPI document. Paths and fields are *proposed* until the first implementation, but every screen in the design maps to a row here.

Two rules, from vision §6 and §8:

- **The confirmation link goes only to the account that made the order**: to that account's simulated phone inbox, and by Twilio SMS to allowlisted numbers when the flag is on (section 8.2). No agent tool, voice message or public endpoint returns the token or the link. The design's "Tap to check it" on the call-end screen fits if it opens the message in the simulated phone. The shop's "Open confirmation page" doesn't: a browser agent works inside that page and could follow the link (vision §8). So the simulated inbox is shown on the phone page only, never in the shop (decided).
- **Agents get the seven tools and nothing else.** Confirm, cancel, acknowledgements, edits on the page, the inbox, the private dashboard and the audit log are web-session endpoints. They never accept MCP tokens and are never registered as WebMCP tools.

### 9.1 Agent tools and their REST twins

The seven tools of vision §8, unchanged. Each has a REST twin with the same Pydantic models, which the WebMCP tools in the shop call with the session cookie.

| MCP tool | REST twin |
|---|---|
| `search_products` | `GET /api/v1/products?q=&claims=&category=&needed_by=` |
| `get_customer_context` | `GET /api/v1/customer-context` |
| `search_recipes` | `GET /api/v1/recipes?q=&diet=&occasion=` |
| `get_recipe` | `GET /api/v1/recipes/{id}?portions=` |
| `build_quote` | `POST /api/v1/quotes` |
| `update_quote` | `POST /api/v1/quotes/{id}/update` (returns a new quote) |
| `request_confirmation` | `POST /api/v1/quotes/{id}/confirmation-request`, returns `{sent_to_masked, sms_status}` |
| `get_order_status` | `GET /api/v1/quotes/{id}/status` |

Fields the screens need that section 4.1 doesn't list yet:

- **Customer context**: `company_name`, exclusions with Finnish and English labels, `phone_masked`, usual items with product id, quantity and unit ("my usual order" asks for all of them at once).
- **Line**: name in Finnish and English, `image_url` (section 5.5), `reason_text` in Finnish and English, price per kg or litre, stock status (verified or unverified), origin, `alternatives[]` (id, label, quantity, line total).
- **Request group**: `LineRequest` gets an optional `group` label that is echoed back, and the quote gives a subtotal per group (Shop-3: "Mon, chicken curry, 3 lines, 118,40 €").
- **Trace**: candidates found, removed per reason, left, and the ranking rule ("14 found, −4 arrive after Monday, −3 out of stock, −2 contain milk, 5 safe"). Each candidate is counted once, at the first step it fails, in the order of section 4.2.
- **Flag**: stable `flag_key`, `line_ids`, `kind` (`acknowledge` or `choose`), `options[]` with line totals for `choose` (Confirm-1: "Keep 24 l / Exactly 20 l"), `acknowledged_at`.
- **Quote**: `version`, `parent_quote_id`, `expires_at`, a delivery summary for the whole order, and `not_ordered[]` for recipe ingredients the buyer said they already have. Nothing is left out unless the buyer said so (vision §6).
- **Recipe**: `image_url` (in the data). The data has no English names, no English diet labels and no cooking time, so the design's "45 min" has no source.

### 9.2 Accounts and web sessions

| Method and path | Request → response | Screens |
|---|---|---|
| `POST /api/v1/demo/accounts` | `{phone_e164, exclusions[], lang}` → creates the demo user and a generated company, sets the session cookie (this is the login), returns `{company_name, phone_masked, kitchen_profile, usual_items}`. Exclusions must be keys of `allergen_rules.yaml` | Main, Call-2 |
| `GET /api/v1/private/inbox` | → `[{id, at, text, link}]` for the logged-in account. New messages also arrive on the private stream as `inbox_message` | Simulated phone (Call-4) |
| `POST /api/v1/signup` | `{email, password, phone_e164}` → session cookie | Connector accounts, shop |
| `POST /api/v1/session`, `DELETE /api/v1/session` | `{email, password}` → session cookie; log out | Shop, dashboard |
| `GET /api/v1/me` | → `{company_name, exclusions, phone_masked}` | Shop header, call screen |

- **Same browser, same account**: number entry again in the same browser updates the profile. A number that already has an account in another browser gets a new account and never logs into the old one, so nobody can read another visitor's chats by typing their number (*proposed*). Private data belongs to the account, not to the phone number.
- **Generated company names**: we generate them when the account is created, and the visitor never types one, so they are safe to show publicly.

The connector's OAuth routes come from the MCP SDK (section 7.3). Every path into a call must go through the number entry, because that number is the SMS recipient and the session is the login. The design's desktop path (Landing → Call-0 → Call-3) skips it.

### 9.3 Voice WebSocket (`/voice/ws`)

Binary frames carry PCM audio (16 kHz up, 24 kHz down). Text frames carry JSON:

| Direction | Message | Fields |
|---|---|---|
| Browser → server | `hangup` | none |
| Server → browser | `ready` | none (Gemini session open) |
| Server → browser | `interrupted` | none (flush playback, section 7.1) |
| Server → browser | `transcript` | `who` (buyer or agent), `text`, `final` |
| Server → browser | `ended` | `duration_s`, `quote_id` or null, `total_cents`, `sms_status` (`sent`, `failed`, `off` when the flag is off or the number isn't allowlisted, or `none` without a quote), `inbox` (true when the message is in the simulated phone) |

`ended` arrives before the socket closes and covers the no-quote and SMS-failed cases. The link itself never travels on this socket: the simulated phone reads it from the inbox endpoint (section 9.2). Live captions need Gemini Live's input and output transcription turned on. Transcripts go to the dashboard as status events and to a separate `call_transcripts` table. They stay out of the engine input (vision §5) and out of the audit chain, which can never be erased (*proposed*).

### 9.4 Confirmation page (web only)

The token is in the path. `GET` never uses it up.

| Method and path | Request → response | Screens |
|---|---|---|
| `GET /api/v1/confirmations/{token}` | → `{state, expires_at, company, exclusions, quote{id, version, hash, total_cents, delivery}, requests[{asked, group, lines[]}], flags[], order?}` | Confirm 1 to 3 |
| `POST …/{token}/acknowledgements` | `{quote_hash, flag_key}` → updated view | "Got it" |
| `POST …/{token}/edits` | `{quote_hash, op: set_quantity \| remove \| choose_alternative, line_id, quantity?, alternative_id?}` → new view; 409 if the hash is stale | Stepper, remove, alternatives |
| `POST …/{token}/confirm` | `{quote_hash}` → `{order_number, confirmed_at}`; 409 with a new view if availability got worse; 422 if a flag isn't acknowledged; 410 if expired | Confirm |
| `POST …/{token}/cancel` | `{quote_hash}` → `{state: cancelled}` | Cancel |

Edits use the same service as `update_quote`. The page also needs states the design doesn't show yet: expired, cancelled, void after the availability recheck, an edit that ends in a clarification or a rejection, and already confirmed. Confirm-3 says the receipt can be reopened "until the end of the event", but the token expires with the quote (section 8.2). This needs a decision: either a read-only receipt after confirming, or no reopening.

### 9.5 Dashboard: public and private

Decided 2026-11-14: general data is public with no login, and private data needs the login from section 9.2.

**Public** (no login, every order):

| Method and path | Response | Screens |
|---|---|---|
| `GET /api/v1/public/orders?state=&channel=&since=` | `business_now`, `totals{active, waiting, confirmed, attention, confirmed_cents, by_channel}`, `companies[{name, exclusions, orders[{session_id, order_number, channel, client, state, state_since, title, step_text, line_count, total_cents, flags, next_step}]}]` | Overview |
| `GET /api/v1/public/orders/{session_id}` | Header, lines with trace and ranked candidates, flags (text, acknowledged or not), `quote{id, version, hash}`, signature valid | Summary |
| `GET /api/v1/public/orders/{session_id}/steps` | `[{seq, order_index, at, actor, type, text{fi, en}, payload_hash, prev_hash, hash}]` | Full flow (engine steps), Audit log (without JSON) |
| `GET /api/v1/public/audit/verify?session_id=` | `{ok, checked, first_bad_seq, signature_valid}` | "Audit chain intact", "Verify again" |
| SSE `/api/v1/public/stream` | `order_updated` (public card), step events | Live updates |

**Private** (logged in; a user sees only their own orders, an operator sees all):

| Method and path | Response | Screens |
|---|---|---|
| `GET /api/v1/private/orders` | The user's own orders, with contact details | "My orders" |
| `GET /api/v1/private/orders/{session_id}/transcript` | The call or chat transcript | Full flow: "Buyer (transcript)", "Agent (transcript)" |
| `GET /api/v1/private/orders/{session_id}/events` | Full events: tool arguments and results, payloads, Identity row; `?download=1` returns the JSON file | Full flow, Audit log JSON, "Download JSON" |
| SSE `/api/v1/private/stream` | The user's own transcripts, `inbox_message`, and the private detail of their events | Live updates, simulated phone |

- **Public**: totals, channel counts, card status, generated company names, kitchen exclusions, lines, flags, templated steps, hashes and the verify result.
- **Private**: transcripts, phone numbers, emails, tool arguments and results, raw payloads and the Identity row.
- Another user's `session_id` in a private endpoint returns 404, so ids reveal nothing.
- "Verify again" works without login because the chain hashes over `payload_hash` (section 8.5).
- The chain is global (section 8.5). The design numbers events per order ("#1 to #31"), so the responses carry `order_index` for display next to the global `seq`.
- The client name ("Claude", "ChatGPT") comes from the OAuth client registration. A WebMCP call can't tell which agent is calling, so it shows as "browser agent".
- *Proposed*: an MCP or WebMCP session counts as active for 10 minutes after its last tool call, since it has no hang-up.
- Operators are users with an operator role. How they log in is a follow-up issue (section 14).

### 9.6 Shop

| Method and path | Purpose |
|---|---|
| `GET /api/v1/quotes/current` | The session's latest quote ("Current order") |
| `GET /api/v1/quotes/{id}` | One quote |
| `POST /api/v1/chat` | `{conversation_id, message}` → streamed text and cards (menu, recipe, quote). Only if the in-page agent is built: it is the stretch A2UI item (vision §13), and it would run a server-side model as an MCP client like the voice relay, with channel `web_chat` |

There is no cart endpoint. The page keeps the order list in the browser and sends it as one `build_quote` (*proposed*). The design shows a static copy of the webshop with a chat panel instead of the P0 shop in section 7.2 (search, product cards, WebMCP). Which one is P0 needs a decision.

### 9.7 Other

- `POST /api/v1/twilio/status`: Twilio delivery callback (signature checked). Emits `sms_delivered` or `sms_failed`.
- `GET /.well-known/jwks.json` (section 8.1), the OAuth metadata and routes (section 7.3), `/mcp`.
- FastAPI docs at `/api/v1/docs` and `/api/v1/openapi.json`, so Caddy routes them to FastAPI. The landing page links to them ("Tool list and OpenAPI docs").

New columns and event types these endpoints need:

- `sessions`: `state`, `state_since`, `ended_at`, `ended_by`, `client_name`, `prompt_version`.
- `orders`: a readable `order_number` (for example D-1042).
- `confirmations`: `opened_at`, and one acknowledgement row per flag (`flag_key`, `at`).
- `users`: `role` (`buyer` or `operator`). `companies`: generated name.
- `sms_messages`: one row per message and delivery path (`twilio` or `inbox`), each with its own status.
- `quotes`: `version`, `parent_quote_id`.
- `audit_events`: `actor`, `text_fi`, `text_en`, `payload_hash` (section 8.5).
- Event types: `tool_returned` (with the response sent to the agent), `link_opened`, `flag_acknowledged`, `stock_rechecked`, `sms_delivered`, `sms_failed`.

## 10. Hosting on Azure

The database is the existing Azure Database for PostgreSQL instance. The app runs on **one Linux VM with Docker Compose** (`caddy`, `api`, `web`).

Why a VM and not Container Apps or Web Apps (asked in review, decided 2026-11-14): with the database managed, setup takes about as long either way. The difference is how long a connection may stay open. Container Apps documents a 240-second request timeout, and App Service has a similar load-balancer limit. Microsoft's docs don't say whether these also cut an open WebSocket or SSE stream, and both carry the core demo: every voice call is one WebSocket, and the dashboard is one SSE stream. On the VM:

- WebSockets and SSE have no time limit;
- Caddy serves the web app and the API on one domain, which keeps cookies and the OAuth metadata simple, and it gets HTTPS certificates by itself;
- one FastAPI process holds the voice sessions in memory, so there is nothing sticky to configure.

### 10.1 Database

- **Extensions**: `vector`, `pg_trgm` and `unaccent` are allowed in the `azure.extensions` server parameter (done 2026-11-14). Each database still needs `CREATE EXTENSION`, which the first migration runs.
- **Connections**: all app connections go straight to port 5432, not through PgBouncer. PgBouncer in transaction mode drops `LISTEN/NOTIFY` notifications (the dashboard) and keeps no session-level state. One API process needs only a few connections.
- **`DATABASE_URL`** includes `sslmode=require`, which Azure requires.
- **Databases**: the VM uses `junction_demo` on the Azure server (stage demo, judges and peers). Each laptop runs its own Postgres in Docker for development (decided in review). We revisit this once we know how many developers change database data or schema at the same time.
- **Laptop database**: the `pgvector/pgvector` image at the same major Postgres version as the Azure server. `pg_trgm` and `unaccent` ship with it. `DATABASE_URL` points at the container without TLS.
- **Firewall**: one rule for the VM's IP (or its VNet). Laptops don't connect to the server, so they need no rules.
- **Backup before the pitch**: a `pg_dump` of `junction_demo`, or the server's point-in-time restore. A VM disk snapshot no longer holds the data.

### 10.2 VM setup

1. VM in the same region as the database server, Ubuntu LTS. The database runs elsewhere, so 2 vCPU and 8 GB is enough (for example D2s v5). Open ports 80 and 443 only.
2. Allow the VM's IP (or VNet) in the database server's firewall.
3. A DNS name: the Azure public IP's DNS label, or a short team domain. A short domain fits better in an SMS.
4. Install Docker. Secrets live in Azure Key Vault, with no `.env` on the VM (decided): `VALIO_API_KEY`, `GEMINI_API_KEY`, Twilio credentials, JWS private key, `DATABASE_URL` with `sslmode=require`, session secret, `SMS_TWILIO_ENABLED`, `SMS_ALLOWLIST`. *Proposed* mechanism:
   - The VM gets a system-assigned managed identity with the "Key Vault Secrets User" role on the vault.
   - FastAPI loads the secrets at startup with `azure-identity` and `azure-keyvault-secrets`, so no secret is written to the VM's disk. Changing the flag or the allowlist takes effect after an API restart.
   - Key Vault secret names allow only letters, digits and dashes, so `VALIO_API_KEY` is stored as `valio-api-key`, and so on.
5. Compose runs `caddy`, `api` (uvicorn, one worker) and `web` (SvelteKit node build). No database service and no volume.
6. Deploy with `git pull && docker compose up -d --build`. Automate with a GitHub Action over SSH if time allows.
7. Caddy routes `/api/*`, `/mcp`, `/.well-known/*`, the OAuth routes and `/voice/*` to FastAPI, and everything else to SvelteKit. Everything is same-origin, so cookies stay simple.

Laptops run the same Compose file plus a development override (`deploy/docker-compose.dev.yml`, *proposed*) that adds a `db` service from the `pgvector/pgvector` image with a volume. The FastAPI and SvelteKit dev servers can also run directly against that container. Laptops read their settings from a local `.env`, which is never committed (only `.env.example` is). The same settings loader reads either `.env` (development) or Key Vault (production).

Production path: the database and Key Vault parts are already in place. Only Azure Container Apps is still pitch-only.

## 11. Repository layout, tooling and tests

```
api/                     FastAPI app
  app/
    engine/              pure decision functions, no IO
    services/            gather inputs, call the engine, persist, audit, notify
    adapters/            Valio client, Twilio, Gemini embeddings, database repositories
    interfaces/
      rest/              /api/v1 routes (OpenAPI)
      mcp/               MCP tools
      voice/             Gemini Live relay
      auth/              OAuth provider, web sessions
    schemas/             Pydantic models shared by REST and MCP
  migrations/            Alembic
  tests/
web/                     SvelteKit
  src/routes/            phone, shop, c/[token], dashboard, orders, login, signup
policy/                  rule files and message templates (versioned)
data/                    existing data files, snapshots/
scripts/                 loaders, embeddings, snapshot recorder, audit-chain checker
deploy/                  docker-compose.yml, docker-compose.dev.yml, Caddyfile, .env.example (development only)
```

Tooling (*proposed*): Python 3.12 with `uv`, `ruff` and `pytest`. `pnpm` and `svelte-check` for the web app. GitHub Actions runs lint and all tests on pull requests, with the same `pgvector/pgvector` image as a service container.

Tests:

- Engine unit tests on hand-built inputs, with no database and no network.
- Scenario tests on the recorded snapshot. The milk case in `valio-api-analysis.md` §11 already covers unlimited stock, partial stock, unverified stock and an unorderable product (464073, 464201, 464306, 462775, 463380, 464119, 464440).
- Allergen tests for every rule in vision §10: `X99`, `AM` versus `ML`, the nut set, `UNDECLARED`, no listing, substitutes.
- Replay test: run the engine again on stored inputs and compare quote hashes.
- MCP contract test with the SDK's client, a WebMCP smoke test in the browser, and one Playwright run of the confirmation page.

## 12. Milestones and workstreams

**Contract first.** Before anything else, write the Pydantic models for the seven tools and a stub engine that returns a fixed milk quote. Every stream then builds against the same contract.

| Milestone | Done when |
|---|---|
| M0 Foundations and spikes | VM with HTTPS and Compose. Key Vault holding the secrets, readable by the VM's managed identity. Database firewall rule for the VM. `junction_demo` created with the extensions enabled (they are already allowed on the server). Development Compose override with Postgres in Docker. Product file in Postgres. Valio client working, with a snapshot of the demo shortlist. Simulated phone inbox working. Twilio flag tested with one allowlisted number. Gemini Live spike on a 3.x model: Finnish recognition of real product names and compound words, latency, and one function call through the relay |
| M1 Walking skeleton | From MCP Inspector: `build_quote` (milk, one line) → `request_confirmation` → SMS and simulated inbox → confirmation page → Confirm → order record → dashboard event → audit chain. Running on the VM |
| M2 Phone demo | Number entry → demo account → call screen → relay → SMS after hang-up |
| M3 Engine breadth (P0) | Allergen and diet rules, units and rounding, availability states and cutoffs, basic substitution with callback, clarifications, rejections with a next step, flags and acknowledgements, edits, re-check at confirmation, JWS |
| M4 WebMCP and dashboard | Webshop tools used from the ChatGPT desktop browser. Dashboard readable from a distance |
| M5 P1 | Sanity checks, recipes over MCP, better substitution and exact-fit, Claude connector with login, OpenAI connector |
| M6 Rehearsal | Stage runs on the snapshot, scenarios scripted, audit chain verified, `pg_dump` of `junction_demo` taken |

| Workstream | Owns | First deliverable |
|---|---|---|
| Engine | `api/app/engine`, `policy/` | Pure pipeline for the milk scenario |
| Data and search | Loaders, search, categories, images, seed data. Recipes and recipe linking (Juho, vision §7) | Products in Postgres and a working search |
| Platform | FastAPI, MCP, auth, Valio adapter, audit, SMS, deploy | VM and the MCP skeleton |
| Voice | Relay, prompt, call screen | The M0 spike |
| Web | Confirmation page, dashboard, webshop with WebMCP | Confirmation page against the stub |

## 13. Risks

| Risk | Effect | Mitigation |
|---|---|---|
| Finnish is only in Gemini's extended language tier (3.x models), so product names and compound words may be misheard | Wrong lines on the main stage demo | Spike in M0 with real product names. Typo-tolerant search. Asked and added side by side on the confirmation page. Fall back to English |
| WebMCP API keeps moving (its location changed in 2026) | Webshop tools invisible to the agent | Detect both locations. Test in the ChatGPT desktop browser in M4. Polyfill for Chrome |
| Twilio trial only sends to verified numbers | Allowlisted numbers get no SMS | Verify each allowlisted number in Twilio, or upgrade |
| Twilio down or slow during the demo | No real SMS | The simulated phone inbox is the main path and always gets the message (section 8.2) |
| A visitor types a made-up number that belongs to someone | A stranger gets our SMS | Real SMS only to allowlisted numbers, behind a flag that is off by default (section 8.2) |
| Valio API rate limit or downtime during the pitch | Quotes fail on stage | Run the stage demo on the snapshot |
| Hotlinked images blocked or slow | Broken images | Placeholder, `no-referrer` |
| Venue Wi-Fi degrades WebSocket audio | Call breaks up | Test on the venue network. Phone hotspot as backup |
| SMS apps open the link to build a preview | Token used up before the buyer sees it | Opening never uses the token up (8.2) |
| One VM | App outage | One-command redeploy. The data lives on the managed server |
| Laptop Postgres (Docker) and the Azure server differ | Works on a laptop, fails on the VM | Same major version and extensions locally. Deploy to the VM from M0 on, so differences show up early |

## 14. Follow-up issues

The first review settled every other open question (section 1). These three get their own issues, created from this spec:

1. **Nut-free set.** Whether pine nut (`PN`), coconut (`SO`) and peanut (`AP`) count as nuts. Vision §10 left this to old issue #6, which is not a source.
2. **Demo account content.** The kitchen profile and order history a new demo account gets (vision §13, still open).
3. **Operator login.** How Aimo operators log in to see every company's private data (vision §11). The public and private split and the buyers' login are decided (sections 9.2 and 9.5).

Inputs we are waiting for:

- The 11-column `data/valio_category_names.csv` from the category brief.
- The product image file (`code`, `name`, `img`).

## 15. External references (checked 2026-11-14)

- Gemini Live API tool use and model support: https://aistudio.google.com/docs/live-api/tools
- Gemini Live languages, Finnish listed for 3.x audio models: https://firebase.google.com/docs/ai-logic/live-api/limits-and-specs and https://ai.google.dev/gemini-api/docs/live-api/capabilities (the second was seen only in summary)
- Vertex AI language list, without Finnish: https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/live-api/configure-language-voice
- Gemini Live ephemeral tokens example (not used, for comparison): https://github.com/google-gemini/gemini-live-api-examples
- Claude custom connectors and authentication: https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp and https://claude.com/docs/connectors/building/authentication.md
- WebMCP in the ChatGPT desktop browser (OpenAI developer announcement): https://x.com/OpenAIDevs/status/2092344959248761263
- WebMCP browser status: https://www.spronta.com/blog/state-of-webmcp-july-2026/
- Azure Container Apps ingress (240-second request timeout): https://learn.microsoft.com/en-us/azure/container-apps/ingress-overview
- Azure App Service request timeout: https://learn.microsoft.com/en-us/troubleshoot/azure/app-service/web-request-times-out-app-service
