# CLAUDE.md

Junction 2026, Valio Aimo challenge: a deterministic ordering engine behind one MCP server, with phone (Gemini voice), WebMCP webshop and chat connector clients on top.

## Source of truth

- `vision.md` (draft v1, 2026-11-14) is the source of truth for what we build. Its section 13 lists what is decided and what is still open.
- `technical-plan.md` (draft v1, 2026-11-14) describes how we build it: architecture, build-or-buy choices, hosting, milestones. Its section 13 lists the open technical questions.
- `valio-api-analysis.md` holds the findings about the mock API and data. Where it disagrees with `vision.md` (for example on `closingTime` or voice-only), `vision.md` wins.
- **The existing GitHub issues (#1 to #21) are not a source.** They describe a superseded model (mandates, caps, approver roles, confirmation tiers, voice only). Don't build on them or cite them. New issues will be created from `vision.md` and `technical-plan.md`, and those are valid.
- There is no organisation model: the caller is assumed eligible, and every order is confirmed by a human through the SMS link.

## Demo UI

- `docs/specs/` says what each demo screen does (dashboard, confirmation page, call screen, webshop chat). Its README lists decisions still to carry into `vision.md`.
- `docs/design/` shows how the screens look: exported PNGs, standalone HTML and the flows documented in its README. The design canvas is https://claude.ai/artifact/Je1fmCEnZv6FDFT4QYmMZ3 ; re-export with `scripts/export_design_screens.py`.
- Design rules to keep when building UI: the agent is always written **S.I.MO**; no middle-dot character in UI text; masked phone numbers use stars (`+358 40 *** **12`); no "DEMO" labels (no-real-order notices stay); the dashboard targets computers, not phones.

## Valio mock API rules

- **Never request all products or large batches from the live API.** It has undisclosed rate limits and the challenge docs forbid polling the whole catalog.
- For catalog-wide questions (allergens, categories, units, conversions), use the **static product file**. Download it once with `curl -L` from `/api/products/download` and work locally.
- Call `/api/price` and `/api/availability` only for a small shortlist of product ids.
- Every `/api` call needs the `X-API-Key` header. Cloudflare blocks Python's default User-Agent, so set one such as `curl/8.4.0`.
- The API key is semi-public for the event, but don't commit it. Read it from the `VALIO_API_KEY` environment variable.
