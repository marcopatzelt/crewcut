"""The local side of an estimate: measured seconds per frame on this machine, and whether it has its own GPU.

The render workbench times a short probe (a few frames of a scene) and calls `record()`. Estimates then use the
median of the last measurements instead of the config default, and say so (`local_measured: true`).
Measurements on rented GPUs are kept too (`where="rented"`), so the rented side improves with use.
"""

from __future__ import annotations

import os
import shutil
import statistics

from . import settings, state

KEEP = 7  # measurements kept per key


def _key(kind: str, where: str, scene: str | None) -> str:
    return f"{where}:{kind}" + (f":{scene}" if scene else "")


def record(kind: str, sec_per_frame: float, *, where: str = "local", scene: str | None = None,
           gpu: str | None = None) -> None:
    """Store one measured value (seconds per frame, or per unit for other kinds)."""
    if where not in ("local", "rented"):
        raise ValueError("where must be local or rented")
    v = float(sec_per_frame)
    if not v > 0:
        raise ValueError("seconds per frame must be above 0")
    entry = {"sec": round(v, 3), "at": state.iso(state.now())}
    if gpu:
        entry["gpu"] = gpu

    def fn(d):
        for key in {_key(kind, where, scene), _key(kind, where, None)}:
            d.setdefault(key, []).append(entry)
            d[key] = d[key][-KEEP:]
        return d

    state.update_json("local.json", {}, fn)


def measured(kind: str, *, where: str = "local", scene: str | None = None) -> float | None:
    """Median of the stored measurements for this scene, else for the kind, else None."""
    d = state.read_json("local.json", {})
    for key in ([_key(kind, where, scene)] if scene else []) + [_key(kind, where, None)]:
        vals = [float(e["sec"]) for e in d.get(key) or [] if e.get("sec")]
        if vals:
            return float(statistics.median(vals))
    return None


def has_gpu() -> bool:
    """True when this machine (the container) sees its own NVIDIA GPU. CREWCUT_LOCAL_GPU=0/1 overrides."""
    env = os.environ.get("CREWCUT_LOCAL_GPU")
    if env is not None:
        return env.strip().lower() in ("1", "true", "yes", "on")
    return shutil.which("nvidia-smi") is not None


def sec_per_frame(kind: str, scene: str | None = None) -> tuple[float | None, bool, str]:
    """(seconds per frame here, measured?, where the number comes from)."""
    m = measured(kind, scene=scene)
    if m is not None:
        return m, True, "measured on this machine"
    k = settings.kind(kind)
    if has_gpu() and k.get("gpu_sec_per_frame"):
        return float(k["gpu_sec_per_frame"]), False, "own GPU found, assumed as fast as a rented one"
    if k.get("local_sec_per_frame"):
        return float(k["local_sec_per_frame"]), False, "config default for a laptop CPU"
    return None, False, "no number yet"
