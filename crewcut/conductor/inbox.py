"""Recordings that land in studio/inbox/<episode>/ start the Editor by themselves.

Copying an SD card takes minutes, so a file counts only when its size has not changed for two checks in a row. Each file
is announced once. Only episodes whose record step is waiting or working are watched.
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
        if p.get("steps", {}).get("record", {}).get("status") not in ("waiting", "working"):
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
            flow.on_upload(eid, ready)
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
