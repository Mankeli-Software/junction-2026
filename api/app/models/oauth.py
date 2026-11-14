"""The OAuth authorization server for `/mcp` (#48, `technical-plan.md` §7.3).

Clients register themselves (RFC 7591), a browser approves an authorization request, the
code is exchanged for an access token (in `access_tokens`, channel `connector`) and a
refresh token, which rotates on every use. Only SHA-256 hashes of secrets, codes and
tokens are stored.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, timestamp_now


class OAuthClient(Base):
    """A registered connector client, such as one Claude or ChatGPT connection."""

    __tablename__ = "oauth_clients"

    client_id: Mapped[str] = mapped_column(Text, primary_key=True)
    # Null for public clients (`token_endpoint_auth_method` "none"), as Claude registers.
    client_secret_hash: Mapped[str | None] = mapped_column(Text)
    client_name: Mapped[str | None] = mapped_column(Text)
    redirect_uris: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    # The rest of the registration (grant types, auth method, scope), without the secret.
    registration: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'")
    )
    created_at: Mapped[datetime] = timestamp_now()


class OAuthRequest(Base):
    """An authorization request waiting for the browser's Allow or Cancel.

    `id` is random and travels in the `/connect?request=` URL of the consent page.
    """

    __tablename__ = "oauth_requests"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    client_id: Mapped[str] = mapped_column(
        ForeignKey("oauth_clients.client_id", ondelete="CASCADE"), nullable=False
    )
    redirect_uri: Mapped[str] = mapped_column(Text, nullable=False)
    redirect_uri_provided_explicitly: Mapped[bool] = mapped_column(Boolean, nullable=False)
    code_challenge: Mapped[str] = mapped_column(Text, nullable=False)
    scopes: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )
    state: Mapped[str | None] = mapped_column(Text)
    resource: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = timestamp_now()


class OAuthCode(Base):
    """An authorization code (PKCE S256), valid for 5 minutes and usable once."""

    __tablename__ = "oauth_codes"

    code_hash: Mapped[str] = mapped_column(Text, primary_key=True)
    client_id: Mapped[str] = mapped_column(
        ForeignKey("oauth_clients.client_id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    redirect_uri: Mapped[str] = mapped_column(Text, nullable=False)
    redirect_uri_provided_explicitly: Mapped[bool] = mapped_column(Boolean, nullable=False)
    code_challenge: Mapped[str] = mapped_column(Text, nullable=False)
    scopes: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )
    resource: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = timestamp_now()


class OAuthRefreshToken(Base):
    """A refresh token, valid for 30 days. Using it marks it used and issues a new one."""

    __tablename__ = "oauth_refresh_tokens"

    token_hash: Mapped[str] = mapped_column(Text, primary_key=True)
    client_id: Mapped[str] = mapped_column(
        ForeignKey("oauth_clients.client_id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scopes: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )
    resource: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = timestamp_now()
