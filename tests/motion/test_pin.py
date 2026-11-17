"""The EffectCraft pin, the patch files, the image tag and the licence files agree."""

from __future__ import annotations

import re
from pathlib import Path

from crewcut import doctor

ROOT = Path(__file__).resolve().parents[2]
EC = ROOT / "third_party" / "effectcraft"


def test_pin_has_commit_and_checksum():
    pin = doctor.read_pin()
    assert re.fullmatch(r"[0-9a-f]{40}", pin["commit"])
    assert re.fullmatch(r"[0-9a-f]{64}", pin["sha256"])


def test_dockerfile_tag_matches_pin_and_patch_count():
    pin = doctor.read_pin()
    patches = sorted(EC.glob("patches/*.patch"))
    assert patches and all(re.match(r"\d{4}-[A-Za-z0-9.-]+\.patch$", p.name) for p in patches)
    assert [p.name[:4] for p in patches] == [f"{i:04d}" for i in range(1, len(patches) + 1)]
    m = re.search(r"ARG EFFECTCRAFT_IMAGE=ghcr\.io/\S+/crewcut-effectcraft:(\S+)", (ROOT / "docker/Dockerfile").read_text())
    assert m, "docker/Dockerfile names no EFFECTCRAFT_IMAGE"
    assert m.group(1) == f"{pin['commit'][:12]}-p{len(patches)}"


def test_upstream_licences_and_no_brand_files():
    for name in ("LICENSE-MIT", "LICENSE-APACHE", "NOTICE"):
        assert (EC / name).stat().st_size > 500
    assert "MIT License" in (EC / "LICENSE-MIT").read_text()
    assert not any(p.suffix in (".png", ".svg") for p in EC.rglob("*")), "upstream brand files must never enter the repo"


def test_patches_are_format_patch_files_with_a_test():
    for p in EC.glob("patches/*.patch"):
        text = p.read_text()
        assert text.startswith("From ") and "\nSubject: [PATCH" in text
        assert "/tests/" in text or "#[test]" in text, f"{p.name}: every patch brings a test"


def test_doctor_without_binary_is_a_note(monkeypatch):
    monkeypatch.setenv("EFFECTCRAFT_CLI", "/nonexistent/effectcraft-cli")
    monkeypatch.setenv("PATH", "/nonexistent")
    status, detail, fix = doctor.motion_engine_status()
    assert status == doctor.NOTE and "pin 7a34ceffe209" in detail and "patches 1" in detail
