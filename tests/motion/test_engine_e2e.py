"""End-to-end tests of crewcut.motion against the real EffectCraft engine (effectcraft-cli).

Skipped when no binary is found through $EFFECTCRAFT_CLI or PATH. They run in the Crewcut image (which ships the
binary) or on a rented machine, never on a laptop without the engine:
    python -m pytest tests/motion/test_engine_e2e.py -v -s
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from crewcut.motion import export as ex
from crewcut.motion import project as pj
from crewcut.motion import templates as tp
from crewcut.motion.backend import Backend, BackendError, find_effectcraft
from crewcut.motion.jsx import parse_result, wrap_program

try:
    find_effectcraft()
except BackendError:
    pytest.skip("effectcraft-cli not found ($EFFECTCRAFT_CLI or PATH)", allow_module_level=True)

LAUNCH = Path(__file__).resolve().parents[2] / "examples" / "launch-film" / "templates"
CURSOR = str(tp.assets_dir() / "cursor.png")


@pytest.fixture()
def tmp_dir(tmp_path):
    return str(tmp_path)


@pytest.fixture()
def be():
    find_effectcraft()          # fails loudly with build instructions when missing
    return Backend()


def _png_size(path):
    with open(path, "rb") as f:
        head = f.read(24)
    assert head[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG"
    return int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")


def _new(be, tmp_dir, duration=2.0, bg="#202020"):
    path = os.path.join(tmp_dir, "t.ecproj")
    pj.create(be, path, pj.comp_params("Main", "1080p60", duration=duration, bg=bg))
    return path


def _prog(be, project, body):
    return parse_result(be.script(wrap_program(body, tp.lib_source()), project=project, save=True))


class TestProjectAndLayers:
    def test_project_written_by_engine(self, be, tmp_dir):
        p = _new(be, tmp_dir)
        assert os.path.getsize(p) > 100
        info = be.exec("comp.info", {"comp": "Main"}, project=p, save=False)
        assert (info["width"], info["height"], info["frameRate"]) == (1920, 1080, 60)
        print(f"\n  project: {p}")

    def test_every_layer_kind(self, be, tmp_dir):
        p = _new(be, tmp_dir)
        png = CURSOR
        r = _prog(be, p, f"""
          var a = EC.solid("Main", {{name: "S", color: "#ff0000", w: 200, h: 200}});
          var b = EC.text("Main", {{text: "Hi", size: 80, fill: "#ffffff", name: "T"}});
          var c = EC.shape("Main", {{kind: "ellipse", size: [100, 100], fill: "#00ff00", name: "E"}});
          var d = EC.nul("Main", {{name: "N"}});
          var e = EC.camera("Main", {{name: "C"}});
          var f = EC.light("Main", {{name: "L", kind: "Point"}});
          var g = EC.footage("Main", "{png}", {{name: "F"}});
          return [a, b, c, d, e, f, g];""")
        assert len(r) == 7 and all(isinstance(x, int) for x in r)
        names = {x["name"] for x in be.exec("comp.info", {"comp": "Main"}, project=p, save=False)["layers"]}
        assert {"S", "T", "E", "N", "C", "L", "F"} <= names


class TestKeysEffects:
    def test_eased_keys_are_not_linear(self, be, tmp_dir):
        p = _new(be, tmp_dir)
        _prog(be, p, """var id = EC.solid("Main", {name: "B", color: "#ffffff", w: 50, h: 50});
          EC.keys("Main", id, "transform/position", [[0, [0, 540]], [1, [1000, 540]]], "expo"); return id;""")
        mid = be.get(p, "Main", "B", "transform/position", time=0.5)
        x = (mid.get("value") or mid.get("evaluated"))[0]
        assert x > 600, f"expo ease should be far along at mid time, got {x}"

    def test_effect_values_read_back(self, be, tmp_dir):
        p = _new(be, tmp_dir)
        r = _prog(be, p, """var id = EC.solid("Main", {name: "B", color: "#ffffff"});
          return EC.fx("Main", id, "Glow", {radius: 33});""")
        assert r == "effects/#1"
        v = be.get(p, "Main", "B", "effects/#1/radius")
        assert abs(v["value"] - 33) < 1e-6

    def test_text_animator_index_path(self, be, tmp_dir):
        p = _new(be, tmp_dir)
        r = _prog(be, p, """var id = EC.text("Main", {text: "Make my next video", size: 80, name: "T"});
          var a1 = EC.animator("Main", id, ["opacity"]); var a2 = EC.animator("Main", id, ["fillColor"]);
          EC.keys("Main", id, a2.path + "/selectors/#1/start", [[0, 0], [1, 100]], "linear"); return [a1.path, a2.path];""")
        assert r == ["text/animators/#1", "text/animators/#2"]
        k = be.get(p, "Main", "T", "text/animators/#2/selectors/#1/start", time=0.5)
        assert 40 < k["value"] < 60

    def test_wiggle_expression_evaluates(self, be, tmp_dir):
        p = _new(be, tmp_dir)
        _prog(be, p, """var id = EC.solid("Main", {name: "B", color: "#ffffff"});
          EC.expr("Main", id, "transform/rotation", "wiggle(3, 20)"); return id;""")
        v = be.get(p, "Main", "B", "transform/rotation", time=0.7)
        assert v.get("expressionError") in (None, "") and abs(v.get("evaluated", v.get("value"))) > 0


class TestRender:
    def test_frame_pixels(self, be, tmp_dir):
        p = _new(be, tmp_dir, bg="#000000")
        _prog(be, p, """EC.solid("Main", {name: "R", color: "#ff0000", w: 400, h: 400}); return 1;""")
        out = os.path.join(tmp_dir, "f.png")
        be.render_frame(p, out, comp="Main", time=0.5)
        assert _png_size(out) == (1920, 1080)
        from PIL import Image
        px = Image.open(out).convert("RGB").getpixel((960, 540))
        assert px[0] > 240 and px[1] < 15 and px[2] < 15
        print(f"\n  frame: {out}")

    def test_chunked_video_exact_frames(self, be, tmp_dir):
        p = _new(be, tmp_dir, duration=2.0)
        _prog(be, p, """var id = EC.solid("Main", {name: "B", color: "#ffffff", w: 100, h: 100, mb: true});
          EC.keys("Main", id, "transform/position", [[0, [100, 540]], [2, [1800, 540]]], "linear"); return id;""")
        out = os.path.join(tmp_dir, "v.mp4")
        r = ex.render_video(be, p, out, "Main", 0, 2.0, 60, chunk=0.7, jobs=2)
        assert r["frames"] == r["expected_frames"] == 120
        with open(out, "rb") as f:
            assert b"ftyp" in f.read(64)
        print(f"\n  video: {out} ({r['bytes']:,} bytes)")


class TestTemplates:
    @pytest.mark.parametrize("name,params", [
        ("burst_rings", {"comp": "Main", "t": 0.2}),
        ("cursor_flyin", {"comp": "Main"}),
        ("app_dock", {"comp": "Main", "icons": ["@cursor"] * 3, "hovers": [[0, 0.5]], "click": [1, 0.8]}),
        ("pixel_burst", {"comp": "Main", "icon": "@cursor", "t": 0.3}),
    ])
    def test_template_renders_something(self, be, tmp_dir, name, params):
        params = json.loads(json.dumps(params).replace('"@cursor"', json.dumps(CURSOR)))
        p = _new(be, tmp_dir, duration=2.0, bg="#808080")
        code, _ = tp.program(name, params, str(LAUNCH))
        parse_result(be.script(code, project=p, save=True))
        out = os.path.join(tmp_dir, f"{name}.png")
        be.render_frame(p, out, comp="Main", time=0.55, max_side=480)
        from PIL import Image
        im = Image.open(out).convert("RGB")
        raw = im.tobytes()
        colours = len({raw[i:i + 3] for i in range(0, len(raw), 3)})
        assert colours > 20, f"{name}: frame looks empty ({colours} colours)"


class TestCLISubprocess:
    CLI_BASE = [sys.executable, "-m", "crewcut", "motion"]

    def _run(self, args, check=True):
        return subprocess.run(self.CLI_BASE + args, capture_output=True, text=True, check=check)

    def test_help(self):
        assert self._run(["--help"]).returncode == 0

    def test_full_workflow_json(self, tmp_dir):
        p = os.path.join(tmp_dir, "w.ecproj")
        r = json.loads(self._run(["--json", "project", "new", "-o", p, "--duration", "2"]).stdout)
        assert r["comp"] == "Main" and os.path.exists(p)
        r = json.loads(self._run(["--json", "--project", p, "layer", "add", "text", "--text", "Crewcut", "--name", "T", "--mb"]).stdout)
        assert isinstance(r["layer"], int)
        self._run(["--json", "--project", p, "key", "set", "T", "transform/position", "0=200,540", "1=960,540", "--ease", "expo"])
        r = json.loads(self._run(["--json", "--project", p, "--templates-dir", str(LAUNCH), "run-template", "burst_rings",
                                  "--params", '{"t": 0.5}']).stdout)
        assert r["template"] == "burst_rings"
        out = os.path.join(tmp_dir, "w.png")
        r = json.loads(self._run(["--json", "--project", p, "render", "frame", "--time", "0.8", "--out", out]).stdout)
        assert _png_size(out) == (1920, 1080)
        before = open(p, "rb").read()
        self._run(["--json", "--project", p, "layer", "add", "solid", "--name", "X"])
        self._run(["--json", "--project", p, "session", "undo"])
        assert open(p, "rb").read() == before, "undo must restore the exact project bytes"
        print(f"\n  workflow frame: {out}")

    def test_dry_run_leaves_file(self, tmp_dir):
        p = os.path.join(tmp_dir, "d.ecproj")
        self._run(["--json", "project", "new", "-o", p])
        before = open(p, "rb").read()
        self._run(["--json", "--dry-run", "--project", p, "layer", "add", "solid", "--name", "Y"])
        assert open(p, "rb").read() == before

    def test_error_is_json(self, tmp_dir):
        p = os.path.join(tmp_dir, "e.ecproj")
        self._run(["--json", "project", "new", "-o", p])
        r = self._run(["--json", "--project", p, "exec", "no.such.command"], check=False)
        assert r.returncode == 1 and "error" in json.loads(r.stdout)


class TestPersistentEngine:
    """The persistent connection (one effectcraft-cli mcp process) must give the same project as one-shot calls."""

    def test_same_result_and_saved(self, be, tmp_dir):
        from crewcut.motion.engine import McpEngine
        p = _new(be, tmp_dir)
        eng = McpEngine(p)
        try:
            be.engine = eng
            r = _prog(be, p, """var id = EC.solid("Main", {name: "P1", color: "#00ff00", w: 300, h: 300});
              EC.keys("Main", id, "transform/position", [[0, [200, 540]], [1, [1700, 540]]], "expo"); return id;""")
            assert isinstance(r, int)
            out = os.path.join(tmp_dir, "p.png")
            be.render_frame(p, out, comp="Main", time=0.5)
            assert _png_size(out) == (1920, 1080)
            assert eng.requests >= 3
        finally:
            be.engine = None
            eng.close()
        # the file on disk holds the change: a fresh one-shot process sees the layer and the eased key
        names = {x["name"] for x in be.exec("comp.info", {"comp": "Main"}, project=p, save=False)["layers"]}
        assert "P1" in names
        x = be.get(p, "Main", "P1", "transform/position", time=0.5)["value"][0]
        assert x > 1000

    def test_reopen_after_file_replaced(self, be, tmp_dir):
        from crewcut.motion.engine import McpEngine
        p = _new(be, tmp_dir)
        before = open(p, "rb").read()
        eng = McpEngine(p)
        try:
            eng.exec("layer.newSolid", {"comp": "Main", "name": "Gone"})
            open(p, "wb").write(before)            # what session undo does
            eng.reopen(p)
            info = eng.exec("comp.info", {"comp": "Main"}, save=False)
            assert "Gone" not in {x["name"] for x in info["layers"]}
        finally:
            eng.close()
