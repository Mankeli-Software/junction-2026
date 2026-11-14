"""Create a batch of hand-out connector accounts for judges and peers (#48).

Each account gets an email (`judge01@simo.mankeli.co` ...) and a random password, and no
phone number: the login page asks for it on first login, and that sets the account's
company. The emails and passwords go to a CSV for printing on cards.

The CSV holds live passwords: write it outside the repository, never commit it
(`.gitignore` also ignores `*handout*.csv`). The file must not exist yet.

Usage, from `api/` so the app's settings and database are used:

    uv run python ../scripts/create_handout_accounts.py --count 20 --prefix judge \\
        --out ~/simo-handout-accounts.csv

On the VM the api image has no `scripts/`, so copy the script in and run it from the
app's directory, where it finds `app` and the app's settings (Key Vault):

    docker compose -f deploy/docker-compose.yml cp scripts/create_handout_accounts.py api:/tmp/
    docker compose -f deploy/docker-compose.yml exec api \
        python /tmp/create_handout_accounts.py --count 20 --out /tmp/handout.csv
    docker compose -f deploy/docker-compose.yml cp api:/tmp/handout.csv ~/handout.csv

Accounts whose email exists already are skipped and left unchanged, so the script can be
re-run with a larger --count or another --start.
"""

import argparse
import asyncio
import csv
import secrets
import sys
from dataclasses import dataclass
from pathlib import Path

# `app` lives in api/ next to this script in the repository, or in the working directory
# inside the api container.
for _path in (Path.cwd(), Path(__file__).resolve().parents[1] / "api"):
    if (_path / "app").is_dir() and str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.services.accounts import EmailTaken, create_unclaimed_account  # noqa: E402

DEFAULT_DOMAIN = "simo.mankeli.co"


@dataclass(frozen=True)
class HandoutAccount:
    email: str
    password: str


def new_password() -> str:
    """12 URL-safe characters (9 random bytes): easy to type from a card."""
    return secrets.token_urlsafe(9)


def handout_emails(count: int, prefix: str, domain: str, start: int = 1) -> list[str]:
    width = max(2, len(str(start + count - 1)))
    return [f"{prefix}{n:0{width}d}@{domain}" for n in range(start, start + count)]


async def create_accounts(
    db: AsyncSession, emails: list[str]
) -> tuple[list[HandoutAccount], list[str]]:
    """Create the accounts that don't exist yet. Returns (created, skipped emails).

    Flushes only; the caller commits.
    """
    created: list[HandoutAccount] = []
    skipped: list[str] = []
    for email in emails:
        password = new_password()
        try:
            await create_unclaimed_account(db, email, password)
        except EmailTaken:
            skipped.append(email)
            continue
        created.append(HandoutAccount(email, password))
    return created, skipped


def write_csv(path: Path, accounts: list[HandoutAccount]) -> None:
    """Write `email,password` rows to a new file, readable only by its owner."""
    with path.open("x", newline="", encoding="utf-8") as handle:
        path.chmod(0o600)
        writer = csv.writer(handle)
        writer.writerow(["email", "password"])
        for account in accounts:
            writer.writerow([account.email, account.password])


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--count", type=int, default=20)
    parser.add_argument("--prefix", default="judge")
    parser.add_argument("--domain", default=DEFAULT_DOMAIN)
    parser.add_argument("--start", type=int, default=1, help="first number (default 1)")
    parser.add_argument("--out", type=Path, required=True, help="CSV to write; must not exist")
    args = parser.parse_args(argv)

    out = args.out.expanduser().resolve()
    if out.exists():
        parser.error(f"{out} exists already; pick a new file")
    if not out.parent.is_dir():
        parser.error(f"{out.parent} is not a directory")

    from app.db import get_engine, get_sessionmaker

    emails = handout_emails(args.count, args.prefix, args.domain, args.start)
    async with get_sessionmaker()() as db:
        created, skipped = await create_accounts(db, emails)
        # The CSV first: if it can't be written, nothing is committed and no password is lost.
        write_csv(out, created)
        try:
            await db.commit()
        except BaseException:
            out.unlink()  # its passwords would match nothing
            raise
    await get_engine().dispose()

    print(f"Created {len(created)} accounts, written to {out}")
    if skipped:
        print(f"Skipped {len(skipped)} that exist already: {', '.join(skipped)}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
