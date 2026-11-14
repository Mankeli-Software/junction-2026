from app.settings import Settings, psycopg_url


def test_plain_postgres_urls_get_the_psycopg_driver():
    assert psycopg_url("postgresql://u:p@host:5432/db?sslmode=require") == (
        "postgresql+psycopg://u:p@host:5432/db?sslmode=require"
    )
    assert psycopg_url("postgres://u:p@host/db") == "postgresql+psycopg://u:p@host/db"


def test_urls_that_already_name_a_driver_are_left_alone():
    url = "postgresql+psycopg://u:p@host/db"

    assert psycopg_url(url) == url


def test_settings_apply_the_driver_to_both_database_urls(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://app:pw@host/db")
    monkeypatch.setenv("MIGRATION_DATABASE_URL", "postgresql://admin:pw@host/db")

    settings = Settings(_env_file=None)

    assert settings.database_url == "postgresql+psycopg://app:pw@host/db"
    assert settings.migrations_url == "postgresql+psycopg://admin:pw@host/db"


def test_migrations_use_the_app_url_when_no_migration_url_is_set(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://app:pw@host/db")
    monkeypatch.delenv("MIGRATION_DATABASE_URL", raising=False)

    assert Settings(_env_file=None).migrations_url == "postgresql+psycopg://app:pw@host/db"


TWILIO = {
    "twilio_account_sid": "AC-test",
    "twilio_auth_token": "test-token",
    "twilio_from_number": "+15005550006",
}


def test_twilio_counts_as_enabled_only_with_the_flag_and_every_setting():
    assert Settings(_env_file=None, sms_twilio_enabled=True, **TWILIO).twilio_enabled
    assert not Settings(_env_file=None, sms_twilio_enabled=False, **TWILIO).twilio_enabled
    for missing in TWILIO:
        settings = Settings(_env_file=None, sms_twilio_enabled=True, **{**TWILIO, missing: ""})
        assert not settings.twilio_enabled, missing
