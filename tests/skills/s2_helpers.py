"""Helpers for the tests of the edit, cut-check, 3d-scene and thumbnail scripts: import a script by path, load a pack."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[2]


def script(rel: str, name: str):
    """Import skills/<rel> as a module (its folder goes on sys.path, like when it runs as a script)."""
    path = APP / "skills" / rel
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class FakePack:
    """Minimal stand-in for crewcut.brand.Pack: JSON files of a pack folder, dotted lookup, rules."""

    FILES = {"brand": "brand.json", "edit_style": "edit-style.json", "channel": "channel.json",
             "thumbnail": "thumbnail.json", "baseline": "baseline.json"}

    def __init__(self, d: Path):
        self.dir, self.is_neutral = d, d.name == "neutral"
        for attr, f in self.FILES.items():
            p = d / f
            setattr(self, attr, json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {})

    def value(self, dotted, default=None):
        head, _, rest = dotted.partition(".")
        cur = getattr(self, head, None)
        for part in rest.split(".") if rest else []:
            if not isinstance(cur, dict) or cur.get(part) is None:
                return default
            cur = cur[part]
        return default if cur is None else cur

    def rules(self, step):
        return []


def pack(d: Path | None = None):
    """The pack through crewcut.brand when it is there, else the minimal stand-in."""
    d = d or APP / "packs" / "neutral"
    try:
        from crewcut import brand

        return brand.load(d)
    except ImportError:
        return FakePack(d)
