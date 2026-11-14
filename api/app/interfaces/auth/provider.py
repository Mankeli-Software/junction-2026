"""The MCP SDK's OAuth provider interface on top of `app.services.oauth` (#48).

Each method opens its own short database session, like `resolve_caller()`, because the
SDK's handlers run outside FastAPI's dependencies.
"""

import base64
import binascii
import hmac
from typing import Any
from urllib.parse import unquote

from mcp.server.auth.middleware.client_auth import ClientAuthenticator
from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationParams,
    OAuthAuthorizationServerProvider,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from starlette.requests import Request

from app.db import get_sessionmaker
from app.services import oauth, tokens
from app.services.oauth import ConnectorClient, ConnectorCode, ConnectorRefreshToken
from app.settings import get_settings


def consent_url(request_id: str) -> str:
    """The SvelteKit consent page, which sends the browser to /login first if needed."""
    return f"{get_settings().public_base_url}/connect?request={request_id}"


class PostgresOAuthProvider(
    OAuthAuthorizationServerProvider[ConnectorCode, ConnectorRefreshToken, AccessToken]
):
    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        async with get_sessionmaker()() as db:
            return await oauth.get_client(db, client_id)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        async with get_sessionmaker()() as db:
            await oauth.register_client(db, client_info)
            await db.commit()

    async def authorize(
        self, client: OAuthClientInformationFull, params: AuthorizationParams
    ) -> str:
        async with get_sessionmaker()() as db:
            request_id = await oauth.create_request(db, client, params)
            await db.commit()
        return consent_url(request_id)

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> ConnectorCode | None:
        assert client.client_id is not None
        async with get_sessionmaker()() as db:
            return await oauth.load_code(db, client.client_id, authorization_code)

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: ConnectorCode
    ) -> OAuthToken:
        async with get_sessionmaker()() as db:
            token = await oauth.redeem_code(db, client, authorization_code)
            await db.commit()
        return token

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> ConnectorRefreshToken | None:
        assert client.client_id is not None
        async with get_sessionmaker()() as db:
            return await oauth.load_refresh_token(db, client.client_id, refresh_token)

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: ConnectorRefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        async with get_sessionmaker()() as db:
            token = await oauth.rotate_refresh_token(db, client, refresh_token, scopes)
            await db.commit()
        return token

    async def load_access_token(self, token: str) -> AccessToken | None:
        async with get_sessionmaker()() as db:
            found = await tokens.resolve_access_token(db, token)
        if found is None or found.channel != "connector" or found.client_id is None:
            return None
        return AccessToken(
            token=token,
            client_id=found.client_id,
            scopes=list(found.scopes),
            expires_at=int(found.expires_at.timestamp()),
            subject=str(found.user_id),
        )

    async def revoke_token(self, token: AccessToken | ConnectorRefreshToken) -> None:
        # The revocation endpoint is not enabled; this keeps the interface complete.
        if isinstance(token, ConnectorRefreshToken):
            async with get_sessionmaker()() as db:
                await oauth.revoke_refresh_token(db, token.token)
                await db.commit()


def _presented_secret(request: Request, form: Any) -> str | None:
    """The client secret in the Basic header or the form, as the SDK reads it."""
    header = request.headers.get("authorization", "")
    if header.startswith("Basic "):
        try:
            decoded = base64.b64decode(header[6:]).decode()
        except (ValueError, UnicodeDecodeError, binascii.Error):
            return None
        _, _, secret = decoded.partition(":")
        return unquote(secret) or None
    value = form.get("client_secret")
    return value if isinstance(value, str) and value else None


class _RawSecretClients:
    """Hands the SDK's authenticator a client whose `client_secret` is the presented
    secret when its hash matches, and a value that never matches otherwise."""

    def __init__(self, provider: PostgresOAuthProvider, presented: str | None) -> None:
        self.provider = provider
        self.presented = presented

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        client = await self.provider.get_client(client_id)
        if not isinstance(client, ConnectorClient) or not client.client_secret:
            return client
        ok = self.presented is not None and hmac.compare_digest(
            tokens.hash_token(self.presented), client.client_secret
        )
        # A fresh random value can't equal what the request sent.
        secret = self.presented if ok else tokens.new_token()
        return client.model_copy(update={"client_secret": secret})


class HashedSecretAuthenticator(ClientAuthenticator):
    """The SDK's token-endpoint client check, for secrets stored only as hashes."""

    provider: PostgresOAuthProvider

    async def authenticate_request(self, request: Request) -> OAuthClientInformationFull:
        form = await request.form()  # Starlette caches it, so the SDK can read it again
        shim = _RawSecretClients(self.provider, _presented_secret(request, form))
        return await ClientAuthenticator(shim).authenticate_request(request)  # type: ignore[arg-type]
