"""The custom comp skeleton of ``crewcut motion new`` against the real engine (motion plan 3.3 check 2): an empty ground
with a slow push in landscape and portrait. Skipped without ``effectcraft-cli``; runs in the Crewcut image."""

from __future__ import annotations

import json
import os

import pytest
from flow_helpers import make_episode

from crewcut.motion import custom
from crewcut.motion import project as pj
from crewcut.motion import templates as tp
from crewcut.motion.backend import Backend, BackendError, find_effectcraft
from crewcut.motion.jsx import parse_result, wrap_program

try:
    find_effectcraft()
except BackendError:
    pytest.skip("effectcraft-cli not found ($EFFECTCRAFT_CLI or PATH)", allow_module_level=True)

SIZES = {"landscape": (1920, 1080), "portrait": (1080, 1920)}


@pytest.mark.parametrize("fmt", ["landscape", "portrait"])
def test_skeleton_renders_ground_and_drift(tmp_path, fmt):
    from PIL import Image, ImageChops
    eid, _ep = make_episode()
    brief = tmp_path / "brief.md"
    brief.write_text("A test piece.\n")
    d = custom.new(eid, "skel", brief)
    w, h = SIZES[fmt]
    be = Backend()
    proj = str(tmp_path / f"{fmt}.ecproj")
    pj.create(be, proj, pj.comp_params("Main", None, width=w, height=h, fps=25, duration=2.0, bg="#F1F1EF"))
    ctx = {"format": fmt, "size": [w, h], "fps": 25, "duration": 2.0, "transparent": False}
    body = f"{(d / 'comp.jsx').read_text()}\nreturn skel({json.dumps({'comp': 'Main'})});"
    code = wrap_program(body, tp.context_source(ctx) + tp.lib_source() + "\nvar EC_ASSETS = \"\";\n")
    parse_result(be.script(code, project=proj, save=True))
    frames = []
    for t in (0.1, 1.9):
        out = os.path.join(tmp_path, f"{fmt}-{t}.png")
        be.render_frame(proj, out, comp="Main", time=t, max_side=480)
        frames.append(Image.open(out).convert("RGB"))
    assert frames[0].size[0] > frames[0].size[1] if fmt == "landscape" else frames[0].size[0] < frames[0].size[1]
    diff = ImageChops.difference(frames[0], frames[1]).getbbox()
    assert diff is not None, "the push moves the picture: the two frames differ"
