"""The OAuth routes for the connectors (#48, `technical-plan.md` §7.3, §10.2 step 7).

The SDK's own handlers on our provider, at paths Caddy already sends to FastAPI:

- `/.well-known/oauth-protected-resource/mcp` (RFC 9728), and the same document at
  `/.well-known/oauth-protected-resource` for clients that probe the root;
- `/.well-known/oauth-authorization-server` (RFC 8414), issuer `PUBLIC_BASE_URL`;
- `/oauth/register` (RFC 7591), `/oauth/authorize` and `/oauth/token`.

The SDK's `create_auth_routes()` would put the endpoints at `/authorize` and so on, which
Caddy sends to SvelteKit, and would compare client secrets in plain text; the routes are
put together here from the same handlers and the same CORS and body-size wrappers instead.
"""

from collections.abc import Awaitable, Callable

from mcp.server.auth.handlers.authorize import AuthorizationHandler
from mcp.server.auth.handlers.metadata import MetadataHandler, ProtectedResourceMetadataHandler
from mcp.server.auth.handlers.register import RegistrationHandler
from mcp.server.auth.handlers.token import TokenHandler
from mcp.server.auth.routes import build_metadata
from mcp.server.auth.settings import ClientRegistrationOptions, RevocationOptions
from mcp.server.streamable_http import MCP_PROTOCOL_VERSION_HEADER
from mcp.server.transport_security import (
    DEFAULT_MAX_REQUEST_BODY_SIZE,
    RequestBodyLimitMiddleware,
)
from mcp.shared.auth import ProtectedResourceMetadata
from pydantic import AnyHttpUrl
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route, request_response
from starlette.types import ASGIApp

from app.settings import get_settings

from .provider import HashedSecretAuthenticator, PostgresOAuthProvider

MCP_PATH = "/mcp"
RESOURCE_METADATA_PATH = "/.well-known/oauth-protected-resource"
AUTHORIZATION_PATH = "/oauth/authorize"
TOKEN_PATH = "/oauth/token"
REGISTRATION_PATH = "/oauth/register"


def resource_url() -> str:
    """The MCP server URL exactly as a user types it into Claude or ChatGPT."""
    return f"{get_settings().public_base_url}{MCP_PATH}"


def resource_metadata_url() -> str:
    return f"{get_settings().public_base_url}{RESOURCE_METADATA_PATH}{MCP_PATH}"


def _cors(app: ASGIApp, methods: list[str]) -> ASGIApp:
    # As in the SDK: browser-based clients such as MCP Inspector call these directly.
    return CORSMiddleware(
        app=app,
        allow_origins="*",
        allow_methods=methods,
        allow_headers=[MCP_PROTOCOL_VERSION_HEADER],
    )


def _limited(handler: Callable[[Request], Awaitable[Response]]) -> ASGIApp:
    return RequestBodyLimitMiddleware(request_response(handler), DEFAULT_MAX_REQUEST_BODY_SIZE)


def auth_routes(provider: PostgresOAuthProvider | None = None) -> list[BaseRoute]:
    provider = provider or PostgresOAuthProvider()
    origin = get_settings().public_base_url
    issuer = AnyHttpUrl(origin)

    registration = ClientRegistrationOptions(enabled=True)
    metadata = build_metadata(issuer, None, registration, RevocationOptions(enabled=False))
    metadata.authorization_endpoint = AnyHttpUrl(origin + AUTHORIZATION_PATH)
    metadata.token_endpoint = AnyHttpUrl(origin + TOKEN_PATH)
    metadata.registration_endpoint = AnyHttpUrl(origin + REGISTRATION_PATH)
    # Claude and ChatGPT register as public clients and rely on PKCE.
    metadata.token_endpoint_auth_methods_supported = [
        "none",
        "client_secret_post",
        "client_secret_basic",
    ]

    resource = ProtectedResourceMetadata(
        resource=AnyHttpUrl(resource_url()),
        authorization_servers=[issuer],
        resource_name="S.I.MO",
    )
    resource_handler = ProtectedResourceMetadataHandler(resource).handle
    token_handler = TokenHandler(provider, HashedSecretAuthenticator(provider))
    get = ["GET", "OPTIONS"]
    post = ["POST", "OPTIONS"]
    return [
        Route(
            RESOURCE_METADATA_PATH + MCP_PATH,
            _cors(request_response(resource_handler), get),
            methods=get,
        ),
        Route(RESOURCE_METADATA_PATH, _cors(request_response(resource_handler), get), methods=get),
        Route(
            "/.well-known/oauth-authorization-server",
            _cors(request_response(MetadataHandler(metadata).handle), get),
            methods=get,
        ),
        # No CORS: the browser is sent here, it doesn't call it.
        Route(
            AUTHORIZATION_PATH,
            _limited(AuthorizationHandler(provider).handle),
            methods=["GET", "POST"],
        ),
        Route(TOKEN_PATH, _cors(_limited(token_handler.handle), post), methods=post),
        Route(
            REGISTRATION_PATH,
            _cors(_limited(RegistrationHandler(provider, registration).handle), post),
            methods=post,
        ),
    ]
