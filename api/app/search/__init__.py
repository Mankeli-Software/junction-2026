"""Deterministic local product search (#30, technical-plan.md §5.3).

uv run python -m app.search "naudan jauheliha" [--claim lactose_free] [--category ID]
uv run python -m app.search.eval [--set NAME] [--save-baseline]
"""

from app.search.search import CLAIM_IDS, SearchHit, search_products

__all__ = ["CLAIM_IDS", "SearchHit", "search_products"]
