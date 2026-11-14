"""The overview behind `GET /orders` and the stream's snapshot (#49).

PLACEHOLDER until #45 (`sessions`, `quotes`) and #41 (`audit_events`, `status_events`)
land: there are no tables to read yet, so the overview is always empty. The filters are
accepted so the URLs the dashboard uses already work.
"""

from datetime import datetime

from app.schemas import Channel, OverviewResponse, StateGroup, Totals
from app.services.policy import get_rule_set


async def load_overview(
    state: StateGroup | None = None,
    channel: Channel | None = None,
    since: datetime | None = None,
) -> OverviewResponse:
    # TODO(#49): read the sessions since EVENT_START, newest activity first, at most 200
    # cards, with the totals over all of them.
    return OverviewResponse(
        business_now=get_rule_set().policy.business_time,
        totals=Totals(
            active=0,
            waiting=0,
            confirmed=0,
            attention=0,
            confirmed_cents=0,
            by_channel={c: 0 for c in Channel},
        ),
        companies=[],
    )
