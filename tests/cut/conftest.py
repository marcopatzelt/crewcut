"""Fixtures for the cut tests. The studio folder (CREWCUT_STUDIO in tmp) comes from tests/conftest.py."""

import json

import pytest


@pytest.fixture
def episode(studio):
    """A minimal episode folder: 001-test, landscape, 25 fps."""
    d = studio / "episodes" / "001-test"
    for sub in ("brief", "originals", "work", "audio", "edit", "review", "export"):
        (d / sub).mkdir(parents=True)
    (d / "project.json").write_text(json.dumps({"id": "001-test", "format": "landscape", "fps": 25}))
    return d
