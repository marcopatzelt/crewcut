"""tests/smoke/motion.py (the image smoke test's motion part) with a fake engine and a fake ffprobe: it finds the
templates, renders one sample per format with the hue check, makes the two clips and checks their frame counts, and
skips templates that do not exist yet. The real run happens only in the image."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from motion_helpers import FakeBackend, backend_factory, template_src
from PIL import Image
from render_helpers import FakeRunner

from crewcut.motion import templates as mtemplates

APP = Path(__file__).resolve().parents[2]


@pytest.fixture
def smoke(monkeypatch, tmp_path):
    spec = importlib.util.spec_from_file_location("smoke_motion", APP / "tests" / "smoke" / "motion.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    lib = tmp_path / "app-motion"
    lib.mkdir()
    monkeypatch.setattr(mtemplates, "app_dir", lambda: lib)
    shutil_lib = mtemplates.paths.templates_dir() / "motion" / "lib"
    (lib / "lib").mkdir()
    for f in shutil_lib.glob("*.jsx"):
        (lib / "lib" / f.name).write_text(f.read_text())

    class Engine(FakeBackend):
        colours = ["#E4572E", "#009CB7", "#B87E00", "#DD508E"]

        def render_frame(self, project, out, comp=None, time=None, frame=None, max_side=None, transparent=False):
            self.calls.append({"cmd": "frame", "out": out, "frame": frame, "max_side": max_side,
                               "transparent": transparent})
            im = Image.new("RGB", (96, 54), "#F1F1EF")
            for i, c in enumerate(self.colours):
                im.paste(Image.new("RGB", (12, 12), c), (8 + 20 * i, 20))
            im.save(out)

    calls: list = []
    monkeypatch.setattr(mod, "Backend", lambda env=None: Engine(env or {}, calls))
    real = mod.rmotion.render_motion
    monkeypatch.setattr(mod.rmotion, "render_motion", lambda plan, **kw: real(
        plan, **{**kw, "runner": FakeRunner(), "backend": backend_factory(calls)}))
    monkeypatch.setattr(mod, "probe", lambda clip: {                   # frames as written: shown + 2 extra
        "codec_name": "qtrle" if clip.suffix == ".mov" else "h264",
        "pix_fmt": "argb" if clip.suffix == ".mov" else "yuv420p",
        "nb_read_frames": len(list(Path(str(clip)[: -len(clip.suffix)]).glob("*.png")))})
    mod.calls, mod.lib = calls, lib
    return mod


def test_samples_and_clips(smoke, tmp_path, capsys):
    (smoke.lib / "keyword_pop.jsx").write_text(template_src("keyword_pop", "overlay", ["landscape", "portrait"]))
    (smoke.lib / "number_roll.jsx").write_text(template_src("number_roll", "full", ["landscape", "stage"]))
    (smoke.lib / "number_roll.v1.jsx").write_text(template_src("number_roll", "full", ["landscape"]))
    (smoke.lib / "broken.jsx").write_text("/* no header */")
    assert smoke.main(["x", str(tmp_path / "out")]) == 0
    out = capsys.readouterr().out
    assert "motion sample broken.jsx: header does not parse" in out
    for name in ("keyword_pop landscape", "keyword_pop portrait", "number_roll landscape", "number_roll stage"):
        assert f"motion sample {name}: ok" in out
    frames = [c for c in smoke.calls if c["cmd"] == "frame"]
    assert len(frames) == 4 and all(c["frame"] == 99 and c["max_side"] == 960 for c in frames)
    assert [c["transparent"] for c in frames] == [True, True, False, False]
    assert "motion clip keyword_pop: ok (40 of 40 frames, qtrle argb)" in out      # 0.5 to 2.0 s: 38 + 2
    assert "motion clip number_roll: ok (78 of 78 frames, h264 yuv420p)" in out
    assert (tmp_path / "out" / "keyword_pop.mov").is_file()


def test_missing_templates_are_skipped(smoke, tmp_path, capsys):
    assert smoke.main(["x", str(tmp_path / "out")]) == 0
    out = capsys.readouterr().out
    assert "motion clip keyword_pop: skipped (no templates/motion/keyword_pop.jsx yet)" in out
    assert "motion clip number_roll: skipped" in out
