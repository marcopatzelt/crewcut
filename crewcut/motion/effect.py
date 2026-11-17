"""Effects: apply by name or id (``ec.stylize.glow`` / ``Glow``) and set or key parameters by their ids
(``effect params NAME`` lists them, e.g. ``radius``, ``physics/gravity``)."""

from __future__ import annotations

from typing import Any

from .jsx import js

# Effects the motion templates rely on; the full catalog (308) comes from the engine (`effect list`).
FAVOURITES = {
    "glow": "Glow", "shatter": "Shatter", "particles3d": "Particle Emitter 3D", "particles2d": "Particle Emitter 2D",
    "particleplayground": "Particle Playground", "echo": "Echo", "radialblur": "Radial Blur",
    "directionalblur": "Directional Blur", "gaussian": "Gaussian Blur", "lensblur": "Camera Lens Blur",
    "fractal": "Fractal Noise", "ramp": "Gradient Ramp", "turbulent": "Turbulent Displace",
    "carddance": "Card Dance", "dof": "Depth of Field", "pixelshatter": "Pixel Shatter",
}


def resolve(name: str) -> str:
    """Short alias -> display name; otherwise the name/id as given."""
    return FAVOURITES.get(name.lower().replace(" ", "").replace("-", ""), name)


def apply_program(comp: str, layer: Any, effect: str, values: dict[str, Any] | None = None,
                  keys: dict[str, list] | None = None, ease: Any = "smooth") -> str:
    """Script body: apply ``effect`` to ``layer``, set ``values`` and keys; returns the effect path."""
    return (f"var path = EC.fx({js(comp)}, {js(layer)}, {js(resolve(effect))}, {js(values or {})}, "
            f"{js(keys or {})}, {js(ease)});\nreturn {{path: path, effect: {js(resolve(effect))}}};")


def find(catalog: Any, query: str) -> list[dict]:
    """Effects from the engine catalog whose name, id or category contains ``query``."""
    effects = catalog.get("effects", catalog) if isinstance(catalog, dict) else catalog
    q = query.lower()
    return [e for e in effects or [] if q in str(e.get("name", "")).lower() or q in str(e.get("id", "")).lower()
            or q in str(e.get("category", "")).lower()]
