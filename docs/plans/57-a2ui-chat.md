# Plan: S.I.MO chat with agent UI (A2UI) in the webshop (#57)

Status: draft v1, 2026-11-14. Implements #57 with `docs/specs/a2ui.md` (what the agent UI is) and `docs/specs/webshop-chat.md` (what the chat does). The look is the "A2UI components" page of the design canvas (`UI-01` to `UI-06`, `Chat-A0` to `Chat-A4`).

## 1. Decisions (Juho, 2026-11-14)

| # | Decision |
|---|---|
| 1 | **The agent runs in FastAPI on Genkit for Python**: `genkit`, `genkit-google-genai` and `genkit-a2ui` 0.13 (experimental), at `POST /api/v1/chat` as #57 says. This closes open question 6 of `a2ui.md` |
| 2 | **Fallback if the spike fails** (phase 0): keep `google-genai` directly and write the same A2UI v0.9 envelopes ourselves. The stream contract in section 3 and the whole page stay the same |
| 3 | **Tools go through `/mcp`** with a `web_chat` caller token, as #57 says (not the REST twins that `a2ui.md` §2 named), so audit, sessions and the dashboard work as for every client |
| 4 | **The model draws, the server fills gaps.** The model writes surfaces with ids only (`a2ui.md` §3). If a turn ran a tool that has a card and no matching card came, the server appends it. Duplicates are dropped by component and id |
| 5 | **Scope: everything in #57's checklist** in this round, including `show_menu` with the menu card and the chat on the confirmation page. The design's "Later" cards (`LineWhy`, `ProductCompare`, `UsualOrderChecklist`, `KitchenProfileBar`, `QuoteDiff`) stay out |
| 6 | **Our own Svelte renderer** (`web/src/lib/a2ui/`), no `@a2ui/lit` (already decided in `a2ui.md` §2) |

## 2. What is on the branch already (checked 2026-11-14)

`web/src/lib/a2ui/` is uncommitted work from the planning session:

| File | State |
|---|---|
| `protocol.ts`, `surfaces.svelte.ts`, `resolve.ts`, `context.ts`, `Surface.svelte` | Sound: v0.9 envelopes, a surface store with JSON Pointer data, prop reading that drops wrong types, prototype-safe `setPath`. Keep; add Vitest |
| `Node.svelte` | **Does not compile**: imports `QuoteCard`, `RecipeCard` and `SentNotice`, which don't exist. `Button` reads `action.name`; the Genkit prompt teaches `action.event.{name, context}`, so accept both |
| `types.ts` | `RecipeDraft` is hand-written from the #80 plan. The real model is on `main` now: use `components['schemas']['RecipeDraft']` from the generated types |
| `api.ts` | Paths match `main` (`/recipe-drafts/{id}`, `/discard`); confirm goes through the `confirm_recipe` REST twin in `tools.py`, and `/copy` ("Edit as new draft") is missing. Check each path against `openapi.json` |
| `catalog.json` | Right format for `load_catalog_file`. Add `MenuWeek`; actions named as in the design (`recipe_confirmed`, `clarification_answered`, `send_for_confirmation`, `recipe_selected`, `recipe_swap`) |
| `components/RecipeDraftCard.svelte`, `CardShell.svelte` | Written before the API existed. Check against `UI-03` and the real `RecipeDraft` |

## 3. The contract between the API and the page

Fixed first, so the backend and the page are built at the same time.

**`POST /api/v1/chat`** (web session cookie only):

```json
{ "conversation_id": "string | null", "message": "string (max 2000) | null",
  "action": "A2uiClientAction | null", "attachment_draft_id": "string | null" }
```

Exactly one of `message` and `action` is set. `action` is `{name, surfaceId, sourceComponentId, timestamp, context}` (A2UI v0.9); the server turns it into the next user turn.

**Response: an SSE stream.** Each event is `event: <type>` with a JSON `data:` line.

| Event | Data | Meaning |
|---|---|---|
| `start` | `{conversation_id}` | Always first |
| `text` | `{delta}` | The agent's words, as plain text |
| `a2ui` | `{envelopes: [...]}` | A2UI v0.9 envelopes: `createSurface`, `updateComponents`, `updateDataModel`, `deleteSurface` |
| `tool` | `{name, status: "started" \| "done"}` | For the "working" line only. No arguments, no results |
| `done` | `{quote_id: string \| null}` | Turn over. The page refreshes "Current order" |
| `error` | `{code, message}` | `not_configured` (503 case), `busy`, `failed` |

**Catalog** `https://simo.mankeli.co/a2ui/catalog/v1.json`, one file used by both sides (`web/src/lib/a2ui/catalog.json`; the API reads a copy checked by a test, or the same file through a path setting):

| Component | Props | Page loads | Actions back |
|---|---|---|---|
| `Column`, `Row` | `children: string[]` | | |
| `Text` | `text`, `variant?: heading\|body\|caption` | | |
| `Notice` | `text` | | |
| `Button` | `label`, `action`, `primary?` | | the action it names |
| `RecipeDraftCard` | `draftId` | `GET /api/v1/recipe-drafts/{id}` | `recipe_confirmed {draftId}`, `recipe_discarded {draftId}` |
| `QuoteCard` | `quoteId` | `GET /api/v1/quotes/{id}` | `clarification_answered {quoteId, lineId, productId}`, `send_for_confirmation {quoteId}` |
| `RecipeCard` | `recipeId`, `portions` | `GET /api/v1/recipes/{id}?portions=` | `recipe_selected {recipeId, portions}`, `recipe_swap {recipeId}` |
| `MenuWeek` | `menuId` | `GET /api/v1/chat/menus/{menuId}` | `menu_swap_day {menuId, day}`, `menu_build {menuId}` |
| `SentNotice` | none | `GET /api/v1/chat/sent/latest` for the masked number, or nothing | none |

**The server's gap filling** (decision 4):

| Tool that returned | Card appended when the model drew none |
|---|---|
| `build_quote`, `update_quote` | `QuoteCard {quoteId}` |
| `propose_recipe`, or a message with `attachment_draft_id` | `RecipeDraftCard {draftId}` |
| `show_menu` | `MenuWeek {menuId}` |
| `request_confirmation` | `SentNotice`; any text containing `/c/` is dropped from the stream |

**Other endpoints:**

- `GET /api/v1/chat/menus/{menu_id}`: the menu `show_menu` stored in the conversation, built from our recipe data.
- `POST /api/v1/confirmations/{token}/chat`: the same stream, authorised by the confirmation token, with only `update_quote` offered.

## 4. Work packages

Three packages run in parallel on Opus 5.5 subagents, in one working tree with separate folders. Nobody commits; the commits are made after review.

### A. Chat agent (`api/app/interfaces/chat/`, `api/tests/`, `scripts/`)

0. **Spike (first, 45 min at most):** with a real key, one Genkit Python agent on `CHAT_MODEL` with `Surfaces(catalog=...)`, our catalog, one tool call and streaming. Answer: do tool calling and streaming work together with the middleware, and how do MCP tools become Genkit tools (dynamic tools built from `McpTools.list_tools()`)? If not, take the fallback (decision 2) and say so.
1. Settings `CHAT_MODEL` (empty answers 503 "chat not configured"), `.env.example`, dependencies with `uv add`.
2. Conversations in memory, keyed by `(user_id, conversation_id)`: history, caller token, language, latest quote id, menus. Dropped after 30 idle minutes. One message at a time per conversation.
3. `POST /api/v1/chat` with the SSE events of section 3. Prompt from `build_system_prompt(context, channel="web_chat", ...)`. Tools from `/mcp` with `issue_caller_token(..., channel="web_chat", client_name="S.I.MO chat")`, using the voice bridge's helpers.
4. Actions: an `action` becomes the user turn (the action's name as text, the action as an A2UI data part), with a plain sentence the model understands ("The buyer confirmed recipe draft {id}").
5. Local tool `show_menu(days)`: every `recipe_id` checked with `get_recipe`, unknown ones rejected; the menu stored and served by `GET /api/v1/chat/menus/{id}`.
6. Gap filling and the link scan (section 3).
7. Audit: `buyer_said` and `agent_said` with `{text, lang, transcript: false}` through `audit.record()`.
8. `POST /api/v1/confirmations/{token}/chat` with `update_quote` only.
9. Tests with the model faked at the client boundary (the list in #57), and `scripts/chat_smoke_test.py`.

### B. Renderer and cards (`web/src/lib/a2ui/`)

1. Fix what section 2 lists: generated types, API paths, `Button` action shapes, the missing imports.
2. `RecipeDraftCard` against `UI-03` and the real API: editable rows, "order this" ticks, "Check this" rows, portions stepper with the scaled amounts, dish-photo banner and "Use what the AI saw instead", Confirm, Start over, and after confirming "Edit as new draft" and the "Save to My Aimo" mock button.
3. `QuoteCard` (`UI-05`): asked versus added grouped per recipe or photo, subtotals, "Not ordered", things to check, total and delivery, clarification answers as buttons, rejection with its next step, "Send to my phone".
4. `SentNotice` (`UI-05`), `RecipeCard` (`UI-04`), `MenuWeek` (`UI-06`, `Shop-2-Menu`).
5. A fixture `ChatData` for tests and the preview. Vitest for the store, the pointer helpers, `resolve.ts` and the action mapping.

### C. Chat panel (`web/src/lib/chat/`, `web/src/routes/shop/`, `web/src/routes/c/[token]/`)

1. Stream client: `fetch` and the reader, an SSE parser, events into the message list and the `SurfaceStore`. Vitest for the parser.
2. Panel on `/shop` (`UI-02`, `Shop-1-Desktop`, `Chat-A1`): launcher, side panel on a computer and full screen on a phone, header with the kitchen exclusions, number entry and the dashboard notice before the first message, message list (text, surfaces, "working" line), input, example prompts, "Current order" from `GET /api/v1/quotes/current`.
3. Photo upload: camera button (`accept="image/*" capture="environment"`), the privacy hint, `POST /api/v1/recipe-drafts/read`, then a chat message with `attachment_draft_id`.
4. Actions: a card's action is shown as the buyer's turn in plain words and posted as `action`.
5. "Ask for changes" panel on `/c/[token]`, the same component against the confirmation chat endpoint; the page reloads its view after `done`.
6. Finnish and English, following the shop's language. Design rules from `CLAUDE.md`.
7. Playwright on `/shop` with a fake chat stream: text order to quote to send to notice; menu, swap, build order; photo to recipe card to confirm.

## 5. Order and review

1. A's spike result decides Genkit or the fallback. B and C don't wait for it.
2. When all three are done: join them (the real stream against the real page), run `ruff`, `pytest`, `pnpm check`, `pnpm test`, `pnpm test:e2e`.
3. Small commits for review, nothing pushed before approval: the spec and this plan; the renderer; each card; the chat agent; the panel; the confirmation chat; the tests.
4. After approval: `git pull --rebase`, tests again if anything came in, push, tick #57 and its line in #63.

## 6. Risks

| Risk | Answer |
|---|---|
| Genkit for Python is 0.13 and its A2UI plugin is experimental | The spike, and the fallback that keeps the page unchanged |
| The model forgets a card or writes a wrong id | Gap filling; a wrong id shows "not found" in the card, and only this session's data can load |
| `CHAT_MODEL=gemini-4-hydrogen` and function calling (#80 decision 18) | Checked in the spike; `gemini-4-argon` is the fallback |
| Three agents in one tree | Separate folders; `pnpm check` may show another package's unfinished file, which is not yours to fix |
| A browser agent following the link | The link is never in the stream (scan for `/c/`), `SentNotice` has no link |
