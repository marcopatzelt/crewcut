"""Keyframes and easing: parsing ``t=value`` pairs and expanding ease presets into engine commands.

Ease presets are pairs ``(outInfluence of the earlier key, inInfluence of the later key)`` with speed 0 on both
sides, the way motion designers set them in the Keyframe Velocity dialog. ``expo`` (3/97) starts fast and lands
softly; ``strong`` (85/85) is a punchy S-curve; ``linear`` leaves the keys linear.
"""

from __future__ import annotations

import json
from itertools import pairwise
from typing import Any

EASES: dict[str, tuple[float, float] | None] = {
    "linear": None,
    "easy": (33.33, 33.33),
    "smooth": (60.0, 60.0),
    "strong": (85.0, 85.0),
    "out": (8.0, 92.0),
    "expo": (3.0, 97.0),
    "in": (92.0, 8.0),
    "expoIn": (97.0, 3.0),
    "soft": (40.0, 75.0),
    "snap": (1.0, 99.0),
}

EXPRESSION_PRESETS: dict[str, str] = {
    "wiggle": "wiggle({freq}, {amp})",
    "loop": "loopOut('{mode}')",
    "spring": (
        "var amp={amp},freq={freq},decay={decay};var n=0;if(numKeys>0){{n=nearestKey(time).index;if(key(n).time>time)n--;}}"
        "if(n>0){{var t=time-key(n).time;var v=velocityAtTime(key(n).time-thisComp.frameDuration/10);"
        "value+v*amp*Math.sin(freq*t*2*Math.PI)/Math.exp(decay*t);}}else value"
    ),
    "time": "value + time*{rate}",
}
EXPRESSION_DEFAULTS: dict[str, dict[str, Any]] = {
    "wiggle": {"freq": 2, "amp": 20},
    "loop": {"mode": "cycle"},
    "spring": {"amp": 0.05, "freq": 2.5, "decay": 6},
    "time": {"rate": 90},
}


class KeyError_(ValueError):
    """A key or ease could not be parsed."""


def parse_value(text: str) -> Any:
    """``960,540`` -> [960, 540]; ``[1,2,3]`` / ``50`` / ``"x"`` JSON; anything else stays a string."""
    t = text.strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass
    if "," in t:
        try:
            return [float(x) if "." in x or "e" in x.lower() else int(x) for x in t.split(",")]
        except ValueError:
            pass
    return t


def parse_keys(items: list[str]) -> list[tuple[float, Any]]:
    """``["0=0", "0.5=100", "1.2=960,540"]`` -> sorted [(time, value)], times unique."""
    keys: list[tuple[float, Any]] = []
    for it in items:
        if "=" not in it:
            raise KeyError_(f"key {it!r}: expected TIME=VALUE, e.g. 0.5=100 or 1=960,540")
        t, v = it.split("=", 1)
        try:
            tt = float(t)
        except ValueError as e:
            raise KeyError_(f"key {it!r}: time {t!r} is not a number") from e
        if tt < 0:
            raise KeyError_(f"key {it!r}: negative time")
        keys.append((tt, parse_value(v)))
    keys.sort(key=lambda k: k[0])
    for a, b in pairwise(keys):
        if abs(a[0] - b[0]) < 1e-9:
            raise KeyError_(f"two keys at {a[0]} s")
    return keys


def resolve_ease(ease: str | None, influence: tuple[float, float] | None = None) -> tuple[float, float] | None:
    """A preset name or explicit (out, in) influences -> influences, or None for linear."""
    if influence is not None:
        o, i = influence
        if not (0.1 <= o <= 100 and 0.1 <= i <= 100):
            raise KeyError_("influence must be within 0.1..100 %")
        return (float(o), float(i))
    if ease is None:
        return EASES["smooth"]
    if ease not in EASES:
        raise KeyError_(f"unknown ease {ease!r}; one of: {', '.join(EASES)}")
    return EASES[ease]


def key_steps(comp: str, layer: Any, path: str, keys: list[tuple[float, Any]],
              ease: tuple[float, float] | None, start: float = 0.0) -> list[dict]:
    """Engine command steps that add the keys (comp seconds) and ease every segment. ``keys.setEase`` takes
    layer time, so ``start`` (the layer's start time) is subtracted there."""
    steps: list[dict] = []
    for t, v in keys:
        steps.append({"command": "prop.addKey", "params": {"comp": comp, "layer": layer, "path": path,
                                                           "time": t, "value": v, "timeBase": "comp"}})
    if ease:
        for (t0, _), (t1, _) in pairwise(keys):
            steps.append({"command": "keys.setEase", "params": {"comp": comp, "layer": layer, "path": path, "time": t0 - start,
                                                                "side": "out", "speed": 0, "influence": ease[0]}})
            steps.append({"command": "keys.setEase", "params": {"comp": comp, "layer": layer, "path": path, "time": t1 - start,
                                                                "side": "in", "speed": 0, "influence": ease[1]}})
    return steps


def expression(preset: str, **params: Any) -> str:
    """Expression source for a preset (``wiggle``, ``loop``, ``spring``, ``time``) with parameters."""
    if preset not in EXPRESSION_PRESETS:
        raise KeyError_(f"unknown expression preset {preset!r}; one of: {', '.join(EXPRESSION_PRESETS)}")
    p = dict(EXPRESSION_DEFAULTS[preset])
    p.update({k: v for k, v in params.items() if v is not None})
    return EXPRESSION_PRESETS[preset].format(**p)


def key_program(comp: str, layer: Any, path: str, keys: list[tuple[float, Any]], ease: tuple[float, float] | None,
                spring: bool = False) -> str:
    """Script body for ``key set``: EC.keys converts comp time to layer time itself (layers moved in time too)."""
    from .jsx import js
    pairs = [[t, v] for t, v in keys]
    body = f"EC.keys({js(comp)}, {js(layer)}, {js(path)}, {js(pairs)}, {js(list(ease) if ease else 'linear')});\n"
    if spring:
        body += f"EC.expr({js(comp)}, {js(layer)}, {js(path)}, {js(expression('spring'))});\n"
    return body + f"return {{keys: {len(pairs)}}};"
