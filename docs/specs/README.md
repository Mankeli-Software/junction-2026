# UI specs for the demo

What each demo screen shows and does. How the screens look is in [`docs/design`](../design/README.md), with exported screens and the link to the design canvas. The design review made a few decisions that are not in these specs yet; they are listed at the end of that README.

| Spec | Status |
|---|---|
| [Dashboard](dashboard.md) | Draft, no open questions |
| [Confirmation page](confirmation-page.md) | Draft, no open questions |
| [Web phone call screen](call-screen.md) | Draft, no open questions |
| [Webshop chat](webshop-chat.md) (stretch) | Draft, no open questions |

## Changes to carry into vision.md

Decided while writing the specs. `vision.md` is updated once, after all the specs are done. Until then, these specs win where they disagree with it.

- **Dashboard: general data public, private data behind the login.** General data is open to anyone with the URL, read-only, with no login. The conversation and contact details are private: only the user who made the order sees them, through the same number-entry login as the call screen and the webshop. Operators see everything. This extends "buyers see only their own company's orders" (vision section 11) for the event.
- **Demo companies.** Each new caller number gets a generated company with a unique, funny-sounding Oy name (vision section 9, demo flow).
- **Conversation in the audit log.** Buyer and agent turns and every tool call are audit events and are shown on the dashboard, in the private view only. Chat connector conversations are not visible to us, only their tool calls (vision sections 8 and 11).
- **Quotes do not expire during the event.** Expiry is a config value for production (vision section 6 says 30 minutes by default; also principle 5 and the hard stops).
- **Every link goes to a simulated phone inbox** on the web call page, never shown in the webshop. Webshop visitors read the link on the phone page in the same browser. Real SMS through Twilio sits behind a flag that is off by default and goes only to allowlisted numbers. The inbox is a demo convenience and weakens the second factor, which we state in the pitch. Production uses SMS only (vision sections 6 and 9).
- **Confirmation page language** follows the language of the call. After an edit, only new or changed flags need a new acknowledgement (vision section 6).
- **The phone is on speaker with live captions**, not held to the ear (vision section 9 says the visitor holds the phone to their ear).
- **The visitor chooses the kitchen profile** on the call page. This answers the open question in vision section 13 for the profile; the seeded order history is still open.
- **The webshop is the scraped current Aimo webshop** with our chat added. The chat runs on Gemini, the same as the phone. Outside agents such as an OpenAI client use the page through WebMCP (vision section 9 says the webshop is "shown working with an OpenAI client").
- **Menu planning in the webshop chat**: weekdays, one main dish per day, turned into one order (vision section 7).
- **The confirmation page chat** is the webshop chat reused, built only after the webshop chat works (vision section 13 lists it as an A2UI stretch item).
