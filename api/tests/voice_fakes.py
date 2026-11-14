"""Fakes for the voice relay tests (#52): Gemini Live, the MCP tools and the call service.

The relay runs inside Starlette's TestClient, in the client's own event loop and thread.
The test drives the fake Gemini session from its thread with `push()`, which hands the
message to that loop safely.
"""

import asyncio
import threading
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from google.genai import types
from mcp.types import Tool

from app.schemas import CustomerContext
from app.services import voice_calls
from app.services.caller import Caller

PCM_24K = b"\x01\x00" * 2400  # 100 ms


class FakeLive:
    """A scripted Gemini Live session."""

    def __init__(self, *, fail: Exception | None = None) -> None:
        self.fail = fail
        self.model: str | None = None
        self.config: types.LiveConnectConfig | None = None
        self.inputs: list[dict[str, Any]] = []
        self.tool_responses: list[types.FunctionResponse] = []
        self.connected = threading.Event()
        self.closed = threading.Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._queue: asyncio.Queue[Any] | None = None
        self._lock = threading.Lock()

    def connect(self, model: str, config: types.LiveConnectConfig):
        self.model, self.config = model, config

        @asynccontextmanager
        async def session() -> AsyncIterator["FakeLive"]:
            if self.fail is not None:
                raise self.fail
            self._loop = asyncio.get_running_loop()
            self._queue = asyncio.Queue()
            self.connected.set()
            try:
                yield self
            finally:
                self.closed.set()

        return session()

    # --- The session interface ---

    async def send_realtime_input(self, **kwargs: Any) -> None:
        with self._lock:
            self.inputs.append(kwargs)

    async def send_tool_response(self, *, function_responses: list[types.FunctionResponse]):
        with self._lock:
            self.tool_responses.extend(function_responses)

    async def receive(self) -> AsyncIterator[types.LiveServerMessage]:
        assert self._queue is not None
        while True:
            message = await self._queue.get()
            if isinstance(message, Exception):
                raise message
            yield message

    # --- Driving it from the test ---

    def push(self, message: types.LiveServerMessage | Exception) -> None:
        assert self.connected.wait(5)
        assert self._loop is not None and self._queue is not None
        self._loop.call_soon_threadsafe(self._queue.put_nowait, message)

    def texts(self) -> list[str]:
        with self._lock:
            return [i["text"] for i in self.inputs if i.get("text")]

    def audio_frames(self) -> int:
        with self._lock:
            return sum(1 for i in self.inputs if i.get("audio") is not None)

    def wait_for(self, predicate, timeout: float = 5.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(0.01)
        raise AssertionError("timed out waiting for the fake Gemini session")


# --- Messages as Gemini sends them ---


def audio(pcm: bytes = PCM_24K) -> types.LiveServerMessage:
    return types.LiveServerMessage(
        server_content=types.LiveServerContent(
            model_turn=types.Content(
                parts=[types.Part(inline_data=types.Blob(data=pcm, mime_type="audio/pcm"))]
            )
        )
    )


def said(text: str) -> types.LiveServerMessage:
    return types.LiveServerMessage(
        server_content=types.LiveServerContent(output_transcription=types.Transcription(text=text))
    )


def heard(text: str) -> types.LiveServerMessage:
    return types.LiveServerMessage(
        server_content=types.LiveServerContent(input_transcription=types.Transcription(text=text))
    )


def generation_complete() -> types.LiveServerMessage:
    return types.LiveServerMessage(server_content=types.LiveServerContent(generation_complete=True))


def interrupted() -> types.LiveServerMessage:
    return types.LiveServerMessage(server_content=types.LiveServerContent(interrupted=True))


def tool_call(name: str, args: dict[str, Any] | None = None, call_id: str | None = None):
    return types.LiveServerMessage(
        tool_call=types.LiveServerToolCall(
            function_calls=[
                types.FunctionCall(id=call_id or uuid.uuid4().hex, name=name, args=args or {})
            ]
        )
    )


# --- MCP tools ---

QUOTE_SCHEMA = {
    "type": "object",
    "properties": {"lines": {"type": "array", "items": {"$ref": "#/$defs/Line"}}},
    "required": ["lines"],
    "additionalProperties": False,
    "$defs": {
        "Line": {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "unit": {"$ref": "#/$defs/Unit"},
            },
        },
        "Unit": {"type": "string", "enum": ["l", "kg"]},
    },
}


def mcp_tool(name: str, schema: dict[str, Any] | None = None) -> Tool:
    return Tool(
        name=name,
        description=f"The {name} tool.",
        inputSchema=schema or {"type": "object", "properties": {}},
    )


class FakeTools:
    """The MCP server as the relay sees it. `delay` slows every call down."""

    def __init__(self, *, delay: float = 0.0) -> None:
        self.delay = delay
        self.tokens: list[str] = []
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.closed = threading.Event()
        self.held = False

    def open(self, token: str):
        self.tokens.append(token)

        @asynccontextmanager
        async def session() -> AsyncIterator["FakeTools"]:
            try:
                yield self
            finally:
                self.closed.set()

        return session()

    async def list_tools(self) -> list[Tool]:
        return [
            mcp_tool("build_quote", QUOTE_SCHEMA),
            mcp_tool("request_confirmation"),
            mcp_tool("get_customer_context"),
        ]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((name, arguments))
        if self.delay:
            await asyncio.sleep(self.delay)
        if name == "build_quote":
            return {"output": {"quote_id": "q-1", "decision": "ready", "total_cents": 4190}}
        if name == "request_confirmation":
            self.held = True
            return {"output": {"sent_to_masked": "+358 40 *** **12", "delivery_status": "held"}}
        return {"output": {}}


# --- The call service, without a database ---

CALLER = Caller(
    user_id=uuid.UUID("00000000-0000-4000-8000-0000000000aa"),
    company_id=uuid.UUID("00000000-0000-4000-8000-0000000000bb"),
    company_name="Hassu Hauki Oy",
    phone_masked="+358 40 *** **12",
    exclusions=[],
    lang="fi",
    channel="phone",
    client_name=voice_calls.CLIENT_NAME,
)
SESSION_ID = uuid.UUID("00000000-0000-4000-8000-0000000000cc")
TOKEN = "caller-token-for-the-test"
LINK_LIKE = "/c/"


class FakeService:
    """Stands in for `app.services.voice_calls` and the database."""

    def __init__(self, tools: FakeTools) -> None:
        self.tools = tools
        self.started = 0
        self.said: list[tuple[str, str, dict[str, Any]]] = []
        self.local_tools: list[tuple[str, dict[str, Any]]] = []
        self.log: list[str] = []  # said and local tool events, in writing order
        self.ended: list[dict[str, Any]] = []
        self.end_called = threading.Event()

    async def start_call(self, db, user_id, *, prompt_version, now=None):
        self.started += 1
        self.prompt_version = prompt_version
        return voice_calls.CallStart(
            caller=CALLER,
            session_id=SESSION_ID,
            call_id="call-1",
            token=TOKEN,
            context=CustomerContext(
                company_name=CALLER.company_name,
                phone_masked=CALLER.phone_masked,
                exclusions=[],
                usual_items=[],
                lang="fi",
            ),
        )

    async def custom_vocabulary(self, db):
        return ["Valio", "vispikerma"]

    async def record_said(self, db, session_id, who, text, **extra):
        self.said.append((who, text, extra))
        self.log.append(f"{who}_said: {text}")

    async def record_local_tool(self, db, session_id, name, arguments, response):
        self.local_tools.append((name, response))
        self.log.append(f"tool: {name}")

    async def end_call(self, db, user_id, session_id, *, ended_by, duration_s, now=None):
        self.ended.append({"ended_by": ended_by, "duration_s": duration_s})
        released = ["q-1"] if self.tools.held else []
        self.tools.held = False
        self.end_called.set()
        return voice_calls.CallEnd(
            released_quote_ids=released,
            quote_id="q-1" if released else None,
            total_cents=4190 if released else None,
        )


class FakeDb:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return None

    async def commit(self):
        return None
