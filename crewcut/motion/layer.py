"""Layers: engine parameters for each kind (solid, text, shape, footage, null, camera, light) and the
common options every kind takes (3D, motion blur, in/out, blend, transform). Built as a small script so the
new layer's id flows into the follow-up commands inside one EffectCraft process."""

from __future__ import annotations

from typing import Any

from .jsx import js

KINDS = ("solid", "text", "shape", "footage", "null", "camera", "light", "precomp")
SWITCHES = ("video", "audio", "solo", "lock", "shy", "collapse", "quality", "fx", "frameBlend", "motionBlur",
            "adjustment", "threeD", "guide", "preserveTransparency")
SHAPES = ("rect", "rounded", "ellipse", "star", "polygon", "none")
LIGHTS = ("Parallel", "Spot", "Point", "Ambient", "Environment")
BLEND_MODES = ("Normal", "Dissolve", "Darken", "Multiply", "Color Burn", "Linear Burn", "Darker Color", "Add",
               "Lighten", "Screen", "Color Dodge", "Linear Dodge", "Lighter Color", "Overlay", "Soft Light",
               "Hard Light", "Linear Light", "Vivid Light", "Pin Light", "Hard Mix", "Difference", "Exclusion",
               "Subtract", "Divide", "Hue", "Saturation", "Color", "Luminosity")


def options(layer_kind: str, **o: Any) -> dict[str, Any]:
    """Validated options for ``EC.<kind>(comp, options)`` in ec_lib.jsx. Unknown kinds or values raise."""
    kind = layer_kind
    if kind not in KINDS:
        raise ValueError(f"unknown layer kind {kind!r}; one of: {', '.join(KINDS)}")
    out = {k: v for k, v in o.items() if v is not None}
    if kind == "text" and not out.get("text"):
        raise ValueError("text layer needs --text")
    if kind == "shape" and out.get("kind", "rect") not in SHAPES:
        raise ValueError(f"shape kind must be one of {', '.join(SHAPES)}")
    if kind == "light" and out.get("kind", "Point") not in LIGHTS:
        raise ValueError(f"light kind must be one of {', '.join(LIGHTS)}")
    if kind == "footage" and not out.get("path"):
        raise ValueError("footage layer needs --path")
    if kind == "precomp" and not out.get("source"):
        raise ValueError("precomp layer needs --source COMP")
    if "blend" in out and out["blend"] not in BLEND_MODES:
        raise ValueError(f"blend mode must be one of {', '.join(BLEND_MODES)}")
    return out


def add_program(comp: str, kind: str, opts: dict[str, Any]) -> str:
    """Script body that adds one layer and returns {layer, name, kind}."""
    c = js(comp)
    if kind == "null":
        call = f"EC.nul({c}, {js(opts)})"
    elif kind == "footage":
        o = dict(opts)
        path = o.pop("path")
        call = f"EC.footage({c}, {js(path)}, {js(o)})"
    elif kind == "precomp":
        o = dict(opts)
        src = o.pop("source")
        call = f"EC.precompLayer({c}, {js(src)}, {js(o)})"
    else:
        call = f"EC.{kind}({c}, {js(opts)})"
    return f"var id = {call};\nreturn {{layer: id, kind: {js(kind)}, name: {js(opts.get('name'))}}};"


def switch_steps(comp: str, layer: Any, switch: str, value: bool) -> list[dict]:
    if switch not in SWITCHES:
        raise ValueError(f"unknown switch {switch!r}; one of: {', '.join(SWITCHES)}")
    return [{"command": "layer.setSwitch", "params": {"comp": comp, "layers": [layer], "switch": switch, "value": value}}]


def timing_steps(comp: str, layer: Any, in_point: float | None, out_point: float | None) -> list[dict]:
    p: dict[str, Any] = {"comp": comp, "layers": [layer]}
    if in_point is not None:
        p["in"] = float(in_point)
    if out_point is not None:
        p["out"] = float(out_point)
    if len(p) == 2:
        raise ValueError("give --in and/or --out")
    if in_point is not None and out_point is not None and out_point <= in_point:
        raise ValueError("out must be after in")
    return [{"command": "layer.timing", "params": p}]
