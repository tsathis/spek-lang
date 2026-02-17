"""Human readable table of what each effect tag means and what
triggers it in the static checker, used by docs and --help output."""

from spek.effects.vocabulary import EFFECTS

ROWS = [
    ("net", "requests.get/post/put/delete, urllib, sockets"),
    ("db", "cursor.execute, ORM query calls"),
    ("fs", "open, read, write"),
    ("hash", "hashlib.sha256/md5/new, hmac"),
]


def render_table():
    lines = ["effect | description | detected via"]
    for name, trigger in ROWS:
        lines.append(f"{name} | {EFFECTS.get(name, '')} | {trigger}")
    return "\n".join(lines)
