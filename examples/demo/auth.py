"""Reference auth implementation for trying spek out end to end."""

import hashlib

users = {
    "alice@example.com": {"hash": hashlib.sha256(b"correct_password").hexdigest(), "locked": False},
    "locked@example.com": {"hash": hashlib.sha256(b"correct_password").hexdigest(), "locked": True},
}


class Wrong(Exception):
    pass


class Locked(Exception):
    pass


def login(email, password):
    if email not in users:
        raise Wrong()
    u = users[email]
    if u["locked"]:
        raise Locked()
    if hashlib.sha256(password.encode()).hexdigest() != u["hash"]:
        raise Wrong()
    return f"session_{email}"
