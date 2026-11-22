"""Recordings that land in studio/inbox/<episode>/ start the Editor by themselves.

Copying an SD card takes minutes, so a file counts only when its size has not changed for two checks in a row. Each file
is announced once. While the record step waits or works, the files start the Editor's ingest and edit. After it, until
the video is published, a new file is announced to the Editor as an additional recording (a second camera copied a
minute later). Episodes whose record step has not come yet keep their files for later.
"""

from __future__ import annotations

import json
import threading
import time
import traceback

from .. import db, episodes, paths

MEDIA = {".mp4", ".mov", ".mxf", ".mts", ".m2ts", ".mkv", ".wav", ".mp3", ".m4a", ".aac", ".flac", ".avi"}
EVERY_S = 20


def _seen(eid: str) -> set[str]:
    try:
        return set(json.loads(db.kv_get(f"inbox_seen:{eid}") or "[]"))
    except ValueError:
        return set()


def _mode(project: dict) -> str | None:
    """'record' while recording is the step, 'more' after it until the video is out, else None (not watched)."""
    steps = project.get("steps", {})
    record = steps.get("record", {}).get("status")
    if record in ("waiting", "working"):
        return "record"
    if record not in ("done", "skipped"):
        return None
    upload = steps.get("upload", {}).get("status")
    if upload == "done":
        return None
    if upload in (None, "skipped") and steps.get("edit", {}).get("status") == "done":
        return None   # no upload step in this episode: the finished edit is the end
    return "more"


def _editor_busy(eid: str) -> bool:
    with db.conn() as c:
        return c.execute("SELECT 1 FROM jobs WHERE episode = ? AND identity = 'editor' AND status IN ('queued', "
                         "'running') LIMIT 1", (eid,)).fetchone() is not None


def scan(sizes: dict[str, int]) -> list[tuple[str, list[str]]]:
    """One pass. `sizes` keeps the sizes of the last pass. Returns [(episode, new stable files)] and announces them."""
    from . import flow
    out = []
    root = paths.studio_root() / "inbox"
    if not root.is_dir():
        return out
    for d in sorted(p for p in root.iterdir() if p.is_dir()):
        eid = d.name
        try:
            p = episodes.read(eid)
        except (FileNotFoundError, ValueError):
            continue
        mode = _mode(p)
        if mode is None:
            continue
        seen = _seen(eid)
        ready = []
        for f in sorted(d.iterdir()):
            if not f.is_file() or f.name.startswith(".") or f.suffix.lower() not in MEDIA:
                continue
            rel = str(f.relative_to(paths.studio_root()))
            if rel in seen:
                continue
            size = f.stat().st_size
            if sizes.get(rel) == size and size > 0:
                ready.append(rel)
            sizes[rel] = size
        if ready:
            db.kv_set(f"inbox_seen:{eid}", json.dumps(sorted(seen | set(ready))))
            if mode == "record" and not _editor_busy(eid):
                flow.on_upload(eid, ready)
            else:   # after the record step, or while an Editor already works on this episode's files
                flow.on_more_media(eid, ready)
            out.append((eid, ready))
    return out


def start_background() -> threading.Thread:
    def loop() -> None:
        sizes: dict[str, int] = {}
        while True:
            try:
                scan(sizes)
            except Exception:  # noqa: BLE001 - the watcher must keep running
                traceback.print_exc()
            time.sleep(EVERY_S)

    t = threading.Thread(target=loop, daemon=True, name="crewcut-inbox")
    t.start()
    return t
