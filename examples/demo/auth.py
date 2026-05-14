"""Implementation verified by auth.spek.

Outcomes follow the spek protocol: success returns, every other outcome is an
exception whose class name contains the outcome word.
"""

from __future__ import annotations

import hashlib
import hmac
import sqlite3
from dataclasses import dataclass

DB_PATH = "auth.db"
_ITERATIONS = 120_000


class WrongCredentials(Exception):
    """Bad email or bad password -- deliberately indistinguishable."""


class AccountLockedError(Exception):
    """Credentials were right, but the account is locked."""


@dataclass(frozen=True)
class Session:
    email: str
    token: str


def hash_password(password: str, salt: str) -> str:
    derived = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), _ITERATIONS)
    return derived.hex()


def _load(email: str) -> tuple[str, str, str, int] | None:
    connection = sqlite3.connect(DB_PATH)
    try:
        cursor = connection.execute(
            "SELECT email, salt, pw_hash, locked FROM users WHERE email = ?", (email,)
        )
        return cursor.fetchone()
    finally:
        connection.close()


def login(email: str, password: str) -> Session:
    row = _load(email)
    if row is None:
        # Same failure as a bad password: no user enumeration.
        raise WrongCredentials("email or password is wrong")

    _, salt, expected, locked = row
    if not hmac.compare_digest(hash_password(password, salt), expected):
        raise WrongCredentials("email or password is wrong")

    if locked:
        raise AccountLockedError(f"{email} is locked")

    return Session(email=email, token=hash_password(expected, "session")[:32])
