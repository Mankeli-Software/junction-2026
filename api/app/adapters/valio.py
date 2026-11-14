"""Price and availability from the Valio mock API. Interim: the recorded fixture offers.

`get_offers()` is the interface the quote service (#45) calls; #31 (Miska) replaces the
body with the live and snapshot adapter and keeps the signature.
"""

from datetime import UTC, date, datetime

from app.schemas import Offer, OfferSource
from app.services import catalog


async def get_offers(ids: list[str], needed_by: date) -> list[Offer]:
    """One offer per id, in the order given. Never raises: a failure is `ok=False`.

    Interim: the fixture offers (snapshot, stock as in `valio-api-analysis.md` §11). An id
    without a recorded offer gets `ok=False`, as an `error: true` response would.
    """
    recorded = {offer.product_id: offer for offer in catalog.offers()}
    return [recorded.get(product_id) or _failed(product_id) for product_id in ids]


def _failed(product_id: str) -> Offer:
    return Offer(
        product_id=product_id,
        ok=False,
        unit_price_gross=None,
        price_valid_to=None,
        sales_unit=None,
        schedule=[],
        sales_block=False,
        closing_time=None,
        fetched_at=datetime.now(UTC),
        source=OfferSource.snapshot,
    )
