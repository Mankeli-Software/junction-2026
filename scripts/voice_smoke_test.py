"""Live smoke test of the voice relay (#52): one short Finnish phone order through /voice/ws.

Against a locally running API (with Postgres, a catalogue and GEMINI_API_KEY), this:

1. makes a demo account like the phone page does (`POST /api/v1/demo/accounts`);
2. speaks the caller's lines, made once with Gemini TTS and cached, into `/voice/ws` in
   real time, with silence in between like an open microphone;
3. answers S.I.MO as a caller would: the order, "that's all" if asked, "kyllä" to the
   link, goodbye;
4. checks that a quote was built, that the link is held during the call (the inbox stays
   empty), that it reaches the inbox after the call and that the socket never carried it;
5. prints the latency from the end of each caller line to S.I.MO's first state change,
   first tool call and first audio.

Each run opens one Gemini Live session. Keep runs few: the key has abuse limits.

    cd api && uv run python ../scripts/voice_smoke_test.py --base http://localhost:8000
"""

import argparse
import asyncio
import audioop  # deprecated in 3.13; the API runs on 3.12
import base64
import hashlib
import io
import json
import os
import random
import statistics
import sys
import time
import wave
from dataclasses import dataclass, field
from pathlib import Path

import httpx
import websockets

CACHE = Path(__file__).resolve().parent / ".voice_smoke_cache"
IN_RATE = 16_000
OUT_RATE = 24_000
FRAME_MS = 40
TTS_MODEL = "gemini-3.8-flash-tts"
CALLER_VOICE = "Achird"
STYLE = "a busy kitchen manager on the phone, natural pace"

LINES = {
    "order": "Hei! Tarvitsisin kaksikymmentä litraa Arki-kevytmaitoa maanantaiksi.",
    "done": "Ei muuta, siinä kaikki.",
    "yes": "Kyllä, lähetä se.",
    "bye": "Kiitos, hei hei.",
    "whole_order": "Hei! Tarvitsisin kaksikymmentä litraa kevytmaitoa maanantaiksi. Siinä kaikki.",
}

# The caller's side of a whole call for the browser's fake microphone (--browser-wav):
# (seconds of silence before, line). Chromium loops the file, so it ends in a long silence.
BROWSER_SCRIPT = [(8.0, "whole_order"), (26.0, "yes"), (60.0, None)]


# --- Caller audio ---------------------------------------------------------------------


def gemini_key() -> str:
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        sys.exit("Set GEMINI_API_KEY (for the caller's TTS lines).")
    return key


def tts(text: str) -> bytes:
    """16 kHz PCM of `text` in the caller's voice, cached in scripts/.voice_smoke_cache/."""
    CACHE.mkdir(exist_ok=True)
    path = CACHE / f"{hashlib.sha256(f'{CALLER_VOICE}:{text}'.encode()).hexdigest()[:16]}.pcm"
    if path.exists():
        return path.read_bytes()
    from google import genai

    client = genai.Client(api_key=gemini_key(), http_options={"api_version": "v1beta"})
    content = {
        "type": "text",
        "text": text,
        "annotations": [{"type": "speech_metadata", "style": STYLE}],
    }
    interaction = client.interactions.create(
        model=TTS_MODEL,
        input=[{"type": "user_input", "content": [content]}],
        response_format={"type": "audio"},
        generation_config={"speech_config": [{"voice": CALLER_VOICE}]},
    )
    data = interaction.output_audio.data
    raw = base64.b64decode(data) if isinstance(data, str) else data
    rate = OUT_RATE
    if raw[:4] == b"RIFF":
        with wave.open(io.BytesIO(raw), "rb") as w:
            rate, raw = w.getframerate(), w.readframes(w.getnframes())
    pcm, _ = audioop.ratecv(raw, 2, 1, rate, IN_RATE, None)
    path.write_bytes(pcm)
    return pcm


# --- The call -------------------------------------------------------------------------


@dataclass
class Turn:
    line: str
    speech_end: float = 0.0
    first_state: float | None = None
    first_tool: float | None = None
    first_audio: float | None = None
    agent: list[str] = field(default_factory=list)


@dataclass
class Call:
    states: list[tuple[float, str, str | None]] = field(default_factory=list)
    texts: list[str] = field(default_factory=list)
    turns: list[Turn] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    ended: dict | None = None
    play_until: float = 0.0
    state: str = "connecting"
    speaking_seen: bool = False
    agent_lines: list[str] = field(default_factory=list)
    buyer_lines: list[str] = field(default_factory=list)


async def receive(ws, call: Call) -> None:
    async for message in ws:
        now = time.monotonic()
        turn = call.turns[-1] if call.turns else None
        if isinstance(message, bytes):
            call.play_until = max(call.play_until, now) + len(message) / 2 / OUT_RATE
            if turn and turn.speech_end and turn.first_audio is None:
                turn.first_audio = now - turn.speech_end
            continue
        call.texts.append(message)
        data = json.loads(message)
        kind = data["type"]
        if kind == "agent_state":
            call.state = data["state"]
            call.states.append((now, data["state"], data["tool"]))
            if data["state"] == "speaking":
                call.speaking_seen = True
            if data["state"] == "working":
                call.tools.append(data["tool"])
                print(f"    [working: {data['tool']}]")
            if turn and turn.speech_end:
                if turn.first_state is None:
                    turn.first_state = now - turn.speech_end
                if data["state"] == "working" and turn.first_tool is None:
                    turn.first_tool = now - turn.speech_end
        elif kind == "transcript" and data["final"]:
            who = "S.I.MO" if data["who"] == "agent" else "caller"
            print(f"  {who}: {data['text']}")
            (call.agent_lines if who == "S.I.MO" else call.buyer_lines).append(data["text"])
        elif kind == "ended":
            call.ended = data
            print(f"  ended: {data}")
            return


async def microphone(ws, queue: asyncio.Queue, call: Call) -> None:
    """Sends silence, or the next queued line, in real time like an open microphone."""
    silence = b"\x00\x00" * (IN_RATE * FRAME_MS // 1000)
    step = FRAME_MS / 1000
    tick = time.monotonic()
    while call.ended is None:
        try:
            pcm = queue.get_nowait()
        except asyncio.QueueEmpty:
            pcm = None
        if pcm:
            frame = len(silence)
            for offset in range(0, len(pcm), frame):
                tick += step
                await asyncio.sleep(max(0, tick - time.monotonic()))
                await ws.send(pcm[offset : offset + frame].ljust(frame, b"\x00"))
            call.turns[-1].speech_end = time.monotonic()
            continue
        tick += step
        await asyncio.sleep(max(0, tick - time.monotonic()))
        try:
            await ws.send(silence)
        except websockets.ConnectionClosed:
            return


async def agent_turn_done(call: Call) -> None:
    """Waits until S.I.MO has spoken and is listening, and its audio has finished playing."""
    deadline = time.monotonic() + 40
    while time.monotonic() < deadline and call.ended is None:
        now = time.monotonic()
        if call.speaking_seen and call.state == "listening" and now > call.play_until + 0.6:
            return
        await asyncio.sleep(0.05)


async def run(base: str) -> int:
    lines = {key: tts(text) for key, text in LINES.items()}
    async with httpx.AsyncClient(base_url=base, timeout=30) as http:
        number = f"+35840{random.randrange(10**6, 10**7)}"
        response = await http.post(
            "/api/v1/demo/accounts", json={"phone_e164": number, "exclusions": [], "lang": "fi"}
        )
        response.raise_for_status()
        print(f"Account: {response.json()['company_name']}")
        cookie = f"simo_session={http.cookies['simo_session']}"
        url = base.replace("http", "ws", 1) + "/voice/ws"
        call = Call()
        queue: asyncio.Queue = asyncio.Queue()
        connect_at = time.monotonic()
        async with websockets.connect(url, additional_headers={"Cookie": cookie}) as ws:
            first = json.loads(await ws.recv())
            assert first == {"type": "ready"}, first
            ready_s = time.monotonic() - connect_at
            print(f"ready after {ready_s:.2f} s")
            receiver = asyncio.create_task(receive(ws, call))
            mic = asyncio.create_task(microphone(ws, queue, call))
            greeting_at = time.monotonic()
            await agent_turn_done(call)
            greeting_s = (call.states[1][0] - greeting_at) if len(call.states) > 1 else None

            def say(key: str) -> None:
                call.turns.append(Turn(LINES[key]))
                call.speaking_seen = False
                print(f"  caller (sent): {LINES[key]}")
                queue.put_nowait(lines[key])

            held: list[bool] = []

            async def check_held() -> None:
                """Once request_confirmation has returned, the inbox must still be empty."""
                while call.ended is None:
                    after = [s for s in call.states if s[1] != "working"]
                    sent = [s for s in call.states if s[2] == "request_confirmation"]
                    if sent and after and after[-1][0] > sent[-1][0]:
                        inbox = (await http.get("/api/v1/private/inbox")).json()
                        print(f"    [inbox during the call: {len(inbox)} message(s)]")
                        held.append(inbox == [])
                        return
                    await asyncio.sleep(0.05)

            checker = asyncio.create_task(check_held())
            say("order")
            for _ in range(6):
                await agent_turn_done(call)
                if call.ended:
                    break
                if "request_confirmation" in call.tools:
                    # S.I.MO should hang up by itself after its goodbye; else we do.
                    await asyncio.sleep(6)
                    if call.ended is None:
                        say("bye")
                        await agent_turn_done(call)
                    break
                quoted = any(t in ("build_quote", "update_quote") for t in call.tools)
                say("yes" if quoted else "done")
            if call.ended is None:
                await ws.send(json.dumps({"type": "hangup"}))
            await asyncio.wait_for(receiver, 15)
            mic.cancel()
            checker.cancel()

        inbox = (await http.get("/api/v1/private/inbox")).json()

    print("\nResult")
    ok = True

    def check(label: str, passed: bool) -> None:
        nonlocal ok
        ok &= passed
        print(f"  [{'x' if passed else ' '}] {label}")

    check("a quote was built", "build_quote" in call.tools)
    check("request_confirmation after the yes", "request_confirmation" in call.tools)
    check("the link was held during the call", held == [True])
    check("ended says the inbox got it", bool(call.ended and call.ended["inbox"]))
    check("the inbox has the link after the call", len(inbox) == 1 and "/c/" in inbox[0]["link"])
    check("no link on the socket", all("/c/" not in t for t in call.texts))
    print(f"  ended by: {call.ended and call.ended['ended_by']}")

    print("\nLatency (s, from the end of the caller's line)")
    print(f"  socket open to ready: {ready_s:.2f}")
    if greeting_s is not None:
        print(f"  ready to greeting audio: {greeting_s:.2f}")
    for turn in call.turns:
        parts = [
            f"state {turn.first_state:.2f}" if turn.first_state is not None else "state -",
            f"tool {turn.first_tool:.2f}" if turn.first_tool is not None else None,
            f"audio {turn.first_audio:.2f}" if turn.first_audio is not None else "audio -",
        ]
        print(f"  {turn.line!r}: " + ", ".join(p for p in parts if p))
    audio = [t.first_audio for t in call.turns if t.first_audio is not None]
    if audio:
        print(f"  first audio: median {statistics.median(audio):.2f}, worst {max(audio):.2f}")
    return 0 if ok else 1


def write_browser_wav(path: Path) -> None:
    """The caller's side of a call as a 48 kHz WAV for Chromium's fake microphone
    (`--use-file-for-fake-audio-capture`), for the call screen screenshots against the
    real relay (web/tests/voice-live-screenshots.spec.ts). No Live session."""
    rate = 48_000
    pcm = b""
    for silence_s, key in BROWSER_SCRIPT:
        pcm += b"\x00\x00" * int(silence_s * rate)
        if key:
            line, _ = audioop.ratecv(tts(LINES[key]), 2, 1, IN_RATE, rate, None)
            pcm += line
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    print(f"{path}: {len(pcm) / 2 / rate:.1f} s")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--base", default="http://localhost:8000")
    parser.add_argument("--browser-wav", type=Path, help="only write the fake microphone file")
    args = parser.parse_args()
    if args.browser_wav:
        write_browser_wav(args.browser_wav)
        return
    sys.exit(asyncio.run(run(args.base)))


if __name__ == "__main__":
    main()
