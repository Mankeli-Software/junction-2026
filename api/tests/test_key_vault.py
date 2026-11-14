from azure.core.exceptions import ResourceNotFoundError

from app.settings import KeyVaultSettingsSource, Settings


class FakeSecret:
    def __init__(self, value: str):
        self.value = value


class FakeVault:
    def __init__(self, secrets: dict[str, str]):
        self.secrets = secrets
        self.asked: list[str] = []

    def get_secret(self, name: str) -> FakeSecret:
        self.asked.append(name)
        if name not in self.secrets:
            raise ResourceNotFoundError("not found")
        return FakeSecret(self.secrets[name])


def test_secrets_are_read_by_their_dashed_names():
    vault = FakeVault({"valio-api-key": "key-1", "session-secret": "s3"})

    values = KeyVaultSettingsSource(Settings, "https://vault", client=vault)()

    assert values == {"valio_api_key": "key-1", "session_secret": "s3"}


def test_the_migration_url_comes_from_the_admin_secret():
    vault = FakeVault({"database-admin-url": "postgresql://admin:pw@host/db"})

    values = KeyVaultSettingsSource(Settings, "https://vault", client=vault)()

    assert values == {"migration_database_url": "postgresql://admin:pw@host/db"}
    assert "migration-database-url" not in vault.asked


def test_without_a_vault_url_nothing_is_read():
    vault = FakeVault({"valio-api-key": "key-1"})

    assert KeyVaultSettingsSource(Settings, "", client=vault)() == {}
    assert vault.asked == []


def test_environment_variables_win_over_key_vault(monkeypatch):
    monkeypatch.setenv("KEY_VAULT_URL", "")
    monkeypatch.setenv("VALIO_API_KEY", "from-env")
    settings = Settings(_env_file=None)

    assert settings.valio_api_key == "from-env"
