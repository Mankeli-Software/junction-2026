"""Vocabulary probe (#116): one Live session per transcription vocabulary.

    uv run vocab_probe.py --variant fi --audio-dir recordings/jesse      # the relay's vocabulary before #116
    uv run vocab_probe.py --variant fi+en --audio-dir recordings/jesse   # plus English order phrases
    uv run vocab_probe.py --list                                         # the variants and the turns
    uv run vocab_probe.py --recheck out/vocab_probe/<dir>                # score a saved run again

#85 found that a short English line after Finnish ("That's all, thanks.") was captioned
as Finnish ("Tässä on.") with the relay's Finnish vocabulary. Measuring that and the
product names separately would take a switch call plus ten single-phrase sessions per
variant (#51 ran one session per phrase), so the probe puts both into one call:

- turns 1 to 4 are `switch_fi_en` from prompt_calls.py with the same audio (Jesse's p01,
  then the cached TTS lines), so turn 3 repeats the #85 failure exactly;
- the ten #51 phrases follow in Jesse's voice (#67), with short English lines between
  them: the #85 lines again, and lines that are in no vocabulary variant;
- then en01 (English) and two short Finnish lines, the other direction (#85 run 3 heard
  "Ei muuta" as "Ääri muuta").

The call runs on the real prompt and tools with the stub engine, as prompt_calls.py
does. An `end_call` from the model is answered but the probe keeps talking, since
only the captions are measured. Each session is logged in out/prompt_calls/sessions.log,
the same log as prompt_calls.py, and --budget stops before the log passes it.

Output: out/vocab_probe/<time>-<variant>/results.md and results.json.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from datetime import date, datetime
from pathlib import Path

import numpy as np
from google.genai import types

from common import (
    HERE,
    IN_RATE,
    LIVE_MODEL,
    TTS_MODEL,
    best_wer,
    load_phrases,
    make_client,
    read_wav,
    resample,
    term_hits,
    trim_silence,
    wer,
    write_wav,
)
from prompt_calls import (
    CALL_CONNECTED,
    CALLER_VOICE,
    CONTEXT,
    SESSIONS_LOG,
    VOICE,
    CallResult,
    LiveCall,
    RateLimited,
    Scenario,
    StubService,
    build_system_prompt,
    declarations,
    is_rate_limit,
    log_session,
    relay_vocabulary,
    send_audio,
    use_mcp_descriptions,
)

OUT_DIR = HERE / "out" / "vocab_probe"
TTS_DIR = HERE / "audio" / "probe"
# TTS lines the #85 runs already spoke, so the probe sends the very same audio.
CACHED = {
    "Sorry, can we go on in English? Add five two-kilo tubs of lactose-free sour cream.": "prompt_calls/switch_fi_en/02.wav",
    "That's all, thanks.": "prompt_calls/switch_fi_en/03.wav",
    "Yes, please send it.": "prompt_calls/switch_fi_en/04.wav",
    "Ei muuta, siinä kaikki.": "prompt_calls/switch_en_fi/03.wav",
    "Joo, lähetä se.": "prompt_calls/switch_en_fi/04.wav",
}

# --- Vocabulary variants -----------------------------------------------------------------

# Short English order lines (the #116 issue's list).
ORDER_PHRASES_EN = ["that's all", "send it", "yes please", "thank you"]
# The terms the recogniser got wrong without a vocabulary: TTS in #51 (Oltermanni,
# novobox, vispikerma, Viola) and Jesse's voice in #67 (novobox, Eila, vispikerma, Viola,
# Oddlygood, Barista, kaurajuoma). "Valio" is the brand on every line.
NEEDED_TERMS = ["Valio", "Eila", "Oltermanni", "novobox", "vispikerma", "Viola", "Oddlygood", "Barista", "kaurajuoma"]


def _fi() -> list[str]:
    """The relay's vocabulary as #85 measured it: BASE_VOCABULARY plus the #51 terms."""
    return [t for t in relay_vocabulary() if t not in ORDER_PHRASES_EN]


VARIANTS = {
    "none": list,
    "fi": _fi,
    "fi+en": lambda: [*_fi(), *ORDER_PHRASES_EN],
    "small": lambda: list(NEEDED_TERMS),
    "small+en": lambda: [*NEEDED_TERMS, *ORDER_PHRASES_EN],
    "relay": relay_vocabulary,  # whatever voice_calls.BASE_VOCABULARY holds now, plus the #51 terms
}

# --- The turns ---------------------------------------------------------------------------

# (language, text or #51 phrase id, note). A phrase id is spoken from --audio-dir.
TURNS: list[tuple[str, str, str]] = [
    ("fi", "p01", "switch_fi_en turn 1"),
    ("en", "Sorry, can we go on in English? Add five two-kilo tubs of lactose-free sour cream.", "switch_fi_en turn 2"),
    ("en", "That's all, thanks.", "switch_fi_en turn 3, the #85 failure"),
    ("en", "Yes, please send it.", "switch_fi_en turn 4"),
    ("fi", "p02", ""),
    ("en", "That's all, thanks.", "right after Finnish"),
    ("fi", "p03", ""),
    ("en", "No, nothing else.", "in no variant"),
    ("fi", "p04", ""),
    ("en", "Okay, sounds good.", "in no variant"),
    ("fi", "p05", ""),
    ("en", "Yes, please send it.", "right after Finnish"),
    ("fi", "p06", ""),
    ("fi", "p07", ""),
    ("fi", "p08", ""),
    ("fi", "p09", ""),
    ("fi", "p10", ""),
    ("en", "That's it for today.", "in no variant"),
    ("en", "en01", "English after Finnish"),
    ("fi", "Ei muuta, siinä kaikki.", "short Finnish after English"),
    ("fi", "Joo, lähetä se.", "short Finnish after English"),
]

SCENARIO = Scenario(
    id="vocab_probe",
    title="Vocabulary probe (#116)",
    channel="phone",
    turns=[],
    quote_turn=0,
    yes_turn=0,
    expected_lines=0,
    no_listing=True,
)


def turn_audio(client, ref: str, audio_dir: Path) -> np.ndarray:
    if re.fullmatch(r"(p\d\d|en\d\d)", ref):
        samples, rate = read_wav(audio_dir / f"{ref}.wav")
        return trim_silence(resample(samples, rate, IN_RATE), IN_RATE)
    path = HERE / "audio" / CACHED[ref] if ref in CACHED else TTS_DIR / f"{re.sub(r'\W+', '-', ref.lower()).strip('-')}.wav"
    if not path.exists():
        from tts import decode_audio, synth_interactions

        raw = synth_interactions(client, TTS_MODEL, ref, CALLER_VOICE, "a busy kitchen manager on the phone")
        samples, rate = decode_audio(raw)
        write_wav(path, trim_silence(resample(samples, rate, IN_RATE), IN_RATE), IN_RATE)
    samples, _ = read_wav(path)
    return samples


# --- Scoring -----------------------------------------------------------------------------


SHORT_WORDS = 5  # a line of at most this many words is a short line


def score(rows: list[dict]) -> dict:
    """Short lines (at most five words) are right when the caption's WER is at most 0.25 ("That's all. Thanks."
    passes, "Tässä on. Thanks." doesn't). Key terms and WER are over the #51 phrases."""
    phrases = {p.id: p for p in load_phrases(include_extra=True)}
    for r in rows:
        p = phrases.get(r["ref"])
        heard = r["heard"]
        if p:
            hits, missed = term_hits(p, heard)
            r.update(text=p.text, wer=round(best_wer(p, heard), 3), terms=f"{hits}/{len(p.terms)}", missed=missed)
            r["right"] = None
        else:
            r.update(text=r["ref"], wer=round(wer(r["ref"], heard), 3), terms="", missed=[])
            r["right"] = r["wer"] <= 0.25 if len(r["ref"].split()) <= SHORT_WORDS else None
    short_en = [r for r in rows if r["right"] is not None and r["lang"] == "en"]
    short_fi = [r for r in rows if r["right"] is not None and r["lang"] == "fi"]
    named = [r for r in rows if r["terms"]]
    hits = sum(int(r["terms"].split("/")[0]) for r in named)
    total = sum(int(r["terms"].split("/")[1]) for r in named)
    wers = [r["wer"] for r in named]
    return {
        "switch_fi_en_turn3": rows[2]["heard"] if len(rows) > 2 else "",
        "short_en_right": f"{sum(r['right'] for r in short_en)}/{len(short_en)}",
        "short_fi_right": f"{sum(r['right'] for r in short_fi)}/{len(short_fi)}",
        "key_terms": f"{hits}/{total}",
        "mean_wer": round(sum(wers) / len(wers), 3) if wers else None,
    }


def report(out_dir: Path, meta: dict, rows: list[dict]) -> None:
    summary = score(rows)
    md = [
        f"# Vocabulary probe {out_dir.name}",
        "",
        f"Variant `{meta['variant']}` ({len(meta['vocabulary'])} terms), model `{meta['model']}`, audio `{meta['audio_dir']}`",
        "",
        f"Vocabulary: {', '.join(meta['vocabulary']) or '(none)'}",
        "",
        f'- switch_fi_en turn 3 ("That\'s all, thanks."): {summary["switch_fi_en_turn3"]}',
        f"- Short English lines right: {summary['short_en_right']}",
        f"- Short Finnish lines after English right: {summary['short_fi_right']}",
        f"- Key terms (#51 phrases): {summary['key_terms']}, mean WER {summary['mean_wer']}",
        "",
        "| # | Lang | Said | Heard | WER | Terms | Right | Note |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        right = "" if r["right"] is None else ("yes" if r["right"] else "**no**")
        terms = r["terms"] + (f" (missed {', '.join(r['missed'])})" if r["missed"] else "")
        md.append(
            f"| {r['index']} | {r['lang']} | {r['text']} | {r['heard']} | {r['wer']:.2f} | {terms} | {right} | {r['note']} |"
        )
    md += ["", "S.I.MO's replies:", ""]
    md += [f"- {r['index']}: {r['agent']}" + (f" (tools: {', '.join(r['tools'])})" if r["tools"] else "") for r in rows]
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "results.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    (out_dir / "results.json").write_text(
        json.dumps({"meta": meta, "summary": summary, "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("\n".join(md[:11]))
    print(f"Saved to {out_dir}")


# --- The call ----------------------------------------------------------------------------


def sessions_used() -> int:
    return len(SESSIONS_LOG.read_text().splitlines()) if SESSIONS_LOG.exists() else 0


async def run(args) -> None:
    vocabulary = VARIANTS[args.variant]()
    audio_dir = Path(args.audio_dir).resolve()
    if args.budget and sessions_used() >= args.budget:
        raise SystemExit(f"{sessions_used()} Live sessions in {SESSIONS_LOG}, budget {args.budget}: not starting another")
    use_mcp_descriptions()
    client = make_client()
    speech = [turn_audio(client, ref, audio_dir) for _, ref, _ in TURNS]
    today = date.fromisoformat(args.today) if args.today else date.today()
    result = CallResult(scenario=SCENARIO.id, mode=f"audio-real-{args.variant}", model=LIVE_MODEL)
    service = StubService(SCENARIO, today)
    config = types.LiveConnectConfig(
        response_modalities=[types.Modality.AUDIO],
        system_instruction=build_system_prompt(CONTEXT, "phone", "auto", today=today),
        input_audio_transcription=types.AudioTranscriptionConfig(custom_vocabulary=vocabulary or None),
        output_audio_transcription=types.AudioTranscriptionConfig(),
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=VOICE))
        ),
        tools=[types.Tool(function_declarations=declarations("phone"))],
    )
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = OUT_DIR / f"{stamp}-{args.variant}"
    meta = {
        "variant": args.variant,
        "vocabulary": vocabulary,
        "model": LIVE_MODEL,
        "audio_dir": args.audio_dir,
        "time": stamp,
    }
    rows: list[dict] = []
    log_session(SCENARIO.id, result.mode)
    try:
        async with client.aio.live.connect(model=LIVE_MODEL, config=config) as session:
            call = LiveCall(session, service, result)
            receiver = asyncio.create_task(call.receive())
            try:
                call.start_turn(0, CALL_CONNECTED)
                await session.send_realtime_input(text=CALL_CONNECTED)
                await call.wait_turn(30)
                for i, ((lang, ref, note), samples) in enumerate(zip(TURNS, speech, strict=True), 1):
                    turn = call.start_turn(i, ref)
                    sender = asyncio.create_task(send_audio(call, samples, timeout_s=args.turn_timeout))
                    await call.wait_turn(args.turn_timeout + len(samples) / IN_RATE)
                    await sender
                    # The caption can come after the reply (session 4 of #116 got p02's
                    # caption in the next turn), so give it a moment before the next turn.
                    for _ in range(30):
                        if turn.heard.strip():
                            break
                        await asyncio.sleep(0.1)
                    rows.append(
                        {
                            "index": i,
                            "lang": lang,
                            "ref": ref,
                            "note": note,
                            "heard": turn.heard.strip(),
                            "agent": turn.agent.strip(),
                            "tools": [c["name"] for c in turn.tool_calls],
                            "timed_out": turn.timed_out,
                        }
                    )
                    print(f"[{i}] {lang} {ref}\n     heard: {turn.heard.strip()}\n     agent: {turn.agent.strip()[:120]}")
            finally:
                receiver.cancel()
                await asyncio.gather(receiver, return_exceptions=True)
    except Exception as exc:  # noqa: BLE001 - report what came through
        if is_rate_limit(exc):
            print(f"Rate limited, stopping: {exc}")
        meta["error"] = f"{type(exc).__name__}: {exc}"
        if not rows:
            raise RateLimited(str(exc)) if is_rate_limit(exc) else exc
    report(out_dir, meta, rows)
    print(f"Live sessions logged so far: {sessions_used()}")


def recheck(out_dir: Path) -> None:
    data = json.loads((out_dir / "results.json").read_text(encoding="utf-8"))
    report(out_dir, data["meta"], data["rows"])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--variant", choices=sorted(VARIANTS), default="relay")
    ap.add_argument("--audio-dir", default="recordings/jesse", help="the #51 phrases in a real voice (DIR/<id>.wav)")
    ap.add_argument("--today", help="business date, YYYY-MM-DD (default: today)")
    ap.add_argument("--turn-timeout", type=float, default=45.0, help="seconds to wait for each reply")
    ap.add_argument("--budget", type=int, default=0, help="don't start if sessions.log already has this many sessions")
    ap.add_argument("--list", action="store_true", help="print the variants and the turns, call nothing")
    ap.add_argument("--recheck", metavar="DIR", help="score a saved run in DIR again, call nothing")
    args = ap.parse_args()
    if args.list:
        for name, terms in VARIANTS.items():
            print(f"{name} ({len(terms())}): {', '.join(terms())}")
        for i, (lang, ref, note) in enumerate(TURNS, 1):
            print(f"{i:2d} {lang} {ref}  {note}")
        return
    if args.recheck:
        recheck(Path(args.recheck))
        return
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
