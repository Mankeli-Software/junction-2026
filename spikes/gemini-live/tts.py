"""Turn the test phrases into 16 kHz 16-bit mono WAVs with Gemini TTS.

    uv run tts.py                     # all Finnish phrases plus the English extra
    uv run tts.py --voice Puck --only p01 p02

Output: audio/tts/<id>.wav (git-ignored). The raw 24 kHz TTS output is kept as
audio/tts/raw/<id>.wav so resampling can be checked by ear.
"""

from __future__ import annotations

import argparse
import base64
import io
import sys
import wave

import numpy as np

from common import HERE, IN_RATE, TTS_MODEL, load_phrases, make_client, resample, trim_silence, write_wav

OUT_DIR = HERE / "audio" / "tts"


def decode_audio(data: bytes, default_rate: int = 24_000) -> tuple[np.ndarray, int]:
    """Accept either a RIFF/WAV container or headerless 16-bit PCM."""
    if data[:4] == b"RIFF":
        with wave.open(io.BytesIO(data), "rb") as w:
            rate, channels = w.getframerate(), w.getnchannels()
            samples = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2")
        if channels > 1:
            samples = samples.reshape(-1, channels).mean(axis=1).astype("<i2")
        return samples, rate
    return np.frombuffer(data, dtype="<i2"), default_rate


def synth_interactions(client, model: str, text: str, voice: str, style: str) -> bytes:
    """The documented TTS path for the 3.8 TTS models (client.interactions)."""
    content = {"type": "text", "text": text}
    if style:
        content["annotations"] = [{"type": "speech_metadata", "style": style}]
    interaction = client.interactions.create(
        model=model,
        input=[{"type": "user_input", "content": [content]}],
        response_format={"type": "audio"},
        generation_config={"speech_config": [{"voice": voice}]},
    )
    data = interaction.output_audio.data
    return base64.b64decode(data) if isinstance(data, str) else data


def synth_generate_content(client, model: str, text: str, voice: str, style: str) -> bytes:
    """Older generate_content TTS path, used if the interactions call fails."""
    from google.genai import types

    prompt = f"Say in a {style} way: {text}" if style else text
    resp = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice))
            ),
        ),
    )
    return resp.candidates[0].content.parts[0].inline_data.data


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", default=TTS_MODEL)
    ap.add_argument("--voice", default="Achird", help="TTS voice for the 'caller' (default: Achird)")
    ap.add_argument("--style", default="a busy kitchen manager on the phone, natural pace")
    ap.add_argument("--only", nargs="*", help="phrase ids to generate")
    ap.add_argument("--force", action="store_true", help="regenerate files that exist")
    args = ap.parse_args()

    client = make_client()
    phrases = [p for p in load_phrases(include_extra=True) if not args.only or p.id in args.only]
    for p in phrases:
        out = OUT_DIR / f"{p.id}.wav"
        if out.exists() and not args.force:
            print(f"{p.id}: exists, skipping")
            continue
        try:
            raw = synth_interactions(client, args.model, p.text, args.voice, args.style)
            path = "interactions"
        except Exception as exc:  # noqa: BLE001 - fall back and report which path worked
            print(f"{p.id}: interactions TTS failed ({type(exc).__name__}: {exc}); trying generate_content",
                  file=sys.stderr)
            raw = synth_generate_content(client, args.model, p.text, args.voice, args.style)
            path = "generate_content"
        samples, rate = decode_audio(raw)
        write_wav(OUT_DIR / "raw" / f"{p.id}.wav", samples, rate)
        pcm16k = trim_silence(resample(samples, rate, IN_RATE), IN_RATE)
        write_wav(out, pcm16k, IN_RATE)
        print(f"{p.id}: {len(pcm16k) / IN_RATE:.2f} s at {IN_RATE} Hz (from {rate} Hz, via {path})")


if __name__ == "__main__":
    main()
