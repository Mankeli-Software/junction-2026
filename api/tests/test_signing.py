"""Quote signature and published key (#40, technical-plan.md §8.1). No database."""

import base64
import json

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

from app.main import app
from app.services import signing
from app.settings import get_settings

PAYLOAD = {
    "quote_id": "00000000-0000-0000-0000-000000000001",
    "lines": [{"product_id": "464306", "unit_price_gross": "1.25", "line_total_cents": 2500}],
    "total_cents": 2500,
}


def pem(key: Ed25519PrivateKey) -> str:
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()


@pytest.fixture
def use_key(monkeypatch):
    """Sets QUOTE_SIGNING_KEY (and ENV) for one test and forgets the cached key after."""

    def use(value: str, env: str = "dev") -> None:
        monkeypatch.setenv("QUOTE_SIGNING_KEY", value)
        monkeypatch.setenv("ENV", env)
        get_settings.cache_clear()
        signing.signing_key.cache_clear()

    yield use
    monkeypatch.delenv("QUOTE_SIGNING_KEY", raising=False)
    monkeypatch.delenv("ENV", raising=False)
    get_settings.cache_clear()
    signing.signing_key.cache_clear()


def test_a_signed_quote_verifies_with_a_standard_jose_library(use_key):
    use_key(pem(Ed25519PrivateKey.generate()))
    token = signing.sign_quote(PAYLOAD)

    [published] = signing.jwks()["keys"]
    header = jwt.get_unverified_header(token)
    assert header == {"alg": "EdDSA", "kid": published["kid"]}
    signed = jwt.PyJWS().decode(token, jwt.PyJWK(published).key, algorithms=["EdDSA"])

    # The payload is the canonical quote, so its hash is the quote hash.
    assert json.loads(signed) == PAYLOAD
    assert signing.verify_quote(token, signing.quote_hash(PAYLOAD))


def test_the_jwks_publishes_only_the_public_key_under_its_thumbprint(use_key):
    use_key(pem(Ed25519PrivateKey.generate()))
    [published] = signing.jwks()["keys"]

    assert published.keys() == {"kty", "crv", "x", "kid", "use", "alg"}
    assert (published["kty"], published["crv"], published["use"]) == ("OKP", "Ed25519", "sig")
    assert published["kid"] == signing.signing_key().thumbprint()


def test_verify_rejects_a_changed_quote_another_key_and_garbage(use_key):
    use_key(pem(Ed25519PrivateKey.generate()))
    token = signing.sign_quote(PAYLOAD)
    expected = signing.quote_hash(PAYLOAD)

    header, payload, signature = token.split(".")
    changed = {**PAYLOAD, "total_cents": 1}
    forged = base64.urlsafe_b64encode(json.dumps(changed).encode()).rstrip(b"=").decode()
    assert not signing.verify_quote(f"{header}.{forged}.{signature}", expected)
    assert not signing.verify_quote(token, signing.quote_hash(changed))
    assert not signing.verify_quote("not.a.jws", expected)

    use_key(pem(Ed25519PrivateKey.generate()))  # rotated: the old quote no longer verifies
    assert not signing.verify_quote(token, expected)


def test_the_key_may_use_escaped_line_breaks(use_key):
    key = Ed25519PrivateKey.generate()
    use_key(pem(key).strip().replace("\n", "\\n"))

    raw = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    assert signing.jwks()["keys"][0]["x"] == base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def test_dev_without_a_key_signs_with_a_key_for_the_process(use_key):
    use_key("")
    token = signing.sign_quote(PAYLOAD)

    assert signing.verify_quote(token, signing.quote_hash(PAYLOAD))
    assert signing.signing_key() is signing.signing_key()


def test_prod_needs_a_key(use_key):
    use_key("", env="prod")
    with pytest.raises(signing.SigningKeyError, match="not set"):
        signing.signing_key()


@pytest.mark.parametrize("value", ["not a key", "rsa"])
def test_a_key_that_is_not_ed25519_is_refused(use_key, value):
    if value == "rsa":
        from cryptography.hazmat.primitives.asymmetric import rsa

        value = (
            rsa.generate_private_key(public_exponent=65537, key_size=2048)
            .private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
            .decode()
        )
    use_key(value)
    with pytest.raises(signing.SigningKeyError):
        signing.signing_key()


def test_the_jwks_endpoint_serves_the_key_to_any_origin(use_key):
    use_key(pem(Ed25519PrivateKey.generate()))
    response = TestClient(app).get("/.well-known/jwks.json")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/jwk-set+json"
    assert response.headers["access-control-allow-origin"] == "*"
    assert response.json() == signing.jwks()
