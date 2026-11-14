# Spec: Live order dashboard

Status: draft v1, 2026-11-14. Builds on `vision.md` sections 4, 6, 9 and 11 and on issue #20. Visual style is decided later, after the specs are agreed. This file says what the dashboard shows and does, not how it looks.

## 1. Purpose

The dashboard is the window into the black box. During the demo it runs on a big screen next to the stage (and on judges' laptops), so anyone can watch an order go from "someone is talking to an agent" to "order confirmed", and see why the engine chose each product.

It answers three questions at a glance:

1. **What is happening right now?** Calls and chats in progress, quotes waiting for confirmation.
2. **Why did the engine decide this?** Products considered, filters applied, what was rejected and why.
3. **Did a human confirm it?** SMS sent, link opened, flags acknowledged, confirmed, or what went wrong.

It is evidence for the judging criteria: end-to-end demo (30%), autonomy and controls (20%), robustness (15%).

## 2. Access: no accounts, open by design

- **No login, no user accounts.** Anyone with the URL sees every order. That keeps the demo easy to follow and lets judges open it on their own device.
- It is read-only. Nothing on the dashboard can confirm, cancel, edit or resend an order. Those actions exist only on the confirmation page (vision section 6).
- It plays the role of the **Aimo operator view** from vision section 11. The **buyer view** is the confirmation page and the "order received" page, reached through the SMS link. We do not build a separate buyer login for the dashboard.
- Agents never read the dashboard. It is not an MCP tool and the MCP server has no route to its data (vision section 8, issue #14).
- **Privacy.** Booth visitors type their own real phone number. The dashboard never shows it in full: mask it as `+358 40 ••• ••12`. What they say on the call is shown as text (section 3.3), and they are told so before the call starts. No other personal data exists.
- **Demo companies.** Each new caller number gets its own generated company with a unique, funny-sounding Oy name (for example "Hassu Hauki Oy" or "Lihapulla ja Pojat Oy"). The same number calling again gets the same company. This makes the grouping by company on the overview meaningful and makes each visitor's order easy to spot on the screen.

Production note for the pitch: in real use this view sits behind Aimo staff login, and buyers see only their own company. That is access control on top of the same read model, not a different dashboard.

## 3. Screens

Four levels, each a drill-down from the one above:

1. **Overview:** all orders, live.
2. **Order summary:** what was ordered and why. The main screen, and the one that has to look good.
3. **Full flow:** everything that happened in the session, including the conversation and tool calls. An extra view for the details.
4. **Audit log:** the raw, hash-chained events.

Everything is audited, and the audit log is grouped by order. There is no global log across all orders; the per-order view is enough for the demo. The presenter navigates between the levels by hand; there is no separate stage or auto-follow mode. Each level has its own URL and updates live while open.

### 3.1 Live overview (default)

The landing page. Shows all activity, newest first.

**Top strip: counters**

| Counter | Meaning |
|---|---|
| Active now | Sessions with a call or chat in progress |
| Waiting for confirmation | SMS sent, not yet confirmed, not expired |
| Confirmed | Orders confirmed |
| Needs attention | Rejected, expired, SMS failed, callback requested |
| Total confirmed value | Sum of confirmed order totals, gross |

The counters add up everything since the server started. There is no reset.

**Main area: order cards, grouped by buyer company**

One card per order session (one conversation that ends in at most one quote being confirmed). Each card shows:

- Company name, masked phone number or channel identity, channel badge (Phone, Web, Chat).
- Status (see section 4) with time in that status ("Waiting for confirmation, 2 min"; the time to expiry is shown only when expiry is on, and it is off during the event).
- What was asked, in one line (from the first request, for example "1,000 L lactose-free milk by Monday").
- Line count, gross total, delivery date.
- Flag count by kind (for example "3 flags: rounding, unverified stock, no allergen info").
- A live activity line while the session is active ("Checking availability for 6 products...").

New cards and status changes animate in so the eye catches them from a distance. Failed states stay visible; they are part of the story, not something to hide.

Filter chips: All, Active, Waiting, Confirmed, Needs attention. Channel filter. That is all the control the overview needs.

### 3.2 Order summary: what was ordered and why

Opens from a card. This is the screen we narrate on stage, so it has to be clear and good-looking at a glance. It answers two questions only: **what was ordered** and **why these products**. Process details live in the full flow view (3.3).

**Header:** company, kitchen profile (allergen and diet exclusions, for example "Milk-free, nut-free"), channel, status, delivery date, total. A short status line under it ("Confirmed by the buyer at 10:04 after acknowledging 2 flags").

**Asked versus added.** The same grouping as the confirmation page (vision section 6): each request on the left, the chosen product lines on the right, with product name (and image when we have one), pack, quantity in sales units and in the asked unit, unit price, line total and the one-line reason ("cheapest lactose-free milk in stock that arrives Monday"). A recipe or a stock split shows as one request with several lines under it. Unmapped recipe ingredients show as "not ordered".

**Why this product (drill-down per line).** By default each line shows only its one-line reason. Clicking a line opens a drill-down that explains why that product was chosen:

- How many candidates were found and how many each filter removed, in plain words: "28 removed: contains milk (AM, CONTAINS)", "3 removed: no stock", "2 removed: arrives too late", "1 removed: unit unclear".
- The remaining candidates in ranked order and the factor that decided (price, stock certainty, history, origin).
- Substitution used, if any, and which rung of the ladder it came from.
- Alternatives that were offered to the buyer (exact-fit product, other date).

Inside the drill-down, each filter's count expands to the products it removed. Product codes are shown small next to names, for credibility, not as the main label.

**Flags.** Every flag on the quote with its plain-language text (the same text the buyer saw) and whether it was acknowledged on the page, and when.

**Trust strip** at the bottom, one line: "Quote signed and verified · Audit chain intact, 14 events · Quote v2 (v1 voided after an edit)". Each part links into the full flow or the audit log.

**Buttons to go deeper:** "See full flow" (3.3) and "Audit log" (3.4).

### 3.3 Full flow: everything that happened

The extra view for the details. Everything that happened in the session, in one timeline with timestamps, built from the audit events (section 5). Four kinds of entries, each with its own marker:

| Entry | What it shows | Source |
|---|---|---|
| Buyer | What the buyer said or typed, word for word | Voice transcript or chat message |
| Agent | What the agent said or wrote back | Voice transcript or chat message |
| Tool call | Which MCP tool the agent called, a readable summary of the arguments, and the decision that came back (`ready`, `needs_clarification`, `rejected`) | MCP server |
| Engine and confirmation | The engine's steps and what happened after the call: SMS, link opened, flags acknowledged, confirmed | Engine and confirmation page |

Example:

> 10:02:14 **Call started.** Caller identified as Hassu Hauki Oy.
> 10:02:20 **Buyer:** "Hi, I need a thousand litres of lactose-free milk by Monday."
> 10:02:31 **Tool call:** `build_quote`: 1 line, lactose-free milk, 1,000 L, needed by Mon 16 Nov.
> 10:02:31 **Engine:** Searched 17,546 products. 35 match "lactose-free" in milk drinks.
> 10:02:32 **Engine:** Checked price and stock for 7 products.
> 10:02:32 **Engine:** Chose Valio Arki semi-skimmed 1 l: cheapest lactose-free milk in stock that arrives Monday.
> 10:02:33 **Engine:** Quote ready: 1,000 pcs, 1,150.00 € incl. VAT. 2 flags. → decision `ready`
> 10:02:36 **Agent:** "I found Valio Arki lactose-free semi-skimmed milk, 1,000 litres for 1,150 euros, arriving Monday. Shall I send it to your phone for confirmation?"
> 10:02:41 **Buyer:** "Yes, please."
> 10:02:42 **Tool call:** `request_confirmation` → SMS queued for the end of the call.
> 10:03:40 **Call ended.** SMS sent to +358 40 ••• ••12. Link shown on the call screen.
> 10:04:05 **Buyer** opened the link.
> 10:04:22 **Buyer** acknowledged 2 flags: stock not confirmed, not ordered before.
> 10:04:23 **Order confirmed.**

(Figures are illustrative; the real ones come from the engine.)

Filter toggle above the timeline: **Everything** (default), **Conversation only** (buyer and agent), **Agent and engine only** (tool calls and engine steps). Seeing the buyer's own words next to the tool call arguments is what makes a mishearing visible ("fifteen" heard as "fifty").

Each tool call entry expands to the full arguments and the full response the agent received, so you can see exactly what the agent was told and what it then said. Quote versions are shown where they happen (v1 built, v1 voided by an edit, v2 built). Every entry links to its audit event (3.4).

The header shows which agent version and prompt version ran the session, with a link to view that prompt. The prompt itself is not in the timeline.

What we can capture depends on the channel:

| Channel | Buyer and agent text | Tool calls |
|---|---|---|
| Phone (our Gemini voice agent) | Yes, from the voice transcripts | Yes |
| Mock webshop with WebMCP | Yes, if the chat runs on our page | Yes |
| Chat connector (Claude, OpenAI) | **No.** The conversation stays in the buyer's own client; our MCP server only sees tool calls | Yes |

For connector sessions the timeline says so in plain words ("Conversation happens in the buyer's own Claude client and is not visible to us. Tool calls shown below.") instead of looking empty.

Rules for conversation text:

- It is data, not instructions. It is escaped when shown and is never used in an engine decision (vision section 8). The engine still only receives the structured tool call arguments.
- Voice transcripts are speech-to-text output and can be wrong. They are labelled as transcripts.
- It is part of the audit log (one event per turn), so it is hash-chained with everything else.
- Booth visitors are shown on screen. The call screen tells them before the call starts that the conversation is shown on the public dashboard.

### 3.4 Audit log

The lowest level: the raw, hash-chained audit events behind one order session. Opened from the order summary's trust strip or from any entry in the full flow.

- **Event list.** Every event of the session in order: sequence number, timestamp, event type, the plain-language sentence, and a short form of its hash. Nothing is summarised or hidden at this level; conversation turns, tool calls, rejected candidates, voided quotes and failed SMS attempts are all there.
- **Event detail.** Clicking an event shows its full record: all fields and the structured payload as formatted JSON (the one place raw JSON is shown), its `prev_hash` and `hash`.
- **Chain check.** A "Verify chain" result at the top: the dashboard recomputes each hash from the event content and the previous hash and shows "Chain intact" or the first event where it breaks. This is how we show tamper evidence live, not only claim it. This needs the backend to chain events per session (or to give each event a per-session link as well as its place in a global chain); with one global chain only, one order's events cannot be checked on their own.
- **Quote check.** For quote events, the quote hash and the result of checking its signature against the published key.
- **Back links.** Each event links back to the entry it explains in the full flow or the order summary.
- **Download.** The session's events as a JSON file, so a judge can check the chain themselves.

The audit log stays read-only and append-only. The dashboard reads it through the read model and never writes to it. Masked identities stay masked here too.

## 4. Order session states

The status the dashboard shows. Derived from events, not stored separately by the clients.

| State | Shown as | Entered when |
|---|---|---|
| `in_conversation` | Active | First event of a session (call started, chat started, first tool call) |
| `needs_clarification` | Active, asking | `build_quote` or `update_quote` returned a clarification question |
| `quote_ready` | Active, quote ready | Latest quote decision is `ready` and SMS not yet sent |
| `awaiting_confirmation` | Waiting | SMS sent |
| `link_opened` | Waiting, buyer looking | Confirmation page loaded |
| `confirmed` | Confirmed | Buyer tapped Confirm and the recheck passed |
| `cancelled` | Cancelled | Buyer tapped Cancel |
| `expired` | Needs attention | Quote expired before confirmation (production only; quotes do not expire during the event) |
| `rejected` | Needs attention | Decision `rejected` with no later ready quote |
| `sms_failed` | Needs attention | SMS delivery failed (on the phone channel the visitor can still confirm through the call screen notification) |
| `callback_requested` | Needs attention | The next step offered was a callback and the buyer accepted |
| `requote_needed` | Needs attention | Availability got worse at confirmation, quote voided |
| `abandoned` | Ended, no order | Conversation ended without a quote |

A session can move back from a waiting state to an active one (the buyer edits on the page and a new quote is built). The card shows the latest state; the timeline shows the full path.

## 5. Data the dashboard needs

**The backend owns the event format.** This section lists what the dashboard needs from it; the backend team decides the actual schema and may rename or restructure fields as long as this information is there.

The dashboard reads its own **read model**, fed from the audit events. It never writes to the audit log and the audit log stays append-only and hash-chained (vision section 11, issue #20).

- Transport: server push (Server-Sent Events are enough; the dashboard only receives). On connect, it gets a snapshot of current sessions, then live events.
- Each event the engine writes needs, at minimum:

| Field | Purpose |
|---|---|
| `session_id` | Groups events into one card |
| `company_id`, `company_name` | Grouping on the overview |
| `channel` | Phone, web, chat badge |
| `identity_masked` | Masked phone or email, masked server-side |
| `ts` | Timeline |
| `type` | Event kind, see below |
| `text_fi`, `text_en` | The ready plain-language sentence, from the same templates as the agent text |
| `payload` | Structured detail for the order summary, full flow and audit log |
| `seq`, `prev_hash`, `hash` | Audit chain status |

- Conversation events, written by our agent runtime (phone, webshop chat) and the MCP server: `buyer_said`, `agent_said` (text, language, whether it is a transcript), `tool_called` (tool name, full arguments), `tool_returned` (full response). These are written for every channel where we have them (see the table in section 3.3).
- Event types (first list, to align with the engine): `session_started`, `customer_identified`, `request_received`, `products_searched`, `candidates_filtered`, `availability_checked`, `line_resolved`, `clarification_asked`, `quote_built`, `quote_voided`, `sms_sent`, `sms_failed`, `link_shown_on_call_screen`, `link_opened`, `flags_acknowledged`, `quote_edited`, `order_confirmed`, `order_cancelled`, `quote_expired`, `callback_requested`, `session_ended`.
- The masking happens before the event reaches the read model. The dashboard never receives the full number.

## 6. Readability rules

- Plain-language first. Codes, ids and hashes are secondary and small.
- Readable at a distance on the big screen: big numbers, few words per line, status shown by colour and by word (never colour alone).
- Money in euros with two decimals, VAT included, labelled once. Quantities in the buyer's unit and in sales units ("1,000 L = 1,000 pcs 1 l").
- Times in Europe/Helsinki. The demo clock (vision section 10) is shown in the header ("Demo time Thu 12 Nov 09:00") so judges are not confused by dates that do not match the real day.
- Language: English by default, with a visible toggle to Finnish.
- Works on a laptop and a large screen. A phone layout is nice to have, not required.

## 7. Demo scenarios it must show well

Taken from vision section 5 and section 10. Each should be visible end to end on the dashboard:

1. Happy path: 1,000 L lactose-free milk by Monday, quoted, confirmed.
2. Rounding and food waste: a need that does not fit whole packs (for example 10 L in 3 L packs), rounded up, exact-fit alternative offered.
3. Partial stock and split: one request becomes two lines from two products.
4. Allergen-safe substitution: milk-free kitchen, product with `AM` rejected, safe substitute chosen, flag shown.
5. Unverified stock (Terminal) flagged and acknowledged.
6. Recipe to order: one request, many lines grouped under it, unmapped ingredients shown as "not ordered".
7. Something goes wrong: SMS fails, or stock changes at confirmation and a new quote is needed, and the next step is visible.
8. Edit on the confirmation page: quote v1 voided, v2 confirmed.

## 8. Out of scope

- Login, roles, per-buyer views.
- A stage or auto-follow mode. The presenter opens the right call by hand.
- Any action on orders from the dashboard.
- Analytics beyond the counters (charts, history over days).
- Search across past orders.
- A global audit log across all orders.
- Exporting orders (Peppol export is a stretch item elsewhere).

## 9. Open questions

None at the moment.

### Decided on 2026-11-14

- English by default, Finnish toggle.
- Each caller gets a generated company with a unique funny-sounding Oy name.
- "Why this product" is a drill-down per line, not shown in full by default.
- The backend owns the event format; section 5 is the dashboard's list of needs.
- No stage or auto-follow mode.
- No counter reset; counters run for the whole event.
- The order summary shows only what was ordered and why. Conversation, tool calls and engine steps are in a separate full flow view.
- Everything is audited, grouped by order. No global audit log view.
