"""Settings for the API.

On laptops the values come from environment variables and the `.env` file at the
repository root. On the VM they come from Azure Key Vault (#28) through this same loader.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


def psycopg_url(url: str) -> str:
    """Make a plain Postgres URL use the psycopg 3 driver that SQLAlchemy needs here.

    Key Vault keeps the plain `postgresql://` form so `psql` can use the same secret.
    """
    for plain in ("postgresql://", "postgres://"):
        if url.startswith(plain):
            return "postgresql+psycopg://" + url[len(plain) :]
    return url


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
