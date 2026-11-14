# Spec: Agent UI (A2UI) in the chat

Status: draft v0, 2026-11-14. First step: the use cases and the components they need. Builds on `vision.md` sections 6 to 8, `technical-plan.md` sections 7.2 and 9.6, `docs/specs/webshop-chat.md`, #57 (chat panel) and #80 (recipe photo).

## 1. Purpose

In the chat, S.I.MO answers with interactive UI as well as text: a recipe the buyer can edit, a menu to swap days in, a quote with its flags. We build it on A2UI: the agent side sends a declarative description of the UI as JSON, and the page renders it with components from a catalog that we write and trust. No code is sent from the agent to the page.

Where it runs:

| Surface | Status |
|---|---|
| Webshop chat panel (#57) | First, the main place |
| Confirmation page chat ("Ask for changes") | After the webshop chat, same components |
| Claude and ChatGPT connectors | Not now. They show our tool results as text. MCP Apps could render the same cards later |
| Phone | No UI during the call. The confirmation page is the phone's UI |

## 2. Genkit (decided 2026-11-14)

The chat agent is built with **Google Genkit** and its A2UI plugin, because it is the most complete way to run an A2UI agent on Gemini. Our MCP server stays as it is for the connectors; MCP has no way to send this UI, so A2UI lives only in our own webshop chat (#57).

- **Agent**: a Genkit agent on Gemini with the shared S.I.MO prompt (#53) and the `a2ui({ catalog: "simo" })` middleware. It runs in FastAPI on Genkit for Python (`docs/plans/57-a2ui-chat.md`). Its tools are the MCP tools, called through `/mcp` with a `web_chat` caller token, so audit, channel and limits work as for the other channels. Gemini is reached through our own small Genkit model on `google-genai`, because Genkit's Gemini plugin needs an older `google-genai` than the voice relay.
- **Protocol**: A2UI v0.9, as the Genkit plugin sends it (`createSurface`, `updateComponents`, `updateDataModel`, `deleteSurface`; actions back as `{name, surfaceId, sourceComponentId, timestamp, context}`).
- **Catalog**: ours, in `web/src/lib/a2ui/catalog.json`, id `https://simo.mankeli.co/a2ui/catalog/v1.json`. The server loads it with `loadCatalog`; the page renders it with our own small Svelte renderer (`web/src/lib/a2ui/`), not `@a2ui/lit`, so the cards use our design and Svelte's escaping.
- **Packages**: `genkit`, `@genkit-ai/google-genai`, `@genkit-ai/a2ui` (0.7, preview) for JavaScript. Genkit for Python has the same plugin (`genkit-a2ui`) if the agent runs in FastAPI instead (open question 6).

## 3. The main rule: engine data comes from tool results

`webshop-chat.md` section 4 says cards are rendered from tool results, never from model text, so every price and product shown is the engine's. With Genkit's A2UI middleware the **model writes the UI**, so our catalog keeps engine data out of the model's hands:

- **Domain components take ids only.** The model writes `QuoteCard { quoteId }`, `RecipeDraftCard { draftId }` or `RecipeCard { recipeId, portions }`. The page loads the quote, draft or recipe itself from the REST API with the session cookie and renders the engine's data. The model never writes a price, product name, amount or total. A wrong id can only show another quote of the same session.
- **Layout components carry only the model's own words** (`Text`, `Notice`, `Button` labels), always as plain text.
- **Buyer actions come back as A2UI actions** to the agent ("The buyer confirmed recipe draft {id}", "send quote {id} for confirmation"), and the agent calls the tool. The one exception is the recipe draft: the card confirms the draft itself through `POST /api/v1/recipe-drafts/{id}/confirm`, then tells the agent (`docs/plans/80-recipe-photo.md` §2.1). An action never confirms an order. Confirm stays on the confirmation page only.
- **Free text from the buyer is data.** Edited ingredient text goes to the engine as a line's `text`, through normal product search and every allergen and diet rule.

## 4. Use cases

Each row is something the buyer does in the chat that text alone handles badly. Priority follows the issue it comes from.

| # | Use case | Example | Tool data | Source | Priority |
|---|---|---|---|---|---|
| U1 | **Check and edit a recipe read from a photo** | Photo of a notebook page: dish, portions, ingredients with amounts. Buyer fixes an amount, adds a missing ingredient, removes one, sets portions, then confirms | `propose_recipe`, `confirm_recipe` (#80, new tools) | #80 | P1, high value |
| U2 | **Edit a recipe before ordering** | "Lasagne for 200": scaled ingredients, buyer edits amounts, adds or removes ingredients, changes portions, sees which ones we can order and which are "not ordered" | `get_recipe` (`ingredients[].product_id`) | webshop-chat §4.1, vision §7 | P1, high value |
| U3 | Dish photo: our guess or a matched recipe | "This is a guess from the picture", switch to the matched recipe from our data | `propose_recipe` (`source: dish_photo`), `search_recipes` | #80 decision 6 | P1 |
| U4 | Pick a recipe from search results | Three to five recipes with image, portions, diet tags | `search_recipes` | webshop-chat §4.1, scenario 3 | P1 |
| U5 | Plan a weekly menu | Mon to Fri, one main dish a day, swap a day by tapping or in words, set portions, build one order | `search_recipes`, `get_recipe` per day | webshop-chat §4.2, scenario 2 | Stretch |
| U6 | See the quote: asked versus added | Lines grouped per request or recipe, subtotal per group, total, delivery, "Not ordered: salt, flour" | `build_quote`, `update_quote` | vision §6, webshop-chat §4.3 | P1 |
| U7 | Answer a clarification in one tap | "Which cream: 1 l or 5 l?" with the options as buttons | `Clarification` in a quote | vision §8 (`needs_clarification`) | P1 |
| U8 | Understand a rejection and its next step | "Can't arrive by Monday. Next delivery Wednesday" with a button for the next step | `Rejection` in a quote | vision §8 | P1 |
| U9 | Preview flags before sending | "2 things to check on your phone": the flag texts, read-only. Acknowledging stays on the confirmation page | `Flag` in a quote | confirmation-page.md | P1 |
| U10 | Why this product, and swap it | The trace ("14 found, −4 late, −2 contain milk, 5 safe") and the alternatives with their line totals | `QuoteLine.trace`, `alternatives` | dashboard and confirmation page | P1 |
| U11 | Compare products | "Which lactose-free milk is cheapest by Monday?": a short list with price per litre, stock, delivery date | `search_products` | vision §1 (compare offers) | P1 |
| U12 | Start from my usual or last order | Checklist of usual items with quantities, untick or change, then quote | `get_customer_context` (`usual_items`, `last_order`) | vision §5, #32 | P1 |
| U13 | See the kitchen profile | Company and exclusions as chips at the top of the chat, so the buyer knows what is filtered out | `get_customer_context` | call-screen.md, #81 | P1 |
| U14 | Sent to the phone | "Sent. Open the demo phone in this browser to confirm." No link in the shop | `request_confirmation` | webshop-chat §4.4 | P1 |
| U15 | Change the order in words on the confirmation page | "Make it 150 portions": the new quote with the changes highlighted, the old one voided | `update_quote` | webshop-chat §5 | Stretch on stretch |
| U16 | Order status | "Is my order through?": confirmed, waiting or replaced, with the order number | `get_order_status` | vision §8 | Later |

## 5. Components

A small catalog: a few layout pieces, then domain components that each map to one piece of tool data. Domain components reuse the Svelte components the confirmation page and shop already have where they fit (`web/src/lib/confirmation/components/`, `web/src/lib/shop/components/ProductCard.svelte`).

### 5.1 Base components

Plain building blocks, as in the A2UI standard catalog. We take only what the domain components need.

| Component | Used for |
|---|---|
| `Card`, `Column`, `Row`, `Divider` | Layout of every card |
| `Text` (heading, body, caption) | Titles, short lines |
| `Image` | Recipe and product images, with the placeholder rule from technical-plan §5.5 |
| `Button` (main, secondary, icon) | Actions. Lime for the one main action per card, as in the design |
| `Chip`, `ChipGroup` | Diet tags, exclusions, quick answers |
| `TextField`, `NumberStepper` | Ingredient text, amounts, portions |
| `Select` | Unit (g, kg, dl, l, pcs) |
| `Notice` | Yellow notice ("This is a guess from the picture", "Safety is checked on the actual products") |

### 5.2 Domain components

| Component | Shows | Buyer can | Action sent | Use cases |
|---|---|---|---|---|
| **`RecipeEditor`** | Dish name, portions, source (photo, notebook, our recipe), ingredient rows, unsure rows highlighted | Rename the dish, set portions (amounts rescale when the source portions are known), edit, add and remove rows, confirm | `recipe.confirm` → `confirm_recipe` or quote from the edited recipe | U1, U2, U3 |
| `IngredientRow` (inside `RecipeEditor`) | Name, amount, unit, "can order" or "not ordered" mark, confidence mark | Edit text, amount and unit, remove | Part of the editor's data model | U1, U2 |
| `RecipeSourceSwitch` | "Our guess" and "Matched recipe" as two tabs | Switch | `recipe.use_match` | U3 |
| **`RecipeCard`** | Image, name, portions, diet tags, two-line ingredient summary | Use this, Swap for another, Show ingredients | `recipe.use`, `recipe.swap`, opens `RecipeEditor` | U4, U5 |
| `RecipeList` | Three to five `RecipeCard`s, compact | Pick one | `recipe.use` | U4 |
| **`MenuWeek`** | Mon to Fri, one dish per day, portions | Tap a day to swap, set portions, Build order | `menu.swap_day`, `menu.build` | U5 |
| **`QuoteSummary`** | Groups with asked versus added lines, subtotals, total, delivery dates, flag count, "Not ordered" list | Open a line, Send to my phone | `quote.send` → `request_confirmation` | U6, U9 |
| `QuoteLineRow` | Asked text next to the product, pack, quantity, line total, reason in one line | Why (info icon), change (pencil icon) | Opens `LineWhy` | U6 |
| `LineWhy` | The trace counts and ranked candidates, alternatives with line totals | Pick an alternative | `line.swap` → `update_quote` | U10 |
| `NotOrderedList` | Ingredients we don't order, with the reason | Nothing | None | U2, U6 |
| `FlagPreview` | Flag texts, read-only, "You check these on your phone" | Nothing | None | U9 |
| **`ClarificationPrompt`** | The question and the options with line totals | Tap an answer | `clarify.answer` → `update_quote` | U7 |
| `RejectionNotice` | What can't be done and the next step | Tap the next step | `reject.next_step` → message to Gemini | U8 |
| `ProductCompare` | Three to five products: name, pack, price per base unit, stock, delivery date, origin | Add one to the order | `product.add` → `build_quote` or `update_quote` | U11 |
| `UsualOrderChecklist` | Usual or last items with quantities | Untick, change amounts, Quote these | `usual.quote` → `build_quote` with `usual: true` lines | U12 |
| `KitchenProfileBar` | Company name, exclusions as chips | Nothing in the chat (changed on the account screen) | None | U13 |
| `SentNotice` | "Sent. Open the demo phone in this browser to confirm." and the masked number when a real SMS went too | Nothing | None | U14 |
| `QuoteDiff` | The new quote with added, changed and removed lines highlighted | Nothing | None | U15 |
| `OrderStatusBadge` | Status word, order number | Nothing | None | U16 |

### 5.3 Build order

1. Renderer and catalog skeleton, base components, the chat service turning tool results into A2UI messages.
2. **`RecipeEditor`** with `IngredientRow` (U1, U2): the highest-value case, and it needs editing, adding and removing rows, so it proves the user-action path end to end.
3. `QuoteSummary`, `QuoteLineRow`, `NotOrderedList`, `FlagPreview`, `ClarificationPrompt`, `SentNotice` (U6, U7, U9, U14): the full path from recipe to confirmation.
4. `RecipeCard`, `RecipeList`, `RecipeSourceSwitch` (U3, U4).
5. `LineWhy`, `ProductCompare`, `UsualOrderChecklist`, `KitchenProfileBar`, `RejectionNotice`.
6. `MenuWeek` (U5), then `QuoteDiff` for the confirmation page chat (U15).

## 6. Open questions

1. ~~A2UI version and renderer~~: decided, A2UI v0.9 through Genkit, our own Svelte renderer (section 2).
2. ~~How Gemini asks for a surface~~: decided, the model writes the surface with ids only (section 3).
3. **Recipe edits without #80.** U2 (edit a recipe from our data) needs somewhere to keep the edited recipe. Reuse the `recipe_drafts` table from #80 with `source: "recipe"`, or send the edited ingredients straight to `build_quote` as lines with `group` set to the dish name.
4. **Adding an ingredient.** A free-text row goes through normal product search and may come back as a clarification or "not ordered". Do we show the match in the editor before quoting, or only in the quote?
5. **Connectors.** Whether to offer the same cards to Claude and ChatGPT through MCP Apps later. Out of scope for the event unless time is left.
6. ~~Where the Genkit agent runs~~: decided, in FastAPI on Genkit for Python at `POST /api/v1/chat` (`docs/plans/57-a2ui-chat.md` decision 1).
