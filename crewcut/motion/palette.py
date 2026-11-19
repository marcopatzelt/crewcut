"""Colour check for frames: how much of the coloured area is one hue. A frame where one hue holds more than
about 30 % of the coloured pixels reads as "everything one colour" and needs rework."""

from __future__ import annotations

from typing import Any


def hue_report(path: str, limit: float = 0.30, bins: int = 12, min_sat: float = 0.25, min_val: float = 0.15,
               accent_area_limit: float = 0.0) -> dict[str, Any]:
    """Hue histogram of coloured pixels (saturation >= min_sat, value >= min_val) in ``bins`` sectors.
    Neighbouring sectors are not merged; the dominant sector's share is compared with ``limit``."""
    from PIL import Image
    im = Image.open(path).convert("RGB")
    im.thumbnail((480, 480))
    hsv = im.convert("HSV")
    counts = [0] * bins
    coloured = 0
    total = 0
    raw = hsv.tobytes()
    for j in range(0, len(raw), 3):
        h, s, v = raw[j], raw[j + 1], raw[j + 2]
        total += 1
        if s >= min_sat * 255 and v >= min_val * 255:
            coloured += 1
            counts[min(bins - 1, h * bins // 256)] += 1
    if coloured == 0:
        return {"image": path, "coloured_share": 0.0, "dominant_hue": None, "dominant_share": 0.0, "ok": True,
                "hues": [], "note": "no coloured pixels (neutral frame)"}
    i = max(range(bins), key=lambda k: counts[k])
    share = counts[i] / coloured
    sparse_accent = coloured / total <= accent_area_limit
    return {"image": path, "coloured_share": round(coloured / total, 3), "dominant_hue": round((i + 0.5) * 360 / bins),
            "dominant_share": round(share, 3), "ok": share <= limit or sparse_accent,
            "accent_area_limit": accent_area_limit, "sparse_accent": sparse_accent,
            "hues": [{"hue": round((k + 0.5) * 360 / bins), "share": round(c / coloured, 3)} for k, c in enumerate(counts) if c]}
