"""The voice relay's `/voice/ws` protocol with Gemini, MCP and the database faked (#52).

The messages and close codes are the ones the phone page expects
(`web/src/lib/demo/types.ts`, `web/src/lib/server/demo/relay.ts`). No database needed.
"""

import json
import logging
import time
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app import telemetry
from app.agent import CALL_CONNECTED, END_CALL, PROMPT_VERSION
from app.interfaces.voice import filler, relay, routes
from app.main import app
from app.services import accounts, voice_calls
from app.services.accounts import SessionUser
from app.settings import get_settings
from tests import voice_fakes as fx


@pytest.fixture
def call(monkeypatch: pytest.MonkeyPatch):
    live = fx.FakeLive()
    tools = fx.FakeTools()
    service = fx.FakeService(tools)
    monkeypatch.setattr(relay, "connect_gemini", live.connect)
    monkeypatch.setattr(relay, "open_tools", tools.open)
    monkeypatch.setattr(relay, "call_limits", lambda: relay.Limits(max_call_s=60))
    monkeypatch.setattr(relay, "get_sessionmaker", lambda: fx.FakeDb)
    monkeypatch.setattr(routes, "get_sessionmaker", lambda: fx.FakeDb)
    for name in ("start_call", "custom_vocabulary", "record_said", "record_local_tool", "end_call"):
        monkeypatch.setattr(voice_calls, name, getattr(service, name))

    async def resolve_session(db, raw, now=None):
        if raw != "good":
            return None
        return SessionUser(
            session_id=fx.SESSION_ID,
            user_id=fx.CALLER.user_id,
            company_id=fx.CALLER.company_id,
            phone_e164="+358401234512",
        )

    monkeypatch.setattr(accounts, "resolve_session", resolve_session)
    monkeypatch.setenv("VOICE_FILLER_AFTER_S", "0.2")
    get_settings.cache_clear()
    yield live, tools, service
    get_settings.cache_clear()


def connect(cookie: str | None = "good", headers: dict[str, str] | None = None):
    client = TestClient(app)
    if cookie:
        client.cookies.set("simo_session", cookie)
    return client.websocket_connect("/voice/ws", headers=headers or {})


class Socket:
    """The browser end: collects everything the relay sends."""

    def __init__(self, ws) -> None:
        self.ws = ws
        self.messages: list[dict[str, Any]] = []
        self.audio = 0
        self.raw_texts: list[str] = []

    def next(self, type_: str, **fields: Any) -> dict[str, Any]:
        """Reads until a JSON message of this type (and these fields) arrives."""
        while True:
            message = self.ws.receive()
            if message["type"] == "websocket.close":
                raise AssertionError(f"closed ({message.get('code')}) before {type_}")
            if message.get("bytes") is not None:
                self.audio += 1
                continue
            self.raw_texts.append(message["text"])
            data = json.loads(message["text"])
            self.messages.append(data)
            if data["type"] == type_ and all(data.get(k) == v for k, v in fields.items()):
                return data

    def states(self) -> list[tuple[str, str | None]]:
        return [(m["state"], m["tool"]) for m in self.messages if m["type"] == "agent_state"]

    def transcripts(self, who: str) -> list[tuple[str, bool]]:
        return [
            (m["text"], m["final"])
            for m in self.messages
            if m["type"] == "transcript" and m["who"] == who
        ]

    def send_audio(self, frames: int = 1) -> None:
        for _ in range(frames):
            self.ws.send_bytes(b"\x00\x00" * 1600)

    def say(self, text: str) -> None:
        self.ws.send_text(json.dumps({"type": "say", "text": text}))

    def hang_up(self) -> dict[str, Any]:
        self.ws.send_text(json.dumps({"type": "hangup"}))
        ended = self.next("ended")
        message = self.ws.receive()
        assert message["type"] == "websocket.close"
        assert message["code"] == 1000
        return ended


def greet(live: fx.FakeLive, sock: Socket) -> None:
    sock.next("ready")
    live.wait_for(lambda: CALL_CONNECTED in live.texts())
    live.push(fx.said("Hei, Hassu Hauki Oy!"))
    live.push(fx.audio())
    live.push(fx.generation_complete())
    sock.next("transcript", who="agent", final=True)


# --- Connecting -------------------------------------------------------------------------


def test_no_session_closes_with_4401(call):
    for cookie in (None, "expired"):
        with connect(cookie) as ws:
            with pytest.raises(WebSocketDisconnect) as closed:
                ws.receive_text()
        assert closed.value.code == relay.CLOSE_NO_SESSION


def test_a_second_call_for_the_same_user_closes_with_4429(call):
    live, _, _ = call
    with connect() as first:
        Socket(first).next("ready")
        with connect() as second:
            with pytest.raises(WebSocketDisconnect) as closed:
                second.receive_text()
        assert closed.value.code == relay.CLOSE_LIMIT
        Socket(first).hang_up()


def test_gemini_failing_to_connect_closes_like_cannot_connect(call, monkeypatch):
    _, _, service = call
    monkeypatch.setattr(relay, "connect_gemini", fx.FakeLive(fail=RuntimeError("down")).connect)
    with connect() as ws:
        with pytest.raises(WebSocketDisconnect) as closed:
            ws.receive_text()
    assert closed.value.code == relay.CLOSE_UNAVAILABLE
    assert service.ended == [{"ended_by": "dropped", "duration_s": 0}]


# --- Session setup ----------------------------------------------------------------------


def test_the_session_greets_first_with_the_tools_vocabulary_and_voice(call):
    live, tools, service = call
    with connect() as ws:
        sock = Socket(ws)
        sock.next("ready")
        assert sock.next("agent_state") == {
            "type": "agent_state",
            "state": "listening",
            "tool": None,
        }
        live.wait_for(lambda: live.texts() == [CALL_CONNECTED])
        sock.hang_up()

    assert service.prompt_version == PROMPT_VERSION
    assert tools.tokens == [fx.TOKEN]
    assert live.model == "gemini-3.8-live"
    config = live.config
    assert config.input_audio_transcription.custom_vocabulary == ["Valio", "vispikerma"]
    assert config.output_audio_transcription is not None
    voice = config.speech_config.voice_config.prebuilt_voice_config.voice_name
    assert voice == get_settings().voice_name == "Achird"
    assert "Hassu Hauki Oy" in config.system_instruction
    names = [d.name for d in config.tools[0].function_declarations]
    assert names == ["build_quote", "request_confirmation", "get_customer_context", END_CALL]
    quote = config.tools[0].function_declarations[0].parameters_json_schema
    assert "$defs" not in json.dumps(quote) and "$ref" not in json.dumps(quote)
    assert quote["properties"]["lines"]["items"]["properties"]["unit"]["enum"] == ["l", "kg"]
    silence = config.realtime_input_config.automatic_activity_detection.silence_duration_ms
    assert silence == get_settings().voice_silence_ms


def test_the_vocabulary_leaves_out_the_agents_own_name():
    # #85: with "S.I.MO" in the list, the recogniser wrote it in place of a caller's
    # first Finnish words after an English opening.
    assert not any("simo" in term.lower().replace(".", "") for term in voice_calls.BASE_VOCABULARY)


# --- Audio, captions and agent_state ---------------------------------------------------


def test_audio_both_ways_captions_and_states(call):
    live, _, service = call
    with connect() as ws:
        sock = Socket(ws)
        sock.next("ready")
        live.wait_for(lambda: CALL_CONNECTED in live.texts())
        live.push(fx.said("Hei, <b>Hassu"))
        live.push(fx.audio())
        live.push(fx.said(" Hauki</td>\nOy!"))
        live.push(fx.audio())
        live.push(fx.generation_complete())
        final = sock.next("transcript", who="agent", final=True)
        sock.next("agent_state", state="listening")

        sock.send_audio(3)
        live.wait_for(lambda: live.audio_frames() == 3)
        live.push(fx.heard("Tarvitsen viisi kiloa"))
        sock.next("agent_state", state="thinking")
        live.push(fx.heard(" jauhelihaa."))
        live.push(fx.said("Selvä."))
        live.push(fx.audio())
        live.push(fx.generation_complete())
        sock.next("transcript", who="agent", final=True)
        sock.hang_up()

    assert sock.audio == 3
    assert final["text"] == "Hei, Hassu Hauki Oy!"
    agent = sock.transcripts("agent")
    assert "".join(t for t, f in agent[:2] if not f) == "Hei, Hassu Hauki Oy!"
    assert all("<" not in t for t, _ in agent)
    assert sock.transcripts("buyer") == [
        ("Tarvitsen viisi kiloa", False),
        (" jauhelihaa.", False),
        ("Tarvitsen viisi kiloa jauhelihaa.", True),
    ]
    assert sock.states() == [
        ("listening", None),
        ("speaking", None),
        ("listening", None),
        ("thinking", None),
        ("speaking", None),
        ("listening", None),
    ]
    assert service.said == [
        ("agent", "Hei, Hassu Hauki Oy!", {"lang": "fi"}),
        ("buyer", "Tarvitsen viisi kiloa jauhelihaa.", {"lang": "fi"}),
        ("agent", "Selvä.", {"lang": "fi"}),
    ]


def test_interruption_flushes_and_listens(call):
    live, _, _ = call
    with connect() as ws:
        sock = Socket(ws)
        sock.next("ready")
        live.push(fx.said("Naudan jauheliha, kaksi"))
        live.push(fx.audio())
        sock.next("agent_state", state="speaking")
        live.push(fx.interrupted())
        sock.next("interrupted")
        assert sock.next("transcript", who="agent")["final"] is True
        sock.next("agent_state", state="listening")
        sock.hang_up()


# --- Tools ------------------------------------------------------------------------------


def test_a_tool_call_goes_through_mcp_with_working_and_the_filler(call, monkeypatch):
    live, tools, service = call
    tools.delay = 0.6
    with connect() as ws:
        sock = Socket(ws)
        greet(live, sock)
        audio_before = sock.audio
        live.push(fx.heard("Kyllä, siinä kaikki."))
        live.push(fx.tool_call("build_quote", {"lines": [{"text": "jauheliha"}]}, "c1"))
        assert sock.next("agent_state", state="working") == {
            "type": "agent_state",
            "state": "working",
            "tool": "build_quote",
        }
        filler_caption = sock.next("transcript", who="agent")
        sock.next("agent_state", state="thinking")
        live.wait_for(lambda: len(live.tool_responses) == 1)
        sock.hang_up()

    assert filler_caption == {
        "type": "transcript",
        "who": "agent",
        "text": filler.TEXT["fi"],
        "final": True,
    }
    clip = filler.clip("Achird", "fi")
    assert clip and sock.audio - audio_before >= len(clip) // relay.CHUNK_BYTES
    assert tools.calls == [("build_quote", {"lines": [{"text": "jauheliha"}]})]
    [response] = live.tool_responses
    assert response.id == "c1" and response.name == "build_quote"
    assert response.response == {
        "output": {"quote_id": "q-1", "decision": "ready", "total_cents": 4190}
    }
    assert ("agent", filler.TEXT["fi"], {"lang": "fi", "filler": True}) in service.said


def test_voice_tool_telemetry_records_safe_mcp_outcomes(call, monkeypatch, caplog):
    live, tools, _ = call
    results = iter(
        [
            {
                "output": {
                    "decision": "rejected",
                    "lines": [{}, {}],
                    "flags": [],
                    "rejections": [
                        {
                            "line_id": "jane.doe@example.com",
                            "reason_code": "INPUT_INVALID",
                            "text": "+358 40 123 4567",
                            "next_step": "https://simo.mankeli.co/c/secret",
                        }
                    ],
                    "not_ordered": [],
                }
            },
            {"error": "jane.doe@example.com +358 40 123 4567 /c/secret"},
        ]
    )

    async def call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return next(results)

    monkeypatch.setattr(tools, "call_tool", call_tool)
    observed = []
    annotate = relay.telemetry.annotate

    def record_annotations(**attributes: Any) -> None:
        if "mcp_outcome" in attributes:
            observed.append(attributes)
        annotate(**attributes)

    monkeypatch.setattr(relay.telemetry, "annotate", record_annotations)
    caplog.set_level(logging.INFO, logger="simo.events")

    with connect() as ws:
        sock = Socket(ws)
        greet(live, sock)
        live.push(fx.tool_call("build_quote", {"lines": []}, "c1"))
        live.wait_for(lambda: len(live.tool_responses) == 1)
        live.push(fx.tool_call("build_quote", {"lines": []}, "c2"))
        live.wait_for(lambda: len(live.tool_responses) == 2)
        sock.hang_up()

    assert len(observed) == 2
    assert {key: value for key, value in observed[0].items() if key != "round_trip_ms"} == {
        "mcp_outcome": "ok",
        "quote_decision": "rejected",
        "quote_line_count": 2,
        "quote_flag_count": 0,
        "quote_rejection_count": 1,
        "quote_not_ordered_count": 0,
        "quote_rejection_codes": "INPUT_INVALID",
    }
    assert {key: value for key, value in observed[1].items() if key != "round_trip_ms"} == {
        "mcp_outcome": "error"
    }
    records = [record for record in caplog.records if record.name == "simo.events"]
    exported = " ".join(f"{record.getMessage()} {record.__dict__}" for record in records)
    assert "jane.doe@example.com" not in exported
    assert "+358 40 123 4567" not in exported
    assert "/c/secret" not in exported


def test_a_quick_tool_gets_no_filler(call):
    live, tools, service = call
    with connect() as ws:
        sock = Socket(ws)
        greet(live, sock)
        live.push(fx.heard("One litre of milk, that's all."))
        live.push(fx.tool_call("build_quote", {"lines": []}))
        sock.next("agent_state", state="thinking")
        sock.hang_up()
    assert not any(extra.get("filler") for _, _, extra in service.said)


def test_the_filler_follows_the_callers_language(call):
    live, tools, service = call
    tools.delay = 0.6
    with connect() as ws:
        sock = Socket(ws)
        greet(live, sock)
        live.push(fx.heard("I need five kilos of ground beef, that's all please."))
        live.push(fx.tool_call("build_quote", {"lines": []}))
        caption = sock.next("transcript", who="agent")
        sock.next("agent_state", state="thinking")
        sock.hang_up()
    assert caption["text"] == filler.TEXT["en"]


def test_request_confirmation_is_refused_until_the_caller_answers(call):
    live, tools, service = call
    with connect() as ws:
        sock = Socket(ws)
        greet(live, sock)
        live.push(fx.heard("Siinä kaikki."))
        live.push(fx.tool_call("build_quote", {"lines": []}, "q"))
        live.wait_for(lambda: len(live.tool_responses) == 1)
        # The model asks for the link in the same turn, without waiting for a yes.
        live.push(fx.tool_call("request_confirmation", {"quote_id": "q-1"}, "r1"))
        live.wait_for(lambda: len(live.tool_responses) == 2, timeout=5)
        refused = live.tool_responses[1].response
        # After the caller's yes it goes through.
        live.push(fx.heard("Kyllä, lähetä."))
        live.push(fx.tool_call("request_confirmation", {"quote_id": "q-1"}, "r2"))
        live.wait_for(lambda: len(live.tool_responses) == 3)
        ended = sock.hang_up()

    assert "error" in refused and "Ask whether to send" in refused["error"]
    assert [name for name, _ in tools.calls] == ["build_quote", "request_confirmation"]
    assert service.local_tools == [("request_confirmation", refused)]
    assert live.tool_responses[2].response["output"]["delivery_status"] == "held"
    assert ended["inbox"] is True


def test_a_yes_whose_caption_trails_the_tool_call_still_counts(call):
    live, tools, _ = call
    with connect() as ws:
        sock = Socket(ws)
        greet(live, sock)
        live.push(fx.heard("Siinä kaikki."))
        live.push(fx.tool_call("build_quote", {"lines": []}))
        live.wait_for(lambda: len(live.tool_responses) == 1)
        live.push(fx.tool_call("request_confirmation", {"quote_id": "q-1"}))
        time.sleep(0.3)
        live.push(fx.heard("Joo."))
        live.wait_for(lambda: len(live.tool_responses) == 2)
        sock.hang_up()
    assert "output" in live.tool_responses[1].response


# --- A call without a voice (#98) -------------------------------------------------------


def test_a_typed_line_goes_to_gemini_and_counts_as_the_caller_speaking(call):
    live, _, service = call
    with connect() as ws:
        sock = Socket(ws)
        greet(live, sock)
        sock.say("  Tarvitsen 20 litraa\n maitoa.  ")
        caption = sock.next("transcript", who="buyer", final=True)
        live.wait_for(lambda: "Tarvitsen 20 litraa maitoa." in live.texts())
        sock.say("   ")  # nothing to say: ignored
        sock.hang_up()

    assert caption["text"] == "Tarvitsen 20 litraa maitoa."
    assert ("thinking", None) in sock.states()
    assert [(who, text) for who, text, _ in service.said if who == "buyer"] == [
        ("buyer", "Tarvitsen 20 litraa maitoa.")
    ]
    assert live.texts() == [CALL_CONNECTED, "Tarvitsen 20 litraa maitoa."]
    assert live.audio_frames() == 0


def test_a_typed_yes_lets_request_confirmation_through(call):
    live, tools, _ = call
    with connect() as ws:
        sock = Socket(ws)
        greet(live, sock)
        sock.say("Siinä kaikki.")
        sock.next("transcript", who="buyer", final=True)
        live.push(fx.tool_call("build_quote", {"lines": []}, "q"))
        live.wait_for(lambda: len(live.tool_responses) == 1)
        # No answer since the quote: refused, as on a spoken call.
        live.push(fx.tool_call("request_confirmation", {"quote_id": "q-1"}, "r1"))
        live.wait_for(lambda: len(live.tool_responses) == 2, timeout=5)
        sock.say("Kyllä, lähetä.")
        sock.next("transcript", who="buyer", final=True)
        live.push(fx.tool_call("request_confirmation", {"quote_id": "q-1"}, "r2"))
        live.wait_for(lambda: len(live.tool_responses) == 3)
        ended = sock.hang_up()

    assert "error" in live.tool_responses[1].response
    assert live.tool_responses[2].response["output"]["delivery_status"] == "held"
    assert [name for name, _ in tools.calls] == ["build_quote", "request_confirmation"]
    assert ended["inbox"] is True


def test_a_live_tests_run_and_case_are_bound_for_the_call(call, monkeypatch):
    live, tools, _ = call
    seen: list[dict[str, str]] = []

    def open_tools(token: str):
        seen.append(telemetry.test_headers())  # what the MCP bridge would send along
        return tools.open(token)

    monkeypatch.setattr(relay, "open_tools", open_tools)
    stamp = {"X-Simo-Test-Run": "demo-script-1", "X-Simo-Test-Case": "call-order-fi"}
    with connect(headers=stamp) as ws:
        sock = Socket(ws)
        greet(live, sock)
        sock.hang_up()
    with connect() as ws:
        sock = Socket(ws)
        sock.next("ready")
        sock.hang_up()

    assert seen == [
        {"x-simo-test-run": "demo-script-1", "x-simo-test-case": "call-order-fi"},
        {},
    ]


# --- Ending the call --------------------------------------------------------------------


def test_hang_up_releases_the_link_and_never_sends_it(call):
    live, tools, service = call
    with connect() as ws:
        sock = Socket(ws)
        greet(live, sock)
        live.push(fx.heard("Kyllä."))
        live.push(fx.tool_call("request_confirmation", {"quote_id": "q-1"}))
        live.wait_for(lambda: len(live.tool_responses) == 1)
        ended = sock.hang_up()

    assert ended["type"] == "ended"
    assert ended["ended_by"] == "visitor"
    assert ended["quote_id"] == "q-1" and ended["total_cents"] == 4190
    assert ended["delivery_status"] == "off" and ended["inbox"] is True
    assert set(ended) == {
        "type",
        "duration_s",
        "ended_by",
        "quote_id",
        "total_cents",
        "delivery_status",
        "inbox",
        "link_pending",
        "session_id",
    }
    assert ended["link_pending"] is False
    assert ended["session_id"] == str(fx.SESSION_ID)
    assert service.ended[0]["ended_by"] == "visitor"
    assert all(fx.LINK_LIKE not in text and fx.TOKEN not in text for text in sock.raw_texts)
    assert live.closed.is_set() and tools.closed.is_set()


def test_a_call_without_a_yes_ends_with_nothing_sent(call):
    live, _, _ = call
    with connect() as ws:
        sock = Socket(ws)
        greet(live, sock)
        ended = sock.hang_up()
    assert ended["inbox"] is False and ended["delivery_status"] == "none"
    assert ended["quote_id"] is None and ended["total_cents"] is None
    assert ended["link_pending"] is False


def test_a_link_still_on_its_way_at_hang_up_is_pending(call, monkeypatch):
    # #88: the relay stops waiting for a slow request_confirmation, whose link the
    # server then delivers after the call; the call screen keeps waiting for it.
    live, tools, _ = call
    monkeypatch.setattr(relay, "PENDING_TOOLS_S", 0.1)
    with connect() as ws:
        sock = Socket(ws)
        greet(live, sock)
        live.push(fx.heard("Kyllä."))
        tools.delay = 5.0
        live.push(fx.tool_call("request_confirmation", {"quote_id": "q-1"}))
        live.wait_for(lambda: len(tools.calls) == 1)
        ended = sock.hang_up()
    assert ended["inbox"] is False and ended["delivery_status"] == "none"
    assert ended["link_pending"] is True


def test_a_dropped_socket_still_releases(call):
    live, tools, service = call
    with connect() as ws:
        sock = Socket(ws)
        greet(live, sock)
        live.push(fx.heard("Kyllä."))
        live.push(fx.tool_call("request_confirmation", {"quote_id": "q-1"}))
        live.wait_for(lambda: len(live.tool_responses) == 1)
    assert service.end_called.wait(5)
    assert service.ended[0]["ended_by"] == "dropped"
    assert tools.held is False  # released


def test_a_lost_gemini_session_ends_as_dropped(call):
    live, _, service = call
    with connect() as ws:
        sock = Socket(ws)
        greet(live, sock)
        live.push(ConnectionError("gone"))
        ended = sock.next("ended")
    assert ended["ended_by"] == "dropped"


def test_the_time_limit_warns_then_ends(call, monkeypatch):
    live, tools, service = call
    monkeypatch.setattr(
        relay, "call_limits", lambda: relay.Limits(max_call_s=0.6, warn_before_s=0.3)
    )
    with connect() as ws:
        sock = Socket(ws)
        sock.next("ready")
        live.push(fx.heard("Kyllä."))
        live.push(fx.tool_call("request_confirmation", {"quote_id": "q-1"}))
        ended = sock.next("ended")
    assert relay.ONE_MINUTE_LEFT in live.texts()
    assert live.texts().index(relay.ONE_MINUTE_LEFT) == 1  # after the greeting cue
    assert ended["ended_by"] == "time_limit"
    assert ended["inbox"] is True


def test_end_call_waits_for_the_goodbye_to_play(call):
    live, _, service = call
    with connect() as ws:
        sock = Socket(ws)
        greet(live, sock)
        goodbye = b"\x01\x00" * 24000  # one second
        live.push(fx.said("Hei hei!"))
        live.push(fx.audio(goodbye))
        live.push(fx.tool_call(END_CALL))
        started = time.monotonic()
        ended = sock.next("ended")
        waited = time.monotonic() - started
    assert ended["ended_by"] == "agent"
    assert waited >= 0.9
    assert (END_CALL, {"ok": True}) in service.local_tools
    assert not live.tool_responses  # Gemini gets no answer, so it says nothing more
    assert service.log[-2:] == ["agent_said: Hei hei!", f"tool: {END_CALL}"]


def test_a_call_reports_its_turns_interruptions_and_summary(call, caplog):
    # Application Insights (#84): one event per reply with its latency, one per
    # interruption, and a summary when the call ends.
    import logging
    import time

    caplog.set_level(logging.INFO, logger="simo.events")
    live, _, _ = call
    with connect() as ws:
        sock = Socket(ws)
        sock.next("ready")
        live.push(fx.said("Hei!"))
        live.push(fx.audio())
        live.push(fx.generation_complete())
        sock.next("agent_state", state="listening")
        live.push(fx.heard("Tarvitsen maitoa."))
        sock.next("agent_state", state="thinking")
        live.push(fx.said("Selvä,"))
        live.push(fx.audio())
        live.push(fx.interrupted())
        sock.next("interrupted")
        sock.hang_up()

    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and not any(
        r.getMessage() == "voice call ended" for r in caplog.records
    ):
        time.sleep(0.05)
    events = {r.getMessage(): r.__dict__ for r in caplog.records if r.name == "simo.events"}
    assert int(events["voice turn"]["simo.latency_ms"]) >= 0
    assert "voice interrupted" in events
    ended = events["voice call ended"]
    assert ended["simo.turns"] == "1" and ended["simo.interruptions"] == "1"
