"""Fixtures for auth.spek.

Binds the bare words the examples use to real values, and seeds a database the
implementation can read.
"""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

from spek.runtime import implementation

KNOWN = "ada@example.com"
LOCKED = "grace@example.com"
RIGHT = "correct horse battery staple"


def _seed() -> None:
    auth = implementation("auth")
    auth.DB_PATH = str(Path(tempfile.mkdtemp(prefix="spek-auth-")) / "auth.db")

    connection = sqlite3.connect(auth.DB_PATH)
    with connection:
        connection.execute(
            "CREATE TABLE users (email TEXT PRIMARY KEY, salt TEXT, pw_hash TEXT, locked INT)"
        )
        connection.executemany(
            "INSERT INTO users VALUES (?, ?, ?, ?)",
            [
                (KNOWN, "salt-a", auth.hash_password(RIGHT, "salt-a"), 0),
                (LOCKED, "salt-g", auth.hash_password(RIGHT, "salt-g"), 1),
            ],
        )
    connection.close()


_seed()

FIXTURES = {
    "known": KNOWN,
    "right": RIGHT,
    "bad_pw": "hunter2",
    "unknown": "nobody@example.com",
    "any": "anything at all",
    "locked_acct": LOCKED,
}
