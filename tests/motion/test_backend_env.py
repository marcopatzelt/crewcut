"""Backend(env=...): every engine process gets the extra environment (EFFECTCRAFT_FONT_DIRS for pack fonts)."""

from __future__ import annotations

import subprocess

from crewcut.motion import backend as bk


class Done:
    returncode = 0
    stdout = '{"ok": true}'
    stderr = ""


def test_env_reaches_every_engine_process(monkeypatch, tmp_path):
    seen = []

    def fake_run(argv, **kw):
        seen.append(kw.get("env") or {})
        return Done()

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setenv("EFFECTCRAFT_KEEP", "1")
    be = bk.Backend(env={"EFFECTCRAFT_FONT_DIRS": str(tmp_path)}, extra_env={"A": "1"})
    be._bin = "/usr/local/bin/effectcraft-cli"
    be.info()
    be.render(str(tmp_path / "p.ecproj"), str(tmp_path / "f_[#####].png"), comp="Main", start=0.0, end=1.0, fmt="png")
    be.version()
    assert len(seen) == 3
    for env in seen:
        assert env["EFFECTCRAFT_FONT_DIRS"] == str(tmp_path) and env["A"] == "1" and env["EFFECTCRAFT_KEEP"] == "1"


def test_no_env_keeps_the_process_environment(monkeypatch):
    monkeypatch.setenv("EFFECTCRAFT_FONT_DIRS", "/fonts/here")
    assert bk.Backend().process_env()["EFFECTCRAFT_FONT_DIRS"] == "/fonts/here"
    assert bk.Backend(env={"EFFECTCRAFT_FONT_DIRS": "/x"}).process_env()["EFFECTCRAFT_FONT_DIRS"] == "/x"


def test_png_sequence_render_arguments(tmp_path):
    be = bk.Backend()
    be._bin = "effectcraft-cli"
    calls = []
    be.call = lambda argv, timeout=None, check=True: calls.append(argv)
    be.render("p.ecproj", "out/f_[#####].png", comp="Main", start=0.99, end=2.03, fmt="png",
              extra=["--channels", "rgba"])
    assert calls[0] == ["effectcraft-cli", "--project", "p.ecproj", "render", "--out", "out/f_[#####].png",
                        "--comp", "Main", "--start", "0.990000", "--end", "2.030000", "--format", "png",
                        "--channels", "rgba", "--json"]
