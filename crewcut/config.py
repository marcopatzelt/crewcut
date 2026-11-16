"""Settings from TOML files: app defaults in <app>/config/, user overrides in <studio>/config/ (same file names)."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

from . import paths


def _merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def _read(p: Path) -> dict:
    try:
        with open(p, "rb") as f:
            return tomllib.load(f)
    except FileNotFoundError:
        return {}


def load(name: str) -> dict[str, Any]:
    """Load config/<name>.toml from the app, then merge the user's studio/config/<name>.toml on top."""
    base = _read(paths.app_root() / "config" / f"{name}.toml")
    user = _read(paths.studio_root() / "config" / f"{name}.toml")
    return _merge(base, user)


def get(name: str, dotted: str, default: Any = None) -> Any:
    cur: Any = load(name)
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur


def env_flag(name: str, default: bool = False) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")
