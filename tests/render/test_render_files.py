"""Static checks of the render files: JavaScript syntax (node --check, no browser), the 3D scripts run frame by frame
against a stand-in for Blender (no Blender), and the stage helpers."""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from crewcut import paths

HERE = Path(__file__).parent
T2D = paths.templates_dir() / "2d"
T3D = paths.templates_dir() / "3d"
NODE = shutil.which("node")


@pytest.mark.skipif(not NODE, reason="node is not installed")
def test_js_files_parse():
    for f in [paths.tools_dir() / "render_html.js", T2D / "motion.js", T2D / "scene.js"]:
        r = subprocess.run([NODE, "--check", str(f)], capture_output=True, text=True)
        assert r.returncode == 0, f"{f.name}: {r.stderr}"


@pytest.mark.skipif(not NODE, reason="node is not installed")
def test_inline_scene_scripts_parse(tmp_path):
    scenes = sorted(T2D.glob("*.html"))
    assert {p.stem for p in scenes} == {"bars", "cards", "clip-card", "counter", "grid", "headline", "keyword", "post"}
    for f in scenes:
        html = f.read_text(encoding="utf-8")
        assert '<link rel="stylesheet" href="base.css">' in html and '<script src="motion.js">' in html
        assert "const EXAMPLE=" in html and "SCENE(EXAMPLE," in html, f"{f.name}: every scene has an example"
        inline = re.findall(r"<script>(.*?)</script>", html, re.S)
        assert len(inline) == 1
        js = tmp_path / f"{f.stem}.js"
        js.write_text(inline[0], encoding="utf-8")
        r = subprocess.run([NODE, "--check", str(js)], capture_output=True, text=True)
        assert r.returncode == 0, f"{f.name}: {r.stderr}"


def test_base_css_takes_every_colour_from_variables():
    css = (T2D / "base.css").read_text(encoding="utf-8")
    body = css.split("}", 1)[1]                       # everything after the :root fallbacks
    assert not re.findall(r"#[0-9A-Fa-f]{3,6}\b", body.replace("#000", "")), "raw colours outside :root"
    assert "@font-face" not in css
    sizes = [int(x) for x in re.findall(r"font-size:(\d+)px", css)]
    assert sizes and min(sizes) >= 40                 # neutral min_text_px


def test_3d_scripts_compile():
    for f in T3D.glob("*.py"):
        compile(f.read_text(encoding="utf-8"), str(f), "exec")


@pytest.mark.parametrize("scene,args", [
    ("box", {"format": "landscape", "frames": 40, "action": "open", "cues": {"word": 20}}),
    ("box", {"format": "portrait", "frames": 40, "action": "closed", "sub": "held back", "cues": {"word": 30}}),
    ("stack", {"format": "landscape", "frames": 40, "count": 6, "cues": {"word": 20}}),
    ("stack", {"format": "portrait", "frames": 40, "action": "clear", "count": 6, "keep": 2, "lead": 3, "cues": {"word": 20}}),
    ("scale", {"format": "landscape", "frames": 50, "count": 4, "cues": {"word": 40}}),
])
def test_3d_scene_runs_every_frame(tmp_path, scene, args):
    d = tmp_path / "d.json"
    d.write_text(json.dumps(args))
    t = tmp_path / "t.json"
    t.write_text(json.dumps({"stage3d": {"material": "gloss", "light": "hard", "font": None},
                             "motion": {"decor": "shapes"}, "colors": {"ink": "#222222"}}))
    r = subprocess.run([sys.executable, str(HERE / "fake_bpy.py"), str(T3D / f"{scene}.py"), "--", "--data", str(d),
                        "--brand", str(t), "--out", str(tmp_path / "out"), "--anim", "--from", "0",
                        "--to", str(args["frames"] - 1), "--gpu"], capture_output=True, text=True, cwd=tmp_path)
    assert r.returncode == 0, r.stderr[-1500:]
    assert f"RENDERS {args['frames']} " in r.stdout


def test_3d_still_and_defaults(tmp_path):
    r = subprocess.run([sys.executable, str(HERE / "fake_bpy.py"), str(T3D / "scale.py"), "--", "--frame", "30",
                        "--scale", "50", "--out", str(tmp_path / "p" / "still.png")], capture_output=True, text=True,
                       cwd=tmp_path)
    assert r.returncode == 0, r.stderr[-1500:]
    assert "RENDERS 1 " in r.stdout and "still.png" in r.stdout


def test_stage_helpers(tmp_path):
    code = f"""
import sys, json
sys.path.insert(0, {str(HERE)!r}); import fake_bpy
sys.argv = ["blender", "--", "--brand", {str(tmp_path / 'b.json')!r}]
sys.path.insert(0, {str(T3D)!r}); import stage
fonts = {str(tmp_path / 'fonts')!r}
print(json.dumps({{
  "stage": stage.STAGE, "spring_end": stage.spring(1.0), "spring_over": max(stage.spring(i / 50) for i in range(51)),
  "linear": stage.linear("#FFFFFF"), "shade": stage.shade("#808080", 0.5),
  "font": stage.find_system_font("Inter", 800, dirs=[fonts]), "font600": stage.find_system_font("Inter", 600, dirs=[fonts]),
  "none": stage.find_system_font("Nope", 800, dirs=[fonts])}}))
"""
    (tmp_path / "b.json").write_text(json.dumps({"stage3d": {"accent": "#2A7AE2", "samples": None}, "colors": {"ink": "#101010"}}))
    f = tmp_path / "fonts" / "inter"
    f.mkdir(parents=True)
    for n in ("Inter-Regular.ttf", "Inter-Bold.ttf", "Inter-ExtraBold.ttf", "Inter-ExtraBoldItalic.ttf", "InterDisplay-Black.ttf"):
        (f / n).write_bytes(b"x")
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=tmp_path)
    assert r.returncode == 0, r.stderr[-1500:]
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert out["stage"]["accent"] == "#2A7AE2" and out["stage"]["samples"] == 128 and out["stage"]["text"] == "#101010"
    assert out["spring_end"] == 1.0 and out["spring_over"] > 1.0
    assert out["linear"] == [1.0, 1.0, 1.0] and out["shade"] == "#404040"
    assert out["font"].endswith("Inter-ExtraBold.ttf") and out["font600"].endswith("Inter-Bold.ttf") and out["none"] is None


JSDOM = paths.app_root() / "web" / "node_modules" / "jsdom"


@pytest.mark.skipif(not NODE or not JSDOM.is_dir(), reason="needs node and jsdom (npm ci in web/)")
def test_scene_scripts_run_every_frame_in_a_dom():
    env = {**os.environ, "NODE_PATH": str(JSDOM.parent)}
    r = subprocess.run([NODE, str(HERE / "scenes_dom.js"), str(T2D)], capture_output=True, text=True, env=env, timeout=300)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-1000:]
    assert "scenes ok 32, bad 0" in r.stdout
