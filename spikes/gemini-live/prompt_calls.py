"""Scripted S.I.MO calls against Gemini Live with the real system prompt (#53).

    uv run prompt_calls.py                          # the scripted calls, caller turns as text
    uv run prompt_calls.py --only fi_milk           # one call
    uv run prompt_calls.py --audio --only fi_milk   # caller turns spoken with Gemini TTS
    uv run prompt_calls.py --dry-run                # print the prompt and declarations only

The system prompt is `build_system_prompt` from `api/app/agent/prompt.py`. The function
declarations are the contract's request models (`api/app/schemas/tools.py`) turned into
JSON Schema with `$ref`s inlined, as the relay will do with the MCP tool list, plus the
relay's local `end_call` on the phone. `build_quote` and `update_quote` are answered by
the stub engine (`stub_engine.py`, a copy of the removed `api/app/engine/stub.py`),
`request_confirmation` by a fake `ConfirmationRequestResponse`.

Phone calls run on `gemini-3.8-live` (one Live session per call). The chat call runs
on a text model with `generate_content`, as the webshop chat would (no Live session).
Every Live session opened is appended to out/prompt_calls/sessions.log, so the usage
stays countable. A 429 stops the run.

Output: out/prompt_calls/<time>/results.md (checklist per call) and results.json
(transcripts, tool calls and arguments).
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import json
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import numpy as np
from google.genai import types

from common import HERE, IN_RATE, LIVE_MODEL, OUT_RATE, TTS_MODEL, make_client, read_wav, resample, trim_silence, write_wav

API_DIR = HERE.parents[1] / "api"
sys.path.insert(0, str(API_DIR))

from app.agent import AGENT_TOOLS, CALL_CONNECTED, END_CALL, PROMPT_VERSION, build_system_prompt  # noqa: E402
from app.schemas import (  # noqa: E402
    BuildQuoteRequest,
    ConfirmationRequestResponse,
    CustomerContext,
    EngineInput,
    Exclusion,
    ExclusionLabel,
    Flag,
    HistorySummary,
    KitchenProfile,
    LineRequest,
    Localized,
    ProductHit,
    QuoteResponse,
    RequestConfirmationRequest,
    SearchProductsResponse,
    StockStatus,
    UpdateQuoteRequest,
    UsualItem,
)
from app.services.policy import load_rule_set  # noqa: E402
from stub_engine import MILK_ID, WHOLE_MILK_ID, decide  # noqa: E402

REPO = HERE.parents[1]
OUT_DIR = HERE / "out" / "prompt_calls"
SESSIONS_LOG = OUT_DIR / "sessions.log"
CHAT_MODEL = "gemini-3.8-flash"
VOICE = "Aoede"  # the spike's proposal for S.I.MO
CALLER_VOICE = "Achird"  # the spike's caller voice

# The harness's demo account. The butter id is made up: the stub prices every line as milk.
CONTEXT = CustomerContext(
    company_name="Hassu Hauki Oy",
    phone_masked="+358 40 *** **12",
    exclusions=[ExclusionLabel(key=Exclusion.lactose_free, label=Localized(fi="laktoositon", en="lactose-free"))],
    usual_items=[
        UsualItem(
            product_id="400100",
            name=Localized(fi="Valio voi 500 g", en="Valio butter 500 g"),
            quantity=Decimal("20"),
            unit="kg",
        )
    ],
    lang="fi",
)

# Short tool descriptions. The real ones come from the MCP server (#43); these follow vision §8.
DESCRIPTIONS = {
    "search_products": "Search products: text, claims, category, needed-by. Returns a shortlist with price and availability.",
    "get_customer_context": "The kitchen profile and usual items.",
    "search_recipes": "Find recipes by ingredient, diet or occasion.",
    "get_recipe": "Get one recipe scaled to a number of portions.",
    "build_quote": "The main call. Takes all order lines at once and returns a decision, priced lines, flags, alternatives and text to speak.",
    "update_quote": "Answer a clarification or change lines. Takes the full new line list and returns a new quote.",
    "request_confirmation": "Sends the confirmation link for a quote to the account's own phone. No recipient argument.",
    "get_order_status": "Pending confirmation, confirmed, cancelled or expired.",
    END_CALL: "Hang up the call.",
}


# --- Declarations ----------------------------------------------------------------


def inline_refs(schema: dict[str, Any]) -> dict[str, Any]:
    """Resolve `#/$defs/...` references in place and drop `$defs`.

    Pydantic and MCP tool schemas use `$ref`; this keeps the declaration self-contained,
    which is the safe form for Gemini function declarations.
    """
    defs = schema.get("$defs", {})

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                target = walk(copy.deepcopy(defs[node["$ref"].split("/")[-1]]))
                rest = {k: walk(v) for k, v in node.items() if k != "$ref"}
                return {**target, **rest}
            return {k: walk(v) for k, v in node.items() if k != "$defs"}
        if isinstance(node, list):
            return [walk(v) for v in node]
        return node

    return walk(schema)


def declarations(channel: str) -> list[types.FunctionDeclaration]:
    decls = []
    for name, model in AGENT_TOOLS.items():
        schema = inline_refs(model.model_json_schema()) if model else {"type": "object", "properties": {}}
        decls.append(types.FunctionDeclaration(name=name, description=DESCRIPTIONS[name], parameters_json_schema=schema))
    if channel == "phone":
        decls.append(
            types.FunctionDeclaration(
                name=END_CALL, description=DESCRIPTIONS[END_CALL], parameters_json_schema={"type": "object", "properties": {}}
            )
        )
    return decls


# --- Scenarios -------------------------------------------------------------------


@dataclass
class Scenario:
    id: str
    title: str
    channel: str  # phone or web_chat
    turns: list[str]  # caller turns after the call connects
    quote_turn: int  # 1-based caller turn that should trigger build_quote
    yes_turn: int  # caller turn with the clear yes to the link
    expected_lines: int
    call_language: str = "auto"
    reply_lang: str = "fi"  # the language every reply after the first caller turn should be in
    unclear_first: bool = False  # the first quote takes the stub's "unclear" path
    reject_words: tuple[str, ...] = ()  # lines whose text has one of these take the "reject" path
    no_listing: bool = False  # add an ALLERGEN_NO_LISTING flag to ready quotes
    pack_terms: tuple[str, ...] = ()  # one of these must be in some line text
    closing: str = ""  # sent only if the agent hasn't ended the call by itself


SCENARIOS = [
    Scenario(
        id="fi_milk",
        title="Finnish milk order, ends with agreeing to the link",
        channel="phone",
        turns=[
            "Moi! Tarvitsisin sata litraa Arki-kevytmaitoa maanantaiksi.",
            "Ja sitten vielä kaksikymmentä litran purkkia samaa maitoa tiistaiksi.",
            "Ei muuta, siinä kaikki.",
            "Joo, lähetä se.",
        ],
        quote_turn=3,
        yes_turn=4,
        expected_lines=2,
        no_listing=True,
        pack_terms=("1 l", "1l", "litra"),
        closing="Kiitos, hei hei.",
    ),
    Scenario(
        id="en_order",
        title="English caller on a Finnish account",
        channel="phone",
        turns=[
            "Hi, sorry, I don't speak Finnish. I need two hundred litres of semi-skimmed milk for Tuesday.",
            "And my usual butter as well, same day.",
            "What would that come to?",
            "Hmm, I'm not sure yet. Where does the link go?",
            "Okay, yes, please send it.",
        ],
        quote_turn=3,
        yes_turn=5,
        expected_lines=2,
        reply_lang="en",
        no_listing=True,
        closing="Thanks, bye.",
    ),
    Scenario(
        id="fi_clarify",
        title="Clarification: the engine asks which milk",
        channel="phone",
        turns=[
            "Hei, laittaisitko viisikymmentä litraa maitoa huomiseksi.",
            "Ei muuta.",
            "Kevytmaitoa.",
            "Kyllä kiitos.",
        ],
        quote_turn=2,
        yes_turn=4,
        expected_lines=1,
        unclear_first=True,
        closing="Kiitos, moi.",
    ),
    Scenario(
        id="chat_reject",
        title="Web chat: a line that can't be ordered",
        channel="web_chat",
        turns=[
            "Tarvitsen 20 litraa kevytmaitoa ja 10 kg Oltermanni-juustoa perjantaiksi.",
            "Siinä kaikki.",
            "Joo, ilman juustoa sitten.",
            "Lähetä vahvistus.",
        ],
        quote_turn=2,
        yes_turn=4,
        expected_lines=2,
        reject_words=("oltermanni", "juusto"),
    ),
]


# --- The stub service --------------------------------------------------------------


class StubService:
    """Answers tool calls the way the MCP server will, with the stub engine behind it."""

    def __init__(self, scenario: Scenario, today: date):
        self.scenario = scenario
        self.today = today
        self.rules = load_rule_set(REPO / "policy", REPO / "data")
        self.quotes = 0
        self.last_quote_id: str | None = None
        self.ended = False

    def _engine(self, lines: list[LineRequest]) -> dict[str, Any]:
        s = self.scenario
        engine_lines = []
        for line in lines:
            text = line.text or ""
            if s.unclear_first and self.quotes == 0 and line.product_id is None:
                text += " unclear"
            if any(w in text.lower() for w in s.reject_words):
                text += " reject"
            engine_lines.append(line.model_copy(update={"text": text}))
        now = datetime.now(UTC)
        out = decide(
            EngineInput(
                lines=engine_lines,
                candidates={},
                kitchen=KitchenProfile(exclusions=[e.key for e in CONTEXT.exclusions]),
                history=HistorySummary(usual_items=CONTEXT.usual_items, recent_lines=[]),
                products=[],
                offers=[],
                rules=self.rules,
                business_now=now,
                issued_at=now,
                lang=CONTEXT.lang,
            )
        )
        if s.no_listing and out.decision == "ready":
            names = ", ".join(line.name.fi for line in out.lines[:1])
            out.flags.append(
                Flag(
                    flag_key="allergen_no_listing",
                    code="ALLERGEN_NO_LISTING",
                    line_ids=[out.lines[0].line_id],
                    kind="acknowledge",
                    text=Localized(
                        fi=f"Huomio: seuraaville tuotteille ei ole ilmoitettu allergeenitietoja: {names}. "
                        "En voi vahvistaa, etteivät ne sisällä laktoosia.",
                        en=f"Note: these products have no allergen information: {out.lines[0].name.en}. "
                        "I can't confirm they are free from lactose.",
                    ),
                )
            )
        self.quotes += 1
        quote_id = f"Q-{self.quotes}"
        response = QuoteResponse(
            **out.model_dump(),
            quote_id=quote_id,
            version=self.quotes,
            parent_quote_id=self.last_quote_id,
            status="ready",
            expires_at=None,
            quote_hash="stub-hash" if out.decision == "ready" else None,
        )
        self.last_quote_id = quote_id
        # Strip the trace: the real tool results will be smaller than the full engine dump.
        data = response.model_dump(mode="json")
        for line in data["lines"]:
            line.pop("trace", None)
        return data

    def call(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        try:
            if name == "build_quote":
                return {"output": self._engine(BuildQuoteRequest.model_validate(args).lines)}
            if name == "update_quote":
                return {"output": self._engine(UpdateQuoteRequest.model_validate(args).lines)}
            if name == "request_confirmation":
                RequestConfirmationRequest.model_validate(args)
                return {
                    "output": ConfirmationRequestResponse(
                        sent_to_masked=CONTEXT.phone_masked,
                        sms_status="held" if self.scenario.channel == "phone" else "off",
                        inbox=True,
                    ).model_dump(mode="json")
                }
            if name == "get_customer_context":
                return {"output": CONTEXT.model_dump(mode="json")}
            if name == "search_products":
                hit = ProductHit(
                    product_id=MILK_ID,
                    name=Localized(fi="Valio Arki kevytmaito 1 l", en="Valio Arki semi skimmed milk 1 l"),
                    category="dairy",
                    sales_unit="ST",
                    sales_unit_label=Localized(fi="kappale", en="piece"),
                    image_url=None,
                    unit_price_gross=Decimal("1.15"),
                    price_per_base_unit=Decimal("1.15"),
                    base_unit="l",
                    stock_status=StockStatus.unverified,
                    available_date=None,
                    origin="FI",
                )
                return {"output": SearchProductsResponse(results=[hit]).model_dump(mode="json")}
            if name == END_CALL:
                self.ended = True
                return {"output": {"ok": True}}
            return {"error": f"{name} is not available in this test."}
        except Exception as exc:  # noqa: BLE001 - the model gets the error, as from MCP
            return {"error": f"{type(exc).__name__}: {exc}"}


# --- Transcript ----------------------------------------------------------------------


@dataclass
class Turn:
    index: int  # 0 is the call-connected cue
    caller: str
    agent: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    heard: str = ""  # input transcription, audio runs only
    seconds: float = 0.0
    timed_out: bool = False


@dataclass
class CallResult:
    scenario: str
    mode: str
    model: str
    turns: list[Turn] = field(default_factory=list)
    ended_by_agent: bool = False
    error: str | None = None


class RateLimited(Exception):
    pass


def is_rate_limit(exc: BaseException) -> bool:
    text = f"{type(exc).__name__} {exc}"
    return "429" in text or "RESOURCE_EXHAUSTED" in text or "quota" in text.lower()


def log_session(scenario: str, mode: str) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with SESSIONS_LOG.open("a") as f:
        f.write(f"{datetime.now().isoformat(timespec='seconds')} {scenario} {mode}\n")


# --- Live phone call -------------------------------------------------------------------


class LiveCall:
    def __init__(self, session, service: StubService, result: CallResult):
        self.session = session
        self.service = service
        self.result = result
        self.turn: Turn | None = None
        self.turn_done = asyncio.Event()
        self.pending = 0
        self.awaiting_reply = False
        self.audio_out = bytearray()
        self.error: BaseException | None = None

    async def receive(self) -> None:
        try:
            while True:
                async for msg in self.session.receive():
                    await self.handle(msg)
                await asyncio.sleep(0.01)
        except Exception as exc:  # noqa: BLE001 - surfaced by wait_turn
            self.error = exc
            self.turn_done.set()

    async def handle(self, msg) -> None:
        turn = self.turn
        if msg.tool_call and turn is not None:
            calls = msg.tool_call.function_calls or []
            self.pending += len(calls)
            responses = []
            for fc in calls:
                args = dict(fc.args or {})
                turn.tool_calls.append({"name": fc.name, "args": args})
                responses.append(
                    types.FunctionResponse(id=fc.id, name=fc.name, response=self.service.call(fc.name, args))
                )
            await self.session.send_tool_response(function_responses=responses)
            self.pending -= len(calls)
            # After end_call the model may stay silent; after any other tool it should speak.
            self.awaiting_reply = any(fc.name != END_CALL for fc in calls)
        sc = msg.server_content
        if not sc or turn is None:
            return
        if sc.input_transcription and sc.input_transcription.text:
            turn.heard += sc.input_transcription.text
        if sc.output_transcription and sc.output_transcription.text:
            turn.agent += sc.output_transcription.text
            self.awaiting_reply = False
        if sc.model_turn:
            for part in sc.model_turn.parts or []:
                if part.inline_data and part.inline_data.data:
                    self.audio_out.extend(part.inline_data.data)
        if sc.turn_complete and self.pending <= 0 and not self.awaiting_reply:
            self.turn_done.set()

    def start_turn(self, index: int, caller: str) -> Turn:
        self.turn = Turn(index=index, caller=caller)
        self.result.turns.append(self.turn)
        self.turn_done.clear()
        self.turn_t0 = time.monotonic()  # moved to the end of speech in audio runs
        return self.turn

    async def wait_turn(self, timeout_s: float) -> None:
        """Wait for the agent's turn to end. `seconds` runs from the end of the caller's
        text or speech to `turn_complete`, which the server holds until the reply would
        have finished playing (README, Surprises)."""
        try:
            await asyncio.wait_for(self.turn_done.wait(), timeout=timeout_s)
        except TimeoutError:
            self.turn.timed_out = True
        self.turn.seconds = round(time.monotonic() - self.turn_t0, 2)
        if self.error is not None:
            raise self.error


async def send_audio(call: LiveCall, samples: np.ndarray, timeout_s: float, chunk_ms: int = 40) -> None:
    """Speak `samples` in real time, then send silence until the agent's turn is done."""
    chunk = int(IN_RATE * chunk_ms / 1000)
    data = samples.astype("<i2")
    start = time.monotonic()
    for i, offset in enumerate(range(0, len(data), chunk)):
        delay = start + (i + 1) * chunk_ms / 1000 - time.monotonic()
        if delay > 0:
            await asyncio.sleep(delay)
        await call.session.send_realtime_input(
            audio=types.Blob(data=data[offset : offset + chunk].tobytes(), mime_type=f"audio/pcm;rate={IN_RATE}")
        )
    call.turn_t0 = time.monotonic()
    silence = np.zeros(chunk, dtype="<i2").tobytes()
    end = time.monotonic() + timeout_s
    while not call.turn_done.is_set() and time.monotonic() < end:
        await call.session.send_realtime_input(audio=types.Blob(data=silence, mime_type=f"audio/pcm;rate={IN_RATE}"))
        await asyncio.sleep(chunk_ms / 1000)


def caller_audio(client, scenario: Scenario) -> list[np.ndarray]:
    """The caller turns spoken by Gemini TTS, cached in audio/prompt_calls/<id>/."""
    from tts import decode_audio, synth_interactions

    folder = HERE / "audio" / "prompt_calls" / scenario.id
    out = []
    for i, text in enumerate([*scenario.turns, scenario.closing], 1):
        path = folder / f"{i:02d}.wav"
        if not path.exists():
            raw = synth_interactions(client, TTS_MODEL, text, CALLER_VOICE, "a busy kitchen manager on the phone")
            samples, rate = decode_audio(raw)
            write_wav(path, trim_silence(resample(samples, rate, IN_RATE), IN_RATE), IN_RATE)
        samples, _ = read_wav(path)
        out.append(samples)
    return out


async def run_phone(client, scenario: Scenario, today: date, audio: bool, out_dir: Path) -> CallResult:
    mode = "audio" if audio else "text"
    result = CallResult(scenario=scenario.id, mode=mode, model=LIVE_MODEL)
    service = StubService(scenario, today)
    speech = caller_audio(client, scenario) if audio else []
    config = types.LiveConnectConfig(
        response_modalities=[types.Modality.AUDIO],
        system_instruction=build_system_prompt(CONTEXT, "phone", scenario.call_language, today=today),
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=VOICE))
        ),
        tools=[types.Tool(function_declarations=declarations("phone"))],
    )
    log_session(scenario.id, mode)
    try:
        async with client.aio.live.connect(model=LIVE_MODEL, config=config) as session:
            call = LiveCall(session, service, result)
            receiver = asyncio.create_task(call.receive())
            try:
                call.start_turn(0, CALL_CONNECTED)
                await session.send_realtime_input(text=CALL_CONNECTED)
                await call.wait_turn(30)
                caller_turns = [*scenario.turns, scenario.closing]
                for i, text in enumerate(caller_turns, 1):
                    if service.ended:
                        break
                    if i == len(caller_turns) and not text:
                        break
                    call.start_turn(i, text)
                    if audio:
                        sender = asyncio.create_task(send_audio(call, speech[i - 1], timeout_s=60))
                        await call.wait_turn(60 + len(speech[i - 1]) / IN_RATE)
                        await sender
                    else:
                        await session.send_realtime_input(text=text)
                        await call.wait_turn(60)
                    print(f"  [{i}] caller: {text}\n      agent: {call.turn.agent.strip()}")
                    for c in call.turn.tool_calls:
                        print(f"      tool: {c['name']} {json.dumps(c['args'], ensure_ascii=False)}")
            finally:
                receiver.cancel()
                await asyncio.gather(receiver, return_exceptions=True)
            if call.audio_out:
                write_wav(out_dir / f"{scenario.id}-{mode}.wav", bytes(call.audio_out), OUT_RATE)
    except Exception as exc:  # noqa: BLE001
        if is_rate_limit(exc):
            raise RateLimited(str(exc)) from exc
        result.error = f"{type(exc).__name__}: {exc}"
    result.ended_by_agent = service.ended
    return result


# --- Chat (generate_content, no Live session) ------------------------------------------


def run_chat(client, scenario: Scenario, today: date) -> CallResult:
    result = CallResult(scenario=scenario.id, mode="text", model=CHAT_MODEL)
    service = StubService(scenario, today)
    config = types.GenerateContentConfig(
        system_instruction=build_system_prompt(CONTEXT, "web_chat", scenario.call_language, today=today),
        tools=[types.Tool(function_declarations=declarations("web_chat"))],
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )
    contents: list[types.Content] = []
    try:
        for i, text in enumerate(scenario.turns, 1):
            turn = Turn(index=i, caller=text)
            result.turns.append(turn)
            contents.append(types.Content(role="user", parts=[types.Part(text=text)]))
            t0 = time.monotonic()
            for _ in range(5):
                resp = client.models.generate_content(model=CHAT_MODEL, contents=contents, config=config)
                content = resp.candidates[0].content
                contents.append(content)
                calls = [p.function_call for p in content.parts or [] if p.function_call]
                turn.agent += "".join(p.text for p in content.parts or [] if p.text and not p.thought)
                if not calls:
                    break
                parts = []
                for fc in calls:
                    args = dict(fc.args or {})
                    turn.tool_calls.append({"name": fc.name, "args": args})
                    parts.append(types.Part.from_function_response(name=fc.name, response=service.call(fc.name, args)))
                contents.append(types.Content(role="user", parts=parts))
            turn.seconds = round(time.monotonic() - t0, 2)
            print(f"  [{i}] caller: {text}\n      agent: {turn.agent.strip()}")
            for c in turn.tool_calls:
                print(f"      tool: {c['name']} {json.dumps(c['args'], ensure_ascii=False)}")
    except Exception as exc:  # noqa: BLE001
        if is_rate_limit(exc):
            raise RateLimited(str(exc)) from exc
        result.error = f"{type(exc).__name__}: {exc}"
    return result


# --- Checks --------------------------------------------------------------------------

FORBIDDEN_CHANNELS = ("sähköpost", "email", "e-mail", "sms", "tekstiviest", "text message")
PLACED = (
    "tilaus on tehty",
    "tilaus on vastaanotettu",
    "tilaus on vahvistettu",
    "tilasin",
    "olen tilannut",
    "order is placed",
    "order has been placed",
    "i've placed",
    "i have placed",
    "order is confirmed",
)
FI_WORDS = {"ja", "ei", "että", "kiitos", "tilaus", "haluatko", "litraa", "euroa", "hei", "moi", "selvä", "vielä", "muuta", "tulee", "puhelimeesi"}


EN_WORDS = {"the", "and", "is", "for", "you", "your", "of", "to", "anything", "else", "it", "would", "order", "link", "got", "that"}


def word_share(text: str, vocabulary: set[str]) -> float:
    words = re.findall(r"[a-zåäö]+", text.lower())
    return sum(w in vocabulary for w in words) / len(words) if words else 0.0


def _calls(result: CallResult, name: str) -> list[tuple[int, dict[str, Any]]]:
    return [(t.index, c["args"]) for t in result.turns for c in t.tool_calls if c["name"] == name]


def check(scenario: Scenario, result: CallResult) -> list[tuple[str, bool | None, str]]:
    """Automatic checks against the #53 checklist. None means not applicable here."""
    rows: list[tuple[str, bool | None, str]] = []
    agent_turns = [t for t in result.turns if t.agent.strip()]
    first = result.turns[0].agent if result.turns else ""
    low = first.lower()
    simo = "simo" in re.sub(r"[.\s]", "", low)
    ai = any(w in low for w in ("tekoäly", "ai helper", "ai assistant", " ai ", "ai-"))
    rows.append(("Greets by company name, says S.I.MO is an AI helper", "hassu hauki" in low and simo and ai, first.strip()))

    builds = _calls(result, "build_quote")
    ok = len(builds) == 1 and builds[0][0] == scenario.quote_turn
    lines = builds[0][1].get("lines", []) if builds else []
    rows.append(
        (
            "One build_quote with all lines, at the trigger turn",
            ok and len(lines) == scenario.expected_lines,
            f"{len(builds)} call(s) at turn(s) {[b[0] for b in builds]}, {len(lines)} line(s)",
        )
    )
    if scenario.pack_terms:
        texts = [str(line.get("text", "")) for line in lines]
        rows.append(("Pack size kept in the line text", any(any(p in t for p in scenario.pack_terms) for t in texts), "; ".join(texts)))
    usual_ids = {u.product_id for u in CONTEXT.usual_items}
    # Stub ids are known only once a tool (search_products, build_quote) has returned them.
    ordered = [c for t in result.turns for c in t.tool_calls]
    invented = [
        line.get("product_id")
        for i, c in enumerate(ordered)
        if c["name"] in ("build_quote", "update_quote")
        for line in c["args"].get("lines", [])
        if line.get("product_id")
        and not (line["product_id"] in usual_ids and line.get("usual"))
        and not (line["product_id"] in (MILK_ID, WHOLE_MILK_ID) and i > 0)
    ]
    rows.append(("product_id only for a usual item or a picked option", not invented, ", ".join(map(str, invented))))
    no_word = [
        line.get("line_id")
        for name in ("build_quote", "update_quote")
        for _, a in _calls(result, name)
        for line in a.get("lines", [])
        if line.get("unit") == "package" and not line.get("package_word")
    ]
    rows.append(("package_word set for every package line", not no_word, f"lines {no_word}"))
    questions = max((t.agent.count("?") for t in agent_turns), default=0)
    # Two '?' can be one question ("Mitä maitoa? Kevytmaitoa vai täysmaitoa?"): read those by hand.
    rows.append(("One question per turn (max '?' in a turn; 2 = read by hand)", None if questions == 2 else questions <= 1, str(questions)))

    if scenario.unclear_first:
        updates = _calls(result, "update_quote")
        chosen = [line.get("product_id") for _, a in updates for line in a.get("lines", [])]
        asked = next((t.agent for t in result.turns if t.index == scenario.quote_turn), "")
        rows.append(
            (
                "Clarification asked, then update_quote with the chosen product",
                "?" in asked and len(updates) == 1 and MILK_ID in chosen and WHOLE_MILK_ID not in chosen,
                f"asked: {asked.strip()} | update_quote product ids: {chosen}",
            )
        )
    if scenario.reject_words:
        updates = _calls(result, "update_quote")
        rows.append(
            (
                "Rejection said, moved on with update_quote without the line",
                len(updates) >= 1 and all(len(a.get("lines", [])) == scenario.expected_lines - 1 for _, a in updates),
                f"{len(updates)} update_quote call(s)",
            )
        )

    all_text = " ".join(t.agent for t in agent_turns).lower()
    if scenario.no_listing:
        mentions = [t.index for t in agent_turns if "allergeen" in t.agent.lower() or "allergen" in t.agent.lower()]
        rows.append(("No-allergen-listing notice exactly once", len(mentions) == 1, f"turns {mentions}"))
    placed = [p for p in PLACED if p in all_text]
    rows.append(("Never says the order is placed", not placed, ", ".join(placed)))

    confirms = _calls(result, "request_confirmation")
    rows.append(
        (
            "request_confirmation once, only after the clear yes",
            len(confirms) == 1 and confirms[0][0] == scenario.yes_turn,
            f"at turn(s) {[c[0] for c in confirms]}, yes was turn {scenario.yes_turn}",
        )
    )
    after = " ".join(t.agent for t in result.turns if confirms and t.index >= confirms[0][0]).lower()
    if scenario.channel == "phone":
        how = any(w in after for w in ("puhelimeesi", "your phone")) and any(
            w in after for w in ("lopetamme", "puhelun jälkeen", "hang up", "after the call", "sulje", "katkais")
        )
        rows.append(("Says the link comes to the phone after hanging up", how, ""))
        ends = _calls(result, END_CALL)
        rows.append(
            (
                "end_call after the link is agreed",
                bool(ends) and bool(confirms) and ends[0][0] >= confirms[0][0],
                f"end_call at turn(s) {[e[0] for e in ends]}",
            )
        )
    else:
        rows.append(("Says the link comes to the phone", any(w in after for w in ("puhelimeesi", "your phone", "puhelimeen")), ""))
    bad = [w for w in FORBIDDEN_CHANNELS if w in all_text]
    rows.append(("Never promises email or SMS", not bad, ", ".join(bad)))
    later = [t for t in agent_turns if t.index >= 1]
    if scenario.reply_lang == "en":
        worst = max((word_share(t.agent, FI_WORDS) for t in later), default=0.0)
        rows.append(("Replies in English after the caller speaks English", worst < 0.05, f"max Finnish word share {worst:.2f}"))
    else:
        worst = max((word_share(t.agent, EN_WORDS) for t in later), default=0.0)
        rows.append(("Replies in Finnish", worst < 0.05, f"max English word share {worst:.2f}"))
    if scenario.channel == "phone":
        listy = [t.index for t in agent_turns if re.search(r"^\s*[-*\d]+[.)]?\s", t.agent, re.M) or "**" in t.agent]
        rows.append(("Spoken style: no lists or markdown", not listy, f"turns {listy}"))
    rows.append(("No middle dot", "\u00b7" not in all_text, ""))
    rows.append(("No turn timed out, no error", not any(t.timed_out for t in result.turns) and not result.error, result.error or ""))
    return rows


# --- Report --------------------------------------------------------------------------


def report(out_dir: Path, results: list[tuple[Scenario, CallResult]], version: str = PROMPT_VERSION) -> None:
    md = [f"# Prompt calls {out_dir.name}", "", f"Prompt version {version}", ""]
    data = []
    for scenario, result in results:
        rows = check(scenario, result)
        md += [f"## {scenario.id}: {scenario.title} ({result.model}, {result.mode})", "", "| Check | Result | Note |", "|---|---|---|"]
        for name, ok, note in rows:
            mark = "n/a" if ok is None else ("pass" if ok else "**fail**")
            md.append(f"| {name} | {mark} | {note.replace('|', '/').replace('\n', ' ')[:300]} |")
        md += ["", "Transcript:", ""]
        for t in result.turns:
            md.append(f"- **{t.index} caller**: {t.caller}" + (f" (heard: {t.heard.strip()})" if t.heard else ""))
            for c in t.tool_calls:
                md.append(f"  - tool `{c['name']}` `{json.dumps(c['args'], ensure_ascii=False)}`")
            md.append(f"  - **agent** ({t.seconds} s{', TIMEOUT' if t.timed_out else ''}): {t.agent.strip()}")
        md.append("")
        data.append({"scenario": scenario.__dict__, "result": {**result.__dict__, "turns": [t.__dict__ for t in result.turns]}, "checks": rows})
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "results.md").write_text("\n".join(md), encoding="utf-8")
    (out_dir / "results.json").write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"Saved to {out_dir}")


def recheck(out_dir: Path) -> None:
    """Score a saved run again with the current checks (no API calls)."""
    by_id = {s.id: s for s in SCENARIOS}
    results = []
    for item in json.loads((out_dir / "results.json").read_text(encoding="utf-8")):
        raw = item["result"]
        turns = [Turn(**t) for t in raw.pop("turns")]
        results.append((by_id[item["scenario"]["id"]], CallResult(**raw, turns=turns)))
    old = (out_dir / "results.md").read_text(encoding="utf-8")
    version = re.search(r"Prompt version (\S+)", old).group(1)
    report(out_dir, results, version)


async def main_async(args) -> None:
    if args.recheck:
        recheck(Path(args.recheck))
        return
    scenarios = [s for s in SCENARIOS if not args.only or s.id in args.only]
    today = date.fromisoformat(args.today) if args.today else date.today()
    if args.dry_run:
        for channel in sorted({s.channel for s in scenarios}):
            print(build_system_prompt(CONTEXT, channel, today=today))
            for d in declarations(channel):
                print(d.name, json.dumps(d.parameters_json_schema)[:300])
        return
    client = make_client()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S") + ("-audio" if args.audio else "")
    out_dir = OUT_DIR / stamp
    results = []
    try:
        for s in scenarios:
            print(f"{s.id}: {s.title}")
            if s.channel == "phone":
                results.append((s, await run_phone(client, s, today, args.audio, out_dir)))
            else:
                results.append((s, run_chat(client, s, today)))
            await asyncio.sleep(1.0)
    except RateLimited as exc:
        print(f"Rate limited, stopping: {exc}")
    report(out_dir, results)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", nargs="*", help=f"scenario ids: {', '.join(s.id for s in SCENARIOS)}")
    ap.add_argument("--audio", action="store_true", help="speak the caller turns with TTS (phone scenarios)")
    ap.add_argument("--today", help="business date, YYYY-MM-DD (default: today)")
    ap.add_argument("--recheck", metavar="DIR", help="score a saved run in DIR again, call nothing")
    ap.add_argument("--dry-run", action="store_true", help="print the prompt and declarations, call nothing")
    asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    main()
