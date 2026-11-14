"""Settings for the API.

On laptops the values come from environment variables and the `.env` file at the
repository root. On the VM, KEY_VAULT_URL points at the Azure Key Vault and the
values come from there.
"""

import os
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

    database_url: str = "postgresql+psycopg://junction:junction@localhost:5432/junction"
    # Alembic uses this one when it is set, so migrations can run as the table owner while
    # the app uses a user that cannot change the schema. Empty means use `database_url`.
    migration_database_url: str = ""

    valio_source: Literal["snapshot", "live"] = "snapshot"
    valio_api_key: str = ""
    gemini_api_key: str = ""

    sms_twilio_enabled: bool = False
    # Comma-separated phone numbers in E.164 form that may get a real SMS.
    sms_allowlist: str = ""

    session_secret: str = ""

    # Rule files (technical-plan.md §4.3). The container mounts them read-only.
    policy_dir: Path = REPO_ROOT / "policy"
    data_dir: Path = REPO_ROOT / "data"

    # Until real accounts land (#44), every request acts as one fixed demo customer when this
    # is on. Off means requests without a caller get 401.
    dev_fake_caller: bool = False

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

    @property
    def migrations_url(self) -> str:
        return self.migration_database_url or self.database_url

    @property
    def sms_allowlist_numbers(self) -> frozenset[str]:
        return frozenset(n.strip() for n in self.sms_allowlist.split(",") if n.strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()
