# Spec: Confirmation page

Status: draft v1, 2026-11-14. Builds on `vision.md` sections 5, 6, 10 and 11. Visual style is decided later, after the specs are agreed. This file says what the page shows and does, not how it looks. Companion to `docs/specs/dashboard.md`.

## 1. Purpose

The confirmation page is the **only place an order can be confirmed**. The agent prepares a quote, the engine sends the buyer a link (by SMS in production, to the demo phone during the event), and the buyer opens it on their phone, checks the order, deals with anything unusual and taps Confirm.

It is the human-in-the-loop step of our guardrail story (judging: autonomy and controls, 20%) and the end of the live demo: a booth visitor ends the call and confirms the order on their own phone while the dashboard updates.

The page must make three things obvious:

1. **What will be ordered**, next to what the buyer asked for, so a mishearing is easy to spot.
2. **What is unusual** about it, shown first, in plain words.
3. **That nothing happens until they tap Confirm.**

## 2. Access: the link is the key

- **No login, no user accounts.** Whoever holds the link can open the page. The link is the second factor: it goes only to the account that made the order (vision section 6).
- The link carries a random single-use token (256 random bits, stored as SHA-256, as in `technical-plan.md` §8.2), bound to the quote, its hash and the recipient. It expires with the quote. **For the event, quotes do not expire** (decided 2026-11-14): visitors can confirm whenever they get to it. Expiry is one config value (`quote_ttl`, off for the event, for example 30 minutes in production), so the expired state below exists in the code but is not reached in the demo.
- The page is server-rendered from engine data only. Nothing from the agent or from product free text is trusted; all text is escaped.
- No agent can open, read or act on the page. Confirm and Cancel exist only here (vision section 8).
- The page shows the company name, never the full phone number.

### How the link reaches the buyer

Two ways, both after the call ends:

1. **The demo phone's inbox.** Every message lands in the inbox of the account that made the order, shown on our web phone page. The call is made from that page, not a real phone call, so when the visitor hangs up the page shows a phone-style notification ("Valio Aimo: confirm your order") that opens the message, and its link opens the confirmation page. This is always on during the event, so the demo never depends on an SMS provider.
2. **SMS through Twilio**, only when real SMS is turned on (a flag, off by default) and the number the visitor typed is on our allowlist. Every other number gets the inbox message only, so a typed number that belongs to a stranger never gets our SMS.

The inbox is a demo convenience. It lets people try the demo at Junction with any number, including foreign ones, without depending on SMS delivery. The notification is shown as a banner inside the call page; a real browser notification is optional and only used if the visitor has allowed notifications. Webshop chat sessions get the inbox message too. The inbox is never shown in the shop, because a browser agent works inside the shop page and could follow the link (vision section 8), so webshop visitors read it on the phone page in the same browser (`webshop-chat.md` section 2).

Trade-off, stated in the pitch: the inbox shows the link in the browser that made the order, so that device can also confirm, and it is not a true second factor. In production only the SMS (or another out-of-band channel) carries the link. This is one config value (`demo_inbox`, on for the event).

Both deliveries are audit events (`inbox_delivered`, and `sms_sent` or `sms_failed` when a real SMS goes out) and show on the dashboard. If the SMS fails, the dashboard still shows the failure, and the visitor can still confirm through the inbox.

## 3. Page states

One URL, different states. The page always says plainly which state it is in and what the buyer can do next (vision principle 4: never a dead end).

| State | What the buyer sees | What they can do |
|---|---|---|
| Ready to confirm | The order, flags, Confirm button | Acknowledge flags, edit, confirm, cancel |
| Updating | "Checking your change..." while the engine requotes | Wait |
| Confirmed | "Order received" page (section 7) | View the order |
| Cancelled | "Order cancelled. Nothing was ordered." | Nothing; the agent can start a new order |
| Expired (production only, off during the event) | "This quote expired at 10:32. Nothing was ordered." | Go back to the agent for a new quote |
| Requote needed | "Stock changed since the quote. Here is the updated order." The new quote is shown in the Ready state with the change highlighted | Same as Ready |
| Invalid link | "This link is not valid." No details about why | Nothing |

## 4. Layout, top to bottom

Phone first. The buyer is holding the phone they just called with. It must also work on a laptop.

### 4.1 Header

- Company name and "Order from your call at 10:02" (or "from your chat", "from the webshop").
- Delivery date ("Delivery Mon 16 Nov").
- Gross total, VAT included, labelled once.
- Time left ("Valid for 24 more minutes"), only when expiry is on. Hidden during the event.

### 4.2 Check these first (flags)

All flags on the quote, before the order lines, in plain words. Each has its own acknowledgement control ("Got it"). **Confirm stays disabled until every flag is acknowledged** (decided, vision section 13).

Flag kinds from vision section 6:

| Flag | Example text |
|---|---|
| Quantity outside the usual range | "5,000 pieces. You usually order 5 to 50." |
| Substitute | "This is a substitute for X. It also contains soy." |
| Rounded up | "Rounded up from 1,000 L to 1,002 L (334 cases)." |
| Stock not confirmed | "Stock is not confirmed for this product." |
| No allergen information | "No allergen information is listed for these products: ..." (one notice for the whole order) |
| Possible duplicate | "Same order was placed 20 minutes ago." |
| Pack size from name | "Pack size was read from the product name." |
| Exact-fit alternative available | "12 L of Valio (4 x 3 L), or 10 L of another milk?" with the choice inline |

Each flag links to the line it is about, and the line shows a matching marker.

### 4.3 Asked versus added (the order lines)

Each request on the left, the product chosen for it on the right (vision section 6):

- **Asked:** what we understood, in the buyer's terms: "1,000 L lactose-free milk, by Monday".
- **Added:** product name (and image when we have one), pack, quantity in sales units and in the asked unit ("1,000 pcs, 1 l each = 1,000 L"), unit price, line total.
- **Why:** one line ("Cheapest lactose-free milk in stock that arrives Monday").

A recipe or a stock split shows as one request with several lines grouped under it. Recipe ingredients that were not ordered are listed under the recipe as "Not ordered: salt, flour, ...", so the buyer knows to get them elsewhere.

Each line can expand to a short "why this product" trace: how many products were considered, the main reasons others were left out ("contains milk", "no stock", "arrives too late") and the deciding factor. This is a shorter version of the dashboard drill-down, written for the buyer. Internal ids and hashes are not shown.

### 4.4 Edit

Per line:

- Change quantity (stepper in sales units, with the asked unit shown alongside).
- Remove the line.
- Pick an offered alternative (exact-fit product, other pack, other date), when the engine offered one.

Every edit is sent to the engine, which builds a **new quote**. The page shows the new quote in place, highlights what changed ("Total 1,150.00 € → 920.00 €") and voids the old one. The link stays the same and now points to the new quote.

Flags already acknowledged stay acknowledged on the new quote. Only flags that are new or whose text changed (for example a new rounding amount) need a new acknowledgement, and they are marked "New".

Not editable on the page: adding new products, changing the delivery date freely, changing the kitchen profile. Those go back through the agent.

If an edit is not possible (for example more than the available stock), the engine's answer is shown on the line with its next step ("Only 51 available. Take 51, or add 949 L of another lactose-free milk?").

### 4.5 Confirm and cancel

- **Confirm** at the bottom, sticky on phone, disabled until all flags are acknowledged. The button says what it does: "Confirm order, 1,150.00 €".
- On tap the engine rechecks availability. If it got worse, the quote is void and the page moves to "Requote needed" (section 3). If it passes, the order record is created and the page moves to "Confirmed".
- Double taps and a second tab cannot create two orders: the token is single-use and confirmation is idempotent.
- **Cancel** is a secondary action with a short "Cancel this order? Nothing will be ordered." check.

## 5. Hard stops

Some things the buyer cannot override on the page (vision section 6): allergen or diet conflict with the kitchen profile, unknown unit conversion, unavailable product, expired or tampered quote. These never reach the page as orderable lines; the engine rejects them first. If an edit would cause one, the engine refuses the edit and the page explains why ("This alternative contains milk, which your kitchen excludes.").

## 6. Language and wording

- Plain language, short sentences, no codes. All texts come from the engine's templates in Finnish and English.
- Language: the language of the call or chat, with a toggle. A buyer who spoke Finnish to the agent gets the page in Finnish.
- Money in euros with two decimals, VAT included. Quantities in sales units and in the asked unit.
- Dates in words ("Mon 16 Nov"). Times in Europe/Helsinki.

## 7. Order received page

Shown after Confirm, at the same link:

- "Order received" with an order number and the time.
- The final lines, total and delivery date.
- The flags that were acknowledged, with the time.
- A note for the demo: "This is a demo. No real order was placed with Valio Aimo."

The link stays readable after confirmation (read-only) so the buyer can look at the order again, until the end of the event. In production this would be a fixed time such as 7 days.

## 8. What the dashboard sees

Every action on the page writes an audit event, which shows on the dashboard live: `link_opened`, `flags_acknowledged` (per flag), `quote_edited`, `quote_built`, `quote_voided`, `order_confirmed`, `order_cancelled`, `quote_expired`, `requote_needed`. The dashboard can show the visitor confirming on their phone as it happens.

## 9. Out of scope

- Login or accounts.
- Adding new products on the page, or editing in words (the A2UI agent on this page is a stretch item, vision section 13).
- Payment. Orders are invoiced (vision section 10).
- A separate confirmation person per account (production option only).
- Resending the SMS from the page. A resend goes through the agent.

## 10. Open questions

None at the moment.

### Decided on 2026-11-14

- The page follows the language of the call or chat, with a toggle.
- The link stays readable until the end of the event after confirmation.
- Quotes do not expire during the event. Expiry is a config value for production.
- After an edit, only new or changed flags need a new acknowledgement.
- Every link goes to the demo phone's inbox. Real SMS through Twilio sits behind a flag that is off by default and goes only to allowlisted numbers.
