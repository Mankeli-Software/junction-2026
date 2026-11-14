"""Connector accounts over HTTP (#48): sign-up, login, the rate limit, hand-out accounts and
their phone step. Needs DATABASE_URL."""

import csv
import importlib.util
import random
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.interfaces.deps import SESSION_COOKIE
from app.main import app
from app.models import User
from app.services.accounts import create_unclaimed_account

pytestmark = pytest.mark.usefixtures("app_db", "no_caller")

PASSWORD = "correct horse battery"
SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "create_handout_accounts.py"


def new_number() -> str:
    return f"+35840{random.randrange(10**6, 10**7)}"


def new_email() -> str:
    return f"Chef.{uuid.uuid4().hex[:10]}@Example.com"


def browser() -> TestClient:
    return TestClient(app)


def sign_up(client: TestClient, email: str, phone: str, password: str = PASSWORD):
    return client.post(
        "/api/v1/signup", json={"email": email, "password": password, "phone_e164": phone}
    )


def log_in(client: TestClient, email: str, password: str = PASSWORD):
    return client.post("/api/v1/session", json={"email": email, "password": password})


def test_sign_up_logs_in_and_gets_the_numbers_company():
    client, other = browser(), browser()
    phone = new_number()
    demo = other.post(
        "/api/v1/demo/accounts", json={"phone_e164": phone, "exclusions": [], "lang": "fi"}
    ).json()

    response = sign_up(client, new_email(), phone.replace("+358", "0"))

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["company_name"] == demo["company_name"]  # same number, same company
    assert body["phone_masked"].startswith("+358 40 *** **")
    assert client.cookies.get(SESSION_COOKIE)
    assert client.get("/api/v1/me").json()["user_id"] == body["user_id"]


@pytest.mark.parametrize(
    ("email", "password", "phone", "field"),
    [
        ("not-an-email", PASSWORD, "+358401234567", "email"),
        ("a@example.com", "short", "+358401234567", "password"),
        ("a@example.com", PASSWORD, "12", "phone_e164"),
    ],
)
def test_sign_up_checks_its_fields(email, password, phone, field):
    response = sign_up(browser(), email, phone, password)
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", field]


def test_duplicate_email_is_409_whatever_the_case():
    email = new_email()
    assert sign_up(browser(), email, new_number()).status_code == 201

    response = sign_up(browser(), email.upper(), new_number())

    assert response.status_code == 409
    assert "email" in response.json()["detail"]


def test_log_in_and_log_out():
    email = new_email()
    sign_up(browser(), email, new_number())
    client = browser()

    response = log_in(client, email.upper())

    assert response.status_code == 200, response.text
    assert response.json() == {"phone_required": False}
    assert client.get("/api/v1/me").status_code == 200
    assert client.delete("/api/v1/session").status_code == 204
    assert client.get("/api/v1/me").status_code == 401


def test_wrong_password_and_unknown_email_get_the_same_answer():
    email = new_email()
    sign_up(browser(), email, new_number())

    wrong = log_in(browser(), email, "wrong password!")
    unknown = log_in(browser(), new_email())
    garbage = log_in(browser(), "no email here")

    assert wrong.status_code == unknown.status_code == garbage.status_code == 401
    assert wrong.json() == unknown.json() == garbage.json() == {"detail": "Wrong email or password"}
    assert SESSION_COOKIE not in wrong.cookies


def test_ten_failed_tries_block_the_email_for_a_while():
    email = new_email()
    sign_up(browser(), email, new_number())
    client = browser()
    for _ in range(10):
        assert log_in(client, email, "wrong password!").status_code == 401

    # Blocked even with the right password, and other emails are not affected.
    assert log_in(client, email).status_code == 429
    other = new_email()
    sign_up(browser(), other, new_number())
    assert log_in(client, other).status_code == 200


def test_a_successful_login_resets_the_count():
    email = new_email()
    sign_up(browser(), email, new_number())
    client = browser()
    for _ in range(9):
        log_in(client, email, "wrong password!")
    assert log_in(client, email).status_code == 200
    for _ in range(9):
        log_in(client, email, "wrong password!")
    assert log_in(client, email).status_code == 200


async def test_first_login_of_a_handout_account_asks_for_the_phone_once(app_db: AsyncEngine):
    email = new_email().lower()
    async with AsyncSession(app_db) as db:
        await create_unclaimed_account(db, email, PASSWORD)
        await db.commit()
    client = browser()

    assert log_in(client, email).json() == {"phone_required": True}
    # Without a number the account can't act yet.
    assert client.get("/api/v1/me").status_code == 401

    response = client.post("/api/v1/me/phone", json={"phone_e164": new_number()})
    assert response.status_code == 200, response.text
    assert response.json()["company_name"].endswith("Oy")
    assert client.get("/api/v1/me").status_code == 200

    again = client.post("/api/v1/me/phone", json={"phone_e164": new_number()})
    assert again.status_code == 409
    assert log_in(browser(), email).json() == {"phone_required": False}


def test_setting_the_phone_needs_a_session_and_a_valid_number():
    assert browser().post("/api/v1/me/phone", json={"phone_e164": new_number()}).status_code == 401

    client = browser()
    sign_up(client, new_email(), new_number())
    assert client.post("/api/v1/me/phone", json={"phone_e164": "12"}).status_code == 422
    # A signed-up account has its number already.
    assert client.post("/api/v1/me/phone", json={"phone_e164": new_number()}).status_code == 409


def _script():
    spec = importlib.util.spec_from_file_location("create_handout_accounts", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_handout_emails_are_numbered():
    script = _script()
    assert script.handout_emails(3, "judge", "simo.mankeli.co") == [
        "judge01@simo.mankeli.co",
        "judge02@simo.mankeli.co",
        "judge03@simo.mankeli.co",
    ]
    assert script.handout_emails(2, "peer", "x.fi", start=99) == ["peer099@x.fi", "peer100@x.fi"]


async def test_handout_script_creates_n_unclaimed_accounts(app_db: AsyncEngine, tmp_path: Path):
    script = _script()
    prefix = f"judge{uuid.uuid4().hex[:6]}"
    out = tmp_path / "handout.csv"

    assert await script.main(["--count", "3", "--prefix", prefix, "--out", str(out)]) == 0

    rows = list(csv.DictReader(out.open()))
    assert [r["email"] for r in rows] == [f"{prefix}0{n}@simo.mankeli.co" for n in (1, 2, 3)]
    assert all(len(r["password"]) == 12 for r in rows)
    assert out.stat().st_mode & 0o077 == 0
    async with AsyncSession(app_db) as db:
        users = (await db.scalars(select(User).where(User.email.startswith(prefix)))).all()
    assert len(users) == 3
    assert all(u.phone_e164 is None and u.company_id is None for u in users)

    # The cards work: the first login asks for the number.
    assert log_in(browser(), rows[0]["email"], rows[0]["password"]).json() == {
        "phone_required": True
    }

    # Re-running skips what exists and refuses to overwrite the CSV.
    again = tmp_path / "again.csv"
    assert await script.main(["--count", "4", "--prefix", prefix, "--out", str(again)]) == 0
    assert [r["email"] for r in csv.DictReader(again.open())] == [f"{prefix}04@simo.mankeli.co"]
    with pytest.raises(SystemExit):
        await script.main(["--count", "1", "--prefix", prefix, "--out", str(out)])
