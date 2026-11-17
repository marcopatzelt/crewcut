"""Motion references: reels and videos to learn timing and look from (motion plan 3.8).

``studio/brand/references/motion/index.json`` holds one entry per reference: the link or the local file, who added
it (the user, through the Showrunner, or the Scout), what to learn from it, timing notes and tags. Clips stay on this
computer: they are never rendered into an output and never go to a rented machine. The Scout adds at most
``SCOUT_PER_EPISODE`` per episode, each with a reason; what the user sends is always filed.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from .. import paths

SCOUT_PER_EPISODE = 3
BY = ("user", "scout")
LINK = re.compile(r"https?://[^\s<>\"']+")
MEDIA = (".mp4", ".mov", ".webm", ".mkv", ".gif", ".png", ".jpg", ".jpeg", ".webp")


def folder(write: bool = False) -> Path:
    if write:
        from .. import approvals
        d = approvals.ensure_user_pack() / "references" / "motion"
        d.mkdir(parents=True, exist_ok=True)
        return d
    return paths.brand_dir() / "references" / "motion"


def read() -> list[dict]:
    p = folder() / "index.json"
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    items = data.get("references") if isinstance(data, dict) else None
    return [x for x in items or [] if isinstance(x, dict)]


def _write(items: list[dict]) -> Path:
    p = folder(write=True) / "index.json"
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"schema": 1, "references": items}, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8")
    tmp.replace(p)
    return p


def ids() -> set[str]:
    return {x.get("id") for x in read() if x.get("id")}


def _next_id(items: list[dict]) -> str:
    n = max([int(m.group(1)) for x in items if (m := re.fullmatch(r"ref-(\d+)", str(x.get("id") or "")))], default=0)
    return f"ref-{n + 1:03d}"


def default_download(url: str, dest: Path) -> Path | None:
    """Fetch a clip with yt-dlp when it is installed (else keep only the link). The file stays in ``dest``."""
    exe = shutil.which("yt-dlp")
    if not exe:
        return None
    dest.mkdir(parents=True, exist_ok=True)
    before = set(dest.iterdir())
    try:
        subprocess.run([exe, "--no-playlist", "--max-filesize", "300M", "-f", "mp4/best", "-o",
                        str(dest / "%(id)s.%(ext)s"), "--", url], capture_output=True, timeout=600, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    new = sorted(set(dest.iterdir()) - before, key=lambda p: p.stat().st_mtime)
    return new[-1] if new else None


def add(source: str, reason: str, by: str = "user", episode: str | None = None, tags: list[str] | None = None,
        timing: str = "", download: Callable[[str, Path], Path | None] | None = default_download) -> dict:
    """File one reference: a link (fetched by ``download`` when possible) or a local file (copied into the pack).
    Returns the entry. Refuses an empty reason, a duplicate link, and a fourth Scout reference in one episode."""
    reason = " ".join(str(reason or "").split())
    if not reason:
        raise ValueError("a reference needs a reason: what to learn from it")
    if by not in BY:
        raise ValueError(f"--by must be {' or '.join(BY)}")
    items = read()
    if by == "scout":
        if not episode:
            raise ValueError("the Scout files references for an episode (--episode)")
        n = sum(1 for x in items if x.get("by") == "scout" and x.get("episode") == episode)
        if n >= SCOUT_PER_EPISODE:
            raise ValueError(f"the Scout already added {n} references for {episode} (at most {SCOUT_PER_EPISODE})")
    rid = _next_id(items)
    d = folder(write=True)
    entry: dict = {"id": rid, "link": None, "file": None, "by": by, "reason": reason, "episode": episode,
                   "tags": list(tags or []), "timing": timing, "added": datetime.now(UTC).strftime("%Y-%m-%d"),
                   "local_only": True}
    if LINK.fullmatch(source.strip()):
        url = source.strip()
        dup = next((x for x in items if x.get("link") == url), None)
        if dup:
            raise ValueError(f"this link is filed already as {dup['id']}")
        entry["link"] = url
        if download:
            got = download(url, d / "files" / rid)
            if got and Path(got).is_file():
                entry["file"] = Path(got).resolve().relative_to(d.resolve()).as_posix()
    else:
        src = Path(source).expanduser()
        if not src.is_absolute() and not src.is_file():
            src = paths.studio_root() / source
        if not src.is_file():
            raise ValueError(f"no such file: {source}")
        if src.suffix.lower() not in MEDIA:
            raise ValueError(f"{src.name}: a reference is a clip or a still ({', '.join(MEDIA)})")
        target = d / "files" / f"{rid}{src.suffix.lower()}"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)
        entry["file"] = target.relative_to(d).as_posix()
        entry["source_name"] = src.name
    items.append(entry)
    _write(items)
    return entry


def from_message(episode: str | None, text: str, download: Callable[[str, Path], Path | None] | None = default_download
                 ) -> list[dict]:
    """The Showrunner's helper: the user dropped one or more links in the chat ("look at this reel"). Each becomes a
    reference by the user, with the user's own sentence (the message without the links) as the reason."""
    links = LINK.findall(text or "")
    if not links:
        return []
    sentence = " ".join(LINK.sub(" ", text).split()).strip(" :-") or "sent by the user in the chat without words"
    out = []
    for url in dict.fromkeys(links):
        try:
            out.append(add(url, sentence, by="user", episode=episode, download=download))
        except ValueError as e:
            if "filed already" not in str(e):
                raise
    return out


def since(date: str | None) -> list[dict]:
    """References added on or after ``date`` (all when None): what is new for the next motion pass."""
    return [x for x in read() if not date or str(x.get("added") or "") >= date]
