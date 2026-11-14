"""Shared helpers for the Gemini Live spike (#51): key loading, audio I/O, scoring."""

from __future__ import annotations

import json
import os
import re
import sys
import unicodedata
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
PHRASES_FILE = HERE / "phrases.fi.json"
KEY_FILE = Path.home() / ".config" / "junction-2026" / "gemini.env"

# Model ids checked against Google's docs on 2026-11-14 (see README "Sources").
LIVE_MODEL = "gemini-3.8-live"
TTS_MODEL = "gemini-3.8-flash-tts"

IN_RATE = 16_000  # Live API input: 16-bit little-endian mono PCM
OUT_RATE = 24_000  # Live API output: 16-bit little-endian mono PCM


# --- API key -----------------------------------------------------------------


def _key_from_file(path: Path) -> str:
    """The GEMINI_API_KEY value in a dotenv-style file, or "" if absent or empty."""
    if not path.is_file():
        return ""
    for line in path.read_text().splitlines():
        line = line.strip()
        if line.startswith("export "):
            line = line[len("export ") :]
        if line.startswith("GEMINI_API_KEY="):
            return line.split("=", 1)[1].strip().strip("'\"")
    return ""


def load_api_key() -> str:
    """Find GEMINI_API_KEY, skipping empty values, in this order:

    1. the GEMINI_API_KEY environment variable;
    2. a .env file in this folder or any parent (the repo root's git-ignored .env;
       from a worktree under .claude/worktrees/ the walk reaches the main checkout's);
    3. ~/.config/junction-2026/gemini.env.

    The key is never printed. Exits with a clear message when it is missing.
    """
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    for directory in (HERE, *HERE.parents):
        if key:
            break
        key = _key_from_file(directory / ".env")
    if not key:
        key = _key_from_file(KEY_FILE)
    if not key:
        sys.exit(f"No GEMINI_API_KEY in the environment, in a .env above {HERE} or in {KEY_FILE}.")
    return key


def make_client():
    from google import genai

    # v1beta: with the SDK's default (v1) the Live and TTS models are not even listed.
    return genai.Client(api_key=load_api_key(), http_options={"api_version": "v1beta"})


# --- Phrases -----------------------------------------------------------------


@dataclass
class Phrase:
    id: str
    text: str
    written: list[str]
    terms: list[list[str]]
    lang: str = "fi"


def load_phrases(include_extra: bool = False) -> list[Phrase]:
    data = json.loads(PHRASES_FILE.read_text(encoding="utf-8"))
    items = data["phrases"] + (data.get("extra", []) if include_extra else [])
    return [
        Phrase(
            id=p["id"],
            text=p["text"],
            written=p.get("written", []),
            terms=p["terms"],
            lang=p.get("lang", "fi"),
        )
        for p in items
    ]


def custom_vocabulary() -> list[str]:
    return json.loads(PHRASES_FILE.read_text(encoding="utf-8")).get("custom_vocabulary", [])


# --- Audio -------------------------------------------------------------------


def read_wav(path: Path) -> tuple[np.ndarray, int]:
    """Return mono int16 samples and the sample rate."""
    with wave.open(str(path), "rb") as w:
        if w.getsampwidth() != 2:
            raise ValueError(f"{path}: expected 16-bit PCM, got {8 * w.getsampwidth()}-bit")
        rate = w.getframerate()
        channels = w.getnchannels()
        data = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2")
    if channels > 1:
        data = data.reshape(-1, channels).mean(axis=1).astype("<i2")
    return data, rate


def write_wav(path: Path, samples: np.ndarray | bytes, rate: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = samples if isinstance(samples, bytes) else np.asarray(samples, dtype="<i2").tobytes()
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(raw)


def resample(samples: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    """Band-limited resampling in numpy (no ffmpeg/scipy).

    Windowed-sinc low-pass at the lower Nyquist, then linear interpolation onto the
    new grid. Good enough for speech going into an ASR model.
    """
    if src_rate == dst_rate:
        return samples.astype("<i2")
    x = samples.astype(np.float64)
    cutoff = 0.5 * min(src_rate, dst_rate) * 0.95  # Hz, a little under Nyquist
    if dst_rate < src_rate:
        taps = 101
        n = np.arange(taps) - (taps - 1) / 2
        h = np.sinc(2 * cutoff / src_rate * n) * np.hamming(taps)
        h /= h.sum()
        x = np.convolve(x, h, mode="same")
    duration = len(x) / src_rate
    n_out = int(round(duration * dst_rate))
    t_out = np.arange(n_out) / dst_rate
    t_in = np.arange(len(x)) / src_rate
    y = np.interp(t_out, t_in, x)
    return np.clip(np.round(y), -32768, 32767).astype("<i2")


def trim_silence(samples: np.ndarray, rate: int, threshold_db: float = -45.0, keep_ms: int = 100) -> np.ndarray:
    """Trim leading and trailing silence, keeping `keep_ms` on each side."""
    if len(samples) == 0:
        return samples
    frame = int(rate * 0.01)
    x = samples.astype(np.float64) / 32768.0
    n_frames = len(x) // frame
    if n_frames == 0:
        return samples
    rms = np.sqrt(np.mean(x[: n_frames * frame].reshape(n_frames, frame) ** 2, axis=1) + 1e-12)
    loud = np.where(20 * np.log10(rms) > threshold_db)[0]
    if len(loud) == 0:
        return samples
    keep = int(rate * keep_ms / 1000)
    start = max(0, loud[0] * frame - keep)
    end = min(len(samples), (loud[-1] + 1) * frame + keep)
    return samples[start:end]


# --- Scoring -----------------------------------------------------------------


def normalise(text: str) -> str:
    """Lowercase, NFC, hyphens to spaces, punctuation out (keep decimal commas/points)."""
    t = unicodedata.normalize("NFC", text).lower()
    t = t.replace("®", "").replace("™", "")
    t = re.sub(r"(?<=\d)[,.](?=\d)", "<dec>", t)  # protect 2,5 and 2.5
    t = re.sub(r"[-‐–—/]", " ", t)
    t = re.sub(r"[^\w\s%<>]", " ", t)
    t = t.replace("<dec>", ",")
    return re.sub(r"\s+", " ", t).strip()


def wer(reference: str, hypothesis: str) -> float:
    ref = normalise(reference).split()
    hyp = normalise(hypothesis).split()
    if not ref:
        return 0.0 if not hyp else 1.0
    prev = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        cur = [i] + [0] * len(hyp)
        for j, h in enumerate(hyp, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (r != h))
        prev = cur
    return prev[-1] / len(ref)


def best_wer(phrase: Phrase, hypothesis: str) -> float:
    return min(wer(ref, hypothesis) for ref in [phrase.text, *phrase.written])


def term_hits(phrase: Phrase, hypothesis: str) -> tuple[int, list[str]]:
    """Count key terms found; return (hits, missed terms). Compounds may be split or joined."""
    hyp = normalise(hypothesis)
    hyp_joined = hyp.replace(" ", "")
    missed = []
    for alternatives in phrase.terms:
        ok = any(
            normalise(alt) in hyp or normalise(alt).replace(" ", "") in hyp_joined for alt in alternatives
        )
        if not ok:
            missed.append(alternatives[0])
    return len(phrase.terms) - len(missed), missed


def median(values: list[float]) -> float | None:
    v = sorted(x for x in values if x is not None)
    if not v:
        return None
    mid = len(v) // 2
    return v[mid] if len(v) % 2 else (v[mid - 1] + v[mid]) / 2


def system_instruction(extra: str = "") -> str:
    """Short Finnish system prompt for S.I.MO, the stand-in for the real one (#53)."""
    base = (
        "Olet S.I.MO, Valio Aimon tekoälyavustaja, joka ottaa vastaan ammattikeittiöiden "
        "tilauksia puhelimessa. Puhu suomea, ellei soittaja puhu muuta kieltä. "
        "Vastaa lyhyesti ja luontevasti, yksi tai kaksi lausetta kerrallaan. "
        "Toista tilausrivit lyhyesti, jotta soittaja voi tarkistaa, että kuulit oikein: "
        "tuote, määrä ja yksikkö. Älä koskaan sano, että tilaus on tehty."
    )
    return f"{base} {extra}".strip()
