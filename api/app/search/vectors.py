"""What search and the embedding script share about vectors (#30, spec §7.11)."""

from collections.abc import Sequence

MODEL = "gemini-embedding-001"
DIMENSIONS = 768


def query_key(q: str) -> str:
    """The cache key for a query: the buyer's text, trimmed and lower case."""
    return " ".join(q.lower().split())


def vector_literal(values: Sequence[float]) -> str:
    return "[" + ",".join(f"{v:.6f}" for v in values) + "]"
