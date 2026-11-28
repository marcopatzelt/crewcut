"""A video goes up once: one upload per episode at a time, and never again once YouTube has it.

On 24.11.2026 two Shorts went up twice. Each Short had two publish cards (the package changed seconds after the first
card), both were accepted at the terminal, and each yes queued its own Publisher job. The terminal session also ran
`crewcut youtube upload` itself. So a Publisher job and the terminal uploaded the same package at the same time:
`upload()` knew no lock and did not look at the episode's earlier upload, any accepted card of the package let both
through, and the later one overwrote export/upload-result.json. The jobs of the second cards did not add a third copy
only because the agent read that file and stopped.

Three layers now, all in `upload.upload()`:

1. **Lock.** One upload of an episode at a time, across processes and restarts: a row in `upload_locks` (SQLite), taken
   in one transaction. A lock whose holder stopped (no sign of life for `youtube.upload_lock_stale_minutes`, or its
   process on this machine is gone) is taken over.
2. **Record.** Every video Crewcut uploaded or found is a row in `uploads` (episode, video id, version = sha256 of the
   video file); the video id in export/upload-result.json counts as well. A recorded video that YouTube still has
   means: it is up already.
3. **YouTube.** Every upload carries a marker tag, `crewcut-<episode>-<version>` (8 hex digits each). Before an upload
   Crewcut reads the channel's newest uploads: a video with this episode's marker, or one from before the marker with
   exactly the same title, is the upload. It is recorded and reported; nothing goes up.

When YouTube cannot be asked, nothing goes up. A second video of an episode next to the first (another version of the
file) needs the person at the terminal: `crewcut youtube upload --new-video`. The same file never goes up twice.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import socket
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from .. import config, db, paths

GONE = ("failed", "rejected", "deleted")
MARKER = re.compile(r"^crewcut-([0-9a-f]{8})-([0-9a-f]{8})$")
MARKER_LEN = len("crewcut-") + 8 + 1 + 8
SCAN = 100              # the channel's newest uploads read before each upload
STALE_MINUTES = 30      # youtube.upload_lock_stale_minutes: no sign of life this long and the lock is free
DEAD_GRACE_S = 120      # a holder whose process is gone keeps the lock this long after its last sign of life, so YouTube
                        # has a moment to list a video that was finished just before


class Busy(RuntimeError):
    """Another upload of this episode runs."""

    def __init__(self, episode: str, lock: dict, now: float | None = None):
        self.lock = lock
        now = time.time() if now is None else now
        who = f"job #{lock['job']}" if lock.get("job") else f"process {lock.get('pid')}"
        quiet = max(0, int(now - float(lock.get("beat") or now)))
        super().__init__(f"Another upload of {episode} is running ({who}, since {lock.get('since')}, last sign of life "
                         f"{quiet} s ago). Crewcut does not start a second one; that run reports the link.")


class CheckFailed(RuntimeError):
    """YouTube could not be asked whether the video is there already: nothing goes up."""


# ---- the marker tag ---------------------------------------------------------------------------------------------------
def version_of(video: Path) -> str:
    from .. import approvals
    return approvals.sha256(video)


def episode_key(episode: str) -> str:
    return hashlib.sha256(episode.encode("utf-8")).hexdigest()[:8]


def marker(episode: str, version: str) -> str:
    """The tag every upload carries: which episode, which video file. 25 characters, no spaces."""
    return f"crewcut-{episode_key(episode)}-{version[:8]}"


def markers(tags: list[str] | None) -> list[str]:
    return [t for t in tags or [] if MARKER.match(t or "")]


def without_markers(tags: list[str] | None) -> list[str]:
    return [t for t in tags or [] if not MARKER.match(t or "")]


# ---- the lock ---------------------------------------------------------------------------------------------------------
def _stale_s() -> float:
    return float(config.get("crewcut", "youtube.upload_lock_stale_minutes", STALE_MINUTES)) * 60


def _start_time(pid: int) -> str | None:
    """When the process started (clock ticks after boot, /proc), so a reused process id is not taken for the holder."""
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
        return stat[stat.rindex(")") + 2:].split()[19]
    except (OSError, ValueError, IndexError):
        return None


def _alive(lock: dict) -> bool:
    """False only when the holder ran on this machine and its process is gone. Elsewhere only its heartbeat tells."""
    if lock.get("host") != socket.gethostname() or not lock.get("pid"):
        return True
    pid = int(lock["pid"])
    if Path("/proc/self/stat").is_file():
        start = _start_time(pid)
        return start is not None and (not lock.get("pid_start") or start == lock["pid_start"])
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _stale(lock: dict, now: float) -> bool:
    quiet = now - float(lock.get("beat") or 0)
    return quiet > _stale_s() or (quiet > DEAD_GRACE_S and not _alive(lock))


def holder(episode: str, now: float | None = None) -> dict | None:
    """The lock of a running upload of this episode, or None (a stale lock counts as free)."""
    now = time.time() if now is None else now
    with db.conn() as c:
        r = c.execute("SELECT * FROM upload_locks WHERE episode = ?", (episode,)).fetchone()
    lock = dict(r) if r else None
    return lock if lock and not _stale(lock, now) else None


def claim(episode: str, job: int | None = None, what: str = "", now: float | None = None) -> dict:
    """Take the episode's upload lock in one transaction, or raise Busy. A stale lock is taken over."""
    now = time.time() if now is None else now
    lock = {"episode": episode, "token": uuid.uuid4().hex, "job": job, "pid": os.getpid(),
            "host": socket.gethostname(), "pid_start": _start_time(os.getpid()), "since": db.now(), "beat": now,
            "what": what}
    with db.conn() as c:
        c.execute("BEGIN IMMEDIATE")
        r = c.execute("SELECT * FROM upload_locks WHERE episode = ?", (episode,)).fetchone()
        old = dict(r) if r else None
        if old and not _stale(old, now):
            c.execute("ROLLBACK")
            raise Busy(episode, old, now)
        c.execute("DELETE FROM upload_locks WHERE episode = ?", (episode,))
        c.execute("INSERT INTO upload_locks (episode, token, job, pid, host, pid_start, since, beat, what) "
                  "VALUES (:episode, :token, :job, :pid, :host, :pid_start, :since, :beat, :what)", lock)
        c.execute("COMMIT")
    return {**lock, "took_over": old}


def beat(lock: dict, now: float | None = None) -> None:
    """A sign of life of the upload that holds the lock (every chunk)."""
    with db.conn() as c:
        c.execute("UPDATE upload_locks SET beat = ? WHERE episode = ? AND token = ?",
                  (time.time() if now is None else now, lock["episode"], lock["token"]))


def release(lock: dict) -> None:
    with db.conn() as c:
        c.execute("DELETE FROM upload_locks WHERE episode = ? AND token = ?", (lock["episode"], lock["token"]))


@contextmanager
def locked(episode: str, job: int | None = None, what: str = "") -> Iterator[dict]:
    lock = claim(episode, job, what)
    try:
        yield lock
    finally:
        release(lock)


# ---- the episode's record ---------------------------------------------------------------------------------------------
def result_file(episode: str) -> dict:
    try:
        d = json.loads((paths.episode_dir(episode) / "export" / "upload-result.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return d if isinstance(d, dict) else {}


def recorded(episode: str) -> list[dict]:
    """Videos of this episode that Crewcut uploaded or found and does not know to be gone, newest first: the uploads
    table, then the video id in export/upload-result.json."""
    with db.conn() as c:
        rows = db.rows(c.execute("SELECT * FROM uploads WHERE episode = ? ORDER BY id DESC", (episode,)))
    up = [r for r in rows if r["status"] == "up"]
    gone = {r["video_id"] for r in rows if r["status"] == "gone"}
    res = result_file(episode)
    vid = res.get("video_id")
    if vid and vid not in gone and vid not in {r["video_id"] for r in up}:
        up.append({"episode": episode, "video_id": vid, "version": None, "source": "result-file",
                   "at": res.get("at"), "card": res.get("card"), "status": "up"})
    return up


def remember(episode: str, video_id: str, source: str, version: str | None = None, package: str | None = None,
             card: int | None = None, job: int | None = None, status: str = "up") -> None:
    """Record a video of this episode (source: upload, youtube or result-file), or that it is gone."""
    with db.conn() as c:
        c.execute("INSERT INTO uploads (episode, video_id, version, marker, package, card, job, source, status, at, "
                  "checked) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(episode, video_id) DO UPDATE SET "
                  "status = excluded.status, checked = excluded.checked, "
                  "version = COALESCE(uploads.version, excluded.version), "
                  "marker = COALESCE(uploads.marker, excluded.marker)",
                  (episode, video_id, version, marker(episode, version) if version else None, package, card, job,
                   source, status, db.now(), db.now()))


# ---- YouTube ----------------------------------------------------------------------------------------------------------
def _ask(what: str, fn):
    try:
        return fn()
    except Exception as e:  # noqa: BLE001 - any failure means: not known, so nothing goes up
        from .upload import error_text
        raise CheckFailed(f"Could not ask YouTube {what} ({error_text(e)}). Nothing was uploaded; try again.") from e


def present(yt, ids: list[str]) -> dict[str, str | None]:
    """uploadStatus of each of these videos that YouTube still has; a missing id is gone."""
    out: dict[str, str | None] = {}
    for i in range(0, len(ids), 50):
        res = yt.videos().list(part="status", id=",".join(ids[i:i + 50])).execute()
        for item in res.get("items") or []:
            out[item["id"]] = (item.get("status") or {}).get("uploadStatus")
    return out


def channel_uploads(yt, limit: int = SCAN) -> list[dict]:
    """The channel's newest uploads with snippet and status (the owner's uploads playlist also has private and
    scheduled videos)."""
    items = yt.channels().list(part="contentDetails", mine=True).execute().get("items") or []
    playlist = ((items[0].get("contentDetails") or {}).get("relatedPlaylists") or {}).get("uploads") if items else None
    if not playlist:
        return []
    ids: list[str] = []
    token = None
    while len(ids) < limit:
        kw = {"part": "contentDetails", "playlistId": playlist, "maxResults": min(50, limit - len(ids))}
        if token:
            kw["pageToken"] = token
        res = yt.playlistItems().list(**kw).execute()
        ids += [v for v in ((it.get("contentDetails") or {}).get("videoId") for it in res.get("items") or []) if v]
        token = res.get("nextPageToken")
        if not token:
            break
    videos: list[dict] = []
    for i in range(0, len(ids), 50):
        videos += yt.videos().list(part="snippet,status", id=",".join(ids[i:i + 50])).execute().get("items") or []
    return videos


def existing(yt, episode: str, version: str, title: str | None, new_video: bool = False) -> dict | None:
    """This episode's video that YouTube has already, or None. Raises CheckFailed when YouTube cannot be asked.

    Returns {"video_id", "why", "source", and from the channel list "at", "privacy", "publish_at"}. With new_video (the
    person at the terminal wants a second video of the episode) only the same video file counts."""
    known = recorded(episode)
    if known:
        there = _ask("whether the recorded video is still there", lambda: present(yt, [k["video_id"] for k in known]))
        for k in known:
            if k["video_id"] not in there or there[k["video_id"]] in GONE:
                remember(episode, k["video_id"], k.get("source") or "result-file", status="gone")
                continue
            if new_video and k.get("version") != version:
                continue
            return {"video_id": k["video_id"], "source": k.get("source"), "at": k.get("at"), "card": k.get("card"),
                    "why": f"Crewcut recorded this upload ({k.get('source')}, {k.get('at')})"}
    videos = _ask("for the channel's newest uploads", lambda: channel_uploads(yt))
    mine, key = marker(episode, version), episode_key(episode)
    for v in videos:
        sn, st = v.get("snippet") or {}, v.get("status") or {}
        if st.get("uploadStatus") in GONE:
            continue
        tags = markers(sn.get("tags"))
        if mine in tags:
            why, same = "it carries this episode's marker tag for this exact video file", True
        elif not new_video and any(MARKER.match(t).group(1) == key for t in tags):
            why, same = "it carries this episode's marker tag (another version of the video file)", False
        elif not new_video and not tags and title and sn.get("title") == title:
            why, same = "it has exactly this title (a video from before the marker tag)", None
        else:
            continue
        remember(episode, v["id"], "youtube", version=version if same else None)
        return {"video_id": v["id"], "source": "youtube", "why": why, "at": sn.get("publishedAt"),
                "privacy": st.get("privacyStatus"), "publish_at": st.get("publishAt")}
    return None
