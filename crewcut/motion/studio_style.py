"""The studio's graphic style for ready-made building blocks: HyperFrames templates, imported Lottie and After Effects
templates, Blender scenes with library assets. One palette of four roles, one font family in two weights, 25 frames
per second and one entrance curve, so a block from any library looks like the channel and not like its source.

Where the values come from (the first one found wins, all from the active style pack):

- palette: ``channel.json`` ``graphics.palette`` (the channel's graphic system: ``ink``, ``paper``, ``accent``,
  ``highlight``; ``cream`` is accepted for ``paper``), then ``brand.json`` ``graphics.palette``, then ``brand.json``
  ``colors`` (``ink``, ``paper``, ``accent``; ``highlight`` falls back to the accent).
- fonts: ``brand.json`` ``fonts.display`` (the word, the number) and ``fonts.body`` (side lines): family, weight and
  the font files of the pack.
- motion: ``channel.json`` ``graphics.motion`` (``enter_s``, ``exit_s``, ``stagger_s``, ``ease``, ``out_ease``), then
  ``edit-style.json`` ``graphics.motion.out_bezier``, else the defaults below (in 0.4 s on the curve "emphasized"
  ``cubic-bezier(0.2, 0, 0, 1)``, out 0.28 s on ``cubic-bezier(0.3, 0, 0.8, 0.15)``, 2 frames between elements);
  ``push_px`` is the way an overlay slides in from the speaker's side (28 px), ``drift`` the slow push of a hold
  (``brand.json`` ``motion_graphics.drift_pct_per_s``; 0 keeps 2D still).
- safe areas: ``edit-style.json`` ``graphics.safe_area`` in pixels per format (``left``, ``right``, ``top``,
  ``bottom``), else the shares in ``SAFE``.
- fps: ``edit-style.json`` ``fps`` (25).

Nothing here renders. ``crewcut motion style`` prints the resolved values.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .. import brand

ROLES = ("ink", "paper", "accent", "highlight")
ALIASES = {"cream": "paper", "creme": "paper", "ground": "paper", "text": "ink"}
MOTION = {"enter_s": 0.4, "exit_s": 0.28, "stagger_s": 0.08, "ease": [0.2, 0.0, 0.0, 1.0],
          "out_ease": [0.3, 0.0, 0.8, 0.15], "push_px": 28}
CURVES = {"emphasized": [0.2, 0.0, 0.0, 1.0], "emphasized_out": [0.3, 0.0, 0.8, 0.15]}   # named curves
SAFE = {  # fractions of the frame kept free (crewcut CC.frame: 16:9 5 % around and 8 % at the bottom for overlays)
    "landscape": {"left": 0.05, "right": 0.05, "top": 0.05, "bottom": 0.08},
    "portrait": {"left": 0.06, "right": 0.18, "top": 0.10, "bottom": 0.20},
}
_HEX = re.compile(r"^#?[0-9A-Fa-f]{6}$")


def _hex(v: Any) -> str | None:
    return ("#" + v.lstrip("#").upper()) if isinstance(v, str) and _HEX.match(v) else None


def _palette_block(pack: brand.Pack) -> tuple[dict, str]:
    for dotted in ("channel.graphics.palette", "brand.graphics.palette"):
        v = pack.value(dotted)
        if isinstance(v, dict) and v:
            return v, dotted.replace(".", " ", 1)
    return {}, ""


def palette(pack: brand.Pack | None = None) -> dict[str, str]:
    """The four colours as #RRGGBB: ink (type, dark ground), paper (light ground), accent (the brand), highlight."""
    pack = pack or brand.load()
    block, _ = _palette_block(pack)
    given = {ALIASES.get(str(k).lower(), str(k).lower()): _hex(v) for k, v in block.items()}
    colors = pack.value("brand.colors", {}) or {}
    mg = pack.motion_graphics()
    out = {
        "ink": given.get("ink") or _hex(colors.get("ink")) or _hex(mg.get("ink")) or "#111111",
        "paper": given.get("paper") or _hex(colors.get("paper")) or _hex(colors.get("cream")) or "#FFFFFF",
        "accent": given.get("accent") or _hex(colors.get("accent")) or "#E4572E",
    }
    out["highlight"] = given.get("highlight") or out["accent"]
    return out


def source(pack: brand.Pack | None = None) -> str:
    """Where the palette came from, for reports: "channel graphics.palette", "brand graphics.palette" or "brand colors"."""
    pack = pack or brand.load()
    return _palette_block(pack)[1] or "brand colors"


def fonts(pack: brand.Pack | None = None) -> dict[str, dict]:
    """``{"display": {family, weight, files: [Path]}, "body": {...}}`` from the pack (files only when they exist)."""
    pack = pack or brand.load()
    out = {}
    for role, weight in (("display", 800), ("body", 500)):
        spec = (pack.value("brand.fonts", {}) or {}).get(role) or {}
        files = [p for p in (pack.file(f) for f in spec.get("files") or []) if p]
        out[role] = {"family": str(spec.get("family") or "Inter"), "weight": int(spec.get("weight") or weight),
                     "files": [Path(p) for p in files]}
    return out


def _curve(v: Any) -> list[float] | None:
    if isinstance(v, str) and v in CURVES:
        return list(CURVES[v])
    if isinstance(v, list) and len(v) == 4 and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in v):
        return [float(x) for x in v]
    return None


def motion(pack: brand.Pack | None = None) -> dict:
    pack = pack or brand.load()
    got = pack.value("channel.graphics.motion", {}) or {}
    out = dict(MOTION)
    for k in ("enter_s", "exit_s", "stagger_s"):
        v = got.get(k)
        if isinstance(v, (int, float)) and not isinstance(v, bool) and 0 < v < 5:
            out[k] = float(v)
    out["ease"] = _curve(got.get("ease")) or out["ease"]
    out["out_ease"] = (_curve(got.get("out_ease")) or _curve(pack.value("edit_style.graphics.motion.out_bezier"))
                       or out["out_ease"])
    push = got.get("push_px")
    if isinstance(push, (int, float)) and not isinstance(push, bool) and 0 <= push <= 200:
        out["push_px"] = float(push)
    drift = pack.motion_graphics().get("drift_pct_per_s")
    out["drift_pct_per_s"] = float(drift) if isinstance(drift, (int, float)) and not isinstance(drift, bool) else 0.0
    return out


def safe_area(pack: brand.Pack | None = None) -> dict[str, dict[str, float]]:
    """Kept-free margins as shares of the frame per format: the pack's pixels (``graphics.safe_area``) when given."""
    pack = pack or brand.load()
    out = {k: dict(v) for k, v in SAFE.items()}
    given = pack.value("edit_style.graphics.safe_area", {}) or {}
    for fmt, (w, h) in (("landscape", (1920, 1080)), ("portrait", (1080, 1920))):
        px = given.get(fmt) if isinstance(given, dict) else None
        if not isinstance(px, dict):
            continue
        for side, full in (("left", w), ("right", w), ("top", h), ("bottom", h)):
            v = px.get(side)
            if isinstance(v, (int, float)) and not isinstance(v, bool) and 0 <= v < full / 2:
                out[fmt][side] = round(v / full, 4)
    return out


def fps(pack: brand.Pack | None = None) -> int:
    pack = pack or brand.load()
    try:
        return int(pack.value("edit_style.fps", 25) or 25)
    except (TypeError, ValueError):
        return 25


def resolve(pack: brand.Pack | None = None) -> dict:
    """Everything at once (JSON-ready): palette, its source, fonts (file paths as text), motion, fps, safe areas and
    the smallest text size."""
    pack = pack or brand.load()
    f = fonts(pack)
    return {"palette": palette(pack), "palette_source": source(pack),
            "fonts": {r: {**v, "files": [str(p) for p in v["files"]]} for r, v in f.items()},
            "motion": motion(pack), "fps": fps(pack), "safe": safe_area(pack),
            "min_text_px": int(pack.value("edit_style.min_text_px", 40) or 40)}


# ---- colour roles for imported files ------------------------------------------------------------------------------
def role_of(color: str, surface: bool = False, text: bool = False, on_dark: bool = False) -> str:
    """The palette role an imported colour takes, in the channel's grammar: the colour that paints the most area (the
    surface) becomes paper when light and ink when dark; another saturated colour becomes the accent (lines, edges,
    small shapes), or the highlight when it is text on a dark surface (the highlight is never a surface and never type
    on paper); a grey goes to ink (dark) or paper (light)."""
    L, C, _ = brand.hex_to_oklch(color)
    if surface:
        return "paper" if L >= 0.6 else "ink"
    if C < 0.045:
        return "paper" if L >= 0.62 else "ink"
    return "highlight" if text and on_dark else "accent"


def css(pack: brand.Pack | None = None, font_urls: dict[str, str] | None = None) -> str:
    """The theme as CSS custom properties for HTML building blocks (HyperFrames), with @font-face rules for the pack's
    font files at the given relative URLs (``{"display": "assets/fonts/x.otf", ...}``)."""
    pack = pack or brand.load()
    p, f, m = palette(pack), fonts(pack), motion(pack)
    ease = "cubic-bezier({})".format(", ".join(f"{x:g}" for x in m["ease"]))
    ease_out = "cubic-bezier({})".format(", ".join(f"{x:g}" for x in m["out_ease"]))
    lines = []
    for role in ("display", "body"):
        url = (font_urls or {}).get(role)
        if url:
            lines.append(f'@font-face {{ font-family: "{f[role]["family"]}"; font-weight: {f[role]["weight"]}; '
                         f'font-style: normal; src: url("{url}"); }}')
    lines.append(":root {")
    for role in ROLES:
        lines.append(f"  --cc-{role}: {p[role]};")
    lines += [f'  --cc-font-display: "{f["display"]["family"]}", "Inter", system-ui, sans-serif;',
              f'  --cc-font-body: "{f["body"]["family"]}", "Inter", system-ui, sans-serif;',
              f"  --cc-weight-display: {f['display']['weight']};",
              f"  --cc-weight-body: {f['body']['weight']};",
              f"  --cc-ease: {ease};",
              f"  --cc-ease-out: {ease_out};",
              f"  --cc-enter-s: {m['enter_s']:g}s;",
              f"  --cc-exit-s: {m['exit_s']:g}s;",
              "}"]
    return "\n".join(lines) + "\n"
