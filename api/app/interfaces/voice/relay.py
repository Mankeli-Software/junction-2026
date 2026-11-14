"""One phone call: the browser's `/voice/ws` socket on one side, Gemini Live on the other,
our MCP server for the tools (#52, technical-plan.md §7.1 and §9.3).

Tasks per call, all in this process (sessions are held in memory, §7.1):

- **up**: browser to Gemini. Binary frames are 16 kHz PCM from the microphone; the JSON
  messages are `hangup` and `say`, a caller's line as text. The live tests (#98) use `say`
  to play a call without a voice: the line goes to Gemini as text and counts as the caller
  speaking, with its caption and its `buyer_said`.
- **down**: Gemini to the browser. 24 kHz PCM, `transcript`, `interrupted` and
  `agent_state`; tool calls start a task each.
- **tools**: one task per tool call, through MCP with the call's bearer token. Calls are
  blocking (#51: non-blocking calls left the agent silent anyway). A call still running
  after about a second gets the filler line (`filler.py`).
- **clock**: the one-minute warning and the time limit (policy.yaml `max_call_seconds`).
- **log**: writes `buyer_said` and `agent_said` in order, off the audio path.

The call ends on `hangup` (visitor), `end_call` once the goodbye has played (agent), the
time limit (time_limit), or a lost browser or Gemini connection (dropped). Every end
releases the held confirmation link and ends the session (`voice_calls.end_call`), then
sends `ended` if the browser is still there. The link itself never goes on this socket.
"""

import asyncio
import json
import logging
import time
import uuid
from collections.abc import Awaitable, Callable, Mapping
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Any

from google.genai import types
from starlette.websockets import WebSocket, WebSocketDisconnect, WebSocketState

from app import telemetry
from app.agent import CALL_CONNECTED, END_CALL, PROMPT_VERSION, build_system_prompt
from app.db import get_sessionmaker
from app.interfaces.voice import bridge, filler, live
from app.interfaces.voice.text import Utterance, guess_language
from app.services import voice_calls
from app.services.policy import get_rule_set
from app.settings import get_settings

log = logging.getLogger(__name__)

CLOSE_NO_SESSION = 4401
CLOSE_LIMIT = 4429
CLOSE_UNAVAILABLE = 1011

QUOTE_TOOLS = frozenset({"build_quote", "update_quote"})
REQUEST_CONFIRMATION = "request_confirmation"

# The caller's yes can reach the relay as a caption a moment after Gemini's tool call.
CAPTION_GRACE_S = 1.5
# After `end_call`: wait for this much quiet from Gemini, then for the browser to finish
# playing, with a cap so a call always ends.
GOODBYE_QUIET_S = 0.8
GOODBYE_MAX_S = 15.0
PLAYBACK_MARGIN_S = 0.4
# Two tool calls in a row get one filler line, not two.
FILLER_GAP_S = 4.0
# How long the end of a call waits for a request_confirmation still running.
PENDING_TOOLS_S = 2.0
# How long a tool call waits for the transcript log to catch up.
LOG_FLUSH_S = 2.0
CHUNK_BYTES = live.OUT_RATE * 2 // 10  # 100 ms of 24 kHz audio
# The longest typed caller line (`say`).
MAX_SAY_CHARS = 500

REFUSED_CONFIRMATION = (
    "Not sent: the caller has not answered since the latest quote. Ask whether to send "
    "the confirmation link to their phone, wait for a clear yes, and only then call "
    "request_confirmation again."
)
ONE_MINUTE_LEFT = (
    "[one minute left: this call ends automatically in one minute. Tell the caller in one "
    "short sentence, then carry on]"
)

# Calls in progress, one per user (decided 2026-11-14: a second socket gets 4429).
_live_calls: dict[uuid.UUID, "Call"] = {}

ToolsFactory = Callable[[str], AbstractAsyncContextManager[bridge.Tools]]


def _open_tools(token: str) -> AbstractAsyncContextManager[bridge.Tools]:
    return bridge.McpTools(get_settings().voice_mcp_url, token)


@dataclass
class Limits:
    max_call_s: float
    warn_before_s: float = 60.0


def call_limits() -> Limits:
    return Limits(max_call_s=get_rule_set().policy.max_call_seconds)


# Swapped out by the tests.
connect_gemini: live.Connect = live.connect
open_tools: ToolsFactory = _open_tools


def live_call_count() -> int:
    return len(_live_calls)


class Call:
    def __init__(
        self, ws: WebSocket, user_id: uuid.UUID, *, test_tags: Mapping[str, str] | None = None
    ) -> None:
        self.ws = ws
        self.user_id = user_id
        # A live test's run and case (`X-Simo-Test-Run`, #98), bound for the whole call.
        self.test_tags = dict(test_tags or {})
        self.settings = get_settings()
        self.limits = call_limits()
        self.start: voice_calls.CallStart | None = None
        self.session: live.LiveSession | None = None
        self.tools: bridge.Tools | None = None

        self.ended_by: str | None = None
        self.done = asyncio.Event()
        self.answered_at: float | None = None
        self.socket_gone = False
        self._send_lock = asyncio.Lock()
        # Audit writes in call order, off the audio path (transcripts, relay-answered tools).
        self._log_queue: asyncio.Queue[Callable[[], Awaitable[None]]] = asyncio.Queue()
        self._tasks: set[asyncio.Task[Any]] = set()

        # What S.I.MO is doing (agent_state), sent only on change.
        self.state: str | None = None
        self.state_tool: str | None = None
        self.pending: dict[str, tuple[str, asyncio.Task[Any]]] = {}

        # Captions.
        self.buyer = Utterance()
        self.agent = Utterance()
        self.agent_open = False
        self.caller_lang: str | None = None
        self.buyer_utterances = 0
        self.buyer_spoke = asyncio.Event()
        self.quote_mark: int | None = None  # buyer_utterances when the latest quote came back
        # Measurements for Application Insights (#84).
        self.last_buyer_at: float | None = None  # the caller's latest transcribed words
        self.awaiting_reply = False  # the caller spoke and S.I.MO hasn't answered yet
        self.turns = 0
        self.interruptions = 0
        self.tokens: dict[str, int] = {"prompt": 0, "response": 0, "total": 0}

        # Audio down: when the browser will have played everything sent so far.
        self.play_until = 0.0
        self.turn_audio = False
        self.last_audio_at = 0.0
        self.last_filler_at = -FILLER_GAP_S
        self.ending = False
        # A request_confirmation still running when the call ended: its link may arrive later.
        self.link_pending = False

    # --- Running the call ---------------------------------------------------------------

    async def run(self) -> None:
        if self.user_id in _live_calls:
            await self.ws.close(CLOSE_LIMIT, "This number already has a call")
            return
        _live_calls[self.user_id] = self
        try:
            await self._run()
        finally:
            _live_calls.pop(self.user_id, None)

    async def _run(self) -> None:
        async with get_sessionmaker()() as db:
            self.start = await voice_calls.start_call(
                db, self.user_id, prompt_version=PROMPT_VERSION
            )
            vocabulary = await voice_calls.custom_vocabulary(db)
            await db.commit()  # the token must be in the database before /mcp sees it
        if self.start is None:
            await self.ws.close(CLOSE_NO_SESSION, "No demo account")
            return
        log.info("Call %s started for session %s", self.start.call_id, self.start.session_id)
        # Every span and log line of this call carries its ids (#84); tasks spawned inside
        # inherit them.
        with telemetry.bound(
            session_id=self.start.session_id,
            call_id=self.start.call_id,
            channel="phone",
            prompt_version=PROMPT_VERSION,
            voice_model=self.settings.voice_model,
            voice=self.settings.voice_name,
            **self.test_tags,
        ):
            try:
                async with open_tools(self.start.token) as tools:
                    self.tools = tools
                    declarations = bridge.declarations(await tools.list_tools())
                    config = live.connect_config(
                        system_prompt=build_system_prompt(
                            self.start.context,
                            "phone",
                            get_rule_set().policy.call_language,
                            today=voice_calls.business_date(),
                        ),
                        declarations=declarations,
                        vocabulary=vocabulary,
                        voice=self.settings.voice_name,
                        silence_ms=self.settings.voice_silence_ms,
                    )
                    async with connect_gemini(self.settings.voice_model, config) as session:
                        self.session = session
                        await self._converse()
            except Exception as error:
                if live.is_rate_limit(error):
                    log.error("Gemini rate limit (429) on call %s", self.start.call_id)
                else:
                    log.exception("Call %s failed", self.start.call_id)
                self._request_end("dropped")
            finally:
                # Shielded: even if this handler is cancelled, the link is released.
                await asyncio.shield(asyncio.ensure_future(self._finish()))

    async def _finish(self) -> None:
        await self._cancel_tasks()
        await self._end()

    async def _converse(self) -> None:
        assert self.session is not None
        self.answered_at = time.monotonic()
        await self._send_json({"type": "ready"})
        await self._set_state("listening")
        # S.I.MO greets first (#53).
        await self.session.send_realtime_input(text=CALL_CONNECTED)
        for coroutine in (self._up(), self._down(), self._clock(), self._log_writer()):
            self._spawn(coroutine)
        await self.done.wait()
        # A request_confirmation in flight may finish first, so its held link is there to
        # release and the `ended` message can say so. Short: the page stops waiting for
        # `ended` 3 s after its hang-up. One that finishes on the server after the release
        # delivers its link at once (#88, `confirmations.call_in_progress`).
        running = [task for name, task in self.pending.values() if name == REQUEST_CONFIRMATION]
        if running:
            _, still_running = await asyncio.wait(running, timeout=PENDING_TOOLS_S)
            self.link_pending = bool(still_running)
        # Let the log task finish its write, so no transcript line is cut off.
        await self._log_flushed()
        await self._cancel_tasks()

    def _spawn(self, coroutine: Any) -> asyncio.Task[Any]:
        task = asyncio.create_task(coroutine)
        self._tasks.add(task)
        task.add_done_callback(self._task_done)
        return task

    def _task_done(self, task: asyncio.Task[Any]) -> None:
        self._tasks.discard(task)
        if not task.cancelled() and task.exception() is not None:
            log.error("Call task failed", exc_info=task.exception())

    def _request_end(self, ended_by: str) -> None:
        if self.ended_by is None:
            self.ended_by = ended_by
        self.done.set()

    async def _cancel_tasks(self) -> None:
        current = asyncio.current_task()
        tasks = [t for t in self._tasks if t is not current and not t.done()]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _end(self) -> None:
        """Release the link, end the session, then tell the browser and close."""
        assert self.start is not None
        ended_by = self.ended_by or "dropped"
        duration = round(time.monotonic() - self.answered_at) if self.answered_at else 0
        # The open captions go into the log too.
        await self._close_buyer()
        await self._close_agent()
        await self._drain_log()
        end: voice_calls.CallEnd | None = None
        try:
            async with get_sessionmaker()() as db:
                end = await voice_calls.end_call(
                    db,
                    self.user_id,
                    self.start.session_id,
                    ended_by=ended_by,
                    duration_s=duration,
                )
                await db.commit()
        except Exception:
            log.exception("Ending call %s failed", self.start.call_id)
        telemetry.event(
            "voice call ended",
            ended_by=ended_by,
            duration_s=duration,
            turns=self.turns,
            interruptions=self.interruptions,
            buyer_utterances=self.buyer_utterances,
            prompt_tokens=self.tokens["prompt"],
            response_tokens=self.tokens["response"],
            total_tokens=self.tokens["total"],
        )
        log.info(
            "Call %s ended by %s after %d s; released %s",
            self.start.call_id,
            ended_by,
            duration,
            end.released_quote_ids if end else "nothing (error)",
        )
        if self.answered_at is None:
            # Never answered: the page is still connecting and shows "could not connect".
            await self._close(CLOSE_UNAVAILABLE, "The call could not start")
            return
        released = bool(end and end.released_quote_ids)
        await self._send_json(
            {
                "type": "ended",
                "duration_s": duration,
                "ended_by": ended_by,
                "quote_id": end.quote_id if end else None,
                "total_cents": end.total_cents if end else None,
                # Twilio is off for now (#46), so a delivered link is `off`.
                "delivery_status": "off" if released else "none",
                "inbox": released,
                # The call screen keeps waiting for the link instead of saying no order.
                "link_pending": self.link_pending and not released,
                # Public on the dashboard already; the live tests read the call back by it.
                "session_id": str(self.start.session_id),
            }
        )
        await self._close(1000, "Call ended")

    # --- Browser to Gemini --------------------------------------------------------------

    async def _up(self) -> None:
        assert self.session is not None
        try:
            while True:
                message = await self.ws.receive()
                if message["type"] == "websocket.disconnect":
                    raise WebSocketDisconnect(message.get("code", 1000))
                if message.get("bytes") is not None:
                    if not self.ending:
                        await self.session.send_realtime_input(
                            audio=live.audio_blob(message["bytes"])
                        )
                elif message.get("text") is not None:
                    try:
                        data = json.loads(message["text"])
                    except ValueError:
                        continue
                    if not isinstance(data, dict):
                        continue
                    if data.get("type") == "hangup":
                        self._request_end("visitor")
                        return
                    if data.get("type") == "say" and isinstance(data.get("text"), str):
                        await self._on_typed_line(data["text"])
        except WebSocketDisconnect:
            self.socket_gone = True
            self._request_end("dropped")
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Sending audio to Gemini failed")
            self._request_end("dropped")

    # --- Gemini to the browser ----------------------------------------------------------

    async def _down(self) -> None:
        assert self.session is not None
        try:
            while not self.done.is_set():
                received = 0
                async for message in self.session.receive():
                    received += 1
                    await self._on_message(message)
                if received == 0:
                    raise ConnectionError("the Gemini session closed")
        except asyncio.CancelledError:
            raise
        except Exception as error:
            if live.is_rate_limit(error):
                log.error("Gemini rate limit (429) during a call")
            else:
                log.warning("Gemini session ended: %s", error)
            self._request_end("dropped")

    async def _on_message(self, message: types.LiveServerMessage) -> None:
        if message.go_away is not None:
            log.warning("Gemini go_away: %s left", message.go_away.time_left)
        if (usage := message.usage_metadata) is not None:
            for key in self.tokens:
                self.tokens[key] += getattr(usage, f"{key}_token_count", None) or 0
        if message.tool_call_cancellation is not None:
            for call_id in message.tool_call_cancellation.ids or []:
                pending = self.pending.pop(call_id, None)
                if pending is not None:
                    pending[1].cancel()
        if message.tool_call is not None:
            for call in message.tool_call.function_calls or []:
                await self._on_tool_call(call)
        content = message.server_content
        if content is None:
            return
        if content.input_transcription and content.input_transcription.text:
            await self._on_buyer_text(content.input_transcription.text)
        if content.model_turn:
            for part in content.model_turn.parts or []:
                if part.inline_data and part.inline_data.data:
                    await self._on_agent_audio(part.inline_data.data)
        if content.output_transcription and content.output_transcription.text:
            await self._close_buyer()
            delta = self.agent.add(content.output_transcription.text)
            if delta:
                self.agent_open = True
                await self._send_json(
                    {"type": "transcript", "who": "agent", "text": delta, "final": False}
                )
        if content.interrupted:
            self.interruptions += 1
            telemetry.event("voice interrupted", turn=self.turns)
            await self._send_json({"type": "interrupted"})
            self.play_until = time.monotonic()
            self.turn_audio = False
            await self._close_agent()
            await self._set_state("listening")
        if content.generation_complete or content.turn_complete:
            # #51: generation_complete marks the end of the agent's turn; turn_complete comes
            # about one reply later and only closes what is still open.
            await self._close_buyer()
            await self._close_agent()
            self.turn_audio = False
            if not self.pending and not self.ending:
                await self._set_state("listening")

    async def _on_buyer_text(self, piece: str) -> None:
        if not self.buyer:
            self.buyer_utterances += 1
        self.buyer_spoke.set()
        self.last_buyer_at = time.monotonic()
        self.awaiting_reply = True
        delta = self.buyer.add(piece)
        if delta:
            await self._send_json(
                {"type": "transcript", "who": "buyer", "text": delta, "final": False}
            )
        if self.state == "listening":
            await self._set_state("thinking")

    async def _on_typed_line(self, line: str) -> None:
        """A caller's line as text (`say`). Gemini sends no transcription for text, so the
        relay counts it as the caller speaking itself."""
        assert self.session is not None
        text = " ".join(line.split())[:MAX_SAY_CHARS]
        if not text or self.ending:
            return
        await self._close_buyer()
        await self._on_buyer_text(text)
        await self._close_buyer()
        await self.session.send_realtime_input(text=text)

    async def _on_agent_audio(self, pcm: bytes) -> None:
        await self._close_buyer()
        now = time.monotonic()
        self.last_audio_at = now
        if not self.turn_audio:
            self.turn_audio = True
            if self.awaiting_reply and self.last_buyer_at is not None:
                # From the caller's last transcribed words (Gemini doesn't say exactly when
                # speech ended) to the first audio of the reply.
                latency = round((now - self.last_buyer_at) * 1000)
                self.awaiting_reply = False
                self.turns += 1
                telemetry.turn_latency.record(latency, telemetry.metric_attrs())
                telemetry.event("voice turn", turn=self.turns, latency_ms=latency)
            if not self.pending:
                await self._set_state("speaking")
        await self._send_audio(pcm)

    async def _send_audio(self, pcm: bytes) -> None:
        now = time.monotonic()
        self.play_until = max(self.play_until, now) + len(pcm) / 2 / live.OUT_RATE
        await self._send_bytes(pcm)

    # --- Captions and the transcript log ------------------------------------------------

    async def _close_buyer(self) -> None:
        if not self.buyer:
            return
        text = self.buyer.close()
        if not text:
            return
        lang = guess_language(text)
        if lang:
            self.caller_lang = lang
        await self._send_json({"type": "transcript", "who": "buyer", "text": text, "final": True})
        self._log("buyer", text, {"lang": lang})

    async def _close_agent(self) -> None:
        text = self.agent.close()
        if not self.agent_open and not text:
            return
        self.agent_open = False
        await self._send_json({"type": "transcript", "who": "agent", "text": text, "final": True})
        if text:
            assert self.start is not None
            self._log("agent", text, {"lang": self.caller_lang or self.start.caller.lang})

    def _log(self, who: str, text: str, extra: dict[str, Any]) -> None:
        self._log_queue.put_nowait(lambda: self._write_said(who, text, extra))

    async def _log_writer(self) -> None:
        while True:
            write = await self._log_queue.get()
            try:
                await write()
            finally:
                self._log_queue.task_done()

    async def _log_flushed(self) -> None:
        """Waits until the log is written, so a tool's own events come after the caption
        that led to it."""
        try:
            await asyncio.wait_for(self._log_queue.join(), LOG_FLUSH_S)
        except TimeoutError:
            log.warning("The transcript log is behind")

    async def _write_said(self, who: str, text: str, extra: dict[str, Any]) -> None:
        assert self.start is not None
        try:
            async with get_sessionmaker()() as db:
                await voice_calls.record_said(db, self.start.session_id, who, text, **extra)
                await db.commit()
        except Exception:
            log.exception("Writing %s_said failed", who)

    async def _drain_log(self) -> None:
        """Writes what the log task had not written yet (it is cancelled by now)."""
        while not self._log_queue.empty():
            write = self._log_queue.get_nowait()
            await write()
            self._log_queue.task_done()

    # --- Tools --------------------------------------------------------------------------

    async def _on_tool_call(self, call: types.FunctionCall) -> None:
        await self._close_buyer()
        await self._close_agent()
        name = call.name or ""
        call_id = call.id or uuid.uuid4().hex
        if name == END_CALL:
            await self._on_end_call(call_id)
            return
        self.turn_audio = False
        task = self._spawn(self._run_tool(call_id, name, dict(call.args or {})))
        self.pending[call_id] = (name, task)
        await self._set_state("working", name)

    async def _run_tool(self, call_id: str, name: str, arguments: dict[str, Any]) -> None:
        """The tool round trip as the caller lives it, from Gemini's call to its answer (#84)."""
        timer = telemetry.Timer()
        with telemetry.span(f"voice tool {name}", arguments=telemetry.summary(arguments)):
            response = await self._run_tool_inner(call_id, name, arguments)
            result = _tool_result_attributes(response)
            telemetry.annotate(round_trip_ms=timer.ms, **result)
        telemetry.event(f"voice tool {name}", round_trip_ms=timer.ms, **result)

    async def _run_tool_inner(
        self, call_id: str, name: str, arguments: dict[str, Any]
    ) -> dict[str, Any] | None:
        assert self.tools is not None and self.session is not None
        filler_task = self._spawn(self._filler_after(time.monotonic()))
        try:
            if name == REQUEST_CONFIRMATION and not await self._caller_answered():
                response: dict[str, Any] = {"error": REFUSED_CONFIRMATION}
                self._record_local_tool(name, arguments, response)
            else:
                await self._log_flushed()
                response = await self.tools.call_tool(name, arguments)
            if name in QUOTE_TOOLS and "output" in response:
                self.quote_mark = self.buyer_utterances
        finally:
            filler_task.cancel()
        if self.pending.pop(call_id, None) is None:
            return None  # cancelled by Gemini meanwhile
        await self.session.send_tool_response(
            function_responses=[types.FunctionResponse(id=call_id, name=name, response=response)]
        )
        if self.pending:
            await self._set_state("working", next(iter(self.pending.values()))[0])
        else:
            await self._set_state("thinking")  # the result went back; no audio yet
        return response

    async def _caller_answered(self) -> bool:
        """The caller has spoken since the latest quote (#53: the link only after a yes,
        enforced in code). Their caption may trail the tool call, so wait a moment for it."""
        if self.quote_mark is None or self.buyer_utterances > self.quote_mark:
            return True
        deadline = time.monotonic() + CAPTION_GRACE_S
        while self.buyer_utterances <= self.quote_mark:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            self.buyer_spoke.clear()
            try:
                await asyncio.wait_for(self.buyer_spoke.wait(), remaining)
            except TimeoutError:
                return False
        return True

    async def _filler_after(self, started: float) -> None:
        """The filler line, once the tool has run and the line has been quiet for a while."""
        wait = self.settings.voice_filler_after_s
        while True:
            due = max(started, self.play_until) + wait
            delay = due - time.monotonic()
            if delay <= 0:
                break
            await asyncio.sleep(delay)
        now = time.monotonic()
        if self.ending or now - self.last_filler_at < FILLER_GAP_S:
            return
        assert self.start is not None
        lang = self.caller_lang or self.start.caller.lang
        pcm = filler.clip(self.settings.voice_name, lang)
        if pcm is None:
            return
        self.last_filler_at = now
        text = filler.TEXT[lang]
        await self._send_json({"type": "transcript", "who": "agent", "text": text, "final": True})
        for offset in range(0, len(pcm), CHUNK_BYTES):
            await self._send_audio(pcm[offset : offset + CHUNK_BYTES])
        self._log("agent", text, {"lang": lang, "filler": True})

    async def _on_end_call(self, call_id: str) -> None:
        """`end_call`: let the goodbye finish playing, then hang up (#53). No response goes
        back, so Gemini says nothing more."""
        if self.ending:
            return
        self.ending = True
        self._record_local_tool(END_CALL, {}, {"ok": True})
        self._spawn(self._end_after_goodbye())

    async def _end_after_goodbye(self) -> None:
        cap = time.monotonic() + GOODBYE_MAX_S
        while time.monotonic() < cap:
            now = time.monotonic()
            quiet = now - self.last_audio_at >= GOODBYE_QUIET_S
            played = now >= self.play_until + PLAYBACK_MARGIN_S
            if quiet and played:
                break
            await asyncio.sleep(0.1)
        self._request_end("agent")

    def _record_local_tool(
        self, name: str, arguments: dict[str, Any], response: dict[str, Any]
    ) -> None:
        self._log_queue.put_nowait(lambda: self._write_local_tool(name, arguments, response))

    async def _write_local_tool(
        self, name: str, arguments: dict[str, Any], response: dict[str, Any]
    ) -> None:
        assert self.start is not None
        try:
            async with get_sessionmaker()() as db:
                await voice_calls.record_local_tool(
                    db, self.start.session_id, name, arguments, response
                )
                await db.commit()
        except Exception:
            log.exception("Recording %s failed", name)

    # --- Clock --------------------------------------------------------------------------

    async def _clock(self) -> None:
        assert self.session is not None
        warn_at = self.limits.max_call_s - self.limits.warn_before_s
        if warn_at > 0:
            await asyncio.sleep(warn_at)
            try:
                await self.session.send_realtime_input(text=ONE_MINUTE_LEFT)
            except Exception:
                log.exception("Sending the one-minute warning failed")
        await asyncio.sleep(self.limits.max_call_s - max(warn_at, 0))
        self._request_end("time_limit")

    # --- Sending to the browser ---------------------------------------------------------

    async def _set_state(self, state: str, tool: str | None = None) -> None:
        if state == self.state and tool == self.state_tool:
            return
        self.state, self.state_tool = state, tool
        await self._send_json({"type": "agent_state", "state": state, "tool": tool})

    async def _send_json(self, message: dict[str, Any]) -> None:
        await self._send({"type": "websocket.send", "text": json.dumps(message)})

    async def _send_bytes(self, data: bytes) -> None:
        await self._send({"type": "websocket.send", "bytes": data})

    async def _send(self, message: dict[str, Any]) -> None:
        if self.socket_gone or self.ws.application_state != WebSocketState.CONNECTED:
            return
        async with self._send_lock:
            try:
                await self.ws.send(message)
            except Exception:
                self.socket_gone = True
                self._request_end("dropped")

    async def _close(self, code: int, reason: str) -> None:
        if self.socket_gone or self.ws.application_state != WebSocketState.CONNECTED:
            return
        try:
            await self.ws.close(code, reason)
        except Exception:
            pass


def _tool_result_attributes(response: dict[str, Any] | None) -> dict[str, Any]:
    """A bounded, non-content summary of the MCP result for the phone tool span."""
    if response is None:
        return {"mcp_outcome": "cancelled"}
    if "error" in response:
        return {"mcp_outcome": "error"}

    output = response.get("output")
    if not isinstance(output, dict):
        return {"mcp_outcome": "ok"}

    attributes: dict[str, Any] = {"mcp_outcome": "ok"}
    decision = output.get("decision")
    if isinstance(decision, str):
        attributes["quote_decision"] = decision[:40]

    for field, attribute in (
        ("lines", "quote_line_count"),
        ("flags", "quote_flag_count"),
        ("rejections", "quote_rejection_count"),
        ("not_ordered", "quote_not_ordered_count"),
    ):
        value = output.get(field)
        if isinstance(value, list):
            attributes[attribute] = len(value)

    rejections = output.get("rejections")
    if isinstance(rejections, list):
        codes = sorted(
            {
                rejection["reason_code"][:80]
                for rejection in rejections
                if isinstance(rejection, dict) and isinstance(rejection.get("reason_code"), str)
            }
        )
        if codes:
            attributes["quote_rejection_codes"] = ",".join(codes)[:200]
    return attributes
