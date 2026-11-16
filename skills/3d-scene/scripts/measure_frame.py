#!/usr/bin/env python3
"""Measure a rendered 3D frame against the 3D values of the style pack (brand.json, stage3d).

  python3 skills/3d-scene/scripts/measure_frame.py FRAME.png [FRAME2.png …] [--pack DIR] [--json]

Measures: background colour and brightness (top band), floor brightness (bottom band), accent share and the median
accent colour, the share of dark pixels outside the accent, and the shadow depth on the floor (how much darker the
darkest 5 % are than the brightest 10 %). Compares them with stage3d.background, stage3d.accent and
stage3d.checks in the pack. Prints CHECK where a value is outside the pack range and OK where it is inside.
A frame that passes here can still look wrong: always put it next to the reference and judge it.
Needs numpy and Pillow. Exit 0 = all inside, 1 = at least one CHECK, 2 = usage.
"""

from __future__ import annotations

import argparse
import colorsys
import json
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image

APP_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CHECKS = {
    "background_tolerance": 0.06,
    "accent_share": [0.01, 0.30],
    "accent_distance": 40,
    "shadow_depth": [0.08, 0.40],
    "dark_share_max": 0.10,
}


def load_pack(pack_dir=None):
    try:
        from crewcut import brand
    except ImportError:
        sys.path.insert(0, str(APP_ROOT))
        from crewcut import brand
    return brand.load(pack_dir) if pack_dir else brand.load()


def hex_rgb(v: str) -> tuple[int, int, int]:
    v = v.lstrip("#")
    return int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16)


def hexa(c) -> str:
    r, g, b = (int(round(x)) for x in c)
    return f"#{r:02X}{g:02X}{b:02X}"


def luma(c) -> float:
    return (0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]) / 255


def accent_mask(im: np.ndarray, accent: tuple[int, int, int], hue_tol: float = 15.0) -> np.ndarray:
    """Pixels with the accent hue and clear saturation (shaded accent surfaces count too)."""
    ah, als, ass = colorsys.rgb_to_hls(*(x / 255 for x in accent))
    if ass < 0.2:  # a grey accent has no hue: fall back to colour distance
        return np.linalg.norm(im - np.array(accent, float), axis=-1) < 40
    mx, mn = im.max(-1), im.min(-1)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0)
    r, g, b = im[..., 0], im[..., 1], im[..., 2]
    d = np.maximum(mx - mn, 1e-6)
    h = np.where(mx == r, ((g - b) / d) % 6, np.where(mx == g, (b - r) / d + 2, (r - g) / d + 4)) * 60
    diff = np.abs(h - ah * 360)
    diff = np.minimum(diff, 360 - diff)
    return (diff <= hue_tol) & (sat >= 0.35) & (mx >= 40)


def measure(im: np.ndarray, accent: tuple[int, int, int]) -> dict:
    """Values of one RGB frame (float array h x w x 3)."""
    h, w, _ = im.shape
    acc = accent_mask(im, accent)
    grey = ~acc & ((im.max(-1) - im.min(-1)) < 25)
    lum = (0.2126 * im[..., 0] + 0.7152 * im[..., 1] + 0.0722 * im[..., 2]) / 255

    def med(y0, y1, x0, x1):
        m = grey[int(y0 * h) : int(y1 * h), int(x0 * w) : int(x1 * w)]
        p = im[int(y0 * h) : int(y1 * h), int(x0 * w) : int(x1 * w)][m]
        return np.median(p, axis=0) if len(p) else np.array([0.0, 0.0, 0.0])

    bg, floor = med(0.03, 0.2, 0.2, 0.8), med(0.88, 0.98, 0.3, 0.7)
    fl, gm = lum[int(0.55 * h) : int(0.95 * h)], grey[int(0.55 * h) : int(0.95 * h)]
    shadow = None
    if gm.any():
        v = fl[gm]
        hi = np.percentile(v, 90)
        shadow = float(1 - np.percentile(v, 5) / hi) if hi > 0 else None
    return {
        "background": hexa(bg),
        "background_luma": luma(bg),
        "background_cast": float(bg[0] - bg[2]),
        "floor_luma": luma(floor),
        "accent_share": float(acc.mean()),
        "accent_color": hexa(np.median(im[acc], axis=0)) if acc.any() else None,
        "dark_share": float(((lum < 0.45) & ~acc).mean()),
        "shadow_depth": shadow,
    }


def verdict(m: dict, background: str | None, accent: str | None, checks: dict) -> list[tuple[str, str]]:
    c = {**DEFAULT_CHECKS, **(checks or {})}
    out = []
    if background:
        want = luma(hex_rgb(background))
        ok = abs(m["background_luma"] - want) <= c["background_tolerance"]
        out.append(
            (
                "OK" if ok else "CHECK",
                f"Background {m['background']} brightness {m['background_luma']:.2f} "
                f"(pack {background} = {want:.2f} ± {c['background_tolerance']}), colour cast R-B {m['background_cast']:+.0f}",
            )
        )
    lo, hi = c["accent_share"]
    out.append(
        (
            "OK" if lo <= m["accent_share"] <= hi else "CHECK",
            f"Accent share {m['accent_share']:.1%} (pack {lo:.0%} to {hi:.0%})",
        )
    )
    if accent and m["accent_color"]:
        d = float(np.linalg.norm(np.array(hex_rgb(m["accent_color"])) - np.array(hex_rgb(accent))))
        out.append(
            (
                "OK" if d <= c["accent_distance"] else "CHECK",
                f"Accent in the frame {m['accent_color']} is {d:.0f} from the pack accent {accent} "
                f"(at most {c['accent_distance']}; a pale accent often means the wrong colour management)",
            )
        )
    out.append(
        (
            "OK" if m["dark_share"] <= c["dark_share_max"] else "CHECK",
            f"Dark pixels outside the accent {m['dark_share']:.1%} (at most {c['dark_share_max']:.0%})",
        )
    )
    if m["shadow_depth"] is not None:
        lo, hi = c["shadow_depth"]
        out.append(
            (
                "OK" if lo <= m["shadow_depth"] <= hi else "CHECK",
                f"Shadow on the floor {m['shadow_depth']:.0%} darker than the lit floor (pack {lo:.0%} to {hi:.0%})",
            )
        )
    out.append(("NOTE", f"Floor brightness {m['floor_luma']:.2f}"))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="Measure rendered 3D frames against the style pack.")
    ap.add_argument("frames", nargs="+")
    ap.add_argument("--pack", help="style pack folder (default: studio/brand, else packs/neutral)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    pack = load_pack(a.pack)
    st = pack.value("brand.stage3d", {}) or {}
    accent = st.get("accent") or pack.value("brand.colors.accent")
    background = st.get("background")
    valid = lambda v: isinstance(v, str) and re.fullmatch(r"#[0-9A-Fa-f]{6}", v)  # noqa: E731
    accent, background = (accent if valid(accent) else None), (background if valid(background) else None)
    bad, results = 0, []
    for f in a.frames:
        im = np.asarray(Image.open(f).convert("RGB")).astype(float)
        m = measure(im, hex_rgb(accent) if accent else (228, 87, 46))
        v = verdict(m, background, accent, st.get("checks") or {})
        bad += sum(1 for lvl, _ in v if lvl == "CHECK")
        results.append({"frame": f, "values": m, "findings": v})
        if not a.json:
            print(f"\n{f}")
            for lvl, t in v:
                print(f"  {lvl:<6} {t}")
    if a.json:
        print(json.dumps(results, indent=1))
    else:
        print(f"\n{len(a.frames)} frame(s), {bad} CHECK. Then: put the frame next to the reference and judge it.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
