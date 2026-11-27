"""Episodes: one folder each under studio/episodes/, with project.json and the ten steps."""

from __future__ import annotations

import json
import re
import secrets
import unicodedata
from pathlib import Path

from . import db, events, paths

STEPS = [
    {"id": "idea", "n": 1, "label": "Idea", "owner": "scout", "card": "topic"},
    {"id": "title", "n": 2, "label": "Title", "owner": "scout", "card": "title"},
    {"id": "proof", "n": 3, "label": "Proof", "owner": "scout", "card": "proof", "optional": True},
    {"id": "script", "n": 4, "label": "Script", "owner": "writer", "card": "script"},
    {"id": "record", "n": 5, "label": "Record", "owner": "editor", "card": None},
    {"id": "edit", "n": 6, "label": "Edit", "owner": "editor", "card": "preview"},
    {"id": "thumbnail", "n": 7, "label": "Thumbnail", "owner": "designer", "card": "thumbnail"},
    {"id": "blog", "n": 8, "label": "Blog", "owner": None, "card": None, "planned": True},
    {"id": "upload", "n": 9, "label": "Upload", "owner": "publisher", "card": "publish"},
    {"id": "results", "n": 10, "label": "Results", "owner": "publisher", "card": None, "planned": True},
]
STEP_IDS = [s["id"] for s in STEPS]
# Steps a studio can switch on or off in config/crewcut.toml [steps], with their default. Proof (a separate fact check
# with its own card) is off by default: the Writer gathers the facts, numbers, clips and scenes that serve the story
# while preparing the script, without a card or a report. The interview (on by default) is not a step of its own: it
# opens the script step (crewcut/interview.py), the Writer asks the user 5 to 8 questions before the first draft.
OPTIONAL_STEPS = {"proof": False, "interview": True}
SWITCHED_OFF = "switched off in this studio"
# A Short is its own small episode with fewer steps (docs/shorts.md): a clip comes from a finished episode, an original
# is recorded for itself. Steps that a mode does not have are not shown.
SHORT_STEPS = {
    "clip": ["idea", "title", "edit", "thumbnail", "upload", "results"],
    "original": ["idea", "title", "proof", "script", "record", "edit", "thumbnail", "upload", "results"],
}
KINDS = ("episode", "short")
STATUSES = ("open", "working", "waiting", "done", "skipped", "unknown")
LIFECYCLES = ("active", "planned", "parked", "archived")
FOLDERS = ("brief", "originals", "work", "audio", "broll", "graphics", "edit", "render", "review", "export")


def step_enabled(step: str) -> bool:
    """False for an optional step the studio has switched off; every other step is always on."""
    if step not in OPTIONAL_STEPS:
        return True
    from . import config
    return bool(config.get("crewcut", f"steps.{step}", OPTIONAL_STEPS[step]))


def skip_switched_off(steps: dict) -> list[str]:
    """Mark optional steps that are switched off and not started yet as skipped (also in older episodes). Returns them."""
    off = []
    for sid in OPTIONAL_STEPS:
        st = steps.get(sid)
        if st is not None and st.get("status") == "open" and not step_enabled(sid):
            steps[sid] = {"status": "skipped", "note": SWITCHED_OFF, "at": db.now()}
            off.append(sid)
    return off


def step_info(step: str) -> dict:
    for s in STEPS:
        if s["id"] == step:
            return s
    raise KeyError(f"unknown step {step}; steps: {', '.join(STEP_IDS)}")


def slug(text: str, max_len: int = 40) -> str:
    t = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    t = re.sub(r"[^a-zA-Z0-9]+", "-", t).strip("-").lower()
    t = t[:max_len].rstrip("-")
    return t or "episode"


def _next_number() -> int:
    n = 0
    for p in paths.episodes_dir().iterdir():
        m = re.match(r"^(\d{3})-", p.name)
        if p.is_dir() and m:
            n = max(n, int(m.group(1)))
    return n + 1


def project_path(episode: str) -> Path:
    return paths.episode_dir(episode) / "project.json"


def read(episode: str) -> dict:
    p = project_path(episode)
    if not p.is_file():
        raise FileNotFoundError(f"no episode {episode}")
    return json.loads(p.read_text(encoding="utf-8"))


def write(episode: str, project: dict) -> None:
    p = project_path(episode)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(project, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    tmp.replace(p)
    events.emit("episode", episode=episode, data=summary(episode, project))


def create(title: str, source: str | None = None, fmt: str | None = None, kind: str = "episode",
           mode: str | None = None, source_episode: str | None = None) -> dict:
    from . import brand
    pack = brand.load()
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {', '.join(KINDS)}")
    if kind == "short":
        if mode not in SHORT_STEPS:
            raise ValueError("a Short is a clip (from a finished episode) or an original: --mode clip|original")
        if mode == "clip":
            if not source_episode:
                raise ValueError("a clip names the episode it comes from: --from <episode>")
            read(source_episode)  # it must exist
        fmt = "portrait"
    fmt = fmt or pack.value("edit_style.format", "landscape")
    eid = f"{_next_number():03d}-{slug(title)}"
    d = paths.episode_dir(eid)
    d.mkdir(parents=True, exist_ok=False)
    for f in FOLDERS:
        (d / f).mkdir()
    steps = {s["id"]: {"status": "skipped" if s.get("planned") else "open"} for s in STEPS}
    step_ids = SHORT_STEPS[mode] if kind == "short" and mode else None
    if step_ids:
        for sid in STEP_IDS:
            if sid not in step_ids:
                steps[sid] = {"status": "skipped", "absent": True}
    skip_switched_off(steps)
    steps["idea"]["status"] = "working"
    project = {
        "id": eid, "title": title, "created": db.now(), "format": fmt, "fps": int(pack.value("edit_style.fps", 25)),
        "source": source, "step": "idea", "steps": steps, "next_action": "Scout looks for the idea and the data behind it.",
        "open_items": [], "prompter_token": secrets.token_urlsafe(12), "kind": kind,
    }
    if kind == "short":
        project.update(mode=mode, source_episode=source_episode, step_ids=step_ids)
        project["next_action"] = ("Scout picks the passages of the source episode." if mode == "clip" else
                                  "Scout proposes three ideas with a proof from the user's own work.")
    (d / "brief" / "BRIEF.md").write_text(f"# {title}\n\nSource: {source or 'the user, in one sentence'}\n",
                                          encoding="utf-8")
    write(eid, project)
    return project


def set_step(episode: str, step: str, status: str, next_action: str | None = None) -> dict:
    if status not in STATUSES:
        raise ValueError(f"status must be one of {', '.join(STATUSES)}")
    step_info(step)
    p = read(episode)
    p.setdefault("steps", {}).setdefault(step, {})["status"] = status
    p["steps"][step]["at"] = db.now()
    if status in ("working", "waiting"):
        p["step"] = step
    elif status in ("done", "skipped") and p.get("step") == step:
        nxt = next((s["id"] for s in STEPS if p["steps"].get(s["id"], {}).get("status") in ("open", "working", "waiting")),
                   None)
        p["step"] = nxt or step
    if next_action is not None:
        p["next_action"] = next_action
    write(episode, p)
    return p


def list_ids() -> list[str]:
    return sorted((p.name for p in paths.episodes_dir().iterdir() if (p / "project.json").is_file()), reverse=True)


def set_lifecycle(episode: str, lifecycle: str) -> dict:
    if lifecycle not in LIFECYCLES:
        raise ValueError(f"lifecycle must be one of {', '.join(LIFECYCLES)}")
    project = read(episode)
    with db.conn() as connection:
        busy = connection.execute("SELECT 1 FROM jobs WHERE episode = ? AND status IN ('queued','running','waiting')",
                                  (episode,)).fetchone()
    if busy:
        raise ValueError("Finish or cancel this episode's jobs before changing its lifecycle.")
    project["lifecycle"] = lifecycle
    project["lifecycle_at"] = db.now()
    write(episode, project)
    return project


def summary(episode: str, project: dict | None = None) -> dict:
    p = project or read(episode)
    with db.conn() as c:
        open_cards = c.execute("SELECT COUNT(*) AS n FROM cards WHERE episode = ? AND status = 'open'",
                               (episode,)).fetchone()["n"]
    st = p.get("steps", {})
    shown = [s for s in STEPS if not st.get(s["id"], {}).get("absent")]
    out = {
        "id": p["id"], "title": p.get("title", p["id"]), "step": p.get("step"), "format": p.get("format"),
        "kind": p.get("kind", "episode"),
        "steps": [{"id": s["id"], "n": i + 1, "label": s["label"], "status": st.get(s["id"], {}).get("status", "open")}
                  for i, s in enumerate(shown)],
        "updated": max([v.get("at") or "" for v in st.values()] +
                       [p.get("created") or "", p.get("imported_at") or ""]),
        "created": p.get("created"), "imported_at": p.get("imported_at"), "history": p.get("history"),
        "history_conflicts": p.get("history_conflicts", []), "production": p.get("production", {}),
        "open_cards": int(open_cards), "next_action": p.get("next_action"),
    }
    from . import interview
    if (iv := interview.summary(p)) is not None:
        out["interview"] = iv          # "Interview: waiting for your answers" on the card and in the episode view
    stage = p.get("legacy", {}).get("stage")
    history = p.get("history") or {}
    if history.get("distribution") in ("published", "scheduled", "uploaded"):
        out["historical_status"] = history["distribution"]
    elif not history and stage in ("published", "posted_by_polo"):
        out["historical_status"] = "published"
    elif stage in ("parked", "paused", "archived"):
        out["historical_status"] = stage
    if p.get("lifecycle") in LIFECYCLES:
        out["lifecycle"] = p["lifecycle"]
    if out["kind"] == "short":
        out.update(mode=p.get("mode"), source_episode=p.get("source_episode"))
    if p.get("show_format") or p.get("length"):
        from . import showformats  # the format system (docs/formats.md): the pick and its reason, once written
        out["length"] = p.get("length")
        choice = showformats.read_choice(p["id"]) if p.get("show_format") else None
        if p.get("show_format"):
            f = showformats.get(p["show_format"]) or {}
            out["show_format"] = {"id": p["show_format"], "name": f.get("name") or p["show_format"],
                                  "length": f.get("length"), "topic_type": p.get("topic_type"),
                                  "reason": (choice or {}).get("reason") or None,
                                  "runner_up": (choice or {}).get("runner_up") or None,
                                  "file": (choice or {}).get("file")}
    out["cover"] = cover(p["id"])
    from . import media  # late import: media reads episodes for the cut's style facts
    out["needs"] = media.needs(p["id"])        # the first open card with small pictures, for "Needs you"
    out["seconds"] = media.seconds(p["id"])    # length of the newest export or cut (ffprobe once per file version)
    return out


def cover(episode: str) -> str | None:
    """The newest thumbnail image of an episode, as the URL the UI shows on its card; None when there is none."""
    d = paths.episode_dir(episode) / "graphics" / "thumbnail"
    root = paths.episode_dir(episode).resolve()
    imgs = [f for f in d.rglob("*") if f.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")
            and f.is_file() and f.resolve().is_relative_to(root)] if d.is_dir() else []
    if not imgs:
        preview = paths.episode_dir(episode) / "work" / "cover-preview.jpg"
        return (f"/api/files/{episode}/work/cover-preview.jpg"
                if preview.is_file() and preview.resolve().is_relative_to(root) else None)
    newest = max(imgs, key=lambda f: f.stat().st_mtime)
    return f"/api/files/{episode}/{newest.relative_to(paths.episode_dir(episode)).as_posix()}"


def files(episode: str) -> list[dict]:
    d = paths.episode_dir(episode)
    out = []
    for sub in ("export", "graphics", "brief", "review"):
        base = d / sub
        if not base.is_dir():
            continue
        for f in sorted(base.rglob("*")):
            if f.is_file() and not f.name.startswith("."):
                kind = {".mp4": "video", ".mov": "video", ".png": "image", ".jpg": "image", ".jpeg": "image",
                        ".webp": "image", ".md": "text", ".json": "data", ".srt": "text"}.get(f.suffix.lower(), "file")
                out.append({"path": str(f.relative_to(d)), "size": f.stat().st_size, "kind": kind})
    return out


def imported_files(episode: str, folder: str = "", offset: int = 0, limit: int = 100) -> dict:
    from .studio_import import EXCLUDED, permitted
    root = paths.episode_dir(episode) / "legacy"
    if root.is_symlink():
        raise ValueError("Imported folders must not be links.")
    relative = Path(folder)
    if relative.is_absolute() or any(part.startswith(".") or part.lower() in EXCLUDED for part in relative.parts):
        raise ValueError("Only imported material can be listed.")
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("Imported folders must not be links.")
    if not current.is_dir():
        raise FileNotFoundError("Imported folder not found.")
    entries = []
    for item in current.iterdir():
        if item.is_symlink() or item.name.startswith(".") or item.name.lower() in EXCLUDED:
            continue
        if item.is_dir():
            entries.append({"path": item.relative_to(root).as_posix(), "name": item.name, "directory": True})
        elif item.is_file() and permitted(item.relative_to(root)):
            entries.append({"path": item.relative_to(root).as_posix(), "name": item.name,
                            "directory": False, "size": item.stat().st_size})
    entries.sort(key=lambda entry: (not entry["directory"], entry["name"].casefold()))
    return {"folder": folder, "total": len(entries), "entries": entries[offset:offset + limit]}


def by_prompter_token(token: str) -> str | None:
    for eid in list_ids():
        try:
            if secrets.compare_digest(read(eid).get("prompter_token", ""), token):
                return eid
        except (OSError, ValueError):
            continue
    return None
