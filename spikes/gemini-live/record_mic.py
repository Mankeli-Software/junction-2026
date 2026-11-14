"""Record the test phrases in your own voice, then score them the same way as the TTS audio.

    uv run --extra mic record_mic.py --speaker jesse             # record all, then evaluate
    uv run --extra mic record_mic.py --speaker jesse --only p03  # re-record one phrase
    uv run --extra mic record_mic.py --list-devices

For each phrase: read the text, press Enter, say it naturally (as on the phone),
press Enter again. Audio is saved as 16 kHz mono WAV in recordings/<speaker>/,
which is git-ignored: never commit recordings of a real voice. Afterwards the
script runs run_live.py on that folder (skip with --no-evaluate).
"""

from __future__ import annotations

import argparse
import subprocess
import sys

import numpy as np

from common import HERE, IN_RATE, load_phrases, resample, write_wav


def record_until_enter(device, rate: int) -> np.ndarray:
    import sounddevice as sd

    chunks: list[np.ndarray] = []

    def callback(indata, frames, time_info, status):  # noqa: ARG001
        if status:
            print(f"  ({status})", file=sys.stderr)
        chunks.append(indata[:, 0].copy())

    with sd.InputStream(samplerate=rate, channels=1, dtype="int16", device=device, callback=callback):
        input("  Recording... press Enter when done. ")
    return np.concatenate(chunks) if chunks else np.zeros(0, dtype="int16")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--speaker", default="me", help="folder name under recordings/")
    ap.add_argument("--only", nargs="*", help="phrase ids")
    ap.add_argument("--extra", action="store_true", help="also record the English extra phrase")
    ap.add_argument("--device", default=None, help="input device index or name (see --list-devices)")
    ap.add_argument("--rate", type=int, default=None, help="capture rate (default: the device's own)")
    ap.add_argument("--list-devices", action="store_true")
    ap.add_argument("--no-evaluate", action="store_true")
    args = ap.parse_args()

    import sounddevice as sd

    if args.list_devices:
        print(sd.query_devices())
        return
    device = int(args.device) if args.device and args.device.isdigit() else args.device
    rate = args.rate or int(sd.query_devices(device, "input")["default_samplerate"])
    out_dir = HERE / "recordings" / args.speaker
    phrases = [p for p in load_phrases(include_extra=args.extra) if not args.only or p.id in args.only]

    print(f"Recording {len(phrases)} phrases at {rate} Hz into {out_dir.relative_to(HERE)}/")
    for p in phrases:
        print(f"\n[{p.id}] {p.text}")
        while True:
            input("  Press Enter to start. ")
            samples = record_until_enter(device, rate)
            seconds = len(samples) / rate
            peak = int(np.abs(samples).max()) if len(samples) else 0
            print(f"  {seconds:.1f} s, peak {peak}/32767")
            if peak < 500:
                print("  That was nearly silent; check the microphone.")
            if input("  Keep it? [Y/n] ").strip().lower() in ("", "y", "yes", "k", "kyllä"):
                break
        write_wav(out_dir / f"{p.id}.wav", resample(samples, rate, IN_RATE), IN_RATE)

    if not args.no_evaluate:
        cmd = [sys.executable, str(HERE / "run_live.py"), "--audio-dir", str(out_dir), "--label", f"mic-{args.speaker}"]
        if args.only:
            cmd += ["--only", *args.only]
        if args.extra:
            cmd.append("--extra")
        subprocess.run(cmd, check=False)


if __name__ == "__main__":
    main()
