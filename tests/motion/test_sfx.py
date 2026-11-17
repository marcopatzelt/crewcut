"""The sound kit: made by code, the right length and level, deterministic, written once, and no audio file in git."""

from __future__ import annotations

import json
import shutil
import subprocess
import wave
from pathlib import Path

import numpy as np
import pytest

from crewcut import paths
from crewcut.motion import sfx

ROOT = Path(__file__).resolve().parents[2]
LIMIT = {"whoosh": 1.0, "tick": 0.12, "typing": 1.5, "pop": 0.2, "click": 0.2, "hit": 0.8, "riser": 1.5,
         "reel_tick": 0.08, "bell": 1.6}                     # longest allowed file per sound, seconds


def read(path: Path) -> tuple[np.ndarray, int, int]:
    """(samples as floats in [-1, 1], sample rate, sample width in bytes)"""
    with wave.open(str(path)) as w:
        sr, width, ch, n = w.getframerate(), w.getsampwidth(), w.getnchannels(), w.getnframes()
        raw = w.readframes(n)
    if width == 3:
        b = np.frombuffer(raw, np.uint8).reshape(-1, 3).astype(np.int32)
        v = b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)
        x = np.where(v >= 1 << 23, v - (1 << 24), v) / float(1 << 23)
    else:
        x = np.frombuffer(raw, "<i2") / 32768.0
    return x.reshape(n, ch), sr, width


def test_every_kit_file_has_the_right_length_and_level(tmp_path):
    kit = sfx.ensure_kit(tmp_path)
    assert set(kit) == set(sfx.SOUNDS) == set(LIMIT)
    for name, p in kit.items():
        assert p == tmp_path / f"{name}.wav" and p.is_file()
        x, sr, width = read(p)
        seconds = x.shape[0] / sr
        assert sr == 48000 and width == 3 and x.shape[1] in (1, 2)
        assert seconds == pytest.approx(sfx.SOUNDS[name][1], abs=1 / sr), name
        assert 0.02 <= seconds <= LIMIT[name], name
        peak_db = 20 * np.log10(np.abs(x).max())
        assert -30.0 < peak_db <= -1.0, (name, peak_db)
    manifest = json.loads((tmp_path / "kit.json").read_text())
    assert manifest["version"] == sfx.KIT_VERSION and manifest["seed"] == sfx.DEFAULT_SEED
    assert set(manifest["files"]) == {f"{n}.wav" for n in sfx.SOUNDS}


def test_same_seed_same_bytes_in_another_folder(tmp_path):
    a = sfx.ensure_kit(tmp_path / "a")
    b = sfx.ensure_kit(tmp_path / "b")
    ja = json.loads((tmp_path / "a" / "kit.json").read_text())["files"]
    jb = json.loads((tmp_path / "b" / "kit.json").read_text())["files"]
    assert ja == jb
    for name in sfx.SOUNDS:
        assert a[name].read_bytes() == b[name].read_bytes(), name
    other = sfx.ensure_kit(tmp_path / "c", seed=8)
    assert other["whoosh"].read_bytes() != a["whoosh"].read_bytes()


def stamp(p: Path) -> tuple[int, int]:
    """Inode and mtime: a rewrite replaces the file, so the inode changes."""
    st = p.stat()
    return st.st_ino, st.st_mtime_ns


def test_second_call_rewrites_nothing_and_repairs_what_changed(tmp_path):
    kit = sfx.ensure_kit(tmp_path)
    files = [*kit.values(), tmp_path / "kit.json"]
    before = {p: stamp(p) for p in files}
    assert sfx.ensure_kit(tmp_path) == kit
    assert {p: stamp(p) for p in files} == before

    good = kit["pop"].read_bytes()
    kit["pop"].write_bytes(good[:100])                        # a damaged file is made again
    kit["click"].unlink()                                     # and so is a missing one
    sfx.ensure_kit(tmp_path)
    assert kit["pop"].read_bytes() == good and kit["click"].is_file()
    assert stamp(kit["hit"]) == before[kit["hit"]]

    m = json.loads((tmp_path / "kit.json").read_text())       # a new kit version makes every file again
    m["version"] = sfx.KIT_VERSION - 1
    (tmp_path / "kit.json").write_text(json.dumps(m))
    sfx.ensure_kit(tmp_path)
    assert stamp(kit["hit"])[0] != before[kit["hit"]][0]
    assert json.loads((tmp_path / "kit.json").read_text())["version"] == sfx.KIT_VERSION


def test_kit_path_defaults_to_the_studio_state_folder():
    p = sfx.kit_path("whoosh")
    assert p == paths.state_dir() / "sfx" / "whoosh.wav" and p.is_file()
    with pytest.raises(KeyError, match="no kit sound"):
        sfx.kit_path("airhorn")


def test_no_audio_file_is_tracked_in_git():
    if not shutil.which("git") or not (ROOT / ".git").exists():
        pytest.skip("not a git checkout")
    out = subprocess.run(["git", "-C", str(ROOT), "ls-files"], capture_output=True, text=True, check=True).stdout
    audio = [f for f in out.splitlines() if f.lower().endswith((".wav", ".mp3", ".flac", ".ogg", ".m4a"))]
    assert audio == []
