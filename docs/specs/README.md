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

- **Dashboard: everything public, no login** (decided by the team 2026-11-14, `technical-plan.md` §9.5; now in vision sections 8, 11 and 13). Everything is open to anyone with the URL, read-only, including the conversation and tool calls. Phone numbers and emails only ever appear masked; the confirmation link never appears. No operator login. This replaces the earlier public/private split. The call screen and the webshop chat tell visitors before they start: "Your order and what you write show on our public demo dashboard under a made-up company name." ("what you say" on the call). Production is revisited in #70.
- **Demo companies.** Each new caller number gets a generated company with a unique, funny-sounding Oy name (vision section 9, demo flow).
- **Conversation in the audit log.** Buyer and agent turns and every tool call are audit events and are shown on the public dashboard. Chat connector conversations are not visible to us, only their tool calls (vision sections 8 and 11).
- **Quotes do not expire during the event.** Expiry is a config value for production (vision section 6 says 30 minutes by default; also principle 5 and the hard stops).
- **Every link goes to a simulated phone inbox** on the web call page, never shown in the webshop. Webshop visitors read the link on the phone page in the same browser. Real SMS through Twilio sits behind a flag that is off by default and goes only to allowlisted numbers. The inbox is a demo convenience and weakens the second factor, which we state in the pitch. Production uses SMS only (vision sections 6 and 9).
- **Confirmation page language** follows the language of the call. After an edit, only new or changed flags need a new acknowledgement (vision section 6).
- **The phone is on speaker with live captions**, not held to the ear (vision section 9 says the visitor holds the phone to their ear).
- **The visitor chooses the kitchen profile** on the call page. This answers the open question in vision section 13 for the profile. The seeded order history is decided too (#61, vision section 13).
- **The webshop is our own static page in the Aimo webshop's style** (#56: no scrape, no logos, about 12 real products), with our chat added. The chat runs on Gemini, the same as the phone. Outside agents such as an OpenAI client use the page through WebMCP (vision section 9 says the webshop is "shown working with an OpenAI client").
- **Menu planning in the webshop chat**: weekdays, one main dish per day, turned into one order (vision section 7).
- **The confirmation page chat** is the webshop chat reused, built only after the webshop chat works (vision section 13 lists it as an A2UI stretch item).
