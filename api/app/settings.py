"""Settings for the API.

On laptops the values come from environment variables and the `.env` file at the
repository root. On the VM, KEY_VAULT_URL points at the Azure Key Vault and the
values come from there.
"""

import os
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import field_validator
from pydantic.fields import FieldInfo
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def psycopg_url(url: str) -> str:
    """Make a plain Postgres URL use the psycopg 3 driver that SQLAlchemy needs here.

    Key Vault keeps the plain `postgresql://` form so `psql` can use the same secret.
    """
    for plain in ("postgresql://", "postgres://"):
        if url.startswith(plain):
            return "postgresql+psycopg://" + url[len(plain) :]
    return url


# A setting is read from the Key Vault secret named like the field with dashes
# (`valio_api_key` is the secret `valio-api-key`), except for these.
KEY_VAULT_SECRET_NAMES = {"migration_database_url": "database-admin-url"}


class KeyVaultSettingsSource(PydanticBaseSettingsSource):
    """Reads settings from Azure Key Vault with the VM's managed identity.

    It does nothing without a vault URL, so a laptop never needs Azure. Secrets that do
    not exist are skipped and the field keeps its default.
    """

    def __init__(self, settings_cls: type[BaseSettings], vault_url: str, client: Any = None):
        super().__init__(settings_cls)
        self.vault_url = vault_url
        self._client = client

    def _get_client(self) -> Any:
        if self._client is None:
            from azure.identity import DefaultAzureCredential
            from azure.keyvault.secrets import SecretClient

            self._client = SecretClient(self.vault_url, DefaultAzureCredential())
        return self._client

    def get_field_value(self, field: FieldInfo, field_name: str) -> tuple[Any, str, bool]:
        return None, field_name, False

    def __call__(self) -> dict[str, Any]:
        if not self.vault_url:
            return {}
        from azure.core.exceptions import ResourceNotFoundError

        client = self._get_client()
        values: dict[str, Any] = {}
        for name in self.settings_cls.model_fields:
            secret_name = KEY_VAULT_SECRET_NAMES.get(name, name.replace("_", "-"))
            try:
                values[name] = client.get_secret(secret_name).value
            except ResourceNotFoundError:
                continue
        return values


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # prod makes the session cookie Secure. Set ENV=prod on the VM.
    env: Literal["dev", "prod"] = "dev"

    database_url: str = "postgresql+psycopg://junction:junction@localhost:5432/junction"
    # Alembic uses this one when it is set, so migrations can run as the table owner while
    # the app uses a user that cannot change the schema. Empty means use `database_url`.
    migration_database_url: str = ""

    # live: call the API (cached 300 s). record: call it and save every response under
    # data/snapshots/. snapshot: read only the saved responses, never the network.
    valio_source: Literal["snapshot", "record", "live"] = "snapshot"
    # Where snapshots are read and recorded. On the VM a host directory outside the repo
    # (deploy/vm.env), so recordings survive rebuilds and never collide with git pulls.
    valio_snapshot_dir: Path = REPO_ROOT / "data" / "snapshots"
    valio_api_key: str = ""
    valio_base_url: str = "https://junction26.valioaimo.fi/api"
    gemini_api_key: str = ""
    # Product search vectors (#30). live: embed a query that is not cached yet (2 s timeout,
    # text-only on failure). cache: use only cached query vectors, never the network (stage).
    # off: text-only search.
    search_vectors: Literal["live", "cache", "off"] = "live"
    # The stage number (#32, #61): it always gets the school kitchen, so the scripted demo
    # knows its usual. Set on the VM or in .env, never committed (CLAUDE.md: no real numbers).
    demo_stage_phone: str = ""

    # The phone call's voice relay (/voice/ws, #52). The model is on the v1beta API only
    # (spikes/gemini-live). The voice is Achird, picked in #67; the filler clips in
    # app/interfaces/voice/filler_clips/ are made per voice
    # (`python -m app.interfaces.voice.filler --voice <name>`).
    voice_model: str = "gemini-3.8-live"
    voice_name: str = "Achird"
    # Silence after which Gemini's voice activity detection ends the caller's turn. Empty
    # leaves Gemini's default (about 1 s in the spike).
    voice_silence_ms: int | None = 600
    # A tool call still running after this long gets the spoken filler line.
    voice_filler_after_s: float = 1.0
    # Where the relay reaches our own MCP server. In-process on the API's own port, which
    # MCP_ALLOWED_HOSTS lets through.
    voice_mcp_url: str = "http://localhost:8000/mcp"

    # Reading a recipe photo in the webshop chat (#80). The Gemini model is picked in the
    # plan's phase 0; while it is empty, POST /api/v1/recipe-drafts/read answers 503.
    recipe_vision_model: str = ""
    # The largest photo upload, in megabytes. Bigger ones get 413.
    recipe_photo_max_mb: int = 100

    # The webshop chat agent (#57, docs/plans/57-a2ui-chat.md). The Gemini model id, picked
    # with RECIPE_VISION_MODEL (#80 decision 18); while it is empty, POST /api/v1/chat answers
    # 503 "chat not configured". Never given a default here.
    chat_model: str = ""

    sms_twilio_enabled: bool = False
    # Comma-separated phone numbers in E.164 form that may get a real SMS.
    sms_allowlist: str = ""

    session_secret: str = ""

    # Azure Application Insights (app.observability). Empty: nothing is sent. Key Vault
    # secret `applicationinsights-connection-string` on the VM.
    applicationinsights_connection_string: str = ""

    # Ed25519 private key that signs quotes, as PKCS#8 PEM (#40); `\n` may stand for line
    # breaks. Key Vault secret `quote-signing-key`. Unset in dev: a key per process. Prod
    # refuses to start without it. Generate with `openssl genpkey -algorithm ed25519`.
    quote_signing_key: str = ""

    # The public origin, where the web app is served: confirmation links are
    # `<public_base_url>/c/<token>`, and it is the OAuth issuer, the /mcp resource URL in the
    # protected-resource metadata and where the login and consent pages are (#48).
    # https://simo.mankeli.co on the VM.
    public_base_url: str = "http://localhost:5173"

    # Rule files (technical-plan.md §4.3). The container mounts them read-only.
    policy_dir: Path = REPO_ROOT / "policy"
    data_dir: Path = REPO_ROOT / "data"

    # The public dashboard (#49) shows and counts only sessions started at or after this
    # (ISO 8601 with an offset, the real clock). Unset shows every session.
    event_start: datetime | None = None

    # Tests and local dev only: a request without a session cookie or bearer token acts as one
    # fixed demo customer. Off means it gets 401. /me and web_session_user() never use it.
    dev_fake_caller: bool = False

    # False lets /mcp requests without a bearer token act as the fixed demo customer, to try
    # a connector with auth off (#48, technical-plan.md §7.3). Never turn it off for long.
    mcp_auth_required: bool = True

    # Host header values /mcp accepts (DNS-rebinding protection). `name:*` allows any port.
    # Browser clients such as MCP Inspector may also send an Origin; http and https origins
    # for the same names are allowed.
    mcp_allowed_hosts: str = "simo.mankeli.co,localhost,localhost:*,127.0.0.1,127.0.0.1:*"

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # Environment variables and .env win over Key Vault, so a value can be overridden.
        vault = KeyVaultSettingsSource(settings_cls, os.environ.get("KEY_VAULT_URL", ""))
        return init_settings, env_settings, dotenv_settings, vault, file_secret_settings

    @field_validator("database_url", "migration_database_url")
    @classmethod
    def _use_psycopg_driver(cls, value: str) -> str:
        return psycopg_url(value)

    @field_validator("event_start", mode="before")
    @classmethod
    def _empty_means_unset(cls, value: Any) -> Any:
        return None if value == "" else value

    @field_validator("event_start")
    @classmethod
    def _aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("EVENT_START needs a UTC offset, for example +02:00")
        return value

    @property
    def migrations_url(self) -> str:
        return self.migration_database_url or self.database_url

    @field_validator("public_base_url")
    @classmethod
    def _no_trailing_slash(cls, value: str) -> str:
        return value.rstrip("/")

    @property
    def mcp_allowed_host_list(self) -> list[str]:
        return [h.strip() for h in self.mcp_allowed_hosts.split(",") if h.strip()]

    @property
    def sms_allowlist_numbers(self) -> frozenset[str]:
        return frozenset(n.strip() for n in self.sms_allowlist.split(",") if n.strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()
