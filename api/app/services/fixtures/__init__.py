"""Small fixture files that stand in for the real data: the usual items (until #32, #61)
and the recipes."""

import json
from functools import cache
from pathlib import Path
from typing import Any

FIXTURES = Path(__file__).parent


@cache
def load(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))
