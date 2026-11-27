"""Idea cards: topics from outside the app (the scout's ranking, saved links) waiting for "Start episode" or "Dismiss".

The container sees only the studio, so a host-side exporter (`host/ideas-export.py`, docs/formats.md) writes one JSON
file per idea into `<studio>/inbox/ideas/<id>.json`:

    {"id", "source": "scout"|"braindump"|…, "url", "title", "summary", "signals": {…}, "topic_type"?,
     "suggested_format"?, "reason"?, "created", "status"?}

`load()` (also every minute in the background) imports new files into the `ideas` table. An open idea takes changes
from its file; a started or dismissed idea is never changed again. Without a suggestion from the file the loader
makes a deterministic first guess from the format library (`showformats.suggest`, keyword rules, no model), marked
`suggestion: "rule"`. "Start episode" creates the episode the same way as New Episode (flow.new_episode). Loading
never starts a job.
"""

from __future__ import annotations

import json
import re
import threading
import time
import traceback
from pathlib import Path

from . import db, paths

STATUSES = ("open", "started", "dismissed")
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,120}$")
EVERY_S = 60
FIELDS = ("source", "url", "title", "summary", "signals", "topic_type", "suggested_format", "reason", "suggestion",
          "length", "created", "file")


def folder() -> Path:
    return paths.studio_root() / "inbox" / "ideas"


def _row(r) -> dict:
    d = dict(r)
    try:
        d["signals"] = json.loads(d["signals"]) if d.get("signals") else {}
    except ValueError:
        d["signals"] = {}
    return d


def _read(p: Path) -> dict | None:
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(d, dict):
        return None
    iid = str(d.get("id") or p.stem)
    if not SAFE_ID.match(iid) or iid != p.stem or not str(d.get("title") or "").strip():
        return None
    d["id"] = iid
    return d


def _fields(d: dict, p: Path) -> dict:
    from . import showformats
    lib = showformats.load()
    out = {"source": str(d.get("source") or "other")[:40], "url": d.get("url") or None,
           "title": " ".join(str(d["title"]).split())[:200], "summary": str(d.get("summary") or "")[:4000] or None,
           "signals": json.dumps(d.get("signals") or {}, ensure_ascii=False)[:8000],
           "topic_type": d.get("topic_type") if d.get("topic_type") in showformats.TOPIC_TYPES else None,
           "created": str(d.get("created") or "") or None, "file": str(p.relative_to(paths.studio_root())),
           "length": d.get("length") if d.get("length") in showformats.CHOICES else None}
    if d.get("suggested_format") in lib:
        out.update(suggested_format=d["suggested_format"], reason=d.get("reason") or None, suggestion="exporter")
    else:
        g = showformats.suggest(f"{out['title']}\n{out['summary'] or ''}", source=out["source"], lib=lib)
        out.update(suggested_format=(g or {}).get("format"), reason=(g or {}).get("reason"),
                   suggestion="rule" if g else None)
        out["topic_type"] = out["topic_type"] or (g or {}).get("topic_type")
    return out


def load() -> dict:
    """One pass over inbox/ideas/. Returns {"new", "updated", "skipped"}."""
    counts = {"new": 0, "updated": 0, "skipped": 0}
    d = folder()
    if not d.is_dir():
        return counts
    with db.conn() as c:
        known = {r["id"]: dict(r) for r in c.execute("SELECT id, status, title, summary, url, signals, created, "
                                                     "topic_type, length FROM ideas")}
    for p in sorted(d.glob("*.json")):
        data = _read(p)
        if data is None:
            counts["skipped"] += 1
            continue
        iid = data["id"]
        cur = known.get(iid)
        file_status = data.get("status") if data.get("status") in STATUSES else "open"
        if cur is None:
            f = _fields(data, p)
            db.insert("ideas", id=iid, status=file_status, imported=db.now(),
                      decided_at=db.now() if file_status != "open" else None, **f)
            counts["new"] += 1
            continue
        if cur["status"] != "open":
            continue   # decided ideas never change
        if file_status != "open":
            with db.conn() as c:
                c.execute("UPDATE ideas SET status = ?, decided_at = ? WHERE id = ? AND status = 'open'",
                          (file_status, db.now(), iid))
            counts["updated"] += 1
            continue
        f = _fields(data, p)
        if any((cur.get(k) or None) != (f.get(k) or None) for k in ("title", "summary", "url", "signals", "created")):
            sets = ", ".join(f"{k} = ?" for k in f)
            with db.conn() as c:
                c.execute(f"UPDATE ideas SET {sets} WHERE id = ? AND status = 'open'", (*f.values(), iid))
            counts["updated"] += 1
    return counts


def list_ideas(status: str | None = None, limit: int = 200) -> list[dict]:
    q, args = "SELECT * FROM ideas", []
    if status:
        if status not in STATUSES:
            raise ValueError(f"status must be one of {', '.join(STATUSES)}")
        q += " WHERE status = ?"
        args.append(status)
    q += " ORDER BY (status = 'open') DESC, COALESCE(created, imported) DESC, id LIMIT ?"
    args.append(limit)
    with db.conn() as c:
        return [_row(r) for r in c.execute(q, args)]


def get(iid: str) -> dict:
    with db.conn() as c:
        r = c.execute("SELECT * FROM ideas WHERE id = ?", (iid,)).fetchone()
    if r is None:
        raise KeyError(iid)
    return _row(r)


def _mark_file(idea: dict, status: str, episode: str | None = None) -> None:
    """Write the decision into the idea's file too, so the exporter never brings it back. Best effort."""
    if not idea.get("file"):
        return
    try:
        p = paths.inside(paths.studio_root(), idea["file"])
        d = json.loads(p.read_text(encoding="utf-8"))
        d.update(status=status, **({"episode": episode} if episode else {}))
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        tmp.replace(p)
    except (OSError, ValueError):
        pass


def _claim(iid: str, to: str) -> dict:
    idea = get(iid)
    with db.conn() as c:
        n = c.execute("UPDATE ideas SET status = ?, decided_at = ? WHERE id = ? AND status = 'open'",
                      (to, db.now(), iid)).rowcount
    if n != 1:
        raise ValueError(f"this idea is {idea['status']} already")
    return idea


def episode_text(idea: dict) -> str:
    parts = [idea["title"]]
    if idea.get("url"):
        parts.append(idea["url"])
    if idea.get("summary"):
        parts.append(idea["summary"])
    return "\n\n".join(parts)


def start(iid: str, length: str | None = None, show_format: str | None = None) -> dict:
    """"Start episode": the same path as New Episode, with the idea's text, its suggested format and length."""
    from . import showformats
    from .conductor import flow
    idea = _claim(iid, "started")
    try:
        fmt = show_format or (idea.get("suggested_format") if showformats.get(idea.get("suggested_format")) else None)
        ln = length or (showformats.get(fmt) or {}).get("length") or idea.get("length") or "auto"
        if fmt and ln != "auto" and (showformats.get(fmt) or {}).get("length") != ln:
            fmt = None   # the user asked for the other length: the Scout picks among those formats
        project = flow.new_episode(episode_text(idea), length=ln, show_format=fmt, topic_type=idea.get("topic_type"),
                                   source=idea.get("url"), title=idea["title"])
    except Exception:
        with db.conn() as c:
            c.execute("UPDATE ideas SET status = 'open', decided_at = NULL WHERE id = ?", (iid,))
        raise
    with db.conn() as c:
        c.execute("UPDATE ideas SET episode = ? WHERE id = ?", (project["id"], iid))
    _mark_file(idea, "started", project["id"])
    return {"idea": get(iid), "episode": project["id"]}


def dismiss(iid: str) -> dict:
    idea = _claim(iid, "dismissed")
    _mark_file(idea, "dismissed")
    return get(iid)


def start_background() -> threading.Thread:
    def loop() -> None:
        while True:
            try:
                load()
            except Exception:  # noqa: BLE001 - the loader must keep running
                traceback.print_exc()
            time.sleep(EVERY_S)

    t = threading.Thread(target=loop, daemon=True, name="crewcut-ideas")
    t.start()
    return t


def _parser():
    import argparse
    p = argparse.ArgumentParser(prog="crewcut ideas", description="Idea cards from inbox/ideas/ (docs/formats.md).")
    p.add_argument("cmd", nargs="?", default="list", choices=["list", "load"])
    p.add_argument("--status", choices=STATUSES)
    p.add_argument("--json", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    a = _parser().parse_args(argv)
    counts = load()
    if a.cmd == "load":
        print(f"{counts['new']} new, {counts['updated']} updated, {counts['skipped']} unreadable files.")
        return 0
    rows = list_ideas(status=a.status)
    if a.json:
        print(json.dumps(rows, ensure_ascii=False, indent=1))
        return 0
    if not rows:
        print(f"No ideas. The exporter writes them into {folder()}.")
        return 0
    for r in rows:
        sug = f" -> {r['suggested_format']} ({r['suggestion']})" if r.get("suggested_format") else ""
        print(f"{r['status']:<9} {r['source']:<9} {r['id'][:40]:<40} {r['title'][:60]}{sug}")
    return 0


__all__ = ["dismiss", "episode_text", "folder", "get", "list_ideas", "load", "main", "start", "start_background"]
