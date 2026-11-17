"""Small state files of the compute module, all under studio/.crewcut/compute/.

  label         the studio id; machines carry the label <prefix>-<id>, and only those are ever destroyed
  blocked.json  hosts and machines that failed us (learned per studio, starts empty)
  local.json    measured seconds per frame (see local.py)
  choices.json  "local is fine" per episode, and the jobs that already saw a rent suggestion
  offers.json   a short cache of live offers for estimates
  ssh/          the studio's own SSH key for rented machines
Sessions live in the database (table kv, keys compute.session.<id>), next to the rentals table.
"""

from __future__ import annotations

import fcntl
import json
import os
import secrets
import socket
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .. import db, paths
from . import settings

# Time goes through these two names so tests can run a whole rental in no time.
clock: Callable[[], float] = time.time
sleep: Callable[[float], None] = time.sleep


def now() -> float:
    return clock()


def iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def hhmm(ts: float) -> str:
    return datetime.fromtimestamp(ts, UTC).strftime("%H:%M UTC")


def compute_dir() -> Path:
    p = paths.state_dir() / "compute"
    p.mkdir(parents=True, exist_ok=True)
    return p


@contextmanager
def locked() -> Iterator[None]:
    """A file lock for read-modify-write of the state files (between threads and between processes)."""
    f = open(compute_dir() / ".lock", "w")
    try:
        fcntl.flock(f, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(f, fcntl.LOCK_UN)
        f.close()


def read_json(name: str, default: Any) -> Any:
    try:
        return json.loads((compute_dir() / name).read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return default


def write_json(name: str, data: Any) -> None:
    p = compute_dir() / name
    tmp = p.with_name(p.name + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    tmp.replace(p)


def update_json(name: str, default: Any, fn: Callable[[Any], Any]) -> Any:
    with locked():
        data = fn(read_json(name, default))
        write_json(name, data)
        return data


# ---- label ---------------------------------------------------------------------------------------------------------
def studio_id() -> str:
    p = compute_dir() / "studio-id"
    with locked():
        if p.is_file():
            sid = p.read_text(encoding="utf-8").strip()
            if sid:
                return sid
        sid = secrets.token_hex(3)
        p.write_text(sid + "\n", encoding="utf-8")
        return sid


def label() -> str:
    prefix = str(settings.get("label_prefix") or "crewcut").strip() or "crewcut"
    return f"{prefix}-{studio_id()}"


# ---- blocked hosts -------------------------------------------------------------------------------------------------
def blocked() -> dict:
    d = read_json("blocked.json", {})
    return {"hosts": dict(d.get("hosts") or {}), "machines": dict(d.get("machines") or {})}


def is_blocked(offer: dict) -> bool:
    b = blocked()
    ip = str(offer.get("public_ipaddr") or "").strip()
    mid = str(offer.get("machine_id") or "")
    return (bool(ip) and ip in b["hosts"]) or (bool(mid) and mid in b["machines"])


def block(offer: dict, reason: str) -> None:
    ip = str(offer.get("public_ipaddr") or "").strip()
    mid = str(offer.get("machine_id") or "")

    def fn(d):
        d.setdefault("hosts", {})
        d.setdefault("machines", {})
        entry = {"at": iso(now()), "reason": reason[:200]}
        if ip:
            d["hosts"][ip] = entry
        if mid:
            d["machines"][mid] = entry
        return d

    update_json("blocked.json", {}, fn)


# ---- choices -------------------------------------------------------------------------------------------------------
def local_is_fine(episode: str | None) -> bool:
    return bool(episode) and episode in (read_json("choices.json", {}).get("local_fine") or {})


def set_local_fine(episode: str) -> None:
    def fn(d):
        d.setdefault("local_fine", {})[episode] = iso(now())
        return d

    update_json("choices.json", {}, fn)


def was_suggested(job: str | int | None) -> bool:
    return job is not None and str(job) in (read_json("choices.json", {}).get("suggested_jobs") or {})


def mark_suggested(job: str | int) -> None:
    def fn(d):
        d.setdefault("suggested_jobs", {})[str(job)] = iso(now())
        return d

    update_json("choices.json", {}, fn)


def image_failed_recently(hours: float = 24) -> bool:
    t = read_json("choices.json", {}).get("image_failed_at")
    return bool(t) and now() - float(t) < hours * 3600


def mark_image_failed() -> None:
    def fn(d):
        d["image_failed_at"] = now()
        return d

    update_json("choices.json", {}, fn)


# ---- sessions (database kv) ----------------------------------------------------------------------------------------
_PREFIX = "compute.session."


def save_session(rec: dict) -> None:
    db.kv_set(_PREFIX + rec["id"], json.dumps(rec, ensure_ascii=False))


def get_session(sid: str | None) -> dict | None:
    if not sid:
        return None
    v = db.kv_get(_PREFIX + sid)
    return json.loads(v) if v else None


def update_session(sid: str, **values) -> dict | None:
    with locked():
        rec = get_session(sid)
        if rec is None:
            return None
        rec.update(values)
        save_session(rec)
        return rec


def add_session_rental(sid: str, rental_id: int) -> None:
    with locked():
        rec = get_session(sid)
        if rec is None:
            return
        if rental_id not in rec.setdefault("rentals", []):
            rec["rentals"].append(rental_id)
        save_session(rec)


def open_sessions() -> list[dict]:
    out = []
    for r in _all_session_rows():
        try:
            rec = json.loads(r["v"])
        except ValueError:
            continue
        if not rec.get("closed"):
            out.append(rec)
    return out


def prune_sessions(days: float = 30) -> int:
    """Forget closed sessions older than this (their rentals and costs stay in the database)."""
    old = []
    for r in _all_session_rows():
        try:
            rec = json.loads(r["v"])
        except ValueError:
            continue
        closed = db.parse_time(rec.get("closed")) if isinstance(rec.get("closed"), str) else None
        if closed and now() - closed > days * 86400:
            old.append(r["k"])
    with db.conn() as c:
        for k in old:
            c.execute("DELETE FROM kv WHERE k = ?", (k,))
    return len(old)


def _all_session_rows():
    with db.conn() as c:
        return c.execute("SELECT k, v FROM kv WHERE k LIKE ?", (_PREFIX + "%",)).fetchall()


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return False
    except (PermissionError, ValueError, TypeError):
        return True
    return True


def session_live(sid: str | None) -> bool:
    """A session is live while it is open and (detached, or its process beats its heartbeat)."""
    rec = get_session(sid)
    if not rec or rec.get("closed"):
        return False
    if rec.get("detached"):
        return True
    stale = max(180.0, 6 * settings.num("limits.check_seconds"))
    if now() - float(rec.get("heartbeat") or 0) > stale:
        return False
    if rec.get("host") == socket.gethostname() and rec.get("pid") and not _pid_alive(rec["pid"]):
        return False
    return True


# ---- machine activity (the idle rule) ------------------------------------------------------------------------------
def touch(rental_id: int, busy: bool) -> None:
    """A rented machine starts (busy) or ends (idle since now) a command, upload or download."""
    def fn(d: dict) -> dict:
        d[str(int(rental_id))] = {"busy": bool(busy), "at": now()}
        return d
    update_json("activity.json", {}, fn)


def activity(rental_id: int) -> dict | None:
    return (read_json("activity.json", {}) or {}).get(str(int(rental_id)))
