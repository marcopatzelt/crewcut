"""The slide check: a full-frame insert that reads as a slide instead of motion design.

The launch film's craft rules (``examples/launch-film/README.md``) say the camera never stops, depth is real and every
transition is caused by a motion. A slide does the opposite: a flat ground, one centred box or a text window, an icon
far from its label, and a picture that stands still while it is on screen. This module measures that on the video
itself, so the Critic's style check (``skills/cut-check/scripts/style_check.py``) and ``crewcut render slides`` can
name it with numbers.

Per insert, inside its hold (the first ``LEAD_S`` and the last ``TAIL_S`` seconds are the entrance and the exit):

    camera   samples every ``STEP_S`` seconds; per pair of samples the best global zoom and pan (a scale search with
             phase correlation, numpy only) and the share of textured pixels that did not change at all ("frozen").
             A pair moves when the camera moves (rate at least ``CAM_MIN`` of the frame per second while most of the
             picture changes) or when nearly nothing of the picture stays the same (real footage, a fast push).
    layout   one frame in the middle of the hold: the share of the frame in one flat ground colour, the share of flat
             areas, the share of flat panels that are not the ground (text windows, number boxes), the widest empty
             gap between two parts of the content (an icon far from its label), and how far the content sits from the
             centre.

The verdict: an insert whose camera never moves during its hold is ``still``; when its layout is also flat it is a
``slide``. Both break rule 2 of the launch film (the camera never stops); the layout says what makes it a slide. A
recording (``clip``) gets a CHECK instead of an ERROR: a still screen recording wants a frame, a crop or a push.

Calibration (2026-11-23): the 51 inserts of a long video with mostly flat 2D windows and number boxes, against the
launch film in its beats and in 2.5 s windows. The numbers are in ``tests/render/test_slide.py``.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from typing import Any

import numpy as np

LEAD_S = 1.0            # the entrance (parts build one after the other): not part of the hold
TAIL_S = 0.4            # the exit
STEP_S = 0.5            # seconds between two camera samples
MAX_PAIRS = 8           # camera samples per insert
MIN_HOLD_S = 0.8        # shorter holds are not judged
CAM_W, CAM_H = 320, 180
LAYOUT_W, LAYOUT_H = 480, 270
MARGIN = 10             # pixels left out at the frame edge when comparing (warp borders)
SCALES = np.linspace(0.97, 1.03, 25)
CAM_MIN = 0.005         # 0.5 % of the frame per second: a talking video drifts 1.5 to 3 %, the launch film 2 to 8 %
FROZEN_MOVE = 0.5       # a camera move changes most textured pixels: at most this share may stay frozen
FROZEN_ALIVE = 0.15     # below this share nothing stands still (footage, a fast push): the pair moves
MOVING_SHARE = 0.5      # the hold moves when more than this share of its samples move
MIN_TEXTURE = 0.002     # a sample without texture (a flash, a solid colour between two scenes) is left out
TEXTURE = 8.0           # gradient (0-255 grey per pixel) of a textured pixel
SAME = 3.0              # grey difference under which a pixel did not change
GROUND_FLAT = 0.45      # one ground colour holds at least this share: a flat ground
FLAT_SHARE = 0.6        # flat 4x4 blocks hold at least this share of the frame
PANEL_SHARE = 0.12      # flat areas that are not the ground: a text window or boxes
GAP_SHARE = 0.15        # an empty band this wide (share of the width) between two parts of the content
CENTRE_OFF = 0.12       # content centre within this distance of the frame centre (share of the width)

Runner = Callable[..., Any]


# ---------------------------------------------------------------- pixels


def gray(rgb: np.ndarray) -> np.ndarray:
    return rgb[..., :3].astype(np.float32) @ np.array([0.299, 0.587, 0.114], np.float32)


def warp(img: np.ndarray, s: float, dx: float = 0.0, dy: float = 0.0) -> np.ndarray:
    """``img`` zoomed by ``s`` around its centre and moved by (dx, dy) pixels (bilinear, edges repeated)."""
    h, w = img.shape
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    cx, cy = (w - 1) / 2, (h - 1) / 2
    sx = (xx - cx - dx) / s + cx
    sy = (yy - cy - dy) / s + cy
    x0 = np.clip(np.floor(sx).astype(int), 0, w - 2)
    y0 = np.clip(np.floor(sy).astype(int), 0, h - 2)
    fx = np.clip(sx - x0, 0, 1)
    fy = np.clip(sy - y0, 0, 1)
    top = img[y0, x0] * (1 - fx) + img[y0, x0 + 1] * fx
    bottom = img[y0 + 1, x0] * (1 - fx) + img[y0 + 1, x0 + 1] * fx
    return top * (1 - fy) + bottom * fy


def shift(a: np.ndarray, b: np.ndarray) -> tuple[float, float]:
    """The whole-pixel move that takes ``a`` onto ``b`` (phase correlation)."""
    fa, fb = np.fft.fft2(a - a.mean()), np.fft.fft2(b - b.mean())
    r = fb * np.conj(fa)
    r /= np.abs(r) + 1e-6
    c = np.fft.ifft2(r).real
    y, x = np.unravel_index(int(np.argmax(c)), c.shape)
    h, w = a.shape
    return float(x - w if x > w // 2 else x), float(y - h if y > h // 2 else y)


def _err(a: np.ndarray, b: np.ndarray) -> float:
    m = MARGIN
    return float(np.mean(np.abs(a[m:-m, m:-m] - b[m:-m, m:-m])))


def camera(a: np.ndarray, b: np.ndarray, dt: float) -> dict:
    """The camera between two grey frames ``dt`` seconds apart: the best global zoom and pan (rate = share of the
    frame per second), the share of textured pixels that did not change (``frozen``) and whether the pair moves."""
    best = (_err(a, b), 1.0, 0.0, 0.0)
    for s in SCALES:
        dx, dy = shift(warp(a, float(s)), b)
        if abs(dx) > a.shape[1] * 0.06 or abs(dy) > a.shape[0] * 0.06:
            dx, dy = 0.0, 0.0
        e = _err(warp(a, float(s), dx, dy), b)
        if e < best[0] - 1e-6:
            best = (e, float(s), dx, dy)
    e, s, dx, dy = best
    for s2 in np.linspace(s - 0.0025, s + 0.0025, 11):
        e2 = _err(warp(a, float(s2), dx, dy), b)
        if e2 < e - 1e-6:
            e, s = e2, float(s2)
    zoom = abs(float(np.log(s))) / dt
    pan = float(np.hypot(dx, dy)) / a.shape[1] / dt
    gy, gx = np.gradient(a)
    tex = np.hypot(gx, gy) > TEXTURE
    m = MARGIN
    tex[:m] = tex[-m:] = False
    tex[:, :m] = tex[:, -m:] = False
    textured = float(tex.mean())
    frozen = float((np.abs(a - b)[tex] < SAME).mean()) if tex.any() else 1.0
    rate = max(zoom, pan)
    moving = (rate >= CAM_MIN and frozen < FROZEN_MOVE) or frozen < FROZEN_ALIVE
    return {"rate": round(rate, 4), "zoom": round(zoom, 4), "pan": round(pan, 4), "frozen": round(frozen, 3),
            "textured": round(textured, 4), "moving": bool(moving), "counted": textured >= MIN_TEXTURE}


def layout(rgb: np.ndarray) -> dict:
    """What a still frame is made of: the ground colour's share, flat areas, flat panels that are not the ground,
    the widest empty gap between two parts of the content and how far the content sits from the centre."""
    f = rgb[..., :3].astype(np.int16)
    h, w = f.shape[:2]
    q = (f // 16).reshape(-1, 3)
    keys = q[:, 0] * 256 + q[:, 1] * 16 + q[:, 2]
    vals, cnt = np.unique(keys, return_counts=True)
    ground_key = vals[int(np.argmax(cnt))]
    ground = float(cnt.max() / keys.size)
    g = gray(rgb)
    b = 4
    hb, wb = h // b, w // b
    blocks = g[:hb * b, :wb * b].reshape(hb, b, wb, b).swapaxes(1, 2).reshape(hb, wb, -1)
    flat = (blocks.max(-1) - blocks.min(-1)) < 6
    kb = keys.reshape(h, w)[:hb * b, :wb * b].reshape(hb, b, wb, b).swapaxes(1, 2).reshape(hb, wb, -1)
    on_ground = (kb == ground_key).mean(-1) > 0.5
    panel = float((flat & ~on_ground).mean())
    content = keys.reshape(h, w) != ground_key
    band = content[int(h * 0.3):int(h * 0.7), int(w * 0.1):int(w * 0.9)]
    cols = band.mean(0) > 0.02
    gap, run, seen = 0, 0, False
    for v in cols:
        if v:
            if seen:
                gap = max(gap, run)
            seen, run = True, 0
        else:
            run += 1
    inner = content[int(h * 0.12):int(h * 0.88), int(w * 0.08):int(w * 0.92)]
    ys, xs = np.nonzero(inner)
    off = float(np.hypot(xs.mean() / inner.shape[1] - 0.5, (ys.mean() / inner.shape[0] - 0.5) * h / w)) \
        if xs.size else 0.0
    return {"ground": round(ground, 3), "flat": round(float(flat.mean()), 3), "panel": round(panel, 3),
            "gap": round(gap / max(1, band.shape[1]), 3), "centre_off": round(off, 3),
            "content": round(float(inner.mean()), 3)}


def flat_reasons(lay: dict) -> list[str]:
    """What makes a still frame read as a slide, in words (empty: the layout is not flat)."""
    out = []
    if lay["ground"] >= GROUND_FLAT:
        out.append(f"{lay['ground']:.0%} of the frame is one flat ground colour")
    elif lay["flat"] >= FLAT_SHARE:
        out.append(f"{lay['flat']:.0%} of the frame is flat")
    if lay["panel"] >= PANEL_SHARE:
        out.append(f"flat boxes or a text window cover {lay['panel']:.0%}")
    if lay["gap"] >= GAP_SHARE:
        out.append(f"an empty gap of {lay['gap']:.0%} of the width between two parts (icon far from its label)")
    if out and lay["centre_off"] <= CENTRE_OFF and lay["content"] < 0.5:
        out.append("one block in the middle of the frame")
    return out


# ---------------------------------------------------------------- one insert


def hold(start: float, end: float) -> tuple[float, float]:
    """The part of an insert between its entrance and its exit (the whole insert when it is short)."""
    a, b = start + LEAD_S, end - TAIL_S
    if b - a < MIN_HOLD_S:
        a, b = start + 0.15, end - 0.1
    return a, b


def judge(pairs: list[dict], lay: dict | None, kind: str = "2d", seconds: float = 0.0) -> dict:
    """The verdict from the camera pairs and the layout: ``slide``, ``still``, ``moves`` or ``short``. The hold moves
    when more than half of its samples move; samples without texture (a flash between two scenes) do not count."""
    flat = flat_reasons(lay) if lay else []
    pairs = [p for p in pairs if p.get("counted", True)]
    moving = sum(1 for p in pairs if p["moving"])
    if not pairs or seconds < MIN_HOLD_S - 1e-6:
        verdict = "short"
    elif moving / len(pairs) > MOVING_SHARE:
        verdict = "moves"
    else:
        verdict = "slide" if flat else "still"
    level = "OK"
    if verdict in ("slide", "still"):
        level = "CHECK" if kind == "clip" else "ERROR"
    return {"verdict": verdict, "level": level, "moving_pairs": moving, "pairs": len(pairs), "reasons": flat,
            "camera": round(float(max((p["rate"] for p in pairs), default=0.0)), 4),
            "frozen": round(float(np.median([p["frozen"] for p in pairs])) if pairs else 0.0, 3)}


def text(iid: str, r: dict, seconds: float) -> str:
    if r["verdict"] == "slide":
        return (f"{iid} reads as a slide: the camera stands still in {r['pairs'] - r['moving_pairs']} of "
                f"{r['pairs']} samples of its {seconds:.1f} s hold ({r['frozen']:.0%} of the picture frozen) and "
                + "; ".join(r["reasons"]))
    if r["verdict"] == "still":
        return (f"{iid}: the camera stands still in {r['pairs'] - r['moving_pairs']} of {r['pairs']} samples of its "
                f"{seconds:.1f} s hold ({r['frozen']:.0%} of the picture frozen)")
    if r["verdict"] == "moves":
        return f"{iid}: the camera moves ({r['moving_pairs']} of {r['pairs']} samples, up to {r['camera']:.1%}/s)"
    return f"{iid}: too short to judge the hold"


FIX = ("Build it as motion design: a shelf piece or a comp with a camera that drifts or pushes (1.5 to 3 % per "
       "second), layers in depth, symbol and label close together; a 2D window only as one element inside it")


# ---------------------------------------------------------------- frames from a video (ffmpeg)


def _run(argv: list[str], runner: Runner | None = None) -> bytes:
    if runner is not None:
        return runner(argv)
    return subprocess.run(argv, capture_output=True, timeout=120).stdout


def frames(video: str, t0: float, dur: float, fps: float, w: int, h: int, crop_top: float = 0.0,
           runner: Runner | None = None) -> list[np.ndarray]:
    """RGB frames from ``t0`` for ``dur`` seconds at ``fps`` (``crop_top``: share of the height left out at the top,
    for review reels that carry a label bar)."""
    vf = f"fps={fps},scale={w}:{h}"
    oh = h
    if crop_top:
        oh = int(round(h * (1 - crop_top)))
        vf += f",crop={w}:{oh}:0:{h - oh}"
    raw = _run(["ffmpeg", "-v", "error", "-ss", f"{max(0.0, t0):.3f}", "-t", f"{dur:.3f}", "-i", str(video),
                "-vf", vf, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], runner)
    n = len(raw) // (w * oh * 3)
    return [np.frombuffer(raw[k * w * oh * 3:(k + 1) * w * oh * 3], np.uint8).reshape(oh, w, 3) for k in range(n)]


def measure(video: str, start: float, end: float, kind: str = "2d", crop_top: float = 0.0,
            runner: Runner | None = None) -> dict:
    """The slide check of one insert of ``video`` that runs from ``start`` to ``end`` seconds."""
    a, b = hold(start, end)
    seconds = max(0.0, b - a)
    pairs: list[dict] = []
    lay = None
    if seconds >= MIN_HOLD_S - 1e-6:
        step = STEP_S if seconds >= STEP_S * 1.5 else seconds / 2
        n = min(MAX_PAIRS + 1, int(seconds / step) + 1)
        span = step * (n - 1)
        got = frames(video, a + (seconds - span) / 2, span + step / 2, 1 / step, CAM_W, CAM_H, crop_top, runner)
        g = [gray(f) for f in got]
        pairs = [camera(x, y, step) for x, y in zip(g, g[1:], strict=False)][:MAX_PAIRS]
        mid = frames(video, (a + b) / 2, 0.05, 30, LAYOUT_W, LAYOUT_H, crop_top, runner)
        lay = layout(mid[0]) if mid else None
    r = judge(pairs, lay, kind, seconds)
    r.update(hold_s=round(seconds, 2), layout=lay, samples=pairs)
    return r


def check(video: str, inserts: list[dict], crop_top: float = 0.0, runner: Runner | None = None) -> list[dict]:
    """Findings for every full-frame insert (``{"id", "kind", "start", "end", "full"}`` in seconds of the video):
    ``{"level", "id", "text", "time", "fix", "measured"}``. Overlays are left out."""
    out = []
    for i in inserts:
        if not i.get("full", True):
            continue
        r = measure(video, float(i["start"]), float(i["end"]), str(i.get("kind") or "2d"), crop_top, runner)
        seconds = r["hold_s"]
        out.append({"level": r["level"], "id": f"slide:{i['id']}", "text": text(str(i["id"]), r, seconds),
                    "time": float(i["start"]), "fix": FIX if r["level"] != "OK" else None,
                    "measured": {k: v for k, v in r.items() if k != "samples"}})
    return out
