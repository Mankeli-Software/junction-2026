"""Run the phrases through Gemini Live and score transcription accuracy and latency.

    uv run run_live.py                         # TTS audio in audio/tts/, baseline config
    uv run run_live.py --vocab --label vocab   # with custom_vocabulary for product names
    uv run run_live.py --tools --label tools   # also declare build_quote and score its arguments
    uv run run_live.py --audio-dir recordings/jesse --label jesse   # your own voice

One fresh session per phrase. Output goes to out/runs/<time>-<label>/: results.json
(everything, including an event timeline), results.md (the table) and the agent's
replies as 24 kHz WAVs.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime
from pathlib import Path

from google.genai import types

from common import (
    HERE,
    LIVE_MODEL,
    OUT_RATE,
    Phrase,
    best_wer,
    load_phrases,
    make_client,
    median,
    read_wav,
    resample,
    term_hits,
    write_wav,
)
from live import build_quote_declaration, live_config, run_turn, stub_quote_result


def args_text(tool_calls: list[dict]) -> str:
    """Flatten build_quote arguments into text so the key-term check can run on them."""
    parts = []
    for call in tool_calls:
        a = call.get("args") or {}
        for line in a.get("lines", []) or []:
            q = line.get("quantity")
            if isinstance(q, float) and q.is_integer():
                q = int(q)
            q_text = str(q).replace(".", ",") if q is not None else ""
            parts.append(f"{q_text} {line.get('unit', '')} {line.get('product_query', '')}")
        if a.get("delivery_day"):
            parts.append(str(a["delivery_day"]))
    return " | ".join(parts)


def fmt(x: float | None, digits: int = 2) -> str:
    return "-" if x is None else f"{x:.{digits}f}"


async def main_async(args) -> None:
    client = make_client()
    audio_dir = (HERE / args.audio_dir) if not Path(args.audio_dir).is_absolute() else Path(args.audio_dir)
    phrases: list[Phrase] = [
        p for p in load_phrases(include_extra=args.extra) if not args.only or p.id in args.only
    ]
    tools = [build_quote_declaration()] if args.tools else None
    extra = (
        "Kun soittaja on kertonut tilausrivit, kutsu build_quote heti näillä riveillä."
        if args.tools
        else "Älä kutsu mitään työkaluja."
    )
    config = live_config(
        voice=args.voice,
        vocab=args.vocab,
        lang_codes=args.lang,
        tools=tools,
        extra_instruction=extra,
        silence_ms=args.silence_ms,
    )

    async def on_tool_call(state, fc: types.FunctionCall) -> None:
        await state.respond(
            types.FunctionResponse(id=fc.id, name=fc.name, response=stub_quote_result(fc.args or {}))
        )

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = HERE / "out" / "runs" / f"{stamp}-{args.label}"
    run_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for p in phrases:
        wav = audio_dir / f"{p.id}.wav"
        if not wav.exists():
            print(f"{p.id}: no audio at {wav}, skipping")
            continue
        samples, rate = read_wav(wav)
        samples = resample(samples, rate, 16_000)
        res = await run_turn(
            client,
            args.model,
            config,
            samples,
            chunk_ms=args.chunk_ms,
            stream_end=args.stream_end,
            on_tool_call=on_tool_call if args.tools else None,
        )
        hits, missed = term_hits(p, res.input_text)
        summary = res.summary()
        row = {
            "id": p.id,
            "expected": p.text,
            "heard": res.input_text.strip(),
            "wer": round(best_wer(p, res.input_text), 3) if res.input_text else None,
            "terms_hit": hits,
            "terms_total": len(p.terms),
            "terms_missed": missed,
            "reply": res.output_text.strip(),
            **{k: summary[k] for k in (
                "connect_s", "speech_s", "first_input_transcript", "first_interim_transcript",
                "first_audio", "first_output_transcript", "first_tool_call", "tool_calls",
                "interrupted", "timed_out", "error", "audio_out_s", "events",
            )},
        }
        if args.tools:
            understood = args_text(res.tool_calls)
            a_hits, a_missed = term_hits(p, understood)
            row.update(args_flat=understood, args_terms_hit=a_hits, args_terms_missed=a_missed)
        rows.append(row)
        if res.audio_out:
            write_wav(run_dir / "replies" / f"{p.id}.wav", bytes(res.audio_out), OUT_RATE)
        print(
            f"{p.id}: WER {fmt(row['wer'])}  terms {hits}/{len(p.terms)}  "
            f"first audio {fmt(res.first_audio)} s  first input transcript {fmt(res.first_input_transcript)} s"
            + (f"  ERROR {res.error}" if res.error else "")
            + ("  TIMEOUT" if res.timed_out else "")
        )
        print(f"     heard: {row['heard']}")
        print(f"     reply: {row['reply']}")
        if args.tools:
            print(f"     args : {row.get('args_flat')}  ({row.get('args_terms_hit')}/{len(p.terms)})")
        await asyncio.sleep(args.pause)

    meta = {
        "model": args.model,
        "label": args.label,
        "audio_dir": str(audio_dir.relative_to(HERE)) if audio_dir.is_relative_to(HERE) else str(audio_dir),
        "vocab": args.vocab,
        "lang_codes": args.lang,
        "tools": args.tools,
        "voice": args.voice,
        "chunk_ms": args.chunk_ms,
        "stream_end": args.stream_end,
        "silence_ms": args.silence_ms,
        "time": stamp,
    }
    (run_dir / "results.json").write_text(json.dumps({"meta": meta, "rows": rows}, ensure_ascii=False, indent=2))
    md = render_markdown(meta, rows)
    (run_dir / "results.md").write_text(md)
    print()
    print(md)
    print(f"Saved to {run_dir.relative_to(HERE)}")


def render_markdown(meta: dict, rows: list[dict]) -> str:
    ok = [r for r in rows if not r["error"]]
    lines = [
        f"Run `{meta['label']}`: model `{meta['model']}`, audio `{meta['audio_dir']}`, vocab {meta['vocab']}, "
        f"lang {meta['lang_codes']}, tools {meta['tools']}, chunk {meta['chunk_ms']} ms",
        "",
        "| id | WER | terms | missed | first transcript (s) | first audio (s) | heard |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['id']} | {fmt(r['wer'])} | {r['terms_hit']}/{r['terms_total']} | {', '.join(r['terms_missed'])} "
            f"| {fmt(r['first_input_transcript'])} | {fmt(r['first_audio'])} | {r['heard'] or r['error'] or ''} |"
        )
    wers = [r["wer"] for r in ok if r["wer"] is not None]
    audio = [r["first_audio"] for r in ok if r["first_audio"] is not None]
    hits = sum(r["terms_hit"] for r in ok)
    total = sum(r["terms_total"] for r in ok)
    lines += [
        "",
        f"- Mean WER {fmt(sum(wers) / len(wers) if wers else None)}, median {fmt(median(wers))}; "
        f"key terms {hits}/{total}",
        f"- First audio after end of speech: median {fmt(median(audio))} s, worst {fmt(max(audio) if audio else None)} s "
        f"({len(audio)}/{len(rows)} replies)",
        f"- Connect: median {fmt(median([r['connect_s'] for r in ok if r['connect_s']]))} s",
    ]
    if meta["tools"]:
        a_hits = sum(r.get("args_terms_hit", 0) for r in ok)
        called = sum(1 for r in ok if r["tool_calls"])
        lines.append(f"- build_quote called in {called}/{len(ok)}; key terms in arguments {a_hits}/{total}")
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", default=LIVE_MODEL)
    ap.add_argument("--audio-dir", default="audio/tts")
    ap.add_argument("--label", default="tts")
    ap.add_argument("--only", nargs="*", help="phrase ids")
    ap.add_argument("--extra", action="store_true", help="also run the English extra phrase")
    ap.add_argument("--vocab", action="store_true", help="pass custom_vocabulary to input transcription")
    ap.add_argument("--lang", nargs="*", help="language_codes hint for input transcription, e.g. fi-FI")
    ap.add_argument("--tools", action="store_true", help="declare build_quote and score its arguments")
    ap.add_argument("--voice", default=None, help="Live voice name (default: the model's default)")
    ap.add_argument("--chunk-ms", type=int, default=40, help="audio chunk size sent in real time")
    ap.add_argument("--silence-ms", type=int, default=None, help="VAD silence_duration_ms (default: server's)")
    ap.add_argument("--stream-end", action="store_true", help="send audio_stream_end instead of trailing silence")
    ap.add_argument("--pause", type=float, default=1.0, help="seconds between phrases")
    asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    main()
