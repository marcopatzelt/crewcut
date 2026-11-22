"""Intermediate renders do not fill the disk.

Every speaker cut writes work/speaker-vNNN.mov (several GB), its clip folder work/cut-vNNN/, and the grade writes
work/speaker-graded-vNNN.mov; a Short writes work/short-vNNN/. Ten rounds of an episode kept them all. Of each series
only the newest `cut.keep_versions` versions stay (default 2). A file that the current cut plan
(edit/cut-plan-vNNN.json) or the current edit plan (edit/plan-vNNN.json) names is never deleted, whatever its version.
Only real files and folders directly in work/ are touched, never a link and nothing outside the episode.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

SERIES = (re.compile(r"^speaker-v(\d+)\.mov$"), re.compile(r"^speaker-graded-v(\d+)\.mov$"),
          re.compile(r"^cut-v(\d+)$"), re.compile(r"^short-v(\d+)$"))
KEEP = 2


def keep_versions() -> int:
    from .. import config
    try:
        return max(1, int(config.get("crewcut", "cut.keep_versions", KEEP)))
    except (TypeError, ValueError, OSError):
        return KEEP


def _newest(folder: Path, prefix: str) -> Path | None:
    found = [(int(m.group(1)), p) for p in folder.glob(f"{prefix}-v*.json")
             if (m := re.match(rf"^{re.escape(prefix)}-v(\d+)\.json$", p.name))]
    return max(found)[1] if found else None


def _strings(value) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in _strings(v)]
    if isinstance(value, list):
        return [s for v in value for s in _strings(v)]
    return []


def protected(ep_dir: Path) -> set[Path]:
    """Every path the current cut plan and the current edit plan name, resolved inside the episode."""
    out: set[Path] = set()
    root = ep_dir.resolve()
    for prefix in ("cut-plan", "plan"):
        plan = _newest(ep_dir / "edit", prefix)
        if plan is None:
            continue
        try:
            data = json.loads(plan.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise OSError(f"{plan} is unreadable: nothing is deleted") from None
        for s in _strings(data):
            if "/" not in s or len(s) > 1024:
                continue
            p = Path(s)
            p = (p if p.is_absolute() else ep_dir / p).resolve()
            if p == root or root in p.parents:
                out.add(p)
    return out


def candidates(ep_dir: Path, keep: int | None = None) -> list[Path]:
    """What `work` would delete: per series all but the newest `keep` versions, minus every protected path."""
    keep = keep_versions() if keep is None else keep
    work = ep_dir / "work"
    if not work.is_dir() or work.is_symlink():
        return []
    guard = protected(ep_dir)
    series: dict[int, list[tuple[int, Path]]] = {}
    for p in work.iterdir():
        if p.is_symlink():
            continue
        for i, rx in enumerate(SERIES):
            m = rx.match(p.name)
            if m and (p.is_dir() if p.suffix != ".mov" else p.is_file()):
                series.setdefault(i, []).append((int(m.group(1)), p))
                break
    out = []
    for items in series.values():
        for _, p in sorted(items, reverse=True)[keep:]:
            r = p.resolve()
            if r in guard or any(r in g.parents for g in guard):
                continue
            out.append(p)
    return sorted(out)


def work(ep_dir: Path, keep: int | None = None, log=None) -> list[str]:
    """Delete the older intermediate renders of one episode. Returns the deleted names (relative to the episode)."""
    gone = []
    for p in candidates(ep_dir, keep):
        if p.is_dir():
            shutil.rmtree(p)
        else:
            p.unlink()
        gone.append(str(p.relative_to(ep_dir)))
        if log:
            log(f"removed older intermediate: {gone[-1]}")
    return gone


def after_write(ep_dir: Path, log=None) -> list[str]:
    """Called right after a new version of a series is written. A failure here never fails the render."""
    try:
        return work(ep_dir, log=log)
    except OSError as e:
        if log:
            log(f"older intermediates kept: {e}")
        return []
