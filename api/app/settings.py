"""Settings for the API.

On laptops the values come from environment variables and the `.env` file at the
repository root. On the VM they come from Azure Key Vault (#28) through this same loader.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql+psycopg://junction:junction@localhost:5432/junction"

    valio_source: Literal["snapshot", "live"] = "snapshot"
    valio_api_key: str = ""
    gemini_api_key: str = ""

    sms_twilio_enabled: bool = False
    # Comma-separated phone numbers in E.164 form that may get a real SMS.
    sms_allowlist: str = ""

    session_secret: str = ""

    @property
    def sms_allowlist_numbers(self) -> frozenset[str]:
        return frozenset(n.strip() for n in self.sms_allowlist.split(",") if n.strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()
