"""Passwords for connector accounts (#48): argon2id hashes and the failed-login limit.

`argon2-cffi` with its default parameters. The limit is in memory, which is enough for
the one uvicorn worker we run (`technical-plan.md` §10.2); a restart clears it.
"""

import threading
import time
from collections import defaultdict, deque

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

MIN_PASSWORD_LENGTH = 10

_hasher = PasswordHasher()
# Verified when the email is unknown, so a wrong email takes as long as a wrong password.
_DUMMY_HASH = _hasher.hash("not a real password")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    """Whether the password matches. A missing hash still costs one verification."""
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and bool(password_hash)
    except (VerificationError, InvalidHashError):
        return False


class FailedLogins:
    """At most `limit` failed tries per email in a sliding `window` of seconds."""

    def __init__(self, limit: int = 10, window: float = 600.0) -> None:
        self.limit = limit
        self.window = window
        self._failures: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, email: str, now: float) -> deque[float]:
        failures = self._failures[email]
        while failures and failures[0] <= now - self.window:
            failures.popleft()
        if not failures:
            del self._failures[email]
            return deque()
        return failures

    def blocked(self, email: str, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        with self._lock:
            return len(self._prune(email, now)) >= self.limit

    def record_failure(self, email: str, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        with self._lock:
            self._prune(email, now)
            self._failures[email].append(now)

    def clear(self, email: str) -> None:
        with self._lock:
            self._failures.pop(email, None)


failed_logins = FailedLogins()
