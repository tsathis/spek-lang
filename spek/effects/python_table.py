"""Which Python symbols mean which effect.

Entries are dotted *prefixes* matched longest-first against a fully resolved
name, so `datetime.datetime.now` is reached from `from datetime import
datetime` as readily as from `import datetime`.

The table is deliberately conservative. A false positive here is an error on
correct code, which is far more expensive than a miss: `os.path.join` is pure
path arithmetic and is not listed, while `os.remove` is.
"""

from __future__ import annotations

_PREFIXES: dict[str, tuple[str, ...]] = {
    "net": (
        "requests", "httpx", "urllib", "urllib3", "http.client", "http.server",
        "aiohttp", "socket", "ssl", "ftplib", "smtplib", "poplib", "imaplib",
        "telnetlib", "websockets", "websocket", "grpc", "boto3", "botocore",
        "paramiko", "xmlrpc", "asyncio.open_connection", "socketserver",
    ),
    "fs": (
        "pathlib", "shutil", "tempfile", "glob", "fileinput", "zipfile",
        "tarfile", "gzip", "bz2", "lzma", "mmap", "os.remove", "os.unlink",
        "os.rename", "os.replace", "os.mkdir", "os.makedirs", "os.rmdir",
        "os.removedirs", "os.listdir", "os.scandir", "os.walk", "os.stat",
        "os.lstat", "os.chmod", "os.chown", "os.link", "os.symlink",
        "os.readlink", "os.truncate", "os.access", "os.chdir", "os.open",
        "aiofiles",
    ),
    "db": (
        "sqlite3", "aiosqlite", "psycopg", "psycopg2", "pymysql", "MySQLdb",
        "mysql", "sqlalchemy", "asyncpg", "redis", "aioredis", "pymongo",
        "motor", "cassandra", "elasticsearch", "opensearchpy", "peewee",
        "django.db", "tortoise", "duckdb", "pyodbc", "clickhouse_driver",
    ),
    "hash": (
        "hashlib", "hmac", "bcrypt", "argon2", "passlib", "cryptography",
        "nacl", "Crypto", "crypt", "scrypt", "jwt",
    ),
    "rand": ("random", "secrets", "uuid", "numpy.random", "os.urandom"),
    "clock": (
        "time", "datetime.datetime.now", "datetime.datetime.utcnow",
        "datetime.datetime.today", "datetime.date.today", "calendar.timegm",
        "asyncio.sleep", "monotonic",
    ),
    "env": ("os.environ", "os.getenv", "os.putenv", "os.unsetenv", "dotenv"),
    "proc": (
        "subprocess", "multiprocessing", "os.system", "os.popen", "os.fork",
        "os.kill", "os.execv", "os.execve", "os.execl", "os.execlp",
        "os.execvp", "os.spawnl", "os.spawnv", "os.spawnvp", "os.abort",
        "os._exit", "signal", "pty", "sys.exit",
    ),
    "io": ("sys.stdout", "sys.stderr", "sys.stdin"),
    "ai": (
        "anthropic", "openai", "cohere", "mistralai", "litellm", "langchain",
        "ollama", "google.generativeai", "transformers.pipeline",
    ),
}

#: dotted prefix -> effect tag
SYMBOL_EFFECTS: dict[str, str] = {
    prefix: tag for tag, prefixes in _PREFIXES.items() for prefix in prefixes
}

#: builtin call name -> effect tag
BUILTIN_EFFECTS: dict[str, str] = {
    "open": "fs",
    "print": "io",
    "input": "io",
}

#: decorators that park results between calls
MEMOIZING_DECORATORS: frozenset[str] = frozenset(
    {"functools.lru_cache", "functools.cache", "functools.cached_property"}
)

#: module-level constructors whose result is mutable, hence shared state
MUTABLE_CONSTRUCTORS: frozenset[str] = frozenset(
    {
        "dict", "list", "set", "bytearray", "collections.defaultdict",
        "collections.OrderedDict", "collections.deque", "collections.Counter",
        "weakref.WeakValueDictionary",
    }
)


#: Modules that compute but never reach outside the process. A call into one of
#: these is not an analysis blind spot, so it does not soften a drift finding.
PURE_MODULES: frozenset[str] = frozenset(
    {
        "abc", "array", "base64", "binascii", "bisect", "collections", "colorsys",
        "copy", "csv", "dataclasses", "decimal", "difflib", "enum", "fnmatch",
        "fractions", "functools", "graphlib", "heapq", "html", "itertools", "json",
        "math", "numbers", "operator", "pprint", "re", "reprlib", "statistics",
        "string", "struct", "textwrap", "types", "typing", "unicodedata",
        "urllib.parse", "warnings", "weakref",
    }
)


def is_opaque(dotted: str) -> bool:
    """True when a call could hide an effect we cannot see."""
    parts = dotted.split(".")
    for stop in range(len(parts), 0, -1):
        if ".".join(parts[:stop]) in PURE_MODULES:
            return False
    return effect_for(dotted) is None


def effect_for(dotted: str) -> str | None:
    """Longest-prefix lookup: `requests.adapters.HTTPAdapter` -> `net`."""
    parts = dotted.split(".")
    for stop in range(len(parts), 0, -1):
        tag = SYMBOL_EFFECTS.get(".".join(parts[:stop]))
        if tag is not None:
            return tag
    return None
