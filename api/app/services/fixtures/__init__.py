"""Small fixture files that stand in for the real data until #29, #30, #31, #44 and #45."""

import json
from functools import cache
from pathlib import Path
from typing import Any

FIXTURES = Path(__file__).parent


@cache
def load(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))
