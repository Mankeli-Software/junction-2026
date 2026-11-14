"""Valio price and availability adapter (#31, technical-plan.md §6).

For a shortlist of product ids and a delivery date it returns one `Offer` per product. Three
sources: `live` (cached in Postgres for 300 s), `record` (live, and every response is saved under
`data/snapshots/`) and `snapshot` (saved responses only, never the network).

The adapter only normalises what the API says. It leaves the amount sentinels (999999 and up) in
the schedule for the engine to flag as unverified, and the sales-unit cross-check against the
product file (§4.2) is the engine's too, since the adapter never sees the product record.
"""

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import telemetry
from app.models.valio import ApiCache
from app.schemas import Offer, OfferSource, ScheduleLine
from app.settings import get_settings

log = logging.getLogger(__name__)

ENDPOINTS = ("price", "availability")
MAX_BATCH = 1000  # the API answers 422 above this
USER_AGENT = "curl/8.4.0"  # Cloudflare blocks Python's default
# Amounts at or above this are "unknown stock" placeholders (Terminal products and unbounded
# Stock), not real quantities. Offers keep the number; the engine treats it as unverified.
UNVERIFIED_AMOUNT = Decimal(999999)


class ValioError(Exception):
    """The API could not be reached or answered with an error."""


def is_unverified(amount: Decimal) -> bool:
    return amount >= UNVERIFIED_AMOUNT


class TokenBucket:
    """At most `rate` requests per second, with a burst of `rate`."""

    def __init__(
        self,
        rate: float = 5,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        self.rate = rate
        self._clock = clock
        self._sleep = sleep
        self._tokens = rate
        self._stamp = clock()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            while True:
                now = self._clock()
                self._tokens = min(self.rate, self._tokens + (now - self._stamp) * self.rate)
                self._stamp = now
                if self._tokens >= 1:
                    self._tokens -= 1
                    return
                await self._sleep((1 - self._tokens) / self.rate)


# --- Normalisation ------------------------------------------------------------------------


def _decimal(value: Any) -> Decimal:
    return Decimal(str(value))


def _day(value: str) -> date:
    return datetime.fromisoformat(value).date()


def parse_price(entry: dict[str, Any] | None) -> tuple[Decimal, date] | None:
    """Gross unit price and `validTo`, or None when the API found no price."""
    if not entry or entry.get("error"):
        return None
    catalog = entry.get("catalogPrice") or {}
    if catalog.get("valueWithTax") is None:
        return None
    valid_to = catalog.get("validTo")
    return _decimal(catalog["valueWithTax"]), _day(valid_to) if valid_to else date.max


def parse_comparison(entry: dict[str, Any] | None) -> tuple[Decimal | None, str | None]:
    """Gross comparison price and its unit (`L`, `KG`), or Nones when the API has none."""
    if not entry or entry.get("error"):
        return None, None
    value = (entry.get("comparisonPrice") or {}).get("valueWithTax")
    unit = entry.get("comparisonUnit")
    if value is None or not unit:
        return None, None
    return _decimal(value), str(unit).upper()


def parse_availability(
    entry: dict[str, Any],
) -> tuple[list[ScheduleLine], str | None, bool, datetime | None]:
    """Schedule, sales unit, sales block and closing time.

    A blocked schedule line is left out. An empty schedule means the product cannot be ordered.
    """
    schedule: list[ScheduleLine] = []
    unit: str | None = None
    for line in entry.get("scheduleLines") or []:
        if line.get("salesBlock") or not line.get("availableDate"):
            continue
        unit = unit or line.get("salesUnit")
        schedule.append(
            ScheduleLine(
                available_date=date.fromisoformat(line["availableDate"]),
                amount=_decimal(line.get("availableAmount") or 0),
            )
        )
    closing = entry.get("closingTime")
    return (
        schedule,
        unit,
        bool(entry.get("salesBlock")),
        datetime.fromisoformat(closing) if closing else None,
    )


def build_offer(
    product_id: str,
    price: tuple[dict[str, Any], datetime] | None,
    availability: tuple[dict[str, Any], datetime] | None,
    source: OfferSource,
    *,
    now: datetime,
) -> Offer:
    """One offer from the two raw entries. `ok` is false when either is missing or has no price."""
    parsed = parse_price(price[0]) if price else None
    comparison_price, comparison_unit = parse_comparison(price[0] if price else None)
    schedule, unit, blocked, closing = (
        parse_availability(availability[0]) if availability else ([], None, False, None)
    )
    fetched = [raw[1] for raw in (price, availability) if raw is not None]
    return Offer(
        product_id=product_id,
        ok=parsed is not None and availability is not None,
        unit_price_gross=parsed[0] if parsed else None,
        price_valid_to=parsed[1] if parsed else None,
        comparison_price_gross=comparison_price,
        comparison_unit=comparison_unit,
        sales_unit=unit,
        schedule=schedule,
        sales_block=blocked,
        closing_time=closing,
        fetched_at=min(fetched) if fetched else now,
        source=source,
    )


# --- Snapshots ----------------------------------------------------------------------------


class SnapshotStore:
    """`data/snapshots/<endpoint>-<requested date>.json`: `{"products": {id: {...}}}`.

    The files hold only API responses and fetch times, never the key.
    """

    def __init__(self, directory: Path | None = None):
        self.directory = directory or get_settings().valio_snapshot_dir

    def _path(self, endpoint: str, requested: date) -> Path:
        return self.directory / f"{endpoint}-{requested.isoformat()}.json"

    def _read(self, path: Path) -> dict[str, Any]:
        return json.loads(path.read_text())["products"]

    def get(
        self, endpoint: str, product_ids: list[str], requested: date
    ) -> dict[str, tuple[dict[str, Any], datetime]]:
        """Recorded entries for the products. Neither price nor availability changed with the
        requested date in the recordings (analysis §3, §4), so when a product is missing for this
        date the nearest other date is used, with a warning."""
        found: dict[str, tuple[dict[str, Any], datetime]] = {}
        files = sorted(self.directory.glob(f"{endpoint}-*.json"))
        by_distance = sorted(
            files, key=lambda p: abs((date.fromisoformat(p.stem.split("-", 1)[1]) - requested).days)
        )
        for product_id in product_ids:
            for path in by_distance:
                row = self._read(path).get(product_id)
                if row is None:
                    continue
                if path != self._path(endpoint, requested):
                    log.warning(
                        "No %s snapshot for product %s on %s, using %s",
                        endpoint, product_id, requested, path.name,
                    )  # fmt: skip
                found[product_id] = (row["data"], datetime.fromisoformat(row["fetched_at"]))
                break
            else:
                log.error(
                    "SNAPSHOT MISSING: no recorded %s response for product %s (requested %s). "
                    "Record it with VALIO_SOURCE=record.",
                    endpoint, product_id, requested,
                )  # fmt: skip
        return found

    def put(
        self,
        endpoint: str,
        entries: dict[str, dict[str, Any]],
        requested: date,
        fetched_at: datetime,
    ) -> None:
        path = self._path(endpoint, requested)
        products = self._read(path) if path.exists() else {}
        for product_id, data in entries.items():
            products[product_id] = {"fetched_at": fetched_at.isoformat(), "data": data}
        body = {"endpoint": endpoint, "requestedDate": requested.isoformat(), "products": products}
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(body, indent=1, sort_keys=True, ensure_ascii=False) + "\n")
        except OSError as error:
            # The live response is still used; only the recording is lost.
            log.error("SNAPSHOT NOT RECORDED: %s %s: %s", endpoint, requested, error)


# --- Client -------------------------------------------------------------------------------


class ValioClient:
    def __init__(
        self,
        *,
        source: str = "snapshot",
        api_key: str = "",
        base_url: str = "https://junction26.valioaimo.fi/api",
        sessions: async_sessionmaker[AsyncSession] | None = None,
        snapshots: SnapshotStore | None = None,
        http: httpx.AsyncClient | None = None,
        cache_seconds: int = 300,
        rate_limit_wait: float = 30,
        bucket: TokenBucket | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ):
        if source not in ("live", "record", "snapshot"):
            raise ValueError(f"unknown VALIO_SOURCE {source!r}")
        self.source = source
        self.sessions = sessions
        self.snapshots = snapshots or SnapshotStore()
        self.cache_seconds = cache_seconds
        self.rate_limit_wait = rate_limit_wait
        self.bucket = bucket or TokenBucket()
        self._sleep = sleep
        self._clock = clock
        self._http = http or httpx.AsyncClient(
            base_url=base_url.rstrip("/") + "/",
            headers={"X-API-Key": api_key, "User-Agent": USER_AGENT},
            timeout=30,
        )

    async def offers(self, product_ids: list[str], requested: date) -> list[Offer]:
        """One offer per id, in the given order (duplicates dropped). Price and availability are
        fetched in parallel. A product that can't be fetched gets `ok=False` rather than an error,
        so the engine can explain it; an unreachable API fails every product that way."""
        ids = list(dict.fromkeys(product_ids))
        if not ids:
            return []
        timer = telemetry.Timer()
        with telemetry.span(
            "valio offers", valio_source=self.source, products=len(ids), requested=requested
        ):
            results = await asyncio.gather(
                *(self._entries(endpoint, ids, requested) for endpoint in ENDPOINTS),
                return_exceptions=True,
            )
            for endpoint, result in zip(ENDPOINTS, results, strict=True):
                if isinstance(result, BaseException):
                    log.error("Valio %s call failed: %s", endpoint, result)
            price, availability = (r if isinstance(r, dict) else {} for r in results)
            source = OfferSource.snapshot if self.source == "snapshot" else OfferSource.live
            now = self._clock()
            offers = [
                build_offer(i, price.get(i), availability.get(i), source, now=now) for i in ids
            ]
            failed = sum(not offer.ok for offer in offers)
            telemetry.annotate(ok=len(offers) - failed, failed=failed)
            if failed:
                telemetry.failed(f"{failed} of {len(offers)} products without price or stock")
        telemetry.valio_duration.record(timer.ms, telemetry.metric_attrs(valio_source=self.source))
        return offers

    async def _entries(
        self, endpoint: str, ids: list[str], requested: date
    ) -> dict[str, tuple[dict[str, Any], datetime]]:
        if self.source == "snapshot":
            found = self.snapshots.get(endpoint, ids, requested)
            if misses := len(ids) - len(found):
                telemetry.snapshot_misses.add(misses, telemetry.metric_attrs(endpoint=endpoint))
            telemetry.event(
                f"valio {endpoint}", endpoint=endpoint, products=len(ids), snapshot_misses=misses
            )
            return found
        found = {} if self.source == "record" else await self._cached(endpoint, ids, requested)
        missing = [i for i in ids if i not in found]
        telemetry.event(
            f"valio {endpoint}", endpoint=endpoint, products=len(ids), cached=len(found),
            fetched=len(missing),
        )  # fmt: skip
        for start in range(0, len(missing), MAX_BATCH):
            batch = missing[start : start + MAX_BATCH]
            fetched_at = self._clock()
            entries = await self._call(endpoint, batch, requested)
            found.update({i: (entry, fetched_at) for i, entry in entries.items()})
            if self.source == "record":
                self.snapshots.put(endpoint, entries, requested, fetched_at)
            else:
                await self._store(endpoint, entries, requested, fetched_at)
        return found

    async def _call(self, endpoint: str, ids: list[str], requested: date) -> dict[str, Any]:
        body = {"customer": "1", "requestedDate": requested.isoformat(), "products": ids}
        for attempt in (1, 2):
            await self.bucket.acquire()
            try:
                response = await self._http.post(endpoint, json=body)
            except httpx.HTTPError as error:
                raise ValioError(f"{endpoint}: {error}") from error
            if response.status_code == 429 and attempt == 1:
                log.warning("Valio %s rate limited, waiting %s s", endpoint, self.rate_limit_wait)
                telemetry.annotate(rate_limited=True)
                await self._sleep(self.rate_limit_wait)
                continue
            if response.status_code != 200:
                raise ValioError(f"{endpoint}: HTTP {response.status_code}")
            break
        entries: dict[str, Any] = {}
        for entry in response.json().get("products", []):
            entries.setdefault(str(entry["productId"]), entry)
        return entries

    async def _cached(
        self, endpoint: str, ids: list[str], requested: date
    ) -> dict[str, tuple[dict[str, Any], datetime]]:
        if self.sessions is None:
            return {}
        oldest = self._clock().timestamp() - self.cache_seconds
        async with self.sessions() as session:
            rows = await session.scalars(
                select(ApiCache).where(
                    ApiCache.endpoint == endpoint,
                    ApiCache.requested_date == requested,
                    ApiCache.product_id.in_(ids),
                )
            )
            return {
                row.product_id: (row.response, row.fetched_at)
                for row in rows
                if row.fetched_at.timestamp() >= oldest
            }

    async def _store(
        self, endpoint: str, entries: dict[str, Any], requested: date, fetched_at: datetime
    ) -> None:
        if self.sessions is None or not entries:
            return
        rows = [
            {
                "endpoint": endpoint,
                "product_id": product_id,
                "requested_date": requested,
                "response": entry,
                "fetched_at": fetched_at,
            }
            for product_id, entry in entries.items()
        ]
        statement = insert(ApiCache).values(rows)
        statement = statement.on_conflict_do_update(
            index_elements=["endpoint", "product_id", "requested_date"],
            set_={"response": statement.excluded.response, "fetched_at": fetched_at},
        )
        async with self.sessions() as session:
            await session.execute(statement)
            await session.commit()


async def get_offers(ids: list[str], needed_by: date) -> list[Offer]:
    """One offer per id, in the order given: the interface the quote service calls.

    Never raises: a product that can't be fetched comes back with `ok=False`.
    """
    return await get_valio_client().offers(ids, needed_by)


def _failed(product_id: str) -> Offer:
    """An offer for a product that could not be fetched."""
    return build_offer(product_id, None, None, OfferSource.snapshot, now=datetime.now(UTC))


@lru_cache
def get_valio_client() -> ValioClient:
    from app.db import get_sessionmaker

    settings = get_settings()
    return ValioClient(
        source=settings.valio_source,
        api_key=settings.valio_api_key,
        base_url=settings.valio_base_url,
        sessions=get_sessionmaker(),
    )


# The milk case from valio-api-analysis.md §11: unbounded stock, partial stock, Terminal and an
# empty schedule.
MILK_SHORTLIST = ["464073", "464201", "464306", "462775", "463380", "464119", "464440"]


async def record(product_ids: list[str], dates: list[date]) -> None:
    settings = get_settings()
    client = ValioClient(
        source="record", api_key=settings.valio_api_key, base_url=settings.valio_base_url
    )
    for day in dates:
        for offer in await client.offers(product_ids, day):
            print(day, offer.product_id, "ok" if offer.ok else "NOT OK", offer.unit_price_gross)


if __name__ == "__main__":
    # python -m app.adapters.valio [2026-11-16 ...] records the milk shortlist (VALIO_API_KEY)
    import sys

    logging.basicConfig(level=logging.INFO)
    days = [date.fromisoformat(a) for a in sys.argv[1:]] or [date(2026, 11, 16)]
    asyncio.run(record(MILK_SHORTLIST, days))
