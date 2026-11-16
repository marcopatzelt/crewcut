"""Shared helpers for the cut tools: episode folders, versions, settings and JSON files."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .. import brand, paths


class CutError(Exception):
    """A problem the user or agent has to fix. The CLI prints the message and exits 1."""


class Waiting(Exception):
    """Waiting for the user's yes, or refused by the user. The CLI exits 3."""

    def __init__(self, message: str, card_id: int | None = None):
        self.card_id = card_id
        super().__init__(message)


VERSION = re.compile(r"v\d{3,}")

# Technical defaults of the speaker cut. Taste values (speed, zoom) can be set in the style pack under
# edit-style.json "cut": {...}, and per episode in the selects file. Values from real episodes are in docs/recording.md.
CUT_DEFAULTS: dict[str, Any] = {
    "speed": 1.0,          # playback speed of the speech (1.1 = 10 % faster)
    "pad_in": 0.12,        # seconds of silence before the first word of a select
    "pad_out": 0.16,       # seconds of silence after the last word of a select
    "pause_gap": 0.30,     # inner pauses longer than this are shortened ...
    "pause_keep": 0.13,    # ... to this much on each side (about 0.26 s in all)
    "zoom_base": 1.0,      # crop factor of the speaker picture (1.0 = full frame)
    "zoom_punch": 1.12,    # every second cut inside the same take punches in to hide the jump
    "face_y": 0.40,        # where the face centre sits in the crop, as a share of the height
    "join_min": 0.17,      # pause at a cut in the finished voice track: shorter sounds chopped
    "join_max": 0.45,      # longer sounds like a gap
    "silence_db": -38.0,   # pause detection on the 16 kHz microphone channel
    "silence_min": 0.12,
    "voice_lufs": -16.0,   # loudness of the cleaned voice track (the final mix is set by the render step)
    "voice_tp": -2.0,
    "voice_lra": 7.0,
    "voice_filter": ("highpass=f=75,afftdn=nr=5:nf=-45:tn=1,equalizer=f=260:t=q:w=0.8:g=-1.2,"
                     "equalizer=f=3200:t=q:w=0.7:g=1.0,deesser=i=0.12:m=0.25:f=0.6,"
                     "acompressor=threshold=0.10:ratio=2.2:attack=8:release=110:makeup=1.2"),
}


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def episode_dir(episode: str) -> Path:
    d = paths.episode_dir(episode)
    if not (d / "project.json").is_file():
        raise CutError(f"no episode {episode}: {d.name}/project.json is missing")
    return d


def find_episode(path: Path) -> tuple[str, Path] | None:
    """The episode a file lies in (any depth under episodes/<id>/), or None."""
    root = paths.episodes_dir().resolve()
    p = Path(path).resolve()
    if root not in p.parents:
        return None
    eid = p.relative_to(root).parts[0]
    d = root / eid
    return (eid, d) if (d / "project.json").is_file() else None


def episode_of_file(path: Path) -> tuple[str, Path]:
    found = find_episode(path)
    if not found:
        raise CutError(f"{path} is not inside an episode folder (studio/episodes/<id>/...)")
    return found


def project(ep_dir: Path) -> dict:
    return read_json(ep_dir / "project.json")


def frame_size(proj: dict) -> tuple[int, int]:
    return (1080, 1920) if proj.get("format") == "portrait" else (1920, 1080)


def resolve_input(arg: str | Path, base: Path | None = None) -> Path:
    """An input file: absolute, or relative to the current folder, the episode folder or the studio folder."""
    p = Path(arg).expanduser()
    if p.is_absolute():
        if not p.exists():
            raise CutError(f"file not found: {arg}")
        return p.resolve()
    for root in [Path.cwd()] + ([base] if base else []) + [paths.studio_root()]:
        q = root / p
        if q.exists():
            return q.resolve()
    raise CutError(f"file not found: {arg}")


def inside(ep_dir: Path, rel_path: str | Path) -> Path:
    """A path named in a plan, resolved inside the episode folder (nothing may point outside)."""
    try:
        return paths.inside(ep_dir, str(rel_path))
    except ValueError as exc:
        raise CutError(str(exc)) from exc


def rel(ep_dir: Path, p: Path) -> str:
    """Path relative to the episode folder, as stored in plans and reports (never an absolute path)."""
    try:
        return Path(p).resolve().relative_to(ep_dir.resolve()).as_posix()
    except ValueError as exc:
        raise CutError(f"{p} is outside the episode folder") from exc


def check_version(v: str) -> str:
    if not isinstance(v, str) or not VERSION.fullmatch(v):
        raise CutError(f"version must look like v001, got {v!r}")
    return v


def version_in(name: str) -> str | None:
    m = re.search(r"-(v\d{3,})(?:\.[A-Za-z0-9]+)?$", name)
    return m.group(1) if m else None


def next_version(folder: Path, prefix: str, suffix: str = ".json") -> str:
    """The next free vNNN for files named <prefix>-vNNN<suffix> in folder."""
    n = 0
    if folder.is_dir():
        for f in folder.iterdir():
            m = re.fullmatch(re.escape(prefix) + r"-v(\d{3,})" + re.escape(suffix), f.name)
            if m:
                n = max(n, int(m.group(1)))
    return f"v{n + 1:03d}"


def read_json(path: Path) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CutError(f"file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise CutError(f"{path} is not valid JSON: {exc}") from exc


def dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=1) + "\n"


def write_new(path: Path, text: str) -> Path:
    """Write a new file. Refuses to overwrite: every change is a new version."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8") as f:
            f.write(text)
    except FileExistsError as exc:
        raise CutError(f"{path.name} exists already. Make a new version instead of overwriting it.") from exc
    return path


def write_new_json(path: Path, data: Any) -> Path:
    return write_new(path, dumps(data))


def write_replace(path: Path, text: str) -> Path:
    """Write derived data that may be rebuilt (pause lists, islands, check reports)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)
    return path


def cut_settings(*overrides: dict | None) -> dict:
    """CUT_DEFAULTS, then the style pack's edit_style.cut, then each override (e.g. the selects file) on top."""
    out = dict(CUT_DEFAULTS)
    try:
        pack_cut = brand.load().value("edit_style.cut", {}) or {}
    except Exception:  # a broken pack must not stop the cut; brand check reports it
        pack_cut = {}
    for layer in (pack_cut, *overrides):
        for k, v in (layer or {}).items():
            if k in CUT_DEFAULTS and v is not None:
                out[k] = v
    return out


def channel_language() -> str:
    try:
        return str(brand.load().value("channel.language", "en") or "en")
    except Exception:
        return "en"
