"""Quote hash and signature (technical-plan.md §8.1). Interim: the hash is final, no signature.

`quote_hash()` and `sign_quote()` are the interface the quote service (#45) calls; #40
(Aku) adds the Ed25519 JWS and the JWKS and keeps the signatures.
"""

import hashlib
from typing import Any

import rfc8785


def quote_hash(payload: dict[str, Any]) -> str:
    """SHA-256 hex over the RFC 8785 canonical JSON of the quote payload."""
    return hashlib.sha256(rfc8785.dumps(payload)).hexdigest()


def sign_quote(payload: dict[str, Any]) -> str | None:
    """A compact JWS over the payload. None until #40."""
    return None
