"""Have S.I.MO say one Finnish reply in a few Live voices, to pick the most natural one.

    uv run voices.py                               # Kore, Aoede, Sulafat, Achird, Charon
    uv run voices.py --voices Puck Zephyr --asr-model gemini-3.8-flash

Listen to out/voices/<time>/<voice>.wav and judge by ear. As a rough intelligibility
check, each reply is also transcribed back with a text model (--asr-model) and
compared with what the voice was asked to say, and the same model rates how native each
clip sounds in one extra request (a hint only; listen yourself).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from datetime import datetime

from google.genai import types

from common import HERE, LIVE_MODEL, OUT_RATE, make_client, wer, write_wav
from live import live_config

REPLY = (
    "Selvä. Eli kaksi laatikkoa Valio Eila laktoositonta kevytmaitojuomaa ja kymmenen litraa "
    "ruokakermaa, toimitus torstaina. Lähetänkö vahvistuslinkin puhelimeesi?"
)
PROMPT = f"Sano soittajalle täsmälleen tämä, sanasta sanaan, äläkä lisää mitään: {REPLY}"


async def speak(client, model: str, voice: str) -> dict:
    config = live_config(voice=voice)
    audio = bytearray()
    text = ""
    first_audio = None
    async with client.aio.live.connect(model=model, config=config) as session:
        t0 = time.monotonic()
        await session.send_client_content(
            turns=types.Content(role="user", parts=[types.Part(text=PROMPT)]), turn_complete=True
        )
        async for msg in session.receive():
            sc = msg.server_content
            if not sc:
                continue
            if sc.model_turn:
                for part in sc.model_turn.parts or []:
                    if part.inline_data and part.inline_data.data:
                        first_audio = first_audio or time.monotonic() - t0
                        audio.extend(part.inline_data.data)
            if sc.output_transcription and sc.output_transcription.text:
                text += sc.output_transcription.text
    return {"voice": voice, "audio": bytes(audio), "transcript": text.strip(), "first_audio_s": first_audio}


def transcribe(client, model: str, wav_bytes: bytes) -> str:
    resp = client.models.generate_content(
        model=model,
        contents=[
            types.Part.from_bytes(data=wav_bytes, mime_type="audio/wav"),
            "Litteroi tämä suomenkielinen puhe sanasta sanaan. Palauta vain teksti.",
        ],
    )
    return (resp.text or "").strip()


def rate(client, model: str, wavs: list) -> str:
    """One request: a text model rates how native each clip's Finnish sounds. A hint, not a human judgement."""
    parts: list = []
    for i, w in enumerate(wavs, 1):
        parts += [f"Clip {i}: voice {w.stem}", types.Part.from_bytes(data=w.read_bytes(), mime_type="audio/wav")]
    parts.append(
        "All clips say the same Finnish sentence. As a native Finnish listener would, rate each clip 1-5 for how "
        "natural and native the Finnish sounds (vowel length, double consonants, stress on the first syllable, "
        "intonation, any foreign accent). One line per voice: name, score, one short reason. Then name the best one."
    )
    return client.models.generate_content(model=model, contents=parts).text or ""


async def main_async(args) -> None:
    client = make_client()
    out_dir = HERE / "out" / "voices" / datetime.now().strftime("%Y%m%d-%H%M%S")
    rows = []
    for voice in args.voices:
        try:
            r = await speak(client, args.model, voice)
        except Exception as exc:  # noqa: BLE001
            print(f"{voice}: ERROR {type(exc).__name__}: {exc}")
            continue
        path = out_dir / f"{voice}.wav"
        write_wav(path, r["audio"], OUT_RATE)
        row = {
            "voice": voice,
            "first_audio_s": r["first_audio_s"],
            "seconds": round(len(r["audio"]) / 2 / OUT_RATE, 2),
            "output_transcript": r["transcript"],
            "output_transcript_wer": round(wer(REPLY, r["transcript"]), 3),
        }
        if args.asr_model:
            try:
                heard = transcribe(client, args.asr_model, path.read_bytes())
                row.update(asr_heard=heard, asr_wer=round(wer(REPLY, heard), 3))
            except Exception as exc:  # noqa: BLE001
                row["asr_error"] = f"{type(exc).__name__}: {exc}"
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False))
        await asyncio.sleep(1.0)
    if args.asr_model and rows:
        try:
            rating = rate(client, args.asr_model, [out_dir / f"{r['voice']}.wav" for r in rows])
            (out_dir / "model_rating.txt").write_text(rating)
            print(rating)
        except Exception as exc:  # noqa: BLE001
            print(f"rating failed: {type(exc).__name__}: {exc}")
    (out_dir / "results.json").write_text(
        json.dumps({"model": args.model, "reply": REPLY, "rows": rows}, ensure_ascii=False, indent=2)
    )
    print(f"Saved to {out_dir.relative_to(HERE)}; listen to the WAVs to judge naturalness.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", default=LIVE_MODEL)
    ap.add_argument("--voices", nargs="*", default=["Kore", "Aoede", "Sulafat", "Achird", "Charon"])
    ap.add_argument("--asr-model", default=None, help="text model for the round-trip check, e.g. a Flash model")
    asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    main()
