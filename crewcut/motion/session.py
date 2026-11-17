"""Session state between one-shot commands, and undo/redo by project snapshots.

EffectCraft's own undo lives inside one process. A CLI call is one process, so the harness keeps undo itself:
before every mutation it copies the ``.ecproj`` into ``<project dir>/.ecproj-history/<name>/NNNN.ecproj``;
``undo`` restores the previous copy, ``redo`` steps forward again. The session JSON (default
``<project>.cli-session.json``) holds the project path, the active comp, the history and the snapshot pointer.
Saves use an exclusive file lock, so two commands never write the session at the same time.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from typing import Any

MAX_HISTORY = 300
MAX_SNAPSHOTS = 60


def _locked_save_json(path: str, data: Any) -> None:
    """Write JSON under an exclusive lock; truncate only inside the lock."""
    try:
        f = open(path, "r+", encoding="utf-8")
    except FileNotFoundError:
        os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
        f = open(path, "w", encoding="utf-8")
    with f:
        locked = False
        try:
            import fcntl
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            locked = True
        except (ImportError, OSError):
            pass
        try:
            f.seek(0)
            f.truncate()
            json.dump(data, f, indent=1)
            f.flush()
        finally:
            if locked:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def session_path_for(project: str) -> str:
    return os.path.abspath(project) + ".cli-session.json"


class Session:
    """What persists between commands: project, active comp, history, snapshots for undo/redo."""

    def __init__(self, path: str | None = None, data: dict | None = None):
        self.path = path
        self.data = data or {"version": 1, "project": None, "comp": None, "history": [], "snapshots": [], "pos": -1}
        self._modified = False

    # ── load/save ────────────────────────────────────────────────────────
    @classmethod
    def load(cls, path: str | None = None, project: str | None = None) -> Session:
        if path is None and project:
            path = session_path_for(project)
        if path and os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                s = cls(path, json.load(f))
        else:
            s = cls(path)
        if project:
            s.set_project(project)
        return s

    def save(self) -> None:
        if not self.path:
            return
        _locked_save_json(self.path, self.data)
        self._modified = False

    # ── context ──────────────────────────────────────────────────────────
    @property
    def project(self) -> str | None:
        return self.data.get("project")

    def set_project(self, project: str) -> None:
        project = os.path.abspath(project)
        if self.data.get("project") != project:
            self.data.update(project=project, snapshots=[], pos=-1)
            if not self.path:
                self.path = session_path_for(project)
            self._modified = True

    def has_project(self) -> bool:
        return bool(self.project)

    @property
    def comp(self) -> str | None:
        return self.data.get("comp")

    def use_comp(self, name: str) -> None:
        self.data["comp"] = name
        self._modified = True

    def require_project(self) -> str:
        if not self.project:
            raise RuntimeError("no project. Use --project P.ecproj or: project new -o P.ecproj")
        if not os.path.exists(self.project):
            raise RuntimeError(f"project file missing: {self.project}")
        return self.project

    def require_comp(self, given: str | None) -> str:
        c = given or self.comp
        if not c:
            raise RuntimeError("no composition. Pass --comp NAME or run: comp use NAME")
        return c

    # ── history and snapshots ────────────────────────────────────────────
    def record(self, command: str, result: Any = None) -> None:
        h = self.data.setdefault("history", [])
        h.append({"t": round(time.time(), 3), "command": command,
                  "result": result if isinstance(result, (str, int, float, bool, type(None))) else
                  (json.dumps(result)[:300] if result is not None else None)})
        del h[:-MAX_HISTORY]
        self._modified = True

    def _snap_dir(self) -> str:
        p = self.require_project()
        d = os.path.join(os.path.dirname(p), ".ecproj-history", os.path.basename(p))
        os.makedirs(d, exist_ok=True)
        return d

    def snapshot(self, label: str) -> str:
        """Copy the project before a mutation. Drops any redo branch after the current position."""
        p = self.require_project()
        snaps = self.data.setdefault("snapshots", [])
        pos = self.data.get("pos", len(snaps) - 1)
        for s in snaps[pos + 1:]:
            try:
                os.remove(s["file"])
            except OSError:
                pass
        del snaps[pos + 1:]
        f = os.path.join(self._snap_dir(), f"{int(time.time() * 1000)}-{len(snaps):04d}.ecproj")
        shutil.copy2(p, f)
        snaps.append({"file": f, "label": label, "t": round(time.time(), 3)})
        while len(snaps) > MAX_SNAPSHOTS:
            old = snaps.pop(0)
            try:
                os.remove(old["file"])
            except OSError:
                pass
        self.data["pos"] = len(snaps) - 1
        self._modified = True
        return f

    def undo(self) -> dict:
        """Restore the project as it was before the last mutation. The current state becomes redoable."""
        p = self.require_project()
        snaps = self.data.get("snapshots", [])
        pos = self.data.get("pos", len(snaps) - 1)
        if pos < 0 or not snaps:
            raise RuntimeError("nothing to undo")
        target = snaps[pos]
        redo_file = target["file"] + ".redo"
        shutil.copy2(p, redo_file)
        target["redo"] = redo_file
        shutil.copy2(target["file"], p)
        self.data["pos"] = pos - 1
        self._modified = True
        return {"undone": target["label"], "remaining": pos}

    def redo(self) -> dict:
        p = self.require_project()
        snaps = self.data.get("snapshots", [])
        pos = self.data.get("pos", len(snaps) - 1) + 1
        if pos >= len(snaps) or not snaps[pos].get("redo"):
            raise RuntimeError("nothing to redo")
        shutil.copy2(snaps[pos]["redo"], p)
        self.data["pos"] = pos
        self._modified = True
        return {"redone": snaps[pos]["label"]}

    def status(self) -> dict:
        snaps = self.data.get("snapshots", [])
        return {"project": self.project, "comp": self.comp, "session": self.path,
                "undo_steps": self.data.get("pos", -1) + 1, "redo_steps": sum(1 for s in snaps[self.data.get("pos", -1) + 1:] if s.get("redo")),
                "history": len(self.data.get("history", [])),
                "last": (self.data.get("history") or [{}])[-1].get("command")}
