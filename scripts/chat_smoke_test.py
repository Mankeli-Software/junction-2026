"""Live smoke test of the webshop chat (#57): one text order through POST /api/v1/chat.

Against a locally running API (with Postgres, a catalogue, GEMINI_API_KEY and CHAT_MODEL set
in its environment), this:

1. makes a demo account like the shop does (`POST /api/v1/demo/accounts`);
2. sends an order in Finnish and prints the stream as it comes (`text`, `tool`, `a2ui`);
3. if a quote came, taps "Send to my phone" (the `send_for_confirmation` action);
4. checks that each turn ended with `done`, that the quote turn had a `QuoteCard`, that the
   send turn had a `SentNotice` and that `/c/` (the confirmation link) never reached the
   stream; the link is in the inbox instead.

Each run makes a few Gemini calls. Keep runs few: the key has abuse limits.

    cd api && uv run python ../scripts/chat_smoke_test.py --base http://localhost:8000
"""

import argparse
import json
import random
import sys
import time
from typing import Any

import httpx

ORDER = "Tarvitsen 20 litraa laktoositonta kevytmaitoa maanantaiksi. Siinä kaikki."


def stream(client: httpx.Client, body: dict[str, Any]) -> tuple[list[tuple[str, Any]], str]:
    """One turn, printed as it streams. Returns the events and the raw body."""
    events: list[tuple[str, Any]] = []
    raw: list[str] = []
    started = time.monotonic()
    first_text: float | None = None
    with client.stream("POST", "/api/v1/chat", json=body, timeout=120) as response:
        if response.status_code != 200:
            response.read()
            sys.exit(f"POST /api/v1/chat answered {response.status_code}: {response.text}")
        kind = None
        for line in response.iter_lines():
            raw.append(line)
            if line.startswith("event:"):
                kind = line[6:].strip()
            elif line.startswith("data:") and kind:
                data = json.loads(line[5:].strip())
                events.append((kind, data))
                if kind == "text":
                    first_text = first_text or time.monotonic()
                    print(data["delta"], end="", flush=True)
                elif kind == "tool":
                    print(f"\n  [tool {data['name']} {data['status']}]", flush=True)
                elif kind == "a2ui":
                    components = [
                        c["component"]
                        for e in data["envelopes"]
                        for c in (e.get("updateComponents") or {}).get("components", [])
                    ]
                    print(f"\n  [a2ui {components}]", flush=True)
                else:
                    print(f"\n  [{kind} {data}]", flush=True)
                kind = None
    took = time.monotonic() - started
    to_text = f"{first_text - started:.1f} s" if first_text else "no text"
    print(f"\n  ({took:.1f} s, first text after {to_text})\n")
    return events, "\n".join(raw)


def components(events: list[tuple[str, Any]]) -> list[dict[str, Any]]:
    return [
        c
        for kind, data in events
        if kind == "a2ui"
        for e in data["envelopes"]
        for c in (e.get("updateComponents") or {}).get("components", [])
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", default="http://localhost:8000")
    parser.add_argument("--message", default=ORDER)
    args = parser.parse_args()

    client = httpx.Client(base_url=args.base, headers={"User-Agent": "curl/8.4.0"})
    phone = f"+35840{random.randrange(10**6, 10**7)}"
    made = client.post(
        "/api/v1/demo/accounts", json={"phone_e164": phone, "exclusions": [], "lang": "fi"}
    )
    if made.status_code != 201:
        sys.exit(f"Could not make a demo account: {made.status_code} {made.text}")

    failures: list[str] = []
    print(f"> {args.message}")
    events, raw = stream(client, {"message": args.message})
    conversation_id = events[0][1]["conversation_id"]
    if events[-1][0] != "done":
        failures.append(f"the order turn ended with {events[-1]}")
    if "/c/" in raw:
        failures.append("the order turn carried /c/")
    quotes = [c for c in components(events) if c["component"] == "QuoteCard"]
    if not quotes:
        failures.append("no QuoteCard in the order turn (the model may have asked a question)")

    if quotes:
        quote_id = quotes[-1]["quoteId"]
        print("> [Send to my phone]")
        action = {
            "name": "send_for_confirmation",
            "surfaceId": "smoke",
            "sourceComponentId": "send",
            "timestamp": "2026-11-14T10:00:00Z",
            "context": {"quoteId": quote_id},
        }
        events, raw = stream(client, {"conversation_id": conversation_id, "action": action})
        if events[-1][0] != "done":
            failures.append(f"the send turn ended with {events[-1]}")
        if "/c/" in raw:
            failures.append("the send turn carried /c/")
        if not any(c["component"] == "SentNotice" for c in components(events)):
            failures.append("no SentNotice after sending")
        inbox = client.get("/api/v1/private/inbox").json()
        if not inbox:
            failures.append("nothing in the inbox")
        else:
            print(f"Inbox: {inbox[-1]['text']}")

    if failures:
        print("FAILED:\n- " + "\n- ".join(failures))
        sys.exit(1)
    print("OK")


if __name__ == "__main__":
    main()
