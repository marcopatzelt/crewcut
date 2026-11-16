"""Measure a rendered still against the style pack: background colour and brightness, accent share, dark share.

Used after a 3D probe. The targets come from the pack (brand.json stage3d), never from code. A value without a
target in the pack is reported, not judged.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from .. import brand


def hex_rgb(h: str) -> np.ndarray:
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], dtype=float)


def rgb_hex(c) -> str:
    r, g, b = (int(round(float(x))) for x in c)
    return f"#{r:02X}{g:02X}{b:02X}"


def luminance(c) -> float:
    """Relative brightness 0..1 (Rec. 709 weights on 0..255 values)."""
    return float((0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]) / 255)


def _hsv(im: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    x = im / 255.0
    mx, mn = x.max(axis=-1), x.min(axis=-1)
    d = mx - mn
    r, g, b = x[..., 0], x[..., 1], x[..., 2]
    hue = np.zeros_like(mx)
    nz = d > 1e-6
    rm = nz & (mx == r)
    gm = nz & (mx == g) & ~rm
    bm = nz & ~rm & ~gm
    hue[rm] = ((g - b)[rm] / d[rm]) % 6
    hue[gm] = (b - r)[gm] / d[gm] + 2
    hue[bm] = (r - g)[bm] / d[bm] + 4
    sat = np.where(mx > 1e-6, d / np.maximum(mx, 1e-6), 0)
    return hue * 60, sat, mx


def accent_mask(im: np.ndarray, accent: str, hue_tol: float = 18.0, min_sat: float = 0.35) -> np.ndarray:
    """Pixels of the accent colour, also where light and shadow make it brighter or darker (same hue, saturated)."""
    h, s, v = _hsv(im)
    ah, as_, _ = _hsv(hex_rgb(accent)[None, None, :])
    dh = np.abs(h - ah[0, 0])
    dh = np.minimum(dh, 360 - dh)
    return (dh < hue_tol) & (s >= min(min_sat, float(as_[0, 0]) * 0.6)) & (v > 0.15)


def _band(im: np.ndarray, keep: np.ndarray, y0: float, y1: float, x0: float, x1: float) -> np.ndarray | None:
    hh, ww = im.shape[:2]
    sl = (slice(int(y0 * hh), max(int(y0 * hh) + 1, int(y1 * hh))), slice(int(x0 * ww), max(int(x0 * ww) + 1, int(x1 * ww))))
    px = im[sl][keep[sl]]
    return np.median(px, axis=0) if len(px) else None


def measure(path: Path | str, pack: brand.Pack | None = None) -> dict:
    pack = pack or brand.load()
    stage = pack.value("brand.stage3d", {}) or {}
    accent = stage.get("accent") or pack.value("brand.colors.accent", "#E4572E")
    bg_target = stage.get("background") or pack.value("brand.colors.paper", "#FFFFFF")
    im = np.asarray(Image.open(path).convert("RGB")).astype(float)
    hh, ww = im.shape[:2]
    acc = accent_mask(im, accent)
    rest = ~acc
    bg = _band(im, rest, 0.03, 0.2, 0.2, 0.8)
    floor = _band(im, rest, 0.88, 0.98, 0.3, 0.7)
    lum = (0.2126 * im[..., 0] + 0.7152 * im[..., 1] + 0.0722 * im[..., 2]) / 255
    target_l = luminance(hex_rgb(bg_target))
    tol = float(stage.get("background_tolerance", 0.06))
    checks = []
    if bg is not None:
        bl = luminance(bg)
        checks.append({"name": "background brightness", "value": round(bl, 3),
                       "target": [round(target_l - tol, 3), round(target_l + tol, 3)], "ok": abs(bl - target_l) <= tol})
        tint = float(np.abs(bg - hex_rgb(bg_target)).max())
        checks.append({"name": "background colour distance", "value": round(tint, 1), "target": [0, 24], "ok": tint <= 24})
    share = 100 * float(acc.mean())
    rng = stage.get("accent_share")
    checks.append({"name": "accent share %", "value": round(share, 1),
                   "target": rng if isinstance(rng, list) and len(rng) == 2 else None,
                   "ok": (rng[0] <= share <= rng[1]) if isinstance(rng, list) and len(rng) == 2 else None})
    return {
        "image": str(path), "size": [ww, hh],
        "background": rgb_hex(bg) if bg is not None else None,
        "background_target": "#" + bg_target.lstrip("#").upper(),
        "floor": rgb_hex(floor) if floor is not None else None,
        "accent": rgb_hex(np.median(im[acc], axis=0)) if acc.any() else None,
        "accent_target": "#" + accent.lstrip("#").upper(),
        "accent_share": round(share, 1),
        "dark_share": round(100 * float(((lum < 0.25) & rest).mean()), 1),
        "checks": checks,
    }


def lines(m: dict) -> list[str]:
    """Plain text for the terminal."""
    out = [f"{Path(m['image']).name}: background {m['background']} (pack {m['background_target']}), "
           f"accent {m['accent']} (pack {m['accent_target']}) {m['accent_share']} %, dark {m['dark_share']} %"]
    for c in m["checks"]:
        state = "no target in the pack" if c["ok"] is None else ("ok" if c["ok"] else "OUTSIDE")
        tgt = "" if c["target"] is None else f" (target {c['target'][0]} to {c['target'][1]})"
        out.append(f"  {c['name']}: {c['value']}{tgt} {state}")
    return out
