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
import shutil
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

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
    for name, entry in read_index().items():
        if entry.get("type") == "source-kit":
            rows.append({**entry, "name": name, "origin": "pack", "kind": "source-kit", "formats": [],
                         "params": {}, "samples": {}, "needs_plates": True, "versions": [entry["version"]],
                         "path": str(user_dir() / entry["bundle"])})
    if include_episodes:
        rows += episode_pieces()
    return rows


def shelf_names() -> dict[str, dict]:
    """Template name -> its shelf row (the one a plan's ``scene`` resolves to)."""
    out: dict[str, dict] = {}
    for r in entries(include_episodes=False):
        if r["origin"] != "episode" and not r.get("overridden") and r.get("kind") != "source-kit":
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


def uses_index() -> dict[str, list[dict]]:
    """Where each template is used, in one pass: the motion inserts with ``"scene": name`` or ``name@N`` in the newest
    edit plan of each episode (an older plan version that the episode moved away from does not count)."""
    out: dict[str, list[dict]] = {}
    newest: dict[Path, Path] = {}
    for plan in paths.episodes_dir().glob("*/edit/plan-v*.json"):
        ep = plan.parent.parent
        if ep not in newest or (len(plan.stem), plan.stem) > (len(newest[ep].stem), newest[ep].stem):
            newest[ep] = plan
    for ep, plan in sorted(newest.items()):
        try:
            data = json.loads(plan.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for e in (data.get("inserts") or []) if isinstance(data, dict) else []:
            if not isinstance(e, dict) or e.get("kind") != "motion" or not isinstance(e.get("scene"), str):
                continue
            n, _, v = e["scene"].partition("@")
            out.setdefault(n, []).append({"episode": ep.name, "plan": plan.name, "insert": e.get("id"),
                                          "version": int(v) if v.isdigit() else None})
    return out


def uses(name: str) -> list[dict]:
    """Where a template is used (see ``uses_index``)."""
    return uses_index().get(name, [])


def shelf() -> list[dict]:
    """The shelf for the web UI (``GET /api/motion/library``): ``entries()``, each template row with ``uses``."""
    idx = uses_index()
    return [r if r["origin"] == "episode" else {**r, "uses": idx.get(r["name"], [])} for r in entries()]


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


# ---------------------------------------------------------------- promotion


def _spoken(ep_dir: Path) -> str:
    from . import density as dens
    words = sorted((ep_dir / "work").glob("words-v*.json"))
    if not words:
        return ""
    try:
        w = dens.norm_words(json.loads(words[-1].read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return ""
    return " ".join(dens.normalize(x["w"]) for x in w)


def plan_entries(ep_dir: Path, insert_id: str) -> list[dict]:
    """The motion inserts of the episode's edit plans that use this custom piece (``source: motion/<id>/...``)."""
    out = []
    for plan in sorted((ep_dir / "edit").glob("plan-v*.json")):
        try:
            data = json.loads(plan.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for e in (data.get("inserts") or []) if isinstance(data, dict) else []:
            src = str(e.get("source") or "") if isinstance(e, dict) else ""
            if src.startswith(f"motion/{insert_id}/"):
                out.append(e)
    return out


STRING = re.compile(r"\"((?:[^\"\\\n]|\\.)*)\"|'((?:[^'\\\n]|\\.)*)'")


def episode_values(ep_dir: Path, insert_id: str, src: str, header: dict) -> list[str]:
    """Why this comp is not yet a template: episode-specific values that are not params with a default. Empty = fine.

    Checked: every param has a default; every ``data``/``cues`` key the episode's plan gives the piece is a param;
    no string in the code is a path into the episode or the studio; no string in the code is text spoken in this
    episode or a value the plan passes (that text must arrive as a param)."""
    from .review import strip_comments
    out = []
    defaults = header["defaults"]
    for k, v in defaults.items():
        if v is None:
            out.append(f"param {k} has no default (every param needs one, so the template renders with {{}})")
    given: dict[str, Any] = {}
    for e in plan_entries(ep_dir, insert_id):
        for key in ("data", "cues"):
            for k, v in (e.get(key) or {}).items():
                given.setdefault(k, v)
    for k in sorted(given):
        if k not in defaults:
            out.append(f"the plan gives {k!r}, but the comp has no param {k!r} with a default")
    body = strip_comments(src[tp.HEADER.search(src).end():])
    spoken = _spoken(ep_dir)
    plan_texts = {v.strip().lower() for v in given.values() if isinstance(v, str) and len(v.strip()) >= 4}
    for m in STRING.finditer(body):
        s = m.group(1) if m.group(1) is not None else m.group(2)
        low = s.strip().lower()
        if not low:
            continue
        if re.search(r"EC_ASSETS\s*\+\s*$", body[max(0, m.start() - 40):m.start()]):
            continue                                      # a file in the piece's own assets/ folder
        if s.startswith("/") or re.match(r"^[A-Za-z]:\\", s) or "episodes/" in s or f"motion/{insert_id}" in s:
            out.append(f"the path {s!r} is written into the comp; files of the piece go in its assets/ folder")
        elif low in plan_texts:
            out.append(f"the text {s!r} is a value the plan passes; use the param instead")
        elif " " in low and len(low) >= 6 and spoken and f" {low} " in f" {spoken} ":
            out.append(f"the text {s!r} is spoken in this episode and written into the comp; make it a param")
    return out


def _longer(defaults: dict) -> dict:
    """The second param set of the promotion check: every text twice as long."""
    def grow(v: Any) -> Any:
        if isinstance(v, str) and v and not v.startswith("#") and v != defaults.get("comp"):
            return f"{v} {v}"
        if isinstance(v, list) and v and all(isinstance(x, str) for x in v):
            return [grow(x) for x in v]
        return v
    return {k: grow(v) for k, v in defaults.items()}


def _rename(src: str, old: str, new: str, version: int) -> str:
    """The comp's text as template ``new``: header name, function name, ``@version`` and the asset folder."""
    out = re.sub(r"(@template\s+)" + re.escape(old) + r"\b", r"\g<1>" + new, src, count=1)
    out = re.sub(r"\bfunction\s+" + re.escape(old) + r"\s*\(", f"function {new}(", out, count=1)
    if re.search(r"(?m)^[ \t]*\*?[ \t]*@version\b", out):
        out = re.sub(r"(?m)^([ \t]*\*?[ \t]*@version)[ \t]+\S+", rf"\g<1> {version}", out, count=1)
    else:
        out = re.sub(r"(?m)^([ \t]*\*?[ \t]*)@end\b", rf"\g<1>@version {version}\n\g<1>@end", out, count=1)
    return re.sub(r"EC_ASSETS(\s*\+\s*)([\"'])/", rf"EC_ASSETS\g<1>\g<2>/{new}/", out)


def promote(episode: str, insert_id: str, name: str, render_sample: Callable[..., Any] | None,
            title: str | None = None, identity: str | None = None, card: bool = True) -> dict:
    """Turn the episode's custom piece into a library template ``name`` in the user's pack (motion plan 3.6).

    Refuses unless the insert's last Critic bundle has 0 errors and every episode-specific value is a param with a
    default. ``render_sample(template, fmt, params, out)`` renders one loop of ``template`` (a ``.jsx`` path) in
    ``fmt`` with ``params`` to ``out`` (an ``.mp4``) and may return ``{"poster": path}``; it is called with the
    defaults and with every text twice as long, in every format the template claims. Then the files are copied, the
    index entry is written (``approved: null``) and the ``template`` card opens. Returns the entry (plus ``card``)."""
    from .. import approvals
    from ..doctor import read_pin
    if not NAME.match(name):
        raise LibraryError(f"name {name!r}: lower case letters, digits and _ (2 to 41), starting with a letter")
    if (tp.app_dir() / f"{name}.jsx").is_file():
        raise LibraryError(f"the app already has a template {name!r}; pick another name")
    ep_dir = paths.episode_dir(episode)
    piece = ep_dir / "motion" / insert_id
    comp = piece / "comp.jsx"
    if not comp.is_file():
        raise LibraryError(f"no custom piece {insert_id} in {episode} (motion/{insert_id}/comp.jsx)")
    bundle, errors = last_bundle(ep_dir, insert_id)
    if bundle is None:
        raise LibraryError(f"{insert_id} has no Critic bundle yet: run `crewcut render motion-review` on the plan first")
    if errors:
        raise LibraryError(f"the last review of {insert_id} ({bundle.parent.name}) has {errors} error(s); only a piece "
                           "with 0 errors joins the library")
    src = comp.read_text(encoding="utf-8")
    h = tp.parse_header(src)
    if not h["formats"]:
        raise LibraryError(f"{insert_id}: the comp's header has no @formats; a template says which formats it renders")
    problems = episode_values(ep_dir, insert_id, src, h)
    if problems:
        raise LibraryError(f"{insert_id} is not generic yet: " + "; ".join(problems))
    if render_sample is None:
        raise LibraryError("samples cannot be rendered here: the motion engine is not connected to promotion")

    d = user_dir()
    idx = read_index() if d.is_dir() else {}
    cur = d / f"{name}.jsx"
    old_v = version_of(_header(cur)) if cur.is_file() else 0
    version = old_v + 1
    text = _rename(src, h["name"], name, version)
    if cur.is_file() and cur.read_text(encoding="utf-8") == text:
        raise LibraryError(f"{name} v{old_v} is already this comp; nothing to promote")

    approvals.ensure_user_pack()
    d.mkdir(parents=True, exist_ok=True)
    stage = d / f".stage-{name}"
    shutil.rmtree(stage, ignore_errors=True)
    stage.mkdir()
    try:
        (stage / f"{name}.jsx").write_text(text, encoding="utf-8")
        if (piece / "assets").is_dir():
            shutil.copytree(piece / "assets", stage / "assets" / name)
        plates = sorted((piece / "plates").glob("*.py")) if (piece / "plates").is_dir() else []
        for p in plates:
            (stage / "plates").mkdir(exist_ok=True)
            shutil.copy2(p, stage / "plates" / f"{name}_{p.name}")
        h2 = tp.parse_header(text)
        bundle_rel = f"bundles/{name}/v{version}"
        source_bundle = stage / bundle_rel
        source_bundle.mkdir(parents=True)
        reusable = [comp, *piece.glob("*.py")]
        for sub in ("plates", "assets"):
            reusable.extend(p for p in (piece / sub).rglob("*") if p.is_file())
        manifest = {"schema": 1, "params": h2["defaults"], "files": {}, "plates": []}
        for source in reusable:
            if source.is_symlink() or piece.resolve() not in source.resolve().parents:
                raise LibraryError("Reusable sources must stay inside the insert; symbolic links are not copied.")
            rel = source.relative_to(piece).as_posix()
            target = source_bundle / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            manifest["files"][rel] = sha256(target)
        for plan_file in sorted((ep_dir / "edit").glob("plan-v*.json"), reverse=True):
            plan_data = json.loads(plan_file.read_text())
            found = next((x for x in plan_data.get("inserts", []) if x.get("source") == f"motion/{insert_id}/comp.jsx"), None)
            if found:
                manifest["plates"] = found.get("plates") or []
                manifest["source_insert"] = insert_id
                break
        (source_bundle / "bundle.json").write_text(json.dumps(manifest, indent=2) + "\n")
        samples: dict[str, str] = {}
        poster = None
        (stage / "samples").mkdir()
        longer = _longer(h2["defaults"])
        for fmt in h2["formats"]:
            out = stage / "samples" / f"{name}-v{version}-{fmt}.mp4"
            res = render_sample(stage / f"{name}.jsx", fmt, dict(h2["defaults"]), out)
            if not out.is_file():
                raise LibraryError(f"the {fmt} sample with the default params was not rendered")
            samples[fmt] = f"samples/{out.name}"
            if isinstance(res, dict) and res.get("poster") and Path(res["poster"]).is_file() and poster is None:
                pp = stage / "samples" / f"{name}-v{version}{Path(res['poster']).suffix.lower()}"
                shutil.copy2(res["poster"], pp)
                poster = f"samples/{pp.name}"
            if longer != h2["defaults"]:
                check = stage / f"check-{fmt}.mp4"
                render_sample(stage / f"{name}.jsx", fmt, longer, check)
                if not check.is_file():
                    raise LibraryError(f"the {fmt} check with every text twice as long did not render")
                check.unlink()
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise

    # into place: the old version is kept as <name>.v<N>.jsx
    if cur.is_file():
        cur.replace(d / f"{name}.v{old_v}.jsx")
    (stage / f"{name}.jsx").replace(cur)
    for sub in ("assets", "plates", "samples", "bundles"):
        if (stage / sub).is_dir():
            for f in (stage / sub).rglob("*"):
                if f.is_file():
                    target = d / sub / f.relative_to(stage / sub)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    f.replace(target)
    shutil.rmtree(stage, ignore_errors=True)

    prev = idx.get(name) or {}
    history = list(prev.get("history") or [])
    if prev.get("version"):
        history.append({"version": prev["version"], "file": f"{name}.v{prev['version']}.jsx",
                        "sha256": prev.get("sha256"), "made_from": prev.get("made_from"),
                        "approved": prev.get("approved"), "samples": prev.get("samples"),
                        "bundle": prev.get("bundle"), "bundle_sha256": prev.get("bundle_sha256")})
    entry = {
        "name": name, "title": title or prev.get("title") or name.replace("_", " "), "description": h2["description"],
        "version": version, "kind": h2["kind"] or "full", "formats": h2["formats"], "params": h2["defaults"],
        "needs_plates": bool(plates), "made_from": {"episode": episode, "insert": insert_id},
        "review": {"bundle": str(bundle.parent.relative_to(ep_dir)), "errors": 0},
        "approved": None, "sample": poster, "samples": samples, "sha256": sha256(cur), "engine_pin": read_pin(),
        "promoted": today(), "history": history, "notes": list(prev.get("notes") or []),
        "bundle": bundle_rel, "bundle_sha256": sha256(d / bundle_rel / "bundle.json"),
    }
    idx[name] = entry
    write_index(idx)
    if card:
        images = [u for u in (file_url(d / poster) if poster else None,) if u]
        c = approvals.propose(
            episode, "edit", "template", f"Keep '{entry['title']}' in your library?",
            body=(f"New motion graphic from {insert_id}, version {version}. Its params: "
                  f"{', '.join(k for k in entry['params'] if k != 'comp') or 'none'}. A second video can use it "
                  "with other params, without touching the comp."),
            data={"template": {"name": name, "title": entry["title"], "version": version, "kind": entry["kind"],
                               "formats": entry["formats"], "params": entry["params"],
                               "samples": {k: file_url(d / v) for k, v in samples.items()},
                               "poster": file_url(d / poster) if poster else None,
                               "made_from": entry["made_from"], "sha256": entry["sha256"],
                               "replaces": old_v or None},
                  "images": images},
            identity=identity or "editor")
        entry = {**entry, "card": c["id"]}
    return entry


# ---------------------------------------------------------------- the user's answer


def check_card(card: dict) -> None:
    """Before a yes on a ``template`` card: the template file is still the one the card showed."""
    t = (card.get("data") or {}).get("template") or {}
    p = user_dir() / f"{t.get('name')}.jsx"
    if not p.is_file() or sha256(p) != t.get("sha256"):
        raise ValueError("The template changed after this card was made. Approving it would approve something you "
                         "did not see; the Editor promotes it again and a new card opens.")
    entry = read_index().get(t.get("name")) or {}
    if entry.get("bundle"):
        checked_bundle(entry)


def checked_bundle(entry: dict) -> tuple[Path, dict]:
    if not entry.get("bundle"):
        raise LibraryError("This older template has no complete source bundle. Promote it again before copying it.")
    folder = paths.inside(user_dir(), entry["bundle"])
    manifest = folder / "bundle.json"
    if sha256(manifest) != entry.get("bundle_sha256"):
        raise LibraryError("The reusable source manifest changed after promotion.")
    data = json.loads(manifest.read_text())
    for rel, digest in data["files"].items():
        source = paths.inside(folder, rel)
        if source.is_symlink() or not source.is_file() or sha256(source) != digest:
            raise LibraryError(f"Reusable source changed: {rel}")
    return folder, data


def import_source_kit(name: str, root: Path, files: list[str], entrypoints: list[str], reason: str) -> dict:
    """Import explicitly selected reusable code, preserving paths; never execute it."""
    if not NAME.fullmatch(name) or not reason.strip() or not entrypoints or not set(entrypoints) <= set(files):
        raise LibraryError("Choose a kit name, explicit files, included entrypoints and the user's selection reason.")
    allowed = {".py", ".js", ".jsx", ".sh", ".json", ".md", ".svg", ".png", ".jpg", ".otf", ".ttf", ".attribution"}
    idx = read_index()
    if name in idx:
        raise LibraryError("Source kit already exists; use a new name to preserve the proven version.")
    checked = []
    for rel in files:
        source = paths.inside(root.resolve(), rel)
        if not source.is_file() or source.is_symlink() or source.suffix.lower() not in allowed:
            raise LibraryError(f"Not a supported source file: {rel}")
        checked.append((rel, source))
    from .. import approvals
    approvals.ensure_user_pack()
    bundle_rel = f"bundles/{name}/v1"
    dest = paths.inside(user_dir(), bundle_rel)
    if dest.exists():
        raise LibraryError("Source bundle exists; choose a new name.")
    dest.mkdir(parents=True)
    manifest = {"schema": 1, "type": "source-kit", "entrypoints": entrypoints, "params": {}, "files": {}}
    for rel, source in checked:
        target = paths.inside(dest, rel)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        manifest["files"][rel] = sha256(target)
    (dest / "bundle.json").write_text(json.dumps(manifest, indent=2) + "\n")
    entry = {"type": "source-kit", "version": 1, "title": name, "description": "Reusable source kit; adapt and review before production.",
             "bundle": bundle_rel, "bundle_sha256": sha256(dest / "bundle.json"), "entrypoints": entrypoints,
             "approved": {"by": "user", "selection": reason, "date": today()}, "notes": [], "history": []}
    idx[name] = entry
    write_index(idx)
    return entry


def reuse(name: str, episode: str, insert_id: str, version: int | None = None) -> dict:
    """Copy an approved, complete version into a fresh insert; never run or change the original."""
    from .. import episodes
    from .custom import piece_dir
    episodes.read(episode)
    entry = read_index().get(name) or {}
    if version and entry.get("version") != version:
        entry = next((e for e in entry.get("history", []) if e.get("version") == version), {})
    if not entry.get("approved"):
        raise LibraryError("Choose an approved template version from the library.")
    source, manifest = checked_bundle(entry)
    target = paths.inside(paths.episode_dir(episode), f"motion/{piece_dir(episode, insert_id).name}")
    if target.exists():
        raise LibraryError("The target insert already exists; choose a new ID.")
    target.mkdir(parents=True)
    for rel in manifest["files"]:
        dest = paths.inside(target, rel)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(paths.inside(source, rel), dest)
    (target / "review").mkdir(exist_ok=True)
    (target / "refs").mkdir(exist_ok=True)
    main = (manifest.get("entrypoints") or ["comp.jsx"])[0]
    recipe = {"source": f"motion/{insert_id}/{main}", "params": manifest["params"],
              "template": name, "version": entry["version"], "plates": manifest.get("plates", []),
              "note": "Adapt text, spoken cues, duration and plate frame ranges; run new style and motion reviews."}
    if manifest.get("type") == "source-kit":
        recipe.update(kind="source-kit", entrypoints=manifest["entrypoints"],
                      note="Copied source kit, not a native scene yet. Adapt its inputs to this episode and render a checked probe before use.")
    old = manifest.get("source_insert")
    if old:
        for plate in recipe["plates"]:
            plate["script"] = plate["script"].replace(f"motion/{old}/", f"motion/{insert_id}/", 1)
    (target / "REUSE.json").write_text(json.dumps(recipe, indent=2) + "\n")
    return recipe


def approve(card: dict) -> dict:
    """The yes of a ``template`` card: the entry gets ``approved`` (date, by the user, card)."""
    t = (card.get("data") or {}).get("template") or {}
    idx = read_index()
    e = idx.get(t.get("name"))
    if not e or e.get("version") != t.get("version"):
        raise ValueError("this template version is no longer in your library")
    e["approved"] = {"date": today(), "by": "user", "card": card.get("id")}
    write_index(idx)
    return e


def withdraw(card: dict) -> None:
    """A no on a ``template`` card: the new version leaves the library, the previous one (if any) comes back."""
    t = (card.get("data") or {}).get("template") or {}
    name, version = t.get("name"), t.get("version")
    idx = read_index()
    e = idx.get(name)
    d = user_dir()
    if not e or e.get("version") != version or e.get("approved"):
        return
    cur = d / f"{name}.jsx"
    if cur.is_file() and sha256(cur) == e.get("sha256"):
        cur.unlink()
    for rel in (e.get("samples") or {}).values():
        (d / rel).unlink(missing_ok=True)
    history = list(e.get("history") or [])
    if history:
        back = history.pop()
        old = d / back["file"]
        if old.is_file():
            old.replace(cur)
        idx[name] = {**e, **{k: v for k, v in back.items() if k != "file"}, "history": history}
    else:
        shutil.rmtree(d / "assets" / name, ignore_errors=True)
        for p in (d / "plates").glob(f"{name}_*.py") if (d / "plates").is_dir() else []:
            p.unlink()
        del idx[name]
    write_index(idx)
