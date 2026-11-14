# Spec: Web phone call screen

Status: draft v1, 2026-11-14. Builds on `vision.md` section 9 (phone: real flow and demo flow) and the decisions in `docs/specs/README.md`. Visual style is decided later, after the specs are agreed. This file says what the screens show and do, not how they look. Companions: `dashboard.md`, `confirmation-page.md`.

## 1. Purpose

This is the main stage demo and the way booth visitors try the product themselves. We cannot get real phone calls working in the time we have, so the "call" runs in the browser: the visitor opens our page on their own phone, types their number, and talks to the Gemini voice agent through the page with the phone on speaker, watching live captions of the conversation. After the call they confirm the order on the same phone.

The number they type is the only thing that differs from the real flow. It stands in for the caller id and the account lookup. Everything after that is the real path (vision section 9).

## 2. Flow

Four screens, in order, on one page:

1. **Start:** enter phone number.
2. **Your demo account:** who you are in the demo and what to try.
3. **Call:** the call itself.
4. **Call ended:** the link to confirm, and what happens next.

### 2.1 Start

- Short intro: "Order from Valio Aimo by talking to an AI agent. You will confirm the order on this phone."
- Phone number field. Country code defaults to +358; other countries are allowed because Twilio can send to them.
- Notices, shown before the visitor continues, in plain words:
  - "Your order shows on our public demo dashboard under a made-up company name. What you say and your number are shown only to you, in this browser."
  - "We send one SMS to this number with a link to confirm your order. This is a demo; no real order is placed."
- One button: "Continue".

Nothing is verified about the number in the demo; whoever types it is treated as its owner. See section 6 for the limits that stop misuse.

### 2.2 Your demo account

On Continue, the server creates a demo account for the number, or finds the existing one if the number has called before (decided: same number, same company).

The screen shows:

- The generated company: "You are **Hassu Hauki Oy**", with a unique, funny-sounding Oy name.
- **Choose your kitchen.** The visitor picks the kitchen's allergen and diet exclusions from a short list, so they can try the allergen-safe substitution themselves. Options (one or more): No restrictions (default), Milk-free, Lactose-free, Gluten-free, Nut-free, Egg-free, Fish-free, Vegan. The exact list follows the rules in issue #6. A returning number shows its last choice, which can be changed; a change applies from the next call. The chosen profile is shown on the dashboard and on the confirmation page.
- A few usual items from the seeded order history, so "my usual" makes sense ("You usually order: Valio butter 500 g, ...").
- **Things to try**, as tappable examples that only show text (they do not start anything):
  - "I need 1,000 litres of lactose-free milk by Monday."
  - "We ran out of ground beef, 5 kilos for tomorrow."
  - "My usual butter, 20 kilos."
  - "A recipe for 200 people, milk-free."
- One button: "Call Valio Aimo".

### 2.3 Call

Tapping "Call Valio Aimo" asks for microphone access (the browser's own prompt) and connects to our server, which runs the Gemini voice agent over the MCP server.

The screen looks like a phone call:

- Who is being called: "Valio Aimo ordering".
- Call state: Connecting, then a running call timer.
- Mute and hang-up buttons.
- A simple activity indicator: listening, agent speaking, agent working ("Checking products..."). Readable at a glance if the visitor looks at the screen on speaker.
- **Live captions for both sides.** The phone is not held to the ear; it is on speaker and the visitor watches the screen. Captions scroll in as people speak, labelled "You" and "Agent", with the text of the current utterance updating while it is spoken. They come from the same voice transcripts as the dashboard and are marked as automatic captions, since speech-to-text can be wrong. Seeing "fifty" where you said "fifteen" lets the visitor correct the agent at once.
- Audio plays through the loudspeaker, with the browser's echo cancellation on so the agent does not hear itself. Headphones work too, which helps at a noisy booth.

Holding the phone to the ear does not work in a web page: browsers give no reliable access to the proximity sensor, so the screen would stay on against the cheek and the captions would be useless. The page should keep the screen awake during the call where the browser allows it (Screen Wake Lock), so the call does not drop when the phone locks.

The agent greets the caller by company name ("Hi, Hassu Hauki Oy, what can I get you?"). It speaks Finnish or English, answering in the language the visitor speaks. That language is also used for the confirmation page (decided in `confirmation-page.md`).

**Ending the call.** Either side can end it:

- The visitor taps hang up.
- The agent ends the call after the order is ready and the visitor has agreed to get the link ("I'll send the link to your phone now. Bye!").
- The backend ends it, if it sets a maximum call length. Whether there is a limit and how long it is, is a backend decision, not decided yet. If there is one, the agent warns shortly before. The call screen only shows the elapsed time.

### 2.4 Call ended

- "Call ended, 2:14".
- If a quote is ready and the visitor agreed to it, two things happen at the same moment:
  - The SMS goes out through Twilio (always).
  - A phone-style **notification banner** appears at the top of the call page: "Valio Aimo: confirm your order, 1,150.00 €". Tapping it opens the confirmation page. A real browser notification is shown too, only if the visitor has allowed notifications (see `confirmation-page.md`, "How the link reaches the buyer").
- Below the banner: "We also sent the link by SMS to +358 40 ••• ••12."
- If no quote was made: "No order was made on this call." and nothing is sent.
- A "Call again" button. A new call is a new order session for the same company.

The banner stays on the page until the visitor taps it or leaves, so it can be opened later.

## 3. When things go wrong

Never a dead end: each case says what happened and what to do.

| Case | What the visitor sees |
|---|---|
| Microphone access denied | "We need the microphone for the call." How to allow it, and a retry button |
| No microphone or unsupported browser | "This browser cannot make the call. Try Chrome or Safari on your phone." |
| Cannot connect | "Could not connect. Try again." with a retry button |
| Call drops mid-call | "The call dropped." If a quote was ready and the visitor had agreed to it (`request_confirmation` was called), the link is still sent by SMS and shown in the banner. Otherwise nothing is sent. A "Call again" button |
| Invalid phone number | Inline message on the field |
| Too many calls or SMS for this number (section 6) | "This number has reached the demo limit. Ask us at the booth." |
| SMS fails | The banner still works. The page says: "The SMS did not arrive, use the link above." The dashboard shows the failure |

## 4. What the dashboard sees

Every step writes an audit event and appears live on the dashboard (`dashboard.md`). The conversation and the masked number show only in the private view, to the visitor who made the call (`dashboard.md` section 2):

- `session_started` (channel phone), `customer_identified` (company, masked number, new or returning account).
- Conversation events: `buyer_said`, `agent_said` (transcripts), `tool_called`, `tool_returned`.
- `session_ended` with call length and who ended it (visitor, agent, time limit, dropped).
- `sms_sent` or `sms_failed`, and `link_shown_on_call_screen`.

Mute, unmute and screen changes are not logged.

## 5. Language and layout

- Page text in English by default with a toggle to Finnish. The agent's language follows the visitor's speech, not the page toggle.
- Phone first. The visitor uses their own phone. It also works on a laptop with its microphone, for judges at a table and for the stage.
- Large buttons for mute and hang-up. The call screen must work one-handed.

## 6. Limits and privacy

The demo trusts any typed number, so we limit what one person can do with someone else's number:

- At most a few SMS per number per hour (for example 3), and a limit per browser session.
- The SMS text says clearly that it is a demo and comes from our Junction project, so a stranger receiving it knows what it is.
- Phone numbers are stored only for the event and deleted afterwards. The dashboard and the audit log only ever get the masked number, and the dashboard shows it only in the private view.
- Transcripts are private: only the browser that made the call sees them on the dashboard. Typing someone else's number never shows their conversations (`dashboard.md` section 2).
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
- The call screen shows elapsed time. Any maximum call length is a backend decision, not decided yet.
- The conversation and the number are private on the dashboard, shown only to the visitor who made the call. The rest of the order is public.
