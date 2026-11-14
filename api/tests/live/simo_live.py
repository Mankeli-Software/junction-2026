"""A client for playing the demo script against a running S.I.MO, as outsiders see it (#98).

It plays three parts:

- **the visitor**: enters a number (`POST /api/v1/demo/accounts`), reads the simulated
  phone's inbox, opens the confirmation page, acknowledges the flags and confirms;
- **a connector agent**: registers over OAuth (public client, PKCE), gets the visitor's
  consent and calls the tools over `/mcp`;
- **a caller**: opens `/voice/ws` and types the caller's lines (`say`), so the real Gemini
  Live model, prompt, tools and relay guards run with nobody talking.

Every request carries `X-Simo-Test-Run` and `X-Simo-Test-Case`. The run id marks the
company as a test company, which keeps it off the public dashboard, and the stamps are on
the spans in Application Insights. What happened is read back from the public dashboard
API by session id.
"""

import asyncio
import base64
import hashlib
import json
import secrets
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

import httpx
import websockets
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from mcp.shared._httpx_utils import create_mcp_http_client

from app.schemas import KitchenType
from app.seed.history import kitchen_type_for
from tests.live.agent import Agent

REDIRECT_URI = "http://localhost/callback"  # never opened: the test reads the code itself
CLIENT_NAME = "S.I.MO live test"
USER_AGENT = "simo-live-test"
OUT_RATE = 24_000  # the relay's audio to the browser, 16-bit mono
HELSINKI = ZoneInfo("Europe/Helsinki")


@dataclass
class Run:
    """One run of the script: where the app is, the run id and the beat being played."""

    base: str
    run_id: str
    case: str = "setup"

    @classmethod
    def start(cls, base: str, prefix: str = "demo-script") -> "Run":
        return cls(base=base.rstrip("/"), run_id=f"{prefix}-{int(time.time())}")

    def stamps(self) -> dict[str, str]:
        return {"X-Simo-Test-Run": self.run_id, "X-Simo-Test-Case": self.case}

    async def _stamp(self, request: httpx.Request) -> None:
        request.headers.update(self.stamps())

    def http(self) -> httpx.AsyncClient:
        """A browser of its own (a cookie jar), stamped with the beat current at each request."""
        return httpx.AsyncClient(
            base_url=self.base,
            timeout=60,
            headers={"User-Agent": USER_AGENT},
            event_hooks={"request": [self._stamp]},
        )

    def school_number(self, salt: str = "") -> str:
        """A made-up Finnish mobile number, new for this run, that gets the school kitchen
        (the stage kitchen): the kitchen type follows from a hash of the number."""
        for attempt in range(10_000):
            digest = hashlib.sha256(f"{self.run_id}:{salt}:{attempt}".encode()).digest()
            number = f"+35840{1_000_000 + int.from_bytes(digest[:4], 'big') % 9_000_000}"
            if kitchen_type_for(number) == KitchenType.school_kitchen:
                return number
        raise RuntimeError("no school kitchen number found")

    # --- The public dashboard API: what happened ---

    async def overview(self) -> dict[str, Any]:
        async with self.http() as http:
            response = await http.get("/api/v1/public/orders", params={"test_run": self.run_id})
            response.raise_for_status()
            return response.json()

    async def sessions(self) -> list[dict[str, Any]]:
        """This run's sessions as dashboard cards, newest first."""
        overview = await self.overview()
        return [card for company in overview["companies"] for card in company["orders"]]

    async def business_date(self) -> date:
        """Today on the app's business clock, which quotes use for `needed_by`."""
        now = datetime.fromisoformat((await self.overview())["business_now"])
        return now.astimezone(HELSINKI).date()

    async def story(self, session_id: str) -> dict[str, list[dict[str, Any]]]:
        """One session's steps and transcript."""
        async with self.http() as http:
            out = {}
            for part in ("steps", "transcript"):
                response = await http.get(f"/api/v1/public/orders/{session_id}/{part}")
                response.raise_for_status()
                out[part] = response.json()
            return out

    async def verify_audit(self, session_id: str | None = None) -> dict[str, Any]:
        async with self.http() as http:
            params = {"session_id": session_id} if session_id else None
            response = await http.get("/api/v1/public/audit/verify", params=params)
            response.raise_for_status()
            return response.json()


def next_weekday(day: date, weekday: int) -> date:
    """The next such weekday strictly after `day` (0 is Monday)."""
    return day + timedelta(days=(weekday - day.weekday() - 1) % 7 + 1)


def describe_story(story: dict[str, list[dict[str, Any]]], lang: str = "en") -> str:
    """A session's steps as the dashboard shows them, one per line."""
    return "\n".join(
        f"    {step['order_index']:>3} {step['actor']:<12} {step['type']:<22} "
        f"{step['text'][lang][:140]}"
        for step in story["steps"]
    )


# --- The visitor ------------------------------------------------------------------------


class Visitor:
    """One browser: a demo account, its inbox and the confirmation page."""

    def __init__(self, run: Run) -> None:
        self.run = run
        self.http = run.http()
        self.account: dict[str, Any] = {}

    async def __aenter__(self) -> "Visitor":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.http.aclose()

    async def enter_number(
        self, exclusions: list[str], lang: str = "fi", number: str | None = None
    ) -> dict[str, Any]:
        response = await self.http.post(
            "/api/v1/demo/accounts",
            json={
                "phone_e164": number or self.run.school_number(),
                "exclusions": exclusions,
                "lang": lang,
            },
        )
        assert response.status_code == 201, response.text
        self.account = response.json()
        return self.account

    def cookie_header(self) -> str:
        return "; ".join(f"{name}={value}" for name, value in self.http.cookies.items())

    async def inbox(self) -> list[dict[str, Any]]:
        response = await self.http.get("/api/v1/private/inbox")
        response.raise_for_status()
        return response.json()

    async def current_quote(self) -> dict[str, Any] | None:
        """The visitor's current quote (the webshop's "current order"), if there is one."""
        response = await self.http.get("/api/v1/quotes/current")
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()

    # --- The confirmation page ---

    async def open_link(self, link: str) -> dict[str, Any]:
        token = link.rsplit("/c/", 1)[1]
        response = await self.http.get(f"/api/v1/confirmations/{token}")
        assert response.status_code == 200, response.text
        return response.json()

    async def confirm(self, link: str) -> dict[str, Any]:
        """Acknowledges every flag that needs it, then confirms. Returns the page's view
        before confirming and the order number."""
        token = link.rsplit("/c/", 1)[1]
        view = await self.open_link(link)
        seen = view
        for _ in range(20):
            waiting = [f for f in view["flags"] if f["requires_ack"] and not f["acknowledged_at"]]
            if not waiting:
                break
            flag = waiting[0]
            body = {"quote_hash": view["quote"]["quote_hash"], "flag_key": flag["flag_key"]}
            if flag["kind"] == "choose":
                body["option_id"] = flag["current_option_id"] or flag["options"][0]["option_id"]
            response = await self.http.post(
                f"/api/v1/confirmations/{token}/acknowledgements", json=body
            )
            assert response.status_code == 204, response.text
            view = await self.open_link(link)
        response = await self.http.post(
            f"/api/v1/confirmations/{token}/confirm",
            json={"quote_hash": view["quote"]["quote_hash"]},
        )
        assert response.status_code == 200, response.text
        return {"view": seen, **response.json()}

    # --- Connecting an agent (OAuth, as a chat connector does) ---

    async def connect_agent(self) -> str:
        """Registers a public client, gets this visitor's consent and returns the access
        token for `/mcp`."""
        async with self.run.http() as connector:
            response = await connector.post(
                "/oauth/register",
                json={
                    "redirect_uris": [REDIRECT_URI],
                    "token_endpoint_auth_method": "none",
                    "grant_types": ["authorization_code", "refresh_token"],
                    "response_types": ["code"],
                    "client_name": CLIENT_NAME,
                },
            )
            assert response.status_code == 201, response.text
            client_id = response.json()["client_id"]

            verifier = secrets.token_urlsafe(48)
            digest = hashlib.sha256(verifier.encode()).digest()
            challenge = base64.urlsafe_b64encode(digest).decode().rstrip("=")
            response = await connector.get(
                "/oauth/authorize",
                params={
                    "response_type": "code",
                    "client_id": client_id,
                    "redirect_uri": REDIRECT_URI,
                    "code_challenge": challenge,
                    "code_challenge_method": "S256",
                    "state": self.run.run_id,
                },
            )
            assert response.status_code == 302, response.text
            request_id = parse_qs(urlsplit(response.headers["location"]).query)["request"][0]

            # The consent page, in the visitor's browser.
            response = await self.http.post(
                f"/api/v1/oauth/requests/{request_id}", json={"allow": True}
            )
            assert response.status_code == 200, response.text
            back = parse_qs(urlsplit(response.json()["redirect_to"]).query)
            assert back["state"] == [self.run.run_id], back

            response = await connector.post(
                "/oauth/token",
                data={
                    "grant_type": "authorization_code",
                    "code": back["code"][0],
                    "redirect_uri": REDIRECT_URI,
                    "client_id": client_id,
                    "code_verifier": verifier,
                },
            )
            assert response.status_code == 200, response.text
            return response.json()["access_token"]


@asynccontextmanager
async def mcp_agent(run: Run, access_token: str) -> AsyncIterator[Agent]:
    """An agent on `/mcp` with the bearer token. Every request of the MCP session is
    stamped with the beat current when it is sent."""

    def http_client(headers=None, timeout=None, auth=None) -> httpx.AsyncClient:
        client = create_mcp_http_client(headers=headers, timeout=timeout, auth=auth)
        client.event_hooks["request"].append(run._stamp)
        return client

    async with (
        streamablehttp_client(
            f"{run.base}/mcp",
            headers={"Authorization": f"Bearer {access_token}", "User-Agent": USER_AGENT},
            httpx_client_factory=http_client,
        ) as (read, write, _),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        yield Agent(session)


# --- The caller -------------------------------------------------------------------------


@dataclass
class CallerScript:
    """What the caller types: the lines in order, then stock answers until the call ends."""

    lines: list[str]
    done: str  # "that's all", when S.I.MO keeps asking and nothing is quoted yet
    yes: str  # to the link question, once a quote exists
    bye: str


@dataclass
class PhoneCall:
    """A typed phone call, as it went."""

    transcript: list[tuple[str, str]] = field(default_factory=list)  # (who, text), finals
    tools: list[str] = field(default_factory=list)  # in the order S.I.MO started them
    said_at: list[int] = field(default_factory=list)  # len(tools) at each caller line
    states: list[tuple[str, str | None]] = field(default_factory=list)
    texts: list[str] = field(default_factory=list)  # every JSON message, raw
    ended: dict[str, Any] | None = None
    gone: asyncio.Event = field(default_factory=asyncio.Event)  # the socket has closed
    state: str = "connecting"
    spoke: bool = False  # S.I.MO has spoken since the caller's last line
    audio_s: float = 0.0
    inbox_during_call: list[dict[str, Any]] | None = None  # read after request_confirmation

    @property
    def closed(self) -> bool:
        return self.gone.is_set()

    def said_by(self, who: str) -> list[str]:
        return [text for speaker, text in self.transcript if speaker == who]

    def link_requested(self) -> bool:
        """S.I.MO asked for the link after the caller had answered the latest quote. The
        relay refuses a `request_confirmation` that comes before that answer."""
        if "request_confirmation" not in self.tools:
            return False
        asked = len(self.tools) - 1 - self.tools[::-1].index("request_confirmation")
        quotes = [
            i
            for i, tool in enumerate(self.tools[:asked])
            if tool in ("build_quote", "update_quote")
        ]
        quoted = quotes[-1] if quotes else -1
        return any(quoted < at <= asked for at in self.said_at)

    def describe(self) -> str:
        names = {"agent": "S.I.MO", "buyer": "caller"}
        lines = [f"    {names[who]}: {text}" for who, text in self.transcript]
        lines.append(f"    tools: {', '.join(self.tools) or 'none'}")
        lines.append(f"    ended: {self.ended}")
        return "\n".join(lines)


TURN_TIMEOUT_S = 60.0
HANG_UP_WAIT_S = 20.0  # how long the caller waits for S.I.MO to hang up after the link
MAX_TURNS = 12


async def play_call(visitor: Visitor, script: CallerScript) -> PhoneCall:
    """Plays one call for this visitor: waits for S.I.MO's turn to end, types the next
    line, and so on, until S.I.MO hangs up or the caller runs out of patience."""
    run = visitor.run
    url = run.base.replace("http", "ws", 1) + "/voice/ws"
    headers = {"Cookie": visitor.cookie_header(), "User-Agent": USER_AGENT, **run.stamps()}
    call = PhoneCall()
    async with websockets.connect(url, additional_headers=headers, max_size=None) as ws:
        receiver = asyncio.create_task(_receive(ws, call))
        try:
            await _play(ws, call, visitor, script)
            if call.ended is None and not call.closed:
                await ws.send(json.dumps({"type": "hangup"}))
            await asyncio.wait_for(receiver, 20)
        finally:
            receiver.cancel()
    return call


async def _receive(ws: Any, call: PhoneCall) -> None:
    try:
        async for message in ws:
            if isinstance(message, bytes):
                call.audio_s += len(message) / 2 / OUT_RATE
                continue
            call.texts.append(message)
            data = json.loads(message)
            kind = data["type"]
            if kind == "agent_state":
                call.state = data["state"]
                call.states.append((data["state"], data["tool"]))
                if data["state"] == "working":
                    call.tools.append(data["tool"])
                if data["state"] == "speaking":
                    call.spoke = True
            elif kind == "transcript" and data["final"] and data["text"]:
                call.transcript.append((data["who"], data["text"]))
                if data["who"] == "agent":
                    call.spoke = True
            elif kind == "ended":
                call.ended = data
                return
    except websockets.ConnectionClosed:
        pass
    finally:
        call.gone.set()


async def _agent_turn_done(call: PhoneCall, wait_s: float = TURN_TIMEOUT_S) -> bool:
    """Waits until S.I.MO has spoken and is listening again. False when it never did."""
    deadline = time.monotonic() + wait_s
    while time.monotonic() < deadline and not call.closed:
        if call.spoke and call.state == "listening":
            await asyncio.sleep(0.5)  # a caption or a second tool call may still follow
            if call.state == "listening":
                return True
        await asyncio.sleep(0.05)
    return False


async def _play(ws: Any, call: PhoneCall, visitor: Visitor, script: CallerScript) -> None:
    async def say(text: str) -> None:
        call.spoke = False
        call.said_at.append(len(call.tools))
        await ws.send(json.dumps({"type": "say", "text": text}))

    await _agent_turn_done(call)  # the greeting
    lines = list(script.lines)
    for _ in range(MAX_TURNS):
        if call.closed:
            return
        if call.link_requested():
            # The link is held until the call ends: the inbox must still be empty.
            call.inbox_during_call = await visitor.inbox()
            # S.I.MO should say goodbye and hang up by itself.
            try:
                await asyncio.wait_for(call.gone.wait(), HANG_UP_WAIT_S)
            except TimeoutError:
                pass
            if not call.closed:
                await say(script.bye)
                await _agent_turn_done(call, HANG_UP_WAIT_S)
            return
        quoted = any(tool in ("build_quote", "update_quote") for tool in call.tools)
        await say(lines.pop(0) if lines else script.yes if quoted else script.done)
        if not await _agent_turn_done(call):
            return
