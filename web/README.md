# web

SvelteKit app with `adapter-node`: phone page, webshop, confirmation page (`/c/[token]`) and dashboard (`technical-plan.md` §11).

```sh
pnpm install
pnpm dev                                  # http://localhost:5173
pnpm check                                # svelte-check
pnpm build                                # node build in build/
pnpm test                                 # Vitest unit tests
pnpm exec playwright install chromium     # once, for the end-to-end tests
pnpm test:e2e                             # Playwright: builds the app and runs it against the fixtures
```

The end-to-end tests run on a phone and a laptop profile (`playwright.config.ts`). They need no API or database.

## Settings

| Variable | Values | Default |
|---|---|---|
| `CONFIRMATION_SOURCE` | `fixture`: an in-memory stand-in for the engine. `api`: the FastAPI endpoints in `technical-plan.md` §9.4 | `fixture` in `pnpm dev`, `api` in a build. Compose sets `api`; set `fixture` to opt in |
| `API_BASE_URL` | Where FastAPI runs, used with `CONFIRMATION_SOURCE=api` | `http://localhost:8000`. Compose sets `http://api:8000` |

The server reads them from its process environment, for example `CONFIRMATION_SOURCE=api pnpm dev`. Neither `pnpm dev` nor the Compose `web` service reads the root `.env` yet, so the lines in `.env.example` document the defaults rather than set them.

## Routes

| Route | What it is |
|---|---|
| `/` | Placeholder for the demo start page |
| `/c/[token]` | The confirmation page (`docs/specs/confirmation-page.md`) |
| `/dashboard` | The live order dashboard (`docs/specs/dashboard.md`, #50) |

The other pages (start, call screen, webshop) are not built yet.

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

`tests/screenshots.spec.ts` saves the screenshots in `docs/screenshots/confirmation-page/`. It is skipped in normal test runs. Regenerate them with:

```sh
SCREENSHOTS=1 pnpm exec playwright test screenshots --project=phone
```

## Dashboard on mock data

The dashboard (`/dashboard`, #50) without the API: `PUBLIC_DASHBOARD_MOCK=1 pnpm dev`, then open http://localhost:5173/dashboard. It serves the fixtures in `src/lib/dashboard/fixtures/` and replays fake live events. `/dashboard/s_2611_0042_tampered/audit` shows a broken chain. Without the flag the server-side loads call FastAPI at `API_INTERNAL_URL` (default `http://localhost:8000`, `http://api:8000` inside Compose). After changing the hash format in `src/lib/dashboard/hash.ts`, regenerate the fixtures with `pnpm fixtures`.
