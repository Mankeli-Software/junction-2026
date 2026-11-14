# Spec: Web phone call screen

Status: draft v1, 2026-11-14. Builds on `vision.md` section 9 (phone: real flow and demo flow) and the decisions in `docs/specs/README.md`. This file says what the screens show and do. How they look is in `docs/design/` (flow 1, screens `10` to `14`). Companions: `dashboard.md`, `confirmation-page.md`.

## 1. Purpose

This is the main stage demo and the way booth visitors try the product themselves. We cannot get real phone calls working in the time we have, so the "call" runs in the browser: the visitor opens our page on their own phone, types their number, and the page becomes a demo phone. They call S.I.MO, the Gemini voice agent, from the phone's Contacts, with the phone on speaker, watching live captions of the conversation. After the call they confirm the order on the same phone.

The number they type is the only thing that differs from the real flow. It stands in for the caller id and the account lookup. Everything after that is the real path (vision section 9).

## 2. Flow

The page looks like a phone app, so it is clear that no real call is placed (design review, `docs/design/README.md` flow 1). The screens, in order, on one page:

1. **Set up:** enter the phone number and choose the kitchen (`10-call-setup`).
2. **Contacts with S.I.MO:** the demo account and what to try (`11-call-contact`).
3. **Call:** the call itself (`12-call-in-call`).
4. **Call ended:** the notification with the link, and what happens next (`13-call-ended`).

On a computer the same screens show at phone size inside a phone frame (section 2.5).

The agent is always written **S.I.MO**. On screen it is not labelled an AI agent; it says it is an AI helper in its greeting (section 2.3).

### 2.1 Set up

- Heading "Your demo phone" and a short intro: "This page becomes a phone. Give S.I.MO a ring and order what your kitchen needs."
- Phone number field ("Your real phone number"). Country code defaults to +358; other countries are allowed.
- **Your kitchen avoids:** the exclusions as chips, with Nothing as the default (section 2.2).
- Notices, shown before the visitor continues, in plain words:
  - "Your order and what you say show on our public demo dashboard under a made-up company name. Your number is never shown in full." (changed 2026-11-14, `technical-plan.md` §9.5)
  - "The link to confirm your order arrives in the demo phone on this page. This is a demo; no real order is placed."
- One button: "Open demo phone".

Nothing is verified about the number in the demo; whoever types it is treated as its owner. See section 6 for the limits that stop misuse.

### 2.2 Contacts with S.I.MO (your demo account)

On "Open demo phone", the server creates a demo account for the number, or finds the existing one if the number has called before (decided: same number, same company).

The phone opens in its Contacts app, with a bottom tab bar (Favourites, Recents, Contacts, Keypad) for the look only. The screen shows:

- The generated company at the top, for example **Hassu Hauki Oy**: a unique, funny-sounding Oy name.
- The **S.I.MO contact card**: "Tell me what your kitchen needs. I will sort it out." and a green **Call** button.
- **Try saying**, as examples that only show text (they do not start anything):
  - "I need 1,000 litres of lactose-free milk by Monday."
  - "We ran out of ground beef, 5 kilos for tomorrow."
  - "My usual butter, 20 kilos."
  - "A recipe for 200 people, milk-free."
- **Kitchen**: the chosen exclusions ("Avoids milk and nuts"), with a Change button.
- **Usual order**: a few usual items from the seeded order history, so "my usual" makes sense.

**The kitchen profile.** The visitor chooses the kitchen's allergen and diet exclusions, so they can try the allergen-safe substitution themselves. Options (one or more): No restrictions (default), Milk-free, Lactose-free, Gluten-free, Nut-free, Egg-free, Fish-free, Vegan. The list is the contract's `Exclusion` values (`api/app/schemas/common.py`), which are the keys of `policy/allergen_rules.yaml`. The choice on the set-up screen is saved for the number, also for a returning number. Change on this screen edits it; a change applies from the next call. The chosen profile is shown on the dashboard and on the confirmation page.

### 2.3 Call

Tapping **Call** asks for microphone access (the browser's own prompt) and connects to our server, which runs the Gemini voice agent over the MCP server.

The screen looks like a phone call:

- Who is being called: **S.I.MO**, and "On speaker".
- Call state: Connecting, then a running call timer.
- Buttons: Mute, Speaker, Captions (show or hide the captions), and a red hang-up button.
- A simple activity indicator: listening, S.I.MO thinking ("S.I.MO is thinking..."), S.I.MO working ("Checking products..."), S.I.MO speaking. Readable at a glance if the visitor looks at the screen on speaker. It follows the relay's `agent_state` message (`technical-plan.md` §9.3).
- **Live captions for both sides**, headed "Live captions, automatic". The phone is not held to the ear; it is on speaker and the visitor watches the screen. Captions are labelled "You" and "S.I.MO". They come from the same voice transcripts as the dashboard and are marked as automatic captions, since speech-to-text can be wrong. Seeing "fifty" where you said "fifteen" lets the visitor correct the agent at once.
- **Captions arrive per utterance**, not word by word. In the Gemini Live spike (#51, `spikes/gemini-live/README.md`) no interim transcripts arrived: the visitor's caption appears in one piece about a second after they stop talking. The screen must not promise word-by-word captions.
- Audio plays through the loudspeaker, with the browser's echo cancellation on so the agent does not hear itself. Headphones work too, which helps at a noisy booth.

Holding the phone to the ear does not work in a web page: browsers give no reliable access to the proximity sensor, so the screen would stay on against the cheek and the captions would be useless. The page should keep the screen awake during the call where the browser allows it (Screen Wake Lock), so the call does not drop when the phone locks.

S.I.MO greets the caller by company name and says it is an AI helper ("Hi Hassu Hauki Oy! I'm S.I.MO, Valio Aimo's AI helper. What can I get you?"). It speaks Finnish or English, answering in the language the visitor speaks. That language is also used for the confirmation page (decided in `confirmation-page.md`).

**Ending the call.** Either side can end it:

- The visitor taps hang up.
- S.I.MO ends the call after the order is ready and the visitor has agreed to get the link ("I'll send the link to your phone now. Bye!").
- The backend ends it, if it sets a maximum call length. Whether there is a limit and how long it is, is a backend decision, not decided yet. If there is one, S.I.MO warns shortly before. The call screen only shows the elapsed time.

### 2.4 Call ended

- "Call ended, 3:40".
- If a quote is ready and the visitor agreed to it, at the same moment:
  - The message with the link lands in the **demo phone's inbox** for this account (always). The inbox is shown on this phone page only.
  - A phone-style **notification** from S.I.MO appears at the top of the screen: "Confirm your order, 128,40 €" and "Tap to check it". Tapping it opens the message in the demo phone, and its link opens the confirmation page. A real browser notification is shown too, only if the visitor has allowed notifications (see `confirmation-page.md`, "How the link reaches the buyer").
  - **Nothing is ordered yet**, in three steps: tap the notification, check what S.I.MO flagged, confirm.
  - A real SMS goes out through Twilio only when real SMS is turned on (a flag, off by default) and the number is on our allowlist (`technical-plan.md` section 8.2). Every other number gets the inbox message only, so a typed number that belongs to a stranger never gets our SMS.
- Only when a real SMS was sent: "Also sent by SMS to +358 40 *** **12."
- If no quote was made: "No order was made on this call." and nothing is sent.
- A "Call again" button. A new call is a new order session for the same company.

The notification stays on the screen until the visitor taps it or leaves. The message stays in the demo phone's inbox, so it can be opened later. Orders made in the webshop chat in the same browser land in the same inbox, since the inbox is never shown in the shop (`webshop-chat.md` section 2).

### 2.5 On a computer

On a computer the same phone screens show at phone size inside a phone frame, so every screen looks the same as on a real phone (`14-call-on-computer`). Beside the frame: "This works best on your phone", with a QR code to move to the visitor's own phone, and a link back to the demo start. The call uses the computer's microphone. The number entry and every rule above stay the same.

## 3. When things go wrong

Never a dead end: each case says what happened and what to do.

| Case | What the visitor sees |
|---|---|
| Microphone access denied | "We need the microphone for the call." How to allow it, and a retry button |
| No microphone or unsupported browser | "This browser cannot make the call. Try Chrome or Safari on your phone." |
| Cannot connect | "Could not connect. Try again." with a retry button |
| Call drops mid-call | "The call dropped." If a quote was ready and the visitor had agreed to it (`request_confirmation` was called), the message still lands in the demo phone's inbox (and goes by SMS to an allowlisted number) and the notification is shown. Otherwise nothing is sent. A "Call again" button |
| Invalid phone number | Inline message on the field |
| Too many calls for this number, or too many SMS for an allowlisted number (section 6) | "This number has reached the demo limit. Ask us at the booth." |
| SMS fails (allowlisted numbers only) | The notification and the inbox message still work. The page says: "The SMS did not arrive, use the message above." The dashboard shows the failure |

## 4. What the dashboard sees

Every step writes an audit event and appears live on the dashboard (`dashboard.md`). Everything is public there, including the conversation; the number only ever appears masked (`dashboard.md` section 2):

- `session_started` (channel phone), `customer_identified` (company, masked number, new or returning account).
- Conversation events: `buyer_said`, `agent_said` (transcripts), `tool_called`, `tool_returned`.
- `session_ended` with call length and who ended it (visitor, agent, time limit, dropped).
- `inbox_delivered` (the message is in the demo phone), and `sms_sent` or `sms_failed` when a real SMS goes out.

Mute, unmute and screen changes are not logged.

## 5. Language and layout

- Page text in English by default with a toggle to Finnish. The agent's language follows the visitor's speech, not the page toggle.
- Phone first. The visitor uses their own phone. It also works on a laptop with its microphone, inside the phone frame (section 2.5), for judges at a table and for the stage.
- Large buttons for mute and hang-up. The call screen must work one-handed.

## 6. Limits and privacy

The demo trusts any typed number, so we limit what one person can do with someone else's number:

- Real SMS go only to numbers on our allowlist, and only when real SMS is turned on (off by default). Any other typed number gets no SMS; its link goes to the demo phone's inbox only.
- For allowlisted numbers: at most a few SMS per number per hour (for example 3), and a limit per browser session.
- The SMS text says clearly that it is a demo and comes from our Junction project, so a stranger receiving it knows what it is.
- Phone numbers are stored only for the event and deleted afterwards. The dashboard and the audit log only ever get the masked number.
- Transcripts are public on the dashboard, and the visitor is told so before the call (`dashboard.md` section 2). Typing someone else's number never shows their inbox or confirmation links.
- No call audio is stored. Only the transcripts, as audit events.

In production none of this is needed: the caller id identifies the account, and the link goes to the account's registered number (vision section 9, real flow).

## 7. Out of scope

- Real phone calls (PSTN). Described as the production path.
- Verifying the number with a code before the call.
- Choosing the agent's voice or speed.
- Holding the phone to the ear (no proximity sensor in the browser).
- Showing the order on the call screen during the call. The order is shown on the confirmation page.

## 8. Open questions

None at the moment.

### Decided on 2026-11-14

- The visitor chooses the kitchen profile on the account screen.
- The phone is on speaker, not held to the ear. Live captions for both the visitor and the agent.
- If the call drops after the visitor agreed to the quote, the link is still sent.
- Every link goes to the demo phone's inbox on this page. Real SMS through Twilio sits behind a flag that is off by default and goes only to allowlisted numbers.
- The call screen shows elapsed time. Any maximum call length is a backend decision, not decided yet.
- The flow looks like a phone app: set up, Contacts with S.I.MO, call, call ended, and a phone frame on a computer. The agent is always written S.I.MO (design review, `docs/design/README.md`).
- ~~The conversation and the number are private on the dashboard.~~ Replaced later the same day: everything is public, the number only masked (`dashboard.md` section 2).
