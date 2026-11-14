"""The dashboard models read the UI's fixtures (`web/src/lib/dashboard/fixtures`) unchanged.

The UI was built against those fixtures, so a model that rejects one, or dumps it
differently, would break a screen.
"""

import json
from pathlib import Path

import pytest
from pydantic import TypeAdapter

from app.schemas import (
    STATE_GROUPS,
    AuditEvent,
    OrderSummary,
    OverviewResponse,
    SessionState,
    StateGroup,
    TranscriptLine,
)

FIXTURES = Path(__file__).resolve().parents[2] / "web" / "src" / "lib" / "dashboard" / "fixtures"

CASES = [
    ("overview.json", OverviewResponse),
    ("d1042-summary.json", OrderSummary),
    ("d1042-events.json", list[AuditEvent]),
    ("d1042-events-tampered.json", list[AuditEvent]),
    ("live-call-events.json", list[AuditEvent]),
    ("d1042-transcript.json", list[TranscriptLine]),
    ("live-call-transcript.json", list[TranscriptLine]),
]


@pytest.mark.parametrize(("name", "model"), CASES, ids=[c[0] for c in CASES])
def test_ui_fixture_round_trips(name, model):
    path = FIXTURES / name
    if not path.exists():
        pytest.skip("the web fixtures are not in this checkout")
    raw = json.loads(path.read_text())
    adapter = TypeAdapter(model)
    dumped = json.loads(adapter.dump_json(adapter.validate_python(raw)))
    assert dumped == _without_absent_defaults(raw, dumped)


def _without_absent_defaults(raw, dumped):
    """The fixture, plus the optional fields the dump fills in with their defaults."""
    if isinstance(raw, dict) and isinstance(dumped, dict):
        merged = {k: _without_absent_defaults(raw[k], dumped[k]) for k in raw}
        for key, value in dumped.items():
            if key not in raw:
                assert value in (None, []), f"{key} has no default"
                merged[key] = value
        return merged
    if isinstance(raw, list) and isinstance(dumped, list):
        return [_without_absent_defaults(r, d) for r, d in zip(raw, dumped, strict=True)]
    return raw


def test_every_state_but_cancelled_and_abandoned_has_a_group():
    ungrouped = set(SessionState) - set(STATE_GROUPS)
    assert ungrouped == {SessionState.cancelled, SessionState.abandoned}
    assert set(STATE_GROUPS.values()) == set(StateGroup)
