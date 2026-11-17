"""Text animators (per-character animation with range selectors): typewriter reveals, colour waves,
tracking-in. Built from engine commands ``layer.addTextAnimator`` / ``layer.addTextSelector`` + keys."""

from __future__ import annotations

from typing import Any

from .jsx import js

ANIMATOR_PROPERTIES = ("anchor", "position", "scale", "skew", "rotation", "opacity", "transformAll", "lineAnchor",
                       "lineSpacing", "characterOffset", "characterValue", "blur", "fillColor", "fillHue",
                       "fillSaturation", "fillBrightness", "fillOpacity", "strokeColor", "strokeHue",
                       "strokeSaturation", "strokeBrightness", "strokeOpacity", "strokeWidth", "tracking", "perChar3d")


def animator_program(comp: str, layer: Any, props: list[str], values: dict[str, Any] | None = None,
                     range_keys: dict[str, list] | None = None, name: str | None = None, ease: Any = "linear") -> str:
    """Script body: add an animator with ``props`` (set to ``values``) and key its range selector
    (``range_keys`` e.g. {"start": [[0,0],[1,100]]}). Returns the animator path."""
    bad = [p for p in props if p not in ANIMATOR_PROPERTIES]
    if bad:
        raise ValueError(f"unknown animator properties {bad}; one of: {', '.join(ANIMATOR_PROPERTIES)}")
    if not props:
        raise ValueError("an animator needs at least one property")
    return f"""var r = EC.animator({js(comp)}, {js(layer)}, {js(props)}, {js(name)});
var base = r.path;
var vals = {js(values or {})};
for (var k in vals) EC.set({js(comp)}, {js(layer)}, base + "/properties/" + k, vals[k]);
var rk = {js(range_keys or {})};
for (var k2 in rk) EC.keys({js(comp)}, {js(layer)}, base + "/selectors/#1/" + k2, rk[k2], {js(ease)});
return {{animator: base, reply: r}};"""
