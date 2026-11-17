"""The motion shelf: the app's templates, the style pack's own templates and the episodes' custom pieces.

``crewcut motion library`` lists all three (motion plan 3.6). The director reads the shelf *after* it has decided what
each beat needs (3.1). A custom piece that passed its review and fits a second video is promoted into the pack:

    studio/brand/templates/motion/<name>.jsx            the template (pack copy wins over the app's, like 2D)
    studio/brand/templates/motion/<name>.v<N>.jsx       older versions, kept so a pinned plan ("name@N") still renders
    studio/brand/templates/motion/plates/<name>_*.py    Blender plate generators of the piece
    studio/brand/templates/motion/assets/<name>/        images the piece uses
    studio/brand/templates/motion/samples/<name>-v<N>-<format>.mp4 (+ a poster image)
    studio/brand/templates/motion/library.json          one entry per name (see ``promote``), keyed by name

The app's ``templates/motion/`` is never edited for one user. Nothing here renders: the samples come from a
``render_sample`` function the caller passes (the render path owns the engine).
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path

from .. import paths
from . import templates as tp

NAME = re.compile(r"^[a-z][a-z0-9_]{1,40}$")
VERSIONED = re.compile(r"^(?P<name>[A-Za-z0-9_]+)\.v(?P<v>[1-9][0-9]{0,3})\.jsx$")
VIDEO = (".mp4", ".mov", ".webm")
IMAGE = (".jpg", ".jpeg", ".png", ".webp")


class LibraryError(ValueError):
    """The shelf cannot do this. The message says what to change."""


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def today() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


# ---------------------------------------------------------------- folders and the index


def user_dir() -> Path:
    """The user's own motion templates: ``studio/brand/templates/motion`` (may not exist yet)."""
    return paths.user_brand_dir() / "templates" / "motion"


def index_path(d: Path | None = None) -> Path:
    return (d or user_dir()) / "library.json"


def read_index(d: Path | None = None) -> dict[str, dict]:
    """``library.json`` as ``{name: entry}`` (empty when there is none)."""
    p = index_path(d)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in data.items() if isinstance(v, dict)} if isinstance(data, dict) else {}


def write_index(idx: dict[str, dict]) -> Path:
    from .. import approvals
    approvals.ensure_user_pack()
    d = user_dir()
    d.mkdir(parents=True, exist_ok=True)
    p = index_path(d)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(idx, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(p)
    return p


def file_url(p: Path | str | None) -> str | None:
    """The API address of a shelf file: studio pack files and episode files through ``/api/files``, the app's samples
    through ``/api/motion/app``. None for anything else."""
    if not p:
        return None
    p = Path(p).resolve()
    roots = [(paths.user_brand_dir().resolve(), "/api/files/_onboarding/brand/"),
             ((tp.app_dir() / "samples").resolve(), "/api/motion/app/samples/")]
    for root, prefix in roots:
        if root in p.parents:
            return prefix + p.relative_to(root).as_posix()
    ep_root = paths.episodes_dir().resolve()
    if ep_root in p.parents:
        rel = p.relative_to(ep_root)
        return f"/api/files/{rel.parts[0]}/{Path(*rel.parts[1:]).as_posix()}"
    return None


# ---------------------------------------------------------------- templates on the shelf


def _header(p: Path) -> dict | None:
    try:
        return tp.parse_header(p.read_text(encoding="utf-8"))
    except (OSError, tp.TemplateError):
        return None


def version_of(h: dict | None) -> int:
    return int((h or {}).get("version") or 1)


def _samples(d: Path, name: str, entry: dict | None) -> dict[str, str]:
    """Sample files of a template: ``library.json`` ``samples``/``sample`` first, else ``samples/<name>*`` files."""
    out: dict[str, str] = {}
    e = entry or {}
    for fmt, rel in (e.get("samples") or {}).items():
        if isinstance(rel, str) and (d / rel).is_file():
            out[fmt] = str(d / rel)
    if isinstance(e.get("sample"), str) and (d / e["sample"]).is_file():
        out.setdefault("poster", str(d / e["sample"]))
    sd = d / "samples"
    if not out and sd.is_dir():
        for f in sorted(sd.glob(f"{name}*")):
            stem = f.stem[len(name):]
            if stem and not stem.startswith(("-", ".", "_")):
                continue                                   # another template that starts with the same letters
            if f.suffix.lower() in VIDEO:
                fmt = next((k for k in ("landscape", "portrait", "stage") if k in f.stem), "landscape")
                out[fmt] = str(f)
            elif f.suffix.lower() in IMAGE:
                out.setdefault("poster", str(f))
    return out


def _row(origin: str, d: Path, p: Path, h: dict, entry: dict | None) -> dict:
    samples = _samples(d, h["name"], entry)
    e = entry or {}
    return {"name": h["name"], "origin": origin, "title": e.get("title") or h["name"].replace("_", " "),
            "description": h["description"], "kind": h["kind"] or "full", "formats": h["formats"] or ["landscape"],
            "version": version_of(h), "params": h["defaults"], "path": str(p),
            "samples": {k: file_url(v) or v for k, v in samples.items()},
            "made_from": e.get("made_from"), "approved": e.get("approved"),
            "needs_plates": bool(e.get("needs_plates")), "notes": e.get("notes") or [],
            "versions": sorted({version_of(h), *(int(x["version"]) for x in e.get("history") or []
                                                 if isinstance(x, dict) and x.get("version"))})}


def _folder(origin: str, d: Path) -> list[dict]:
    if not d.is_dir():
        return []
    idx = read_index(d)
    out = []
    for p in sorted(d.glob("*.jsx")):
        if VERSIONED.match(p.name):
            continue
        h = _header(p)
        if h is None or h["name"] != p.stem:
            continue
        out.append(_row(origin, d, p, h, idx.get(h["name"])))
    return out


def episode_pieces() -> list[dict]:
    """Custom pieces in the episodes (``episodes/<id>/motion/<insert>/comp.jsx``), promoted or not."""
    promoted = {(str((e.get("made_from") or {}).get("episode")), str((e.get("made_from") or {}).get("insert"))): n
                for n, e in read_index().items()}
    out = []
    root = paths.episodes_dir()
    for comp in sorted(root.glob("*/motion/*/comp.jsx")):
        ep, iid = comp.parent.parent.parent.name, comp.parent.name
        h = _header(comp)
        brief = comp.parent / "brief.md"
        first = ""
        if brief.is_file():
            first = next((x.strip("# ").strip() for x in brief.read_text(encoding="utf-8").splitlines()
                          if x.strip() and not x.startswith("#")), "")
        frames = sorted(comp.parent.glob("frame-v*.png"))
        out.append({"name": f"{ep}/{iid}", "origin": "episode", "episode": ep, "insert": iid,
                    "title": first or iid, "description": (h or {}).get("description", ""),
                    "kind": (h or {}).get("kind") or "full", "formats": (h or {}).get("formats") or [],
                    "version": version_of(h), "params": (h or {}).get("defaults", {}), "path": str(comp),
                    "samples": {"poster": file_url(frames[-1])} if frames else {},
                    "promoted_as": promoted.get((ep, iid)), "header_ok": h is not None})
    return out


def entries(include_episodes: bool = True) -> list[dict]:
    """The shelf: the pack's templates (they win over the app's of the same name), the app's, then episode pieces."""
    pack = _folder("pack", tp.pack_dir()) if tp.pack_dir().resolve() != tp.app_dir().resolve() else []
    names = {r["name"] for r in pack}
    app = [dict(r, overridden=r["name"] in names) for r in _folder("app", tp.app_dir())]
    rows = pack + app
    if include_episodes:
        rows += episode_pieces()
    return rows


def shelf_names() -> dict[str, dict]:
    """Template name -> its shelf row (the one a plan's ``scene`` resolves to)."""
    out: dict[str, dict] = {}
    for r in entries(include_episodes=False):
        if r["origin"] != "episode" and not r.get("overridden"):
            out.setdefault(r["name"], r)
    return out


def line(r: dict) -> str:
    """One plain line of ``crewcut motion library``."""
    loop = "loop" if any(k != "poster" for k in r.get("samples") or {}) else ("still" if r.get("samples") else "no loop")
    params = ", ".join(k for k in r.get("params") or {} if k != "comp") or "-"
    who = {"app": "app", "pack": "yours", "episode": "episode"}[r["origin"]]
    extra = ""
    if r["origin"] == "pack" and r.get("approved") is None and r.get("made_from"):
        extra = "  (waiting for your yes)"
    if r["origin"] == "episode":
        extra = f"  (in your library as {r['promoted_as']})" if r.get("promoted_as") else ""
    return (f"{r['name']:<28} {who:<8} {r['kind']:<8} v{r['version']:<3} {','.join(r['formats']) or '-':<26} "
            f"{loop:<8} params: {params}{extra}")


# ---------------------------------------------------------------- versions


def resolve_version(name: str, pin: int | None = None) -> Path:
    """The ``.jsx`` of library template ``name``: the latest (``<name>.jsx``) without a pin; with pin N the file whose
    ``@version`` is N (``<name>.jsx`` when it is N, no ``@version`` counts as 1, else the kept ``<name>.v<N>.jsx``).
    The pack's folder is searched before the app's."""
    if "@" in name and pin is None:
        name, _, v = name.partition("@")
        pin = int(v) if v.isdigit() else None
    for d in (tp.pack_dir(), tp.app_dir()):
        cur = d / f"{name}.jsx"
        if pin is None:
            if cur.is_file():
                return cur
            continue
        if cur.is_file() and version_of(_header(cur)) == pin:
            return cur
        old = d / f"{name}.v{pin}.jsx"
        if old.is_file():
            return old
    want = f"{name}@{pin}" if pin else name
    raise tp.TemplateError(f"no motion template '{want}' in your pack or the app")


def uses(name: str) -> list[dict]:
    """Where a template is used: every motion insert with ``"scene": name`` or ``name@N`` in the episodes' edit plans."""
    out = []
    for plan in sorted(paths.episodes_dir().glob("*/edit/plan-v*.json")):
        try:
            data = json.loads(plan.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for e in (data.get("inserts") or []) if isinstance(data, dict) else []:
            if not isinstance(e, dict) or e.get("kind") != "motion" or not isinstance(e.get("scene"), str):
                continue
            n, _, v = e["scene"].partition("@")
            if n == name:
                out.append({"episode": plan.parent.parent.name, "plan": plan.name, "insert": e.get("id"),
                            "version": int(v) if v.isdigit() else None})
    return out


def last_bundle(ep_dir: Path, insert_id: str) -> tuple[Path | None, int]:
    """The newest Critic bundle (``review/motion-vNNN/bundle.json``, also under ``motion/<id>/review/``) that holds
    this insert, and the number of its ERROR findings for the insert. (None, 0) when there is none."""
    found: list[tuple[int, float, Path]] = []
    for root in (ep_dir / "review", ep_dir / "motion" / insert_id / "review"):
        for b in root.glob("motion-v*/bundle.json"):
            m = re.fullmatch(r"motion-v(\d+)", b.parent.name)
            if m:
                found.append((int(m.group(1)), b.stat().st_mtime, b))
    for _v, _t, b in sorted(found, reverse=True):
        try:
            data = json.loads(b.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if insert_id not in {str(r.get("id")) for r in data.get("inserts") or [] if isinstance(r, dict)}:
            continue
        errors = sum(1 for f in data.get("findings") or []
                     if isinstance(f, dict) and f.get("insert") == insert_id and f.get("level") == "ERROR")
        return b, errors
    return None, 0


def add_note(name: str, text: str, source: str) -> None:
    """A note on a shelf entry (review result, retention hint). App templates get a notes-only entry in the pack."""
    idx = read_index()
    e = idx.setdefault(name, {"name": name})
    notes = [n for n in e.get("notes") or [] if not (isinstance(n, dict) and n.get("source") == source
                                                       and n.get("text") == text)]
    notes.append({"date": today(), "text": " ".join(text.split()), "source": source})
    e["notes"] = notes[-20:]
    write_index(idx)
