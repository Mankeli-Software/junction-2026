# CLAUDE.md

Junction 2026, Valio Aimo challenge: a voice ordering agent on top of a deterministic decision engine.

## Source of truth

- `vision.md` (draft v1, 2026-11-14) is the source of truth. Check it before relying on the GitHub issues. It adopts the no-organisation direction below; its section 13 lists what still needs team agreement.
- Issue #1 (engine model) assumes mandates, allowed categories, approver roles, caps and confirmation tiers C2/C3. That organisation model is **under review**: the proposed direction is no organisation structure, the caller is assumed eligible, and every purchase is finished with an SMS confirmation (2FA). Not yet agreed by the whole team. Don't build on the mandate model until `vision.md` settles it.
- `valio-api-analysis.md` holds the findings about the mock API and data.

## Valio mock API rules

- **Never request all products or large batches from the live API.** It has undisclosed rate limits and the challenge docs forbid polling the whole catalog.
- For catalog-wide questions (allergens, categories, units, conversions), use the **static product file**. Download it once with `curl -L` from `/api/products/download` and work locally.
- Call `/api/price` and `/api/availability` only for a small shortlist of product ids.
- Every `/api` call needs the `X-API-Key` header. Cloudflare blocks Python's default User-Agent, so set one such as `curl/8.4.0`.
- The API key is semi-public for the event, but don't commit it. Read it from the `VALIO_API_KEY` environment variable.
