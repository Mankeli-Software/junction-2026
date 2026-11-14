# web

SvelteKit app with `adapter-node`: start page (`/`), demo phone (`/phone`), webshop, confirmation page (`/c/[token]`) and dashboard (`technical-plan.md` §11).

```sh
pnpm install
pnpm dev                                  # http://localhost:5173, with the fixtures and the mock voice relay
pnpm check                                # svelte-check
pnpm build                                # node build in build/
pnpm test                                 # Vitest unit tests
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

The server reads them from its process environment, for example `CONFIRMATION_SOURCE=api pnpm dev`. Neither `pnpm dev` nor the Compose `web` service reads the root `.env` yet, so the lines in `.env.example` document the defaults rather than set them.

## Routes

| Route | What it is |
|---|---|
| `/` | The demo start page (`docs/design` 00 and 01) |
| `/phone` | The demo phone: set up, Contacts with S.I.MO, call, call ended and the inbox (`docs/specs/call-screen.md`, `docs/design` 10 to 14). On a computer it shows inside a phone frame |
| `/c/[token]` | The confirmation page (`docs/specs/confirmation-page.md`) |
| `/dashboard` | The live order dashboard (`docs/specs/dashboard.md`, #50) |
| `/api/v1/demo/accounts`, `/api/v1/me`, `/api/v1/private/inbox`, `/api/v1/private/inbox/stream` | The fixture for `technical-plan.md` §9.2 with `DEMO_SOURCE=fixture`; passed through to FastAPI with `api` |

The webshop is not built yet.

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

## Screenshots

`tests/screenshots.spec.ts` and `tests/phone-screenshots.spec.ts` save screenshots in `docs/screenshots/confirmation-page/` and `docs/screenshots/phone/`. They are skipped in normal test runs. Regenerate them with:

```sh
SCREENSHOTS=1 pnpm exec playwright test screenshots --project=phone
SCREENSHOTS=1 pnpm exec playwright test phone-screenshots
```

## Dashboard on mock data

The dashboard (`/dashboard`, #50) without the API: `PUBLIC_DASHBOARD_MOCK=1 pnpm dev`, then open http://localhost:5173/dashboard. It serves the fixtures in `src/lib/dashboard/fixtures/` and replays fake live events. `/dashboard/s_2611_0042_tampered/audit` shows a broken chain. Without the flag the server-side loads call FastAPI at `API_INTERNAL_URL` (default `http://localhost:8000`, `http://api:8000` inside Compose). After changing the hash format in `src/lib/dashboard/hash.ts`, regenerate the fixtures with `pnpm fixtures`.
