"""Known effect tags."""

EFFECTS = {
    "net": "Network operations",
    "db": "Database operations",
    "fs": "Filesystem operations",
    "hash": "Hashing/cryptography",
}


def is_valid(name):
    return name in EFFECTS
