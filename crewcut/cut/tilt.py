"""The camera roll of the rendered video, measured on speaker frames.

A cut plan can declare a roll correction (`"camera_roll_correction": {"degrees": -1.0}`, a number, or "-1.0°"). The
preview must then show the speaker level: the check measures three or more speaker frames of the rendered video (no
insert, no overlay on screen) and takes the median. More than 0.3° left over is an ERROR, and the preview or final card
is refused. Without a declared correction a tilt above 0.5° is a CHECK. In episode 019 four previews went out without
the declared -1.0° and nobody saw it.

The angle is the mean of the dominant horizontal and vertical edge directions (Sobel edges, a Hough-like projection
search), on the frame scaled to 960 px with a 5 % margin left out (the black corners of a rotation have straight edges
of their own). Positive = the right side is lower (the picture is turned clockwise). It is good to about ±0.3° per
frame, which is why the median of several frames counts.
"""

from __future__ import annotations

import json
import re
import statistics
import subprocess
from pathlib import Path

import numpy as np

ERROR_DEG = 0.3
CHECK_DEG = 0.5
MIN_FRAMES = 3
KEYS = ("camera_roll_correction", "roll_correction")


class Tilted(ValueError):
    """A preview or final card refused: its video misses the declared roll correction, or it is not measured."""


def declared(cut_plan: dict | None) -> float | None:
    """The roll correction a cut plan declares, in degrees, or None."""
    for k in KEYS:
        v = (cut_plan or {}).get(k)
        if isinstance(v, dict):
            v = v.get("degrees", v.get("deg"))
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return float(v)
        if isinstance(v, str) and (m := re.search(r"[-+−]?\d+(?:[.,]\d+)?", v)):
            return float(m.group(0).replace(",", ".").replace("−", "-"))
    return None


def _version(name: str) -> str | None:
    m = re.findall(r"v\d{3,}", name)
    return m[-1] if m else None


def cut_plan_for(ep: Path, plan: dict | None) -> Path | None:
    """The cut plan behind an edit plan: the one of its base's version, else the newest."""
    edit = ep / "edit"
    v = _version(str((plan or {}).get("base") or ""))
    if v and (edit / f"cut-plan-{v}.json").is_file():
        return edit / f"cut-plan-{v}.json"
    found = sorted((int(m.group(1)), p) for p in edit.glob("cut-plan-v*.json")
                   if (m := re.match(r"^cut-plan-v(\d+)\.json$", p.name)))
    return found[-1][1] if found else None


def newest_plan(ep: Path) -> Path | None:
    found = sorted((int(m.group(1)), p) for p in (ep / "edit").glob("plan-v*.json")
                   if (m := re.match(r"^plan-v(\d+)\.json$", p.name)))
    return found[-1][1] if found else None


def _sobel(g: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    gx = (g[:-2, 2:] + 2 * g[1:-1, 2:] + g[2:, 2:]) - (g[:-2, :-2] + 2 * g[1:-1, :-2] + g[2:, :-2])
    gy = (g[2:, :-2] + 2 * g[2:, 1:-1] + g[2:, 2:]) - (g[:-2, :-2] + 2 * g[:-2, 1:-1] + g[:-2, 2:])
    return gx, gy


def _direction(px: np.ndarray, py: np.ndarray, w: np.ndarray) -> float | None:
    if len(px) < 50:
        return None

    def score(a: float) -> float:
        r = np.deg2rad(a)
        rho = py * np.cos(r) - px * np.sin(r)
        h, _ = np.histogram(rho, bins=int(rho.max() - rho.min()) + 1, weights=w)
        return float((h * h).sum())

    best = max(np.arange(-4.0, 4.0 + 1e-9, 0.25), key=score)
    return float(max(np.arange(best - 0.3, best + 0.3 + 1e-9, 0.02), key=score))


def angle(gray: np.ndarray) -> float | None:
    """The roll of one frame in degrees (positive = clockwise), or None when it has too few straight edges."""
    g = np.asarray(gray, dtype=np.float32)
    h0, w0 = g.shape
    if max(h0, w0) > 960:   # the measure works on 960 px, like the studio's measuring script
        from PIL import Image
        f = 960 / max(h0, w0)
        g = np.asarray(Image.fromarray(g.astype(np.uint8)).resize((round(w0 * f), round(h0 * f))), dtype=np.float32)
        h0, w0 = g.shape
    g = g[int(h0 * 0.05):h0 - int(h0 * 0.05), int(w0 * 0.05):w0 - int(w0 * 0.05)]
    gx, gy = _sobel(g)
    mag = np.hypot(gx, gy)
    thr = max(float(np.percentile(mag, 95)), 1e-3)   # the strongest 5 % of the edges (a flat picture: any edge)
    ys, xs = np.nonzero((np.abs(gy) > 3 * np.abs(gx)) & (mag > thr))
    hz = _direction(xs.astype(float), ys.astype(float), mag[ys, xs])
    ys2, xs2 = np.nonzero((np.abs(gx) > 3 * np.abs(gy)) & (mag > thr))
    vt = _direction(ys2.astype(float), xs2.astype(float), mag[ys2, xs2])
    vt = -vt if vt is not None else None
    parts = [a for a in (hz, vt) if a is not None]
    return round(sum(parts) / len(parts), 2) if parts else None


def frame_gray(video: Path, t: float, width: int = 960) -> np.ndarray | None:
    """One frame of the video at t seconds, grey, scaled to `width` (height in proportion)."""
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                            "stream=width,height", "-of", "json", str(video)], capture_output=True, text=True)
    try:
        s = json.loads(probe.stdout)["streams"][0]
        w, h = int(s["width"]), int(s["height"])
    except (ValueError, KeyError, IndexError):
        return None
    oh = max(2, round(h * width / w / 2) * 2)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{max(0.0, t):.3f}", "-i", str(video), "-frames:v", "1",
                          "-vf", f"scale={width}:{oh}", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                         capture_output=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(oh, width) if len(raw) == width * oh else None


def speaker_times(runs: list[tuple[int, int]], fps: float, n: int = 5, min_s: float = 1.0) -> list[float]:
    """n times spread evenly over the stretches with only the speaker on screen (each at least min_s long), a quarter
    second away from their cuts, in time order."""
    long = [(a, b) for a, b in runs if (b - a) / fps >= min_s]
    total = sum(b - a for a, b in long)
    out = []
    for i in range(n if total else 0):
        pos, cum = (i + 0.5) * total / n, 0
        for a, b in long:
            if pos < cum + (b - a):
                edge = 0.25 * fps
                out.append(round(min(max(a + pos - cum, a + edge), b - edge) / fps, 2))
                break
            cum += b - a
    return out


def verdict(correction: float | None, angles: list[float]) -> tuple[str, str]:
    """(level, text) for the report: ERROR, CHECK or OK."""
    got = [a for a in angles if a is not None]
    shown = ", ".join(f"{a:+.2f}°" for a in got)
    if len(got) < MIN_FRAMES:
        return ("CHECK" if correction is not None else "NOTE",
                f"Camera roll: only {len(got)} speaker frame(s) measurable, {MIN_FRAMES} needed. Check it by eye.")
    med = statistics.median(got)
    if correction is not None:
        if abs(med) > ERROR_DEG:
            return ("ERROR", f"Camera roll: the cut plan corrects {correction:+.1f}°, but the speaker frames still tilt "
                    f"{med:+.2f}° (median of {shown}; at most ±{ERROR_DEG}°). The correction is not in this render.")
        return "OK", f"Camera roll {med:+.2f}° after the declared {correction:+.1f}° ({shown})"
    if abs(med) > CHECK_DEG:
        return ("CHECK", f"Camera roll: the speaker frames tilt {med:+.2f}° ({shown}) and the cut plan declares no "
                "correction. Level it (cut plan camera_roll_correction) or say why not.")
    return "OK", f"Camera roll {med:+.2f}° ({shown})"


def record_path(video: Path, ep: Path) -> Path:
    return ep / "review" / f"roll-{video.name}.json"


def measure(video: Path, ep: Path, times: list[float], correction: float | None) -> dict:
    """Measure the frames, judge them, and keep the result next to the reviews (the card gate reads it)."""
    angles = []
    for t in times:
        g = frame_gray(video, t)
        angles.append(angle(g) if g is not None else None)
    level, text = verdict(correction, angles)
    st = video.stat()
    out = {"video": video.name, "size": st.st_size, "mtime": int(st.st_mtime), "correction": correction,
           "times": times, "angles": angles, "level": level, "text": text}
    p = record_path(video, ep)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    return out


def gate(ep: Path, video: Path) -> None:
    """Refuse a preview or final card whose video misses the declared roll correction. Raises Tilted."""
    cp = cut_plan_for(ep, read(newest_plan(ep)))
    correction = declared(read(cp))
    if correction is None or video.suffix.lower() not in (".mp4", ".mov", ".mkv", ".webm"):
        return
    p = record_path(video, ep)
    rec = read(p)
    st = video.stat()
    if not rec or rec.get("size") != st.st_size or rec.get("mtime") != int(st.st_mtime):
        raise Tilted(f"The cut plan {cp.name} declares a camera roll correction of {correction:+.1f}°, and the "
                         f"roll of {video.name} is not measured yet. Run style_check.py on the plan with --video "
                         f"{video.name}: it measures the speaker frames.")
    level, text = verdict(correction, rec.get("angles") or [])
    if level == "ERROR":
        raise Tilted(text + " Build the video again with the correction, check it, then propose the card.")


def read(p: Path | None) -> dict | None:
    if not p or not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
