"""List the Live, TTS and audio models this API key can use.

    uv run check_models.py          # Live/TTS/audio models only
    uv run check_models.py --all    # every model
"""

from __future__ import annotations

import argparse

from common import make_client

KEYWORDS = ("live", "tts", "audio", "transcribe")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()
    client = make_client()
    for m in client.models.list():
        name = (m.name or "").removeprefix("models/")
        if not args.all and not any(k in name for k in KEYWORDS):
            continue
        actions = ",".join(m.supported_actions or [])
        print(f"{name:55s} {actions}")


if __name__ == "__main__":
    main()
