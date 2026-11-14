# web

SvelteKit app with `adapter-node`: start page (`/`), demo phone (`/phone`), webshop (`/shop`), confirmation page (`/c/[token]`) and dashboard (`technical-plan.md` §11).

```sh
pnpm install
pnpm dev                                  # http://localhost:5173, with the fixtures and the mock voice relay
pnpm check                                # svelte-check
pnpm build                                # node build in build/
pnpm test                                 # Vitest unit tests
pnpm gen:api-types                        # TypeScript types from src/lib/generated/openapi.json
pnpm serve:mock                           # the build with the fixtures and the mock voice relay on /voice/ws
pnpm exec playwright install chromium     # once, for the end-to-end tests
pnpm test:e2e                             # Playwright: builds the app and runs it against the fixtures
```

The end-to-end tests run on a phone and a laptop profile (`playwright.config.ts`). They need no API, database or Gemini. Chromium gets a fake microphone that plays a speech-like sound (`tests/support/fake-voice.ts`), so the call works headless.

## Settings

| Variable | Values | Default |
|---|---|---|
| `CONFIRMATION_SOURCE` | `fixture`: an in-memory stand-in for the engine. `api`: the FastAPI endpoints in `technical-plan.md` §9.4 | `fixture` in `pnpm dev`, `api` in a build. Compose sets `api`; set `fixture` to opt in |
| `DEMO_SOURCE` | `fixture`: in-memory demo accounts and inbox, and the mock voice relay. `api`: the FastAPI endpoints in `technical-plan.md` §9.2 and the real relay (§9.3) | `fixture` in `pnpm dev`, `api` in a build. Compose sets `api`; `pnpm serve:mock` sets `fixture` |
| `API_BASE_URL` | Where FastAPI runs, used with either setting on `api` | `http://localhost:8000`. Compose sets `http://api:8000` |
| `SHOP_LANG` | The webshop's default language. `auto`: Finnish when the browser's most preferred language (`Accept-Language`) is `fi` or `fi-*`, English for anything else. `fi` or `en`: always that language. The EN/FI toggle (`?lang=fi`, `?lang=en`) works with every value | `auto` |

The server reads them from its process environment, for example `CONFIRMATION_SOURCE=api pnpm dev`. Neither `pnpm dev` nor the Compose `web` service reads the root `.env` yet, so the lines in `.env.example` document the defaults rather than set them.

## Routes

| Route | What it is |
|---|---|
| `/` | The demo start page (`docs/design` 00 and 01) |
| `/phone` | The demo phone: set up, Contacts with S.I.MO, call, call ended and the inbox (`docs/specs/call-screen.md`, `docs/design` 10 to 14). On a computer it shows inside a phone frame |
| `/c/[token]` | The confirmation page (`docs/specs/confirmation-page.md`) |
| `/dashboard` | The live order dashboard (`docs/specs/dashboard.md`, #50) |
| `/shop` | The webshop with the WebMCP tools (#56): our own page in the Aimo webshop's style, twelve Valio products, the phone's number entry |
| `/api/v1/demo/accounts`, `/api/v1/me`, `/api/v1/private/inbox`, `/api/v1/private/inbox/stream` | The fixture for `technical-plan.md` §9.2 with `DEMO_SOURCE=fixture`; passed through to FastAPI with `api` |
| The agent tools' REST twins (`/api/v1/products`, `/api/v1/quotes`, ...) | Passed through to FastAPI with `DEMO_SOURCE=api`. With `fixture` they answer 503: there is no engine fixture |

### The demo phone with the fixtures

The browser always calls the same-origin paths of `technical-plan.md` §9.2 and §9.3, so switching to the real backend is just `DEMO_SOURCE=api`. On the VM, Caddy sends `/api/*` and `/voice/*` to FastAPI and these SvelteKit routes are never reached; locally, they pass the request through to `API_BASE_URL`, and `pnpm dev` proxies `/voice/ws` there.

With `DEMO_SOURCE=fixture`, `/voice/ws` is the mock relay in `src/lib/server/demo/relay.ts`, attached to Vite's server by `vite.config.ts` and to the build by `mock/serve.ts` (plain `node build` has no `/voice/ws`). It speaks the §9.3 protocol: it plays a speech-like hum for each scripted S.I.MO turn and sends captions for both sides. It doesn't understand speech: each time the caller says something, the next scripted line becomes their caption. The caller agrees to the link on their second line, and hanging up after that drops a message with a `/c/fx-ready-<id>` link into the inbox. Talking over S.I.MO sends `interrupted`.

Fixture test numbers (the national part): ending in `0429` hits the demo limit, `7001` reports an SMS sent, `7002` an SMS that failed.

### Fixture tokens

With `CONFIRMATION_SOURCE=fixture`, the token picks a scenario: `fx-<scenario>` or `fx-<scenario>-<anything>`, so every test or browser tab can have its own order. Any other token shows the invalid-link page. The scenarios are in `src/lib/server/confirmation/fixture.ts`.

| Token | Scenario |
|---|---|
| `fx-ready-...` | The order from the design screens, with three flags to check |
| `fx-requote-...` | Stock gets worse at Confirm, so a new quote is shown |
| `fx-fi-...` | The same order in Finnish |
| `fx-confirmed-...` | Already confirmed: the receipt |
| `fx-cancelled-...` | Cancelled |
| `fx-expired-...` | Expired |

For example http://localhost:5173/c/fx-ready-mine. The fixture keeps its state in memory until the server restarts.

## Webshop and WebMCP

`/shop` (#56) is a static page: twelve real Valio products (`src/lib/shop/products.json`, picked from the static product file by `scripts/select_shop_products.py` in the repository root), no prices, cart or search. Visitors type their number in the same number entry as the phone, which makes the same demo account and `simo_session` cookie, so `/phone` in the same tab opens on Contacts with that account. Product pictures are hotlinked with `referrerpolicy="no-referrer"` and a placeholder; the product image file is not in the repository yet, so every product shows the placeholder for now.

The page registers the agent tools with the browser's agent through `document.modelContext`, falling back to `navigator.modelContext` (`src/lib/shop/webmcp.ts`). They are exactly the tools `/mcp` lists, with the same names, descriptions and input schemas, and each calls its REST twin under `/api/v1` with the session cookie. Confirm, cancel, the inbox and page edits are never tools. After `request_confirmation` the page says the link is in the demo phone and links to `/phone`, never to the link itself.

Generated files in `src/lib/generated/`, never edited by hand:

| File | Made by | Checked by |
|---|---|---|
| `agent-tools.json` | `uv run python -m app.interfaces.web_contract` in `api/`, from the MCP server's tool list and the REST twins' routes | `api/tests/test_web_contract.py` |
| `openapi.json` | the same command, from FastAPI's OpenAPI document | `api/tests/test_web_contract.py` |
| `openapi.ts` | `pnpm gen:api-types`, with `openapi-typescript` from `openapi.json` | `scripts/api-types.test.ts` (`pnpm test`) |

After changing a tool, a tool description or an API schema, run both commands and commit the three files.

To try the tools locally, run FastAPI (see `api/`) and the web app against it: `DEMO_SOURCE=api pnpm dev`, then open http://localhost:5173/shop. With the default `DEMO_SOURCE=fixture` the page and the number entry work, but the tools answer 503. The page needs a browser with WebMCP: the ChatGPT desktop app's built-in browser, or ordinary Chrome with the MCP-B extension (its `@mcp-b/global` polyfill) or Chrome's WebMCP testing flag in `chrome://flags`. The tools card on the page says whether it found one. The Playwright tests use a shim instead (`tests/support/webmcp-shim.ts`).

## Screenshots

`tests/screenshots.spec.ts`, `tests/phone-screenshots.spec.ts` and `tests/shop-screenshots.spec.ts` save screenshots in `docs/screenshots/confirmation-page/`, `docs/screenshots/phone/` and `docs/screenshots/shop/`. They are skipped in normal test runs. Regenerate them with:

```sh
SCREENSHOTS=1 pnpm exec playwright test screenshots --project=phone
SCREENSHOTS=1 pnpm exec playwright test phone-screenshots
SCREENSHOTS=1 pnpm exec playwright test shop-screenshots
```

## Dashboard on mock data

The dashboard (`/dashboard`, #50) without the API: `PUBLIC_DASHBOARD_MOCK=1 pnpm dev`, then open http://localhost:5173/dashboard. It serves the fixtures in `src/lib/dashboard/fixtures/` and replays fake live events. `/dashboard/s_2611_0042_tampered/audit` shows a broken chain. Without the flag the server-side loads call FastAPI at `API_INTERNAL_URL` (default `http://localhost:8000`, `http://api:8000` inside Compose). After changing the hash format in `src/lib/dashboard/hash.ts`, regenerate the fixtures with `pnpm fixtures`.
