"""The Valio adapter (#31): normalisation, rate limiting, the three sources and the cache."""

import json
import logging
from datetime import UTC, date, datetime
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.adapters.valio import (
    MILK_SHORTLIST,
    SnapshotStore,
    TokenBucket,
    ValioClient,
    is_unverified,
    parse_availability,
    parse_comparison,
    parse_price,
)
from app.models.valio import ApiCache
from app.schemas import OfferSource

DAY = date(2026, 11, 16)
NOW = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)

MILK_PRICE = {
    "productId": "464073",
    "catalogPrice": {
        "value": 1.64,
        "valueWithTax": 1.86,
        "validTo": "2026-12-31T00:00:00+0200",
    },
    "error": False,
}
MILK_STOCK = {
    "productId": "464073",
    "closingTime": "2026-11-15T17:00:00+0200",
    "salesBlock": False,
    "logisticModel": "Stock",
    "scheduleLines": [
        {
            "salesBlock": False,
            "availableAmount": 9999999999.0,
            "availableDate": "2026-11-16",
            "salesUnit": "ST",
        }
    ],
}
EMPTY_PRICE = {"productId": "464440", "error": True}
EMPTY_STOCK = {"productId": "464440", "salesBlock": False, "scheduleLines": []}
PRODUCTS = {
    "price": {"464073": MILK_PRICE, "464440": EMPTY_PRICE},
    "availability": {"464073": MILK_STOCK, "464440": EMPTY_STOCK},
}


class FakeApi:
    """Stands in for the Valio API. `statuses` is the queue of HTTP statuses to answer with."""

    def __init__(self, statuses: list[int] | None = None):
        self.statuses = list(statuses or [])
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        endpoint = request.url.path.rsplit("/", 1)[1]
        self.calls.append((endpoint, body))
        assert request.headers["X-API-Key"] == "test-key"
        assert request.headers["User-Agent"] == "curl/8.4.0"
        if self.statuses and (status := self.statuses.pop(0)) != 200:
            return httpx.Response(status)
        entries = [PRODUCTS[endpoint][i] for i in body["products"] if i in PRODUCTS[endpoint]]
        return httpx.Response(200, json={"products": entries})


def make_client(api: FakeApi, tmp_path, source="live", **options) -> ValioClient:
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    http = httpx.AsyncClient(
        transport=httpx.MockTransport(api),
        base_url="https://valio.test/api/",
        headers={"X-API-Key": "test-key", "User-Agent": "curl/8.4.0"},
    )
    client = ValioClient(
        source=source,
        http=http,
        snapshots=SnapshotStore(tmp_path),
        sleep=fake_sleep,
        clock=lambda: NOW,
        **options,
    )
    client.slept = sleeps  # type: ignore[attr-defined]
    return client


# --- Normalisation


def test_price_is_the_gross_value_as_an_exact_decimal():
    price, valid_to = parse_price(MILK_PRICE)
    assert price == Decimal("1.86")
    assert valid_to == date(2026, 12, 31)


@pytest.mark.parametrize("entry", [None, EMPTY_PRICE, {"catalogPrice": None, "error": False}])
def test_no_price_is_none(entry):
    assert parse_price(entry) is None


def test_comparison_price_is_the_gross_value_with_its_unit():
    entry = {
        "catalogPrice": {"valueWithTax": 5.84},
        "comparisonPrice": {"valueWithTax": 2.92},
        "comparisonUnit": "l",
        "error": False,
    }
    assert parse_comparison(entry) == (Decimal("2.92"), "L")


@pytest.mark.parametrize(
    "entry",
    [None, EMPTY_PRICE, {"comparisonPrice": {"valueWithTax": 1}, "error": False}],
)
def test_no_comparison_price_is_none(entry):
    assert parse_comparison(entry) == (None, None)


def test_availability_is_parsed_and_the_sentinel_is_left_for_the_engine():
    schedule, unit, blocked, closing = parse_availability(MILK_STOCK)
    assert unit == "ST" and not blocked
    assert closing == datetime.fromisoformat("2026-11-15T17:00:00+02:00")
    assert schedule[0].available_date == DAY
    assert is_unverified(schedule[0].amount)
    assert not is_unverified(Decimal(51))


def test_an_empty_schedule_means_not_available():
    schedule, unit, blocked, closing = parse_availability(EMPTY_STOCK)
    assert (schedule, unit, blocked, closing) == ([], None, False, None)


def test_blocked_lines_are_dropped_and_a_top_level_block_is_kept():
    entry = {
        "salesBlock": True,
        "scheduleLines": [
            {"salesBlock": True, "availableAmount": 5, "availableDate": "2026-11-16"},
            {"salesBlock": False, "availableAmount": 0, "salesUnit": "ST"},
        ],
    }
    schedule, _, blocked, _ = parse_availability(entry)
    assert schedule == [] and blocked


# --- Rate limiting


async def test_token_bucket_spreads_requests_over_time():
    now = [0.0]
    sleeps: list[float] = []

    async def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        now[0] += seconds

    bucket = TokenBucket(5, clock=lambda: now[0], sleep=sleep)
    for _ in range(5):
        await bucket.acquire()
    assert sleeps == []  # the burst
    for _ in range(5):
        await bucket.acquire()
    assert now[0] == pytest.approx(1.0)  # five more take a second


async def test_429_waits_30_seconds_and_retries_once(tmp_path):
    api = FakeApi([429, 200, 200])
    client = make_client(api, tmp_path)
    [offer] = await client.offers(["464073"], DAY)
    assert offer.ok
    assert client.slept == [30]  # type: ignore[attr-defined]
    assert [c[0] for c in api.calls].count("price") + [c[0] for c in api.calls].count(
        "availability"
    ) == 3  # one call was retried


async def test_a_second_429_fails_the_offer_instead_of_looping(tmp_path, caplog):
    api = FakeApi([429, 429, 429, 429])
    client = make_client(api, tmp_path)
    with caplog.at_level(logging.ERROR):
        [offer] = await client.offers(["464073"], DAY)
    assert not offer.ok
    assert len(api.calls) == 4  # two endpoints, each tried twice
    assert "HTTP 429" in caplog.text


# --- Live and record


async def test_one_batched_call_per_endpoint(tmp_path):
    api = FakeApi()
    client = make_client(api, tmp_path)
    offers = await client.offers(["464073", "464440", "464073"], DAY)
    assert sorted(c[0] for c in api.calls) == ["availability", "price"]
    assert all(c[1]["products"] == ["464073", "464440"] for c in api.calls)
    assert [o.product_id for o in offers] == ["464073", "464440"]
    milk, empty = offers
    assert milk.ok and milk.unit_price_gross == Decimal("1.86") and milk.source == OfferSource.live
    assert milk.fetched_at == NOW
    assert not empty.ok and empty.schedule == []  # no price: not quoted


async def test_large_shortlists_are_split_at_1000(tmp_path):
    api = FakeApi()
    client = make_client(api, tmp_path)
    await client.offers([str(i) for i in range(1500)], DAY)
    assert sorted(len(c[1]["products"]) for c in api.calls) == [500, 500, 1000, 1000]


async def test_record_saves_snapshots_that_snapshot_mode_replays(tmp_path):
    recorder = make_client(FakeApi(), tmp_path, source="record")
    recorded = await recorder.offers(["464073", "464440"], DAY)
    assert (tmp_path / "price-2026-11-16.json").exists()
    assert "test-key" not in (tmp_path / "price-2026-11-16.json").read_text()

    api = FakeApi()
    replayed = await make_client(api, tmp_path, source="snapshot").offers(["464073", "464440"], DAY)
    assert api.calls == []
    assert [o.model_copy(update={"source": OfferSource.live}) for o in replayed] == recorded
    assert all(o.source == OfferSource.snapshot for o in replayed)


async def test_snapshot_uses_the_nearest_recorded_date_with_a_warning(tmp_path, caplog):
    await make_client(FakeApi(), tmp_path, source="record").offers(["464073"], DAY)
    with caplog.at_level(logging.WARNING):
        [offer] = await make_client(FakeApi(), tmp_path, source="snapshot").offers(
            ["464073"], date(2026, 11, 20)
        )
    assert offer.ok
    assert "using price-2026-11-16.json" in caplog.text


async def test_a_missing_snapshot_is_logged_loudly_and_not_quoted(tmp_path, caplog):
    with caplog.at_level(logging.ERROR):
        [offer] = await make_client(FakeApi(), tmp_path, source="snapshot").offers(["1"], DAY)
    assert not offer.ok and offer.source == OfferSource.snapshot
    assert "SNAPSHOT MISSING" in caplog.text


# --- Cache (needs the database)


async def test_responses_are_cached_for_300_seconds(db_engine, tmp_path):
    sessions = async_sessionmaker(db_engine, expire_on_commit=False)
    try:
        api = FakeApi()
        client = make_client(api, tmp_path, sessions=sessions)
        await client.offers(["464073"], DAY)
        await client.offers(["464073"], DAY)
        assert len(api.calls) == 2  # the second call came from the cache

        await client.offers(["464073"], date(2026, 11, 17))
        assert len(api.calls) == 4  # the cache is keyed by date

        later = datetime(2026, 11, 14, 12, 5, 1, tzinfo=UTC)
        client._clock = lambda: later
        await client.offers(["464073"], DAY)
        assert len(api.calls) == 6  # expired

        async with sessions() as session:
            count = await session.scalar(select(func.count()).select_from(ApiCache))
        assert count == 4  # price and availability for two dates, refreshed in place
    finally:
        async with sessions() as session:
            await session.execute(delete(ApiCache))
            await session.commit()


async def test_the_recorded_milk_shortlist_works_in_snapshot_mode():
    client = ValioClient(source="snapshot", http=httpx.AsyncClient())
    offers = {o.product_id: o for o in await client.offers(MILK_SHORTLIST, DAY)}
    assert all(o.ok for o in offers.values())
    assert is_unverified(offers["464073"].schedule[0].amount)  # unbounded stock
    assert offers["462775"].schedule[0].amount == 51  # partial stock
    assert offers["464440"].schedule == []  # empty schedule: not available


def test_snapshots_use_the_configured_directory(tmp_path, monkeypatch):
    from app.adapters.valio import SnapshotStore
    from app.settings import get_settings

    monkeypatch.setattr(get_settings(), "valio_snapshot_dir", tmp_path)
    assert SnapshotStore().directory == tmp_path


def test_a_failed_recording_is_logged_and_does_not_break_the_lookup(tmp_path, caplog):
    # On the VM a missing or read-only snapshot directory must not fail the quote.
    from datetime import UTC, date, datetime

    from app.adapters.valio import SnapshotStore

    blocker = tmp_path / "not-a-directory"
    blocker.write_text("a file where the directory should be")
    store = SnapshotStore(blocker / "snapshots")

    store.put("price", {"464306": {"price": 1}}, date(2026, 11, 16), datetime.now(UTC))

    assert "SNAPSHOT NOT RECORDED" in caplog.text
