"""One Live API turn: stream user audio in real time, collect everything that comes back.

Used by run_live.py, function_call.py and record_mic.py. Times are seconds on the
monotonic clock, reported relative to the moment the last speech chunk was sent
("end of user audio"), which is what the caller perceives as "I stopped talking".
After the speech we keep sending silence, as a real microphone would, so the
server's automatic voice activity detection decides when the turn ended. The
measured latency therefore includes VAD end-of-speech detection.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

import numpy as np
from google.genai import types

from common import IN_RATE, custom_vocabulary, system_instruction

# --- Tool declaration used by the spike -------------------------------------------


def build_quote_declaration(non_blocking: bool = False) -> types.FunctionDeclaration:
    """Simplified stand-in for the MCP build_quote tool (technical-plan.md 9.1)."""
    return types.FunctionDeclaration(
        name="build_quote",
        description=(
            "Builds a quote from the caller's order lines. Call it once the caller has said what they want. "
            "Pass the product as the caller said it (in Finnish), the quantity as a number and the unit the "
            "caller used (e.g. laatikko, litra, kilo, paketti, purkki, sanko). Also pass the delivery day if given."
        ),
        parameters_json_schema={
            "type": "object",
            "properties": {
                "lines": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "product_query": {"type": "string", "description": "Product as the caller said it"},
                            "quantity": {"type": "number"},
                            "unit": {"type": "string", "description": "Unit the caller used, in Finnish"},
                        },
                        "required": ["product_query", "quantity", "unit"],
                    },
                },
                "delivery_day": {"type": "string", "description": "Requested delivery day, if any"},
            },
            "required": ["lines"],
        },
        behavior=types.Behavior.NON_BLOCKING if non_blocking else None,
    )


def stub_quote_result(args: dict[str, Any]) -> dict[str, Any]:
    """A fake engine result: echo the lines with a made-up product name and price."""
    lines = []
    total = 0.0
    for i, line in enumerate(args.get("lines", []) or []):
        qty = float(line.get("quantity") or 0)
        price = 4.85 + i
        total += qty * price
        lines.append(
            {
                "asked": line.get("product_query"),
                "added": f"Valio {line.get('product_query', '').strip()} (testituote)",
                "quantity": qty,
                "unit": line.get("unit"),
                "unit_price_eur": price,
            }
        )
    return {
        "quote_id": "Q-SPIKE-1",
        "lines": lines,
        "total_eur": round(total, 2),
        "say": "Tarjous on valmis. Kerro soittajalle rivit ja kokonaishinta lyhyesti ja kysy, lähetetäänkö vahvistuslinkki.",
    }


# --- Connect config --------------------------------------------------------------


def live_config(
    *,
    voice: str | None = None,
    vocab: bool = False,
    lang_codes: list[str] | None = None,
    tools: list[types.FunctionDeclaration] | None = None,
    extra_instruction: str = "",
    silence_ms: int | None = None,
) -> types.LiveConnectConfig:
    transcription = types.AudioTranscriptionConfig(
        custom_vocabulary=custom_vocabulary() if vocab else None,
        language_codes=lang_codes or None,
    )
    cfg: dict[str, Any] = {
        "response_modalities": [types.Modality.AUDIO],
        "system_instruction": system_instruction(extra_instruction),
        "input_audio_transcription": transcription,
        "output_audio_transcription": types.AudioTranscriptionConfig(),
    }
    if voice:
        cfg["speech_config"] = types.SpeechConfig(
            voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice))
        )
    if tools:
        cfg["tools"] = [types.Tool(function_declarations=tools)]
    if silence_ms is not None:
        cfg["realtime_input_config"] = types.RealtimeInputConfig(
            automatic_activity_detection=types.AutomaticActivityDetection(silence_duration_ms=silence_ms)
        )
    return types.LiveConnectConfig(**cfg)


# --- One turn --------------------------------------------------------------------


@dataclass
class TurnResult:
    connect_s: float | None = None
    speech_s: float = 0.0
    input_text: str = ""
    interim_input_text: str = ""
    output_text: str = ""
    output_segments: list[tuple[float, str]] = field(default_factory=list)
    audio_out: bytearray = field(default_factory=bytearray)
    # Seconds after the end of user audio (negative = before it ended)
    first_input_transcript: float | None = None
    first_interim_transcript: float | None = None
    first_audio: float | None = None
    first_output_transcript: float | None = None
    first_tool_call: float | None = None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    tool_responses: list[dict[str, Any]] = field(default_factory=list)
    audio_while_tool_pending_bytes: int = 0
    interrupted: int = 0
    timed_out: bool = False
    error: str | None = None
    events: list[tuple[float, str, str]] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        d = {k: v for k, v in self.__dict__.items() if k not in ("audio_out", "events")}
        d["audio_out_s"] = round(len(self.audio_out) / 2 / 24_000, 2)
        d["events"] = [(round(t, 3), k, v) for t, k, v in self.events]
        return d


ToolHandler = Callable[["TurnState", types.FunctionCall], Awaitable[None]]


class TurnState:
    """Shared between the sender, the receiver and a tool handler."""

    def __init__(self, session, result: TurnResult):
        self.session = session
        self.result = result
        self.speech_end: float | None = None
        self.pending_tools = 0
        self.last_response_at: float | None = None
        self.done = asyncio.Event()

    def rel(self, t: float | None = None) -> float:
        t = time.monotonic() if t is None else t
        return t - self.speech_end if self.speech_end is not None else float("nan")

    def log(self, kind: str, detail: str = "") -> None:
        self.result.events.append((self.rel(), kind, detail))

    async def respond(self, response: types.FunctionResponse) -> None:
        await self.session.send_tool_response(function_responses=[response])
        self.pending_tools -= 1
        self.last_response_at = time.monotonic()
        self.result.tool_responses.append(
            {"at": round(self.rel(), 3), "name": response.name, "scheduling": str(response.scheduling or "")}
        )
        self.log("tool_response", f"{response.name} {response.scheduling or ''}")


async def _send_audio(state: TurnState, samples: np.ndarray, chunk_ms: int, trailing_s: float, stream_end: bool):
    session = state.session
    chunk = int(IN_RATE * chunk_ms / 1000)
    data = samples.astype("<i2")
    start = time.monotonic()
    i = 0
    for offset in range(0, len(data), chunk):
        piece = data[offset : offset + chunk]
        # Pace in real time: chunk i goes out when its audio would have been captured.
        delay = start + (i + 1) * chunk_ms / 1000 - time.monotonic()
        if delay > 0:
            await asyncio.sleep(delay)
        await session.send_realtime_input(
            audio=types.Blob(data=piece.tobytes(), mime_type=f"audio/pcm;rate={IN_RATE}")
        )
        i += 1
    state.speech_end = time.monotonic()
    state.log("speech_end")
    if stream_end:
        await session.send_realtime_input(audio_stream_end=True)
        state.log("audio_stream_end")
    silence = np.zeros(chunk, dtype="<i2").tobytes()
    t_end = time.monotonic() + trailing_s
    n = 0
    while not state.done.is_set() and time.monotonic() < t_end:
        n += 1
        delay = state.speech_end + n * chunk_ms / 1000 - time.monotonic()
        if delay > 0:
            await asyncio.sleep(delay)
        if not stream_end:
            await session.send_realtime_input(audio=types.Blob(data=silence, mime_type=f"audio/pcm;rate={IN_RATE}"))


async def _receive(state: TurnState, on_tool_call: ToolHandler | None):
    r = state.result
    session = state.session
    while not state.done.is_set():
        async for msg in session.receive():
            now = time.monotonic()
            if msg.tool_call:
                for fc in msg.tool_call.function_calls or []:
                    if r.first_tool_call is None:
                        r.first_tool_call = state.rel(now)
                    r.tool_calls.append({"at": round(state.rel(now), 3), "id": fc.id, "name": fc.name, "args": fc.args})
                    state.log("tool_call", f"{fc.name} {fc.args}")
                    state.pending_tools += 1
                    if on_tool_call:
                        asyncio.create_task(on_tool_call(state, fc))
            if msg.tool_call_cancellation:
                state.log("tool_call_cancellation", str(msg.tool_call_cancellation.ids))
            if msg.go_away:
                state.log("go_away", str(msg.go_away.time_left))
            sc = msg.server_content
            if not sc:
                continue
            if sc.interim_input_transcription and sc.interim_input_transcription.text:
                if r.first_interim_transcript is None:
                    r.first_interim_transcript = state.rel(now)
                r.interim_input_text = sc.interim_input_transcription.text
            if sc.input_transcription and sc.input_transcription.text:
                if r.first_input_transcript is None:
                    r.first_input_transcript = state.rel(now)
                    state.log("first_input_transcript")
                r.input_text += sc.input_transcription.text
            if sc.output_transcription and sc.output_transcription.text:
                if r.first_output_transcript is None:
                    r.first_output_transcript = state.rel(now)
                    state.log("first_output_transcript")
                r.output_text += sc.output_transcription.text
                r.output_segments.append((round(state.rel(now), 3), sc.output_transcription.text))
            if sc.model_turn:
                for part in sc.model_turn.parts or []:
                    if part.inline_data and part.inline_data.data:
                        if r.first_audio is None:
                            r.first_audio = state.rel(now)
                            state.log("first_audio")
                        if state.pending_tools > 0:
                            if r.audio_while_tool_pending_bytes == 0:
                                state.log("audio_while_tool_pending")
                            r.audio_while_tool_pending_bytes += len(part.inline_data.data)
                        r.audio_out.extend(part.inline_data.data)
                    if part.text:
                        state.log("text_part", part.text[:200])
            if sc.interrupted:
                r.interrupted += 1
                state.log("interrupted")
            if sc.generation_complete:
                state.log("generation_complete")
            if sc.turn_complete:
                state.log("turn_complete", f"status={sc.interaction_status} reason={sc.turn_complete_reason}")
                answered_after_tools = state.last_response_at is not None and now > state.last_response_at
                # On 3.8, turn_complete alone does not mean idle while async reasoning runs.
                idle = sc.interaction_status in (
                    None,
                    types.InteractionStatus.INTERACTION_STATUS_UNSPECIFIED,
                    types.InteractionStatus.IDLE,
                )
                if (
                    idle
                    and state.pending_tools <= 0
                    and r.audio_out
                    and (not r.tool_calls or answered_after_tools)
                ):
                    state.done.set()
                    return


async def run_turn(
    client,
    model: str,
    config: types.LiveConnectConfig,
    samples: np.ndarray,
    *,
    chunk_ms: int = 40,
    trailing_s: float = 25.0,
    timeout_s: float = 45.0,
    stream_end: bool = False,
    on_tool_call: ToolHandler | None = None,
) -> TurnResult:
    """Open a fresh session, speak `samples` (16 kHz int16) and wait for the full reply."""
    result = TurnResult(speech_s=len(samples) / IN_RATE)
    t0 = time.monotonic()
    try:
        async with client.aio.live.connect(model=model, config=config) as session:
            result.connect_s = time.monotonic() - t0
            state = TurnState(session, result)
            sender = asyncio.create_task(_send_audio(state, samples, chunk_ms, trailing_s, stream_end))
            receiver = asyncio.create_task(_receive(state, on_tool_call))
            try:
                await asyncio.wait_for(receiver, timeout=result.speech_s + timeout_s)
            except asyncio.TimeoutError:
                result.timed_out = True
                state.log("timeout")
            finally:
                state.done.set()
                sender.cancel()
                await asyncio.gather(sender, return_exceptions=True)
    except Exception as exc:  # noqa: BLE001 - a spike should report, not crash mid-batch
        result.error = f"{type(exc).__name__}: {exc}"
    return result
