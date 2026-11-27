"""One small SQLite file for jobs, cards, the cost book, rentals, events and chat messages.

Use `with db.conn() as c:` for every access. Each call opens its own connection, so threads and the `crewcut` command
(run by agents in other processes) can share the file. WAL mode keeps readers and one writer from blocking each other.
"""

from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from . import paths

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  episode TEXT, step TEXT, identity TEXT,
  kind TEXT NOT NULL DEFAULT 'agent',          -- agent | tool
  task TEXT NOT NULL DEFAULT '',
  heavy INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'queued',        -- queued | running | waiting | done | failed | cancelled
  doing TEXT, progress REAL,
  created TEXT NOT NULL, started TEXT, ended TEXT,
  cost_usd REAL NOT NULL DEFAULT 0, equiv_usd REAL NOT NULL DEFAULT 0,
  log_path TEXT, result TEXT, parent INTEGER, data TEXT
);
CREATE INDEX IF NOT EXISTS jobs_status ON jobs(status);
CREATE TABLE IF NOT EXISTS cards (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  episode TEXT, step TEXT, kind TEXT NOT NULL, identity TEXT,
  title TEXT NOT NULL, body TEXT, file TEXT, sha256 TEXT, preview TEXT,
  options TEXT, data TEXT,
  status TEXT NOT NULL DEFAULT 'open',          -- open | accepted | declined | expired
  choice INTEGER, reason TEXT, decided_at TEXT,
  created TEXT NOT NULL, job INTEGER
);
CREATE INDEX IF NOT EXISTS cards_status ON cards(status);
CREATE TABLE IF NOT EXISTS costs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  at TEXT NOT NULL, episode TEXT, step TEXT,
  kind TEXT NOT NULL,                           -- gpu | api | other
  amount_usd REAL NOT NULL, detail TEXT, ref TEXT
);
CREATE TABLE IF NOT EXISTS rentals (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  provider TEXT NOT NULL, instance TEXT, label TEXT,
  episode TEXT, job INTEGER,
  price_per_hour REAL, started TEXT, deadline TEXT, ended TEXT,
  status TEXT NOT NULL DEFAULT 'starting',      -- starting | ready | running | destroyed | failed
  detail TEXT
);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  at TEXT NOT NULL, episode TEXT, kind TEXT NOT NULL, identity TEXT, text TEXT, data TEXT
);
CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  at TEXT NOT NULL, episode TEXT NOT NULL, author TEXT NOT NULL, text TEXT NOT NULL,
  cite TEXT, card INTEGER, job INTEGER, step TEXT, data TEXT
);
CREATE INDEX IF NOT EXISTS messages_episode ON messages(episode, id);
CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS ideas (
  id TEXT PRIMARY KEY,
  source TEXT NOT NULL,                         -- scout | braindump | other
  url TEXT, title TEXT NOT NULL, summary TEXT, signals TEXT,
  topic_type TEXT, suggested_format TEXT, reason TEXT, suggestion TEXT,   -- suggestion: exporter | rule
  length TEXT,
  status TEXT NOT NULL DEFAULT 'open',          -- open | started | dismissed
  episode TEXT, created TEXT, imported TEXT NOT NULL, decided_at TEXT, file TEXT
);
CREATE INDEX IF NOT EXISTS ideas_status ON ideas(status);
"""

_ready: set[str] = set()


def now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_time(s: str | None) -> float | None:
    if not s:
        return None
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC).timestamp()


@contextmanager
def conn(path: Path | None = None) -> Iterator[sqlite3.Connection]:
    p = str(path or paths.db_path())
    c = sqlite3.connect(p, timeout=30, isolation_level=None)
    c.row_factory = sqlite3.Row
    try:
        if p not in _ready:
            c.execute("PRAGMA journal_mode=WAL")
            c.executescript(SCHEMA)
            c.execute("BEGIN IMMEDIATE")
            if "scope" not in {r["name"] for r in c.execute("PRAGMA table_info(messages)")}:
                c.execute("ALTER TABLE messages ADD COLUMN scope TEXT NOT NULL DEFAULT 'episode'")
                c.execute("UPDATE messages SET scope = 'onboarding' WHERE episode = '_onboarding'")
                c.execute("UPDATE messages SET scope = 'channel', episode = '' WHERE episode = '_channel'")
            c.execute("CREATE INDEX IF NOT EXISTS messages_scope ON messages(scope, id)")
            c.commit()
            _ready.add(p)
        c.execute("PRAGMA busy_timeout=30000")
        yield c
    finally:
        c.close()


def row(r: sqlite3.Row | None) -> dict | None:
    if r is None:
        return None
    d = dict(r)
    for k in ("options", "data"):
        if k in d and isinstance(d[k], str):
            try:
                d[k] = json.loads(d[k])
            except ValueError:
                pass
    return d


def rows(rs) -> list[dict]:
    return [row(r) for r in rs]


def insert(table: str, **values) -> int:
    for k in ("options", "data"):
        if k in values and values[k] is not None and not isinstance(values[k], str):
            values[k] = json.dumps(values[k], ensure_ascii=False)
    cols = ", ".join(values)
    marks = ", ".join("?" for _ in values)
    with conn() as c:
        cur = c.execute(f"INSERT INTO {table} ({cols}) VALUES ({marks})", tuple(values.values()))
        return int(cur.lastrowid)


def update(table: str, id_: int, **values) -> None:
    if not values:
        return
    for k in ("options", "data"):
        if k in values and values[k] is not None and not isinstance(values[k], str):
            values[k] = json.dumps(values[k], ensure_ascii=False)
    sets = ", ".join(f"{k} = ?" for k in values)
    with conn() as c:
        c.execute(f"UPDATE {table} SET {sets} WHERE id = ?", (*values.values(), id_))


def get(table: str, id_: int) -> dict | None:
    with conn() as c:
        return row(c.execute(f"SELECT * FROM {table} WHERE id = ?", (id_,)).fetchone())


def kv_get(k: str, default: str | None = None) -> str | None:
    with conn() as c:
        r = c.execute("SELECT v FROM kv WHERE k = ?", (k,)).fetchone()
        return r["v"] if r else default


def kv_set(k: str, v: str) -> None:
    with conn() as c:
        c.execute("INSERT INTO kv (k, v) VALUES (?, ?) ON CONFLICT(k) DO UPDATE SET v = excluded.v", (k, v))


def wait_until(check, timeout: float | None = None, every: float = 1.0):
    """Poll check() until it returns something truthy or the timeout passes (then None)."""
    t0 = time.time()
    while True:
        v = check()
        if v:
            return v
        if timeout is not None and time.time() - t0 > timeout:
            return None
        time.sleep(every)
