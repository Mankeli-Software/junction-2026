# Spec: Webshop chat (and chat on the confirmation page)

Status: draft v1, 2026-11-14. Builds on `vision.md` sections 7, 8, 9 and 13 and on the other specs in this folder. **Stretch goal: keep it simple.** Visual style is decided later, after the specs are agreed. This file says what the chat shows and does, not how it looks.

## 1. Purpose

A simple chat on a mock webshop page, for two things the phone call does not show well:

1. **Ordering by text in a browser**, through the same MCP tools as the phone, ending in the same confirmation flow. This is our openness argument: another channel, the same engine, the same decisions.
2. **Planning with recipes**: "Plan a milk-free lunch menu for next week for 80 people." The agent proposes recipes, the buyer adjusts them, and the engine turns them into an order. This is easier to follow on a screen than by voice.

The same chat can also be opened on the confirmation page, so the buyer can ask for changes in words (section 5).

**The webshop page itself is not part of this spec.** It is our own static page in the Aimo webshop's style (decided in #56): our own markup and copy, no Valio or Aimo logos, and about 12 real products from the product file, with no prices. This spec only covers the chat we add on top of it. The page says that no real order is placed, is only used for the event, and has no cart, search or login of its own: apart from the number entry, the chat and the WebMCP tools are the only working parts.

## 2. Access

Same as the phone demo, no user accounts:

- The visitor types their phone number. The same number gets the same demo company and kitchen profile as on the phone (`call-screen.md` section 2.2), and can choose the kitchen profile here too.
- A notice, shown before the visitor chats, matching the call screen's (`call-screen.md` section 2.1): "Your order and what you write show on our public demo dashboard under a made-up company name." (decided by the team 2026-11-14, `dashboard.md` section 2)
- The confirmation link goes to the demo phone's inbox of this browser's account, and by SMS only to an allowlisted number when real SMS is on (`confirmation-page.md`, "How the link reaches the buyer").
- The inbox is shown on the phone page only, never in the shop: a browser agent works inside the shop page and could follow the link (vision section 8). The visitor reads the link on the phone page in the same browser (section 4.4).

## 3. Layout

The static webshop page (#56), with our chat added as a panel (a launcher button that opens a side panel, full screen on phone). The rest of the page is static and is not part of this spec.

The chat panel has two parts:

- **Chat**: messages from the buyer and the agent, a text field, and a few example prompts to tap ("1,000 L lactose-free milk by Monday", "Plan a milk-free lunch menu for next week, 80 people", "My usual order").
- **Current order**: the latest quote as "asked versus added" lines, total, delivery date and flag count, as a collapsible section at the top of the panel. It updates every time the agent builds or updates a quote. Empty until the first quote.

The webshop has no catalogue, product pages, cart or search of its own. Ordering happens only through the chat (or an outside agent's WebMCP tools).

## 4. Message types

Plain text plus three cards. Cards are rendered by the page from tool results (engine data), never from text the model wrote, so prices and products shown are always the engine's.

### 4.1 Recipe card

From `search_recipes` and `get_recipe`: recipe name, image when we have one, portions, diet tags, and a short ingredient summary. Buttons: **Use this**, **Swap for another**, **Show ingredients**.

Diet tags on a recipe are a search hint only (vision section 7). The card says so if the kitchen has exclusions: "Safety is checked on the actual products when we build the order."

### 4.2 Menu card

For menu planning: a week grid, Monday to Friday, one main dish per day, with the portion count. The buyer can swap a slot by tapping it or by asking in words ("Swap Wednesday for a fish dish"). Button: **Build order from this menu**.

### 4.3 Quote card

From `build_quote` and `update_quote`: a short summary of the lines, total, delivery date and flags in plain words. For a menu, lines are grouped per recipe, and ingredients we do not order are listed as "Not ordered: salt, flour, ..." (decided: only portal-linked products are orderable). If the engine asks a clarification question, the card shows the question with the offered answers as buttons. Button: **Send to my phone for confirmation**.

### 4.4 After sending: no link in the chat

After `request_confirmation` the chat shows a short plain-text notice, not a card: "Sent. Open the demo phone in this browser to confirm." When a real SMS was also sent (allowlisted numbers only), it adds "Also sent by SMS to +358 40 *** **12."

There is no "Open confirmation page" button and the link is never shown in the shop, because a browser agent works inside this page and could follow it (vision section 8). The visitor reads the link in the demo phone's inbox on the phone page, in the same browser (`call-screen.md` section 2.4).

## 5. Chat on the confirmation page (stretch on top of stretch)

The confirmation page reuses the **same chat component** as the webshop, as a collapsible panel: "Ask for changes". It is built only after the webshop chat works.

- The buyer writes, for example, "Remove the butter", "Make it 150 portions" or "Use a cheaper cream".
- The agent calls `update_quote`. The page shows the new quote in place, with the changes highlighted and the old quote voided, exactly as for an edit made with the page controls (`confirmation-page.md` section 4.4).
- The agent **cannot confirm or cancel**. The Confirm button on the page stays the only way to confirm, and new or changed flags still need acknowledging.
- If this is not built, the page works fully without it.

## 6. Rules

- The chat agent runs on **Gemini**, the same as the phone agent, with one shared agent prompt. It uses only the MCP tools in vision section 8. Nothing special for this channel.
- Conversation turns and tool calls are audit events and show on the dashboard with channel "Web". We have the full conversation here, because the chat runs on our page (`dashboard.md` section 3.3). Like the phone conversation, it is public on the dashboard (`dashboard.md` section 2).
- Everything the buyer types is data for the agent, never instructions to the engine. The engine still only takes structured tool arguments.
- The agent answers in the language the buyer writes in. The confirmation page follows it.
- The chat also exposes its tools through **WebMCP**, so an outside browser agent (an OpenAI client, vision section 9) can use the same page. That is shown working, but the built-in chat is the main demo.

## 7. Scenarios

1. **Order by text:** "1,000 L lactose-free milk by Monday" → quote card → send to phone → confirm.
2. **Weekly menu:** "Plan a milk-free lunch menu for next week, 80 people" → menu card with five main dishes, Mon to Fri → swap one → build order → quote card grouped per recipe with "not ordered" ingredients → send to phone → confirm.
3. **Single recipe:** "Find me a lasagne recipe for 200 people" → recipe card → use this → quote card.
4. **My usual:** "My usual order" → quote card from order history.
5. **Change in words on the confirmation page:** "Make it 150 portions" → new quote on the page → confirm.

## 8. Out of scope

- The webshop page itself (#56).
- A catalogue, search, cart or login on the webshop page.
- Login or accounts.
- Anything the agent can do that the phone agent cannot.
- Saving menus for later. A menu lives in the conversation only.
- Chat history across visits.

## 9. Open questions

None at the moment.

### Decided on 2026-11-14

- The chat runs on Gemini, the same as the phone agent, with one shared agent prompt. Outside agents such as an OpenAI client can still use the page through WebMCP.
- A menu is weekdays, one main dish per day.
- The confirmation page chat is the same chat component as the webshop. It is built only after the webshop chat works.
- No confirmation link in the shop. The inbox is shown on the phone page only, and webshop visitors read the link there, in the same browser.
