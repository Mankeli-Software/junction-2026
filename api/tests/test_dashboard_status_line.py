"""The summary's `status_line` for a confirmed order: singular and plural flag counts."""

import uuid
from datetime import UTC, datetime

import pytest

from app.schemas import Channel, Localized, SessionState, SummaryFlag
from app.services.dashboard.orders import _status_line
from app.services.dashboard.overview import SessionRow

NOW = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)


def _row(state: SessionState) -> SessionRow:
    return SessionRow(
        id=uuid.uuid4(),
        channel=Channel.web_chat,
        stored_channel="web_chat",
        client_name=None,
        stored_state=state,
        state=state,
        state_since=NOW,
        activity=NOW,
        last_activity_at=NOW,
        ended_at=None,
        prompt_version=None,
        company_name="Ravintola Testi",
        exclusions=[],
        identity_masked=None,
        step_text=Localized(fi="odottaa", en="waiting"),
    )


def _flags(checked: int, unchecked: int = 1) -> list[SummaryFlag]:
    return [
        SummaryFlag(
            flag_key=f"flag_{i}",
            code="stock",
            text=Localized(fi="huomio", en="flag"),
            detail=None,
            acknowledged_at=NOW if i < checked else None,
        )
        for i in range(checked + unchecked)
    ]


@pytest.mark.parametrize(
    ("checked", "fi", "en"),
    [
        (0, "ostajan vahvistama", "by the buyer"),
        (1, "ostajan vahvistama, 1 huomio kuitattu", "by the buyer, after checking 1 flag"),
        (2, "ostajan vahvistama, 2 huomiota kuitattu", "by the buyer, after checking 2 flags"),
    ],
)
def test_confirmed_status_line_counts_checked_flags(checked: int, fi: str, en: str):
    line = _status_line(_row(SessionState.confirmed), _flags(checked))
    assert line == Localized(fi=fi, en=en)


def test_unconfirmed_status_line_is_the_latest_step():
    row = _row(SessionState.awaiting_confirmation)
    assert _status_line(row, _flags(2)) == row.step_text
