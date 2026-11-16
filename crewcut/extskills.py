"""Skills from other projects, always the newest version: downloaded at start, never copied into this repository.

The first one is Humanizer (https://github.com/blader/humanizer, MIT): the Writer runs it over every script draft so
the text reads like the user, not like a model. Same policy as the engine (`engines/versions.py`): at every start and
once a day while nothing runs, Crewcut asks GitHub for the newest release, downloads it next to the current one,
checks that it is a skill (a `SKILL.md` with a name), and only then switches the link `<prefix>/skills/<name>/current`.
Offline, the current version stays. A skill can be held on a tag with `channel = "v4.0.0"` in `[[skills.external]]`.

Claude Code loads it as a plugin (`--plugin-dir`, the repository is a Claude Code plugin); Codex gets the skill text in
its prompt, the way Codex takes the crew member's identity.
"""

from __future__ import annotations

import io
import json
import os
import re
import shutil
import tarfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from . import config

DEFAULT = [{"name": "humanizer", "repo": "blader/humanizer", "channel": "latest", "license": "MIT",
            "steps": ["script", "title", "upload"]}]
UA = {"User-Agent": "crewcut-skill-updater", "Accept": "application/vnd.github+json"}


def prefix() -> Path:
    return Path(os.environ.get("CREWCUT_ENGINE_PREFIX", "/opt/engine")) / "skills"


def configured() -> list[dict]:
    items = config.get("crewcut", "skills.external", None)
    if not items:
        return [dict(x) for x in DEFAULT]
    return [dict(x) for x in items if isinstance(x, dict) and x.get("name") and x.get("repo")]


def spec(name: str) -> dict | None:
    return next((s for s in configured() if s["name"] == name), None)


def _get(url: str, timeout: int = 20) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 (fixed https hosts)
        return r.read()


def latest_tag(repo: str, channel: str = "latest", fetch=_get) -> str | None:
    """The tag to use: a fixed tag as given, else the newest release, else the newest tag. None when offline."""
    if channel and channel != "latest":
        return channel
    try:
        return json.loads(fetch(f"https://api.github.com/repos/{repo}/releases/latest"))["tag_name"]
    except (urllib.error.URLError, OSError, ValueError, KeyError):
        pass
    try:
        tags = json.loads(fetch(f"https://api.github.com/repos/{repo}/tags?per_page=1"))
        return tags[0]["name"] if tags else None
    except (urllib.error.URLError, OSError, ValueError, KeyError, IndexError):
        return None


def _safe_extract(data: bytes, dest: Path) -> None:
    """Extract a GitHub tarball without its top folder; refuse links and paths that leave `dest`."""
    dest.mkdir(parents=True, exist_ok=True)
    root = dest.resolve()
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
        for m in tf.getmembers():
            parts = Path(m.name).parts[1:]
            if not parts:
                continue
            if m.issym() or m.islnk() or m.isdev():
                continue
            target = (dest / Path(*parts)).resolve()
            if root not in target.parents and target != root:
                raise ValueError(f"unsafe path in archive: {m.name}")
            if m.isdir():
                target.mkdir(parents=True, exist_ok=True)
            elif m.isfile():
                target.parent.mkdir(parents=True, exist_ok=True)
                f = tf.extractfile(m)
                if f is not None:
                    target.write_bytes(f.read())


def skill_name(folder: Path) -> str | None:
    """The `name:` in the front matter of SKILL.md, or None when the folder is not a skill."""
    try:
        text = (folder / "SKILL.md").read_text(encoding="utf-8")
    except OSError:
        return None
    m = re.match(r"^---\s*\n(.*?)\n---", text, re.S)
    if not m:
        return None
    n = re.search(r"(?m)^name:\s*['\"]?([\w.-]+)", m.group(1))
    return n.group(1) if n else None


def current(name: str) -> dict | None:
    link = prefix() / name / "current"
    if not link.exists():
        return None
    path = link.resolve()
    meta = {}
    try:
        meta = json.loads((path / ".crewcut.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    return {"name": name, "path": str(path), "version": meta.get("tag") or path.name, "repo": meta.get("repo"),
            "license": meta.get("license"), "skill": skill_name(path)}


def install(name: str, repo: str, tag: str, fetch=_get, license_: str | None = None) -> Path:
    dest = prefix() / name / "versions" / tag
    if (dest / "SKILL.md").is_file() and skill_name(dest):
        return dest
    tmp = dest.with_name(dest.name + ".part")
    shutil.rmtree(tmp, ignore_errors=True)
    _safe_extract(fetch(f"https://codeload.github.com/{repo}/tar.gz/refs/tags/{tag}", 60), tmp)
    if not skill_name(tmp):
        shutil.rmtree(tmp, ignore_errors=True)
        raise ValueError(f"{repo} {tag} has no SKILL.md with a name")
    (tmp / ".crewcut.json").write_text(json.dumps({"repo": repo, "tag": tag, "license": license_,
                                                   "installed": time.time()}) + "\n", encoding="utf-8")
    shutil.rmtree(dest, ignore_errors=True)
    tmp.rename(dest)
    return dest


def switch(name: str, tag: str) -> None:
    base = prefix() / name
    link = base / "current"
    tmp = base / "current.new"
    if tmp.is_symlink() or tmp.exists():
        tmp.unlink()
    tmp.symlink_to(Path("versions") / tag)
    os.replace(tmp, link)


def update(name: str | None = None, fetch=_get) -> list[dict]:
    """Bring each external skill (or one) to its newest version. Never removes the current one."""
    out = []
    for s in configured():
        if name and s["name"] != name:
            continue
        cur = current(s["name"])
        res = {"name": s["name"], "current": cur["version"] if cur else None, "changed": False, "notes": []}
        tag = latest_tag(s["repo"], str(s.get("channel") or "latest"), fetch)
        if not tag:
            res["notes"].append("GitHub did not answer (offline?): keeping " + (res["current"] or "nothing"))
        elif cur and tag == cur["version"]:
            res["notes"].append("already on the newest version")
        else:
            try:
                install(s["name"], s["repo"], tag, fetch, s.get("license"))
                switch(s["name"], tag)
                res.update(current=tag, changed=True)
            except (urllib.error.URLError, OSError, ValueError, tarfile.TarError) as e:
                res["notes"].append(f"{tag} could not be installed ({type(e).__name__}): keeping "
                                    + (res["current"] or "nothing"))
        _stamp(s["name"])
        out.append(res)
    return out


def _stamp(name: str) -> None:
    p = prefix() / name / "checked_at"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(str(time.time()), encoding="utf-8")


def due(name: str, every_s: int) -> bool:
    try:
        return time.time() - float((prefix() / name / "checked_at").read_text()) > every_s
    except (OSError, ValueError):
        return True


def plugin_dirs() -> list[str]:
    """Folders Claude Code loads with --plugin-dir: every installed external skill that is a Claude Code plugin."""
    dirs = []
    for s in configured():
        cur = current(s["name"])
        if cur and (Path(cur["path"]) / ".claude-plugin" / "plugin.json").is_file():
            dirs.append(cur["path"])
    return dirs


def for_step(step: str | None) -> list[dict]:
    """The installed external skills that belong to a step (Humanizer: script, title, upload)."""
    found = []
    for s in configured():
        if step and step in (s.get("steps") or []):
            cur = current(s["name"])
            if cur:
                found.append({**cur, "steps": s.get("steps")})
    return found


def skill_text(name: str) -> str:
    cur = current(name)
    if not cur:
        return ""
    try:
        return (Path(cur["path"]) / "SKILL.md").read_text(encoding="utf-8")
    except OSError:
        return ""


def humanizer_enabled() -> bool:
    return bool(config.get("crewcut", "humanizer.enabled", True))


__all__ = ["configured", "current", "update", "plugin_dirs", "for_step", "skill_text", "latest_tag", "install",
           "switch", "due", "humanizer_enabled"]
