"""Helpers for the skill script tests: load a script by path and load a style pack folder."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def load_script(rel: str):
    """Import a skill script (skills/<name>/scripts/<x>.py) as a module."""
    path = ROOT / rel
    name = "skilltest_" + path.stem
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def load_pack(rel: str):
    try:
        from crewcut import brand
    except ImportError:  # minimal fallback: the neutral JSON files only
        pytest.skip("crewcut.brand is not importable")
    return brand.load(ROOT / rel)


@pytest.fixture
def neutral():
    return load_pack("packs/neutral")


@pytest.fixture
def striq():
    return load_pack("examples/striq")
