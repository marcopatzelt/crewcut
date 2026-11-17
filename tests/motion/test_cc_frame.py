"""lib/cc_frame.jsx (CC.frame) in the three formats, run with node (skipped when node is missing), and the
context injection of templates.program."""

from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from crewcut import paths
from crewcut.motion import templates as tp

LIB = paths.templates_dir() / "motion" / "lib" / "cc_frame.jsx"
NODE = shutil.which("node")


def frame(ctx: dict | None) -> dict:
    pre = "" if ctx is None else f"var CC_CTX = {json.dumps(ctx)};\n"
    src = pre + LIB.read_text() + "\nconsole.log(JSON.stringify({f: CC.frame(), font: CC.font('display'), c0: CC.color(0)}));"
    r = subprocess.run([NODE, "-e", src], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


needs_node = pytest.mark.skipif(NODE is None, reason="node is not installed")


@needs_node
def test_landscape_safe_box_and_free_side():
    out = frame({"format": "landscape", "size": [1920, 1080], "face": {"x": 0.42, "y": 0.38, "w": 0.2, "h": 0.3}})
    f = out["f"]
    assert f["u"] == 1 and f["safe"]["x"] == pytest.approx(96) and f["safe"]["h"] == pytest.approx(1080 * 0.9)
    assert f["side"] == "right"                                   # the face sits left of centre
    assert f["sideBox"]["x"] >= f["face"]["x"] + f["face"]["w"] - 1e-6
    assert f["face"]["w"] == pytest.approx(0.32 * 1920)           # at least ± 0.16 of the width
    ax, ay = f["anchor"]
    assert f["face"]["cy"] < ay < f["safe"]["y"] + f["safe"]["h"]  # chest to shoulder height, below the face centre


@needs_node
def test_overlay_keeps_player_bar_free():
    f = frame({"format": "landscape", "size": [1920, 1080], "transparent": True})["f"]
    assert f["safe"]["y"] + f["safe"]["h"] == pytest.approx(1080 * 0.92)
    assert f["side"] == "center" and f["face"] is None


@needs_node
def test_portrait_right_strip_and_centred_face_goes_below():
    f = frame({"format": "portrait", "size": [1080, 1920], "face": {"x": 0.5, "y": 0.33}})["f"]
    s = f["safe"]
    assert s["x"] == pytest.approx(0.06 * 1080) and s["x"] + s["w"] == pytest.approx(1080 * 0.82)
    assert s["y"] == pytest.approx(192) and s["y"] + s["h"] == pytest.approx(1920 * 0.8)
    assert f["side"] == "below" and f["sideBox"]["y"] >= f["face"]["y"] + f["face"]["h"] - 1e-6
    assert f["anchor"][0] == pytest.approx(0.41 * 1080)          # left of the platform's buttons


@needs_node
def test_stage_format_and_units():
    f = frame({"format": "stage", "size": [1080, 960]})["f"]
    assert f["u"] == pytest.approx(960 / 1080)
    assert f["safe"]["y"] + f["safe"]["h"] == pytest.approx(960 * 0.94)


@needs_node
def test_brand_font_and_palette_from_context():
    out = frame({"brand": {"fonts": {"display": {"family": "Fraunces", "weight": 700}},
                           "mg": {"palette": ["#123456", "#654321"]}}})
    assert out["font"] == {"font": "Fraunces", "style": "Bold"} and out["c0"] == "#123456"
    assert frame(None)["font"]["font"] == "Inter"                 # no context: neutral defaults, landscape


def test_program_injects_context_and_both_libraries(tmp_path):
    (tmp_path / "t1.jsx").write_text('/* @template t1\n @params {"a": 1}\n @end */\nfunction t1(P) { return CC.frame(); }\n')
    code, merged = tp.program("t1", {"a": 2}, str(tmp_path), context={"format": "portrait", "fps": 30})
    assert merged == {"a": 2}
    assert code.index("var CC_CTX = ") < code.index("var EC = ") < code.index("var CC = ")
    assert '"format": "portrait"' in code
    assert [p.name for p in tp.lib_files()] == ["ec_lib.jsx", "cc_frame.jsx"]
