"""Shared fixtures for the render tests. Nothing here runs ffmpeg, Chromium or Blender: a fake runner records the
argument lists and creates the files those programs would write."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from render_helpers import WORDS


@pytest.fixture
def studio(tmp_path, monkeypatch):
    s = tmp_path / "studio"
    s.mkdir()
    monkeypatch.setenv("CREWCUT_STUDIO", str(s))
    for k in ("CREWCUT_IDENTITY", "CREWCUT_JOB", "CREWCUT_GPU", "CREWCUT_BLENDER"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("CREWCUT_GPU", "0")
    return s


@pytest.fixture
def episode(studio):
    """An episode folder with a words file; returns a function that writes a plan and gives its path."""
    ep = studio / "episodes" / "001-test"
    for d in ("edit", "work", "render", "export", "audio"):
        (ep / d).mkdir(parents=True)
    (ep / "work" / "words-v001.json").write_text(json.dumps(WORDS), encoding="utf-8")
    (ep / "project.json").write_text(json.dumps({"id": "001-test", "format": "landscape", "fps": 25}), encoding="utf-8")

    def write(plan: dict, name: str = "plan-v001.json") -> Path:
        p = ep / "edit" / name
        p.write_text(json.dumps(plan), encoding="utf-8")
        return p
    write.dir = ep
    return write
