"""Projects and compositions: the ``.ecproj`` file (EffectCraft's versioned JSON) is the state on disk.

``create`` makes a new project with one composition through the engine (``comp.new`` + ``--save-as``), so the
file is always written by EffectCraft itself. ``info`` reads it back through ``effectcraft-cli info``.
"""

from __future__ import annotations

import json
import os
from typing import Any

from .backend import Backend, BackendError

PROFILES: dict[str, dict[str, Any]] = {
    "1080p60": {"width": 1920, "height": 1080, "frameRate": 60},
    "1080p30": {"width": 1920, "height": 1080, "frameRate": 30},
    "1080p25": {"width": 1920, "height": 1080, "frameRate": 25},
    "vertical60": {"width": 1080, "height": 1920, "frameRate": 60},
    "vertical30": {"width": 1080, "height": 1920, "frameRate": 30},
    "square60": {"width": 1080, "height": 1080, "frameRate": 60},
    "4k30": {"width": 3840, "height": 2160, "frameRate": 30},
    "720p30": {"width": 1280, "height": 720, "frameRate": 30},
}


def list_profiles() -> dict[str, dict[str, Any]]:
    """Composition presets (size and frame rate)."""
    return dict(PROFILES)


def comp_params(name: str = "Main", profile: str | None = "1080p60", width: int | None = None,
                height: int | None = None, fps: float | None = None, duration: float = 10.0,
                bg: str | None = None, shutter_angle: float | None = None, samples: int | None = None,
                renderer: str | None = None) -> dict[str, Any]:
    """Parameters for ``comp.new`` from a profile plus overrides. Validates sizes and rates."""
    p: dict[str, Any] = {"name": name}
    if profile:
        if profile not in PROFILES:
            raise ValueError(f"unknown profile {profile!r}; one of: {', '.join(PROFILES)}")
        p.update(PROFILES[profile])
    if width is not None:
        p["width"] = int(width)
    if height is not None:
        p["height"] = int(height)
    if fps is not None:
        p["frameRate"] = float(fps)
    for k in ("width", "height"):
        if k in p and not (1 <= p[k] <= 30000):
            raise ValueError(f"{k} must be 1..30000")
    if p.get("frameRate") is not None and not (1 <= p["frameRate"] <= 999):
        raise ValueError("fps must be 1..999")
    if duration <= 0:
        raise ValueError("duration must be > 0")
    p["duration"] = float(duration)
    if bg:
        p["background"] = bg
    if shutter_angle is not None:
        p["shutterAngle"] = float(shutter_angle)
    if samples is not None:
        p["motionBlurSamples"] = int(samples)
    if renderer:
        if renderer not in ("classic3D", "advanced3D"):
            raise ValueError("renderer must be classic3D or advanced3D")
        p["renderer"] = renderer
    return p


def create(backend: Backend, path: str, comp: dict[str, Any], motion_blur: bool = True,
           overwrite: bool = False) -> dict[str, Any]:
    """A new project file at ``path`` holding one composition."""
    path = os.path.abspath(path)
    if os.path.exists(path) and not overwrite:
        raise BackendError(f"{path} exists (use --overwrite)")
    if os.path.exists(path):
        os.remove(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    steps = [{"command": "comp.new", "params": comp}]
    if motion_blur:
        steps.append({"command": "comp.setSwitch", "params": {"comp": comp["name"], "switch": "motionBlur", "value": True}})
    reply = backend.run_steps(steps, save_as=path)
    if not os.path.exists(path):
        raise BackendError(f"EffectCraft did not write {path}", detail=reply)
    return {"project": path, "comp": comp["name"], "reply": reply}


def read(path: str) -> dict[str, Any]:
    """The project JSON as written by EffectCraft (read-only inspection)."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def summary(path: str) -> dict[str, Any]:
    """Comps and layer counts straight from the file (no engine call; cheap for agents)."""
    data = read(path)
    items = data.get("items") or data.get("project", {}).get("items") or []
    comps = []

    def walk(xs: Any) -> None:
        if isinstance(xs, dict):
            xs = list(xs.values())
        for it in xs or []:
            if not isinstance(it, dict):
                continue
            kind = str(it.get("kind") or it.get("type") or "").lower()
            if "comp" in kind or "layers" in it:
                comps.append({"name": it.get("name"), "id": it.get("id"),
                              "layers": len(it.get("layers") or []),
                              "size": [it.get("width"), it.get("height")], "fps": it.get("frameRate") or it.get("fps"),
                              "duration": it.get("duration")})
            if it.get("children"):
                walk(it["children"])
    walk(items)
    return {"project": os.path.abspath(path), "version": data.get("version") or data.get("formatVersion"),
            "comps": comps, "bytes": os.path.getsize(path)}


def open_project(path: str) -> dict[str, Any]:
    """Check that ``path`` is an EffectCraft project and return its summary (the session then points at it)."""
    if not os.path.exists(path):
        raise BackendError(f"no such project: {path}")
    return summary(path)


def save_as(backend: Backend, path: str, target: str) -> dict[str, Any]:
    """Let EffectCraft write a copy of the project under ``target`` (engine save, not a file copy)."""
    reply = backend.call(backend.argv(["info"], project=path, save_as=target))
    return {"project": os.path.abspath(target), "reply": reply}


def info(backend: Backend, path: str) -> Any:
    """Engine summary of the project (comps, layers, renderer)."""
    return backend.info(path)
