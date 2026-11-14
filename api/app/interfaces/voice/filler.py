"""The filler line S.I.MO says when a tool call takes a while (#52).

The #51 spike found that Gemini stays silent while a blocking tool call runs, even when
told to talk, so the relay itself plays a short line into the call: one fixed clip per
language, made once with Gemini TTS in the call's voice and committed next to this file
(`filler_clips/<voice>-<lang>.wav`, 24 kHz 16-bit mono, the format the call screen
plays). A pre-made clip costs no model time, can't say anything unexpected and starts at
once. Decided with the team on 2026-11-14: the words below, at most once per tool call,
in the language of the caller's last caption, shown as an S.I.MO caption and written as
`agent_said`.

Make the clips for a new voice (needs GEMINI_API_KEY; a few TTS requests, no Live
session):

    uv run python -m app.interfaces.voice.filler --voice Achird
"""

import argparse
import base64
import io
import logging
import wave
from functools import cache
from pathlib import Path

from app.schemas import Lang

log = logging.getLogger(__name__)

CLIP_DIR = Path(__file__).resolve().parent / "filler_clips"
RATE = 24_000
TTS_MODEL = "gemini-3.8-flash-tts"

TEXT: dict[Lang, str] = {
    "fi": "Hetki, tarkistan.",
    "en": "One moment, let me check.",
}
_STYLE = "a friendly, calm phone assistant, natural pace, short and light"


def clip_path(voice: str, lang: Lang) -> Path:
    return CLIP_DIR / f"{voice.lower()}-{lang}.wav"


@cache
def clip(voice: str, lang: Lang) -> bytes | None:
    """The clip's 24 kHz PCM, or None when there is no clip for this voice yet."""
    path = clip_path(voice, lang)
    if not path.is_file():
        log.warning("No filler clip %s; the relay plays no filler line", path.name)
        return None
    with wave.open(str(path), "rb") as w:
        if w.getframerate() != RATE or w.getsampwidth() != 2 or w.getnchannels() != 1:
            log.warning("Filler clip %s is not 24 kHz 16-bit mono; skipped", path.name)
            return None
        return w.readframes(w.getnframes())


def _decode(data: bytes) -> tuple[bytes, int]:
    if data[:4] == b"RIFF":
        with wave.open(io.BytesIO(data), "rb") as w:
            return w.readframes(w.getnframes()), w.getframerate()
    return data, RATE


def _trim(pcm: bytes, threshold: int = 300, keep_ms: int = 60) -> bytes:
    """Cuts leading and trailing near-silence, keeping a short margin."""
    samples = memoryview(pcm).cast("h")
    loud = [i for i, s in enumerate(samples) if abs(s) > threshold]
    if not loud:
        return pcm
    keep = RATE * keep_ms // 1000
    start = max(0, loud[0] - keep)
    end = min(len(samples), loud[-1] + keep)
    return pcm[start * 2 : end * 2]


def make_clips(voice: str) -> None:
    from google import genai

    from app.settings import get_settings

    client = genai.Client(
        api_key=get_settings().gemini_api_key, http_options={"api_version": "v1beta"}
    )
    CLIP_DIR.mkdir(exist_ok=True)
    for lang, text in TEXT.items():
        interaction = client.interactions.create(
            model=TTS_MODEL,
            input=[
                {
                    "type": "user_input",
                    "content": [
                        {
                            "type": "text",
                            "text": text,
                            "annotations": [{"type": "speech_metadata", "style": _STYLE}],
                        }
                    ],
                }
            ],
            response_format={"type": "audio"},
            generation_config={"speech_config": [{"voice": voice}]},
        )
        data = interaction.output_audio.data
        pcm, rate = _decode(base64.b64decode(data) if isinstance(data, str) else data)
        if rate != RATE:
            raise SystemExit(f"TTS returned {rate} Hz, expected {RATE}")
        pcm = _trim(pcm)
        path = clip_path(voice, lang)
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(RATE)
            w.writeframes(pcm)
        print(f"{path.name}: {len(pcm) / 2 / RATE:.2f} s, {text!r}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Make the filler clips for one voice.")
    parser.add_argument("--voice", default=None, help="default: VOICE_NAME from the settings")
    args = parser.parse_args()
    if args.voice is None:
        from app.settings import get_settings

        args.voice = get_settings().voice_name
    make_clips(args.voice)


if __name__ == "__main__":
    main()
