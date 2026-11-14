"""Quote hash, signature and published key (technical-plan.md §8.1, #40).

The hash is SHA-256 over the RFC 8785 canonical JSON of `quotes.quote_payload()`. The
signature is a compact JWS with Ed25519 whose payload is those same canonical bytes, so a
verifier gets the signed quote back and can recompute the hash from it. The public key is
served at `/.well-known/jwks.json`; its `kid` is the key's RFC 7638 thumbprint.

The private key is the `quote_signing_key` setting (PKCS#8 PEM, Key Vault secret
`quote-signing-key`). Without it, dev generates a key for the life of the process, so quotes
signed before a restart no longer verify; prod refuses to start.
"""

import hashlib
import logging
import warnings
from functools import lru_cache
from typing import Any

import rfc8785
from joserfc import jws
from joserfc.errors import JoseError
from joserfc.jwk import KeySet, OKPKey

from app.settings import get_settings

log = logging.getLogger(__name__)

# RFC 9864 prefers the fully specified "Ed25519", but "EdDSA" is what JOSE libraries and
# tools verify today. The key is Ed25519 either way.
ALG = "EdDSA"


class SigningKeyError(RuntimeError):
    """The signing key is missing (in prod) or isn't an Ed25519 private key."""


def quote_hash(payload: dict[str, Any]) -> str:
    """SHA-256 hex over the RFC 8785 canonical JSON of the quote payload."""
    return hashlib.sha256(rfc8785.dumps(payload)).hexdigest()


@lru_cache
def signing_key() -> OKPKey:
    """The Ed25519 private key quotes are signed with, loaded once per process."""
    settings = get_settings()
    pem = settings.quote_signing_key.strip().replace("\\n", "\n")
    if pem:
        try:
            key = OKPKey.import_key(pem)
        except (JoseError, ValueError, TypeError) as error:
            raise SigningKeyError("QUOTE_SIGNING_KEY is not a PEM key") from error
        if key.curve_name != "Ed25519" or not key.is_private:
            raise SigningKeyError("QUOTE_SIGNING_KEY must be an Ed25519 private key")
    elif settings.env == "prod":
        raise SigningKeyError("QUOTE_SIGNING_KEY is not set")
    else:
        log.warning("QUOTE_SIGNING_KEY is not set: signing quotes with a key for this process")
        key = OKPKey.generate_key("Ed25519", private=True)
    return OKPKey.import_key(key.as_dict(private=True), {"kid": key.thumbprint()})


def jwks() -> dict[str, Any]:
    """The public JWK Set served at `/.well-known/jwks.json`."""
    public = signing_key().as_dict(private=False)
    return {"keys": [{**public, "use": "sig", "alg": ALG}]}


def sign_quote(payload: dict[str, Any]) -> str:
    """A compact JWS over the RFC 8785 canonical JSON of the quote payload."""
    key = signing_key()
    header = {"alg": ALG, "kid": key.kid}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # the RFC 9864 deprecation notice for "EdDSA"
        return jws.serialize_compact(header, rfc8785.dumps(payload), key, algorithms=[ALG])


def verify_quote(token: str, expected_hash: str | None) -> bool:
    """True when `token` is signed by the published key and its payload is the quote with
    `expected_hash`. False for a bad signature, another key or a changed quote."""
    public = KeySet([OKPKey.import_key(key) for key in jwks()["keys"]])
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            signed = jws.deserialize_compact(token, public, algorithms=[ALG])
    except (JoseError, ValueError):
        return False
    return hashlib.sha256(signed.payload).hexdigest() == expected_hash
