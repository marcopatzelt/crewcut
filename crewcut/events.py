"""Events feed the live UI. Any process (server, worker, an agent's `crewcut` call) appends; the server streams them."""

from __future__ import annotations

from . import db

KINDS = ("activity", "message", "card", "cost", "episode", "log")


def emit(kind: str, episode: str | None = None, identity: str | None = None, text: str = "", data: dict | None = None) -> int:
    if kind not in KINDS:
        raise ValueError(f"unknown event kind {kind}")
    return db.insert("events", at=db.now(), episode=episode, kind=kind, identity=identity, text=text, data=data or {})


def since(last_id: int, limit: int = 500) -> list[dict]:
    with db.conn() as c:
        return db.rows(c.execute("SELECT * FROM events WHERE id > ? ORDER BY id LIMIT ?", (last_id, limit)))


def last_id() -> int:
    with db.conn() as c:
        r = c.execute("SELECT MAX(id) AS m FROM events").fetchone()
        return int(r["m"] or 0)
