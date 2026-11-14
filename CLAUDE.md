# CLAUDE.md

Junction 2026, Valio Aimo challenge: a deterministic ordering engine behind one MCP server, with phone (Gemini voice), WebMCP webshop and chat connector clients on top.

## Source of truth

- `vision.md` (draft v1, 2026-11-14) is the source of truth for what we build. Its section 13 lists what is decided and what is still open.
- `technical-plan.md` (draft v4, 2026-11-14) describes how we build it: architecture, build-or-buy choices, endpoints, hosting, milestones. Its section 9.8 lists where it differs from `docs/specs/`, and section 14 lists the follow-up issues.
- `valio-api-analysis.md` holds the findings about the mock API and data. Where it disagrees with `vision.md` (for example on `closingTime` or voice-only), `vision.md` wins.
- **The old GitHub issues (#1 to #21) are not a source.** They describe a superseded model (mandates, caps, approver roles, confirmation tiers, voice only). Don't build on them or cite them.
- **Work is tracked in issues #26 to #62, with the overview and owners in #63.** Each issue links to the `technical-plan.md` sections it implements. Read the issue and those sections before starting.
- There is no organisation model: the caller is assumed eligible, and every order is confirmed by a human through the SMS link.

## Workflow

Work goes issue by issue:

1. **Take the issue.** Assign it to yourself (`gh issue edit <n> --add-assignee @me`) so nobody else starts on it.
2. **Check the issue against `main`.** Pull `main` and compare the issue with the current code, `vision.md` and `technical-plan.md`. Part of it may already be done, or a later decision may have changed it. If so, update the issue text (`gh issue edit`) before starting, and say what changed. Also set its labels (`gh issue edit <n> --add-label ...`), using only the labels that already exist in the repo (`gh label list`); ask before creating a new one:
   - **One or more `area:` labels**: `area:engine`, `area:data`, `area:infra`, `area:platform`, `area:dashboard`, `area:voice`, `area:web`.
   - **Exactly one priority**: `P0` (must have for the demo), `P1` (should have) or `stretch` (nice to have), following the priorities in `technical-plan.md`.
   - **A type**: `enhancement`, `bug` or `documentation`.
   - **`decision`** if it needs a team answer before it can be built. Remove it once the decision is written into the issue.
3. **Grill the questions.** Before writing code, list every open question, ambiguity and assumption in the issue and ask them, one round at a time. Don't guess at product decisions; `vision.md` §13 and `technical-plan.md` §14 may already answer some. Write the answers back into the issue. Questions go in the issue itself, not in #63.
4. **Implement the issue.** Tick the issue's checklist items as they land on `main`. Run the linters and tests for what you touched.
5. **Rebase and push to `main`** when it is ready: `git pull --rebase`, rerun the tests if the rebase pulled in changes, then push. Put `Closes #<n>` in the last commit's body so the issue closes on push.

Git rules:

- **Push straight to `main`.** No feature branches or pull requests, not even at a handoff.
- **Keep history linear.** Always rebase, never merge: `git pull --rebase` before pushing (or set `git config pull.rebase true`). If a push is rejected, rebase onto `origin/main` and push again. No merge commits.
- **Never force-push `main`** and never rewrite commits that are already pushed. If a pushed commit is wrong, fix it with a new commit or `git revert`.
- **Small, focused commits.** One logical change per commit, so a rebase conflict stays small and a bad change is easy to revert. Commit and push often, because teammates are working on `main` at the same time.
- **Commit messages**: imperative mood, sentence case, no prefix and no trailing period, matching the existing history (for example "Send the confirmation only after the visitor agrees"). Add a body when the reason isn't obvious from the subject.
- **`main` must always work.** Teammates rebase onto it all the time, so run the linters and tests for what you touched before pushing. Don't push a half-finished feature that breaks startup; hide it behind a flag or keep it local.
- **The `production` branch deploys, not `main`.** The VM runs whatever is on `production`. To release, fast-forward `production` to a tested commit on `main` (`git push origin <commit>:production`). Never commit directly to `production` and never merge into it, so it always points at a commit that is already on `main`. Deploy only when someone asks.
- **Resolve conflicts by hand**, keeping both sides' intent. In `vision.md` and `technical-plan.md`, don't silently drop a teammate's decision; if the two sides disagree, ask.

Handoff: before someone leaves for good (Juho on Saturday night), for every open issue they hold: push whatever works to `main`, tick the checklist items that are done, and write a status comment on the issue (what works, what's next, anything surprising, and where any unpushed work stands). Then reassign the issue.

## Ownership

Stay inside your own area so agents don't wander into other people's folders. #63 has the full table and the order of work.

| Person | Areas | Folders and scope |
|---|---|---|
| Aku | `area:engine` | `api/app/engine/`, `policy/`, audit and signing |
| Miska | `area:data`, `area:infra` | loaders, search, Valio adapter, seed, `deploy/`, CI, recipes |
| Juho, then Jesse after Saturday night | `area:platform`, `area:dashboard` | FastAPI, MCP, services, auth, dashboard |
| Jesse | `area:voice`, `area:web` | voice relay, prompt, call screen, confirmation page and its backend, webshop |

- **Changes outside your area** stay small, and the owner is named in the commit body and told directly.
- **`api/app/schemas/` is the shared contract (#26)** and everyone builds on it. Change a model there only in its own commit, with a heads-up to the whole team before pushing. Never slip a schema change into another commit.
- **`api/app/engine/` is pure.** No database, HTTP, clock reads or randomness. Everything comes in through `EngineInput`.

## Commands

To be filled in once the scaffold (#27) lands: the exact run, test and lint commands (`uv`, `pnpm`, `docker compose`), so agents don't guess them.

## Database and secrets

- **Laptops** run Postgres with pgvector in Docker (`deploy/docker-compose.dev.yml`) and read a local `.env`. Only `.env.example` is committed.
- **Never point a laptop at `junction_demo`** on the Azure server. It belongs to the VM and the stage demo.
- **On the VM**, secrets come from Azure Key Vault. There is no `.env` on the VM.
- **Never commit secrets**: no `.env`, API keys, Twilio credentials or real phone numbers.

## Demo UI

- `docs/specs/` says what each demo screen does (dashboard, confirmation page, call screen, webshop chat). Its README lists decisions still to carry into `vision.md`.
- `docs/design/` shows how the screens look: exported PNGs, standalone HTML and the flows documented in its README. The design canvas is https://claude.ai/artifact/Je1fmCEnZv6FDFT4QYmMZ3 ; re-export with `scripts/export_design_screens.py`.
- Design rules to keep when building UI: the agent is always written **S.I.MO**; no middle-dot character in UI text; masked phone numbers use stars (`+358 40 *** **12`); no "DEMO" labels (no-real-order notices stay); the dashboard targets computers, not phones.

## Valio mock API rules

- **Never request all products or large batches from the live API.** It has undisclosed rate limits and the challenge docs forbid polling the whole catalog.
- **Use `VALIO_SOURCE=snapshot`** for tests and the stage demo. Use the live API only for a small shortlist.
- For catalog-wide questions (allergens, categories, units, conversions), use the **static product file**. Download it once with `curl -L` from `/api/products/download` and work locally.
- Call `/api/price` and `/api/availability` only for a small shortlist of product ids.
- Every `/api` call needs the `X-API-Key` header. Cloudflare blocks Python's default User-Agent, so set one such as `curl/8.4.0`.
- The API key is semi-public for the event, but don't commit it. Read it from the `VALIO_API_KEY` environment variable.
