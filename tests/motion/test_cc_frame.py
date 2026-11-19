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


def run(ctx: dict | None, expr: str):
    """Evaluate a JS expression after cc_frame.jsx (with an optional CC_CTX) and return its JSON value."""
    pre = "" if ctx is None else f"var CC_CTX = {json.dumps(ctx)};\n"
    src = pre + LIB.read_text() + f"\nconsole.log(JSON.stringify({expr}));"
    r = subprocess.run([NODE, "-e", src], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


FACE16 = {"x": 0.48, "y": 0.30, "w": 0.18, "h": 0.34}


@needs_node
def test_behind_centres_on_the_face_at_shoulder_height_landscape():
    ctx = {"format": "landscape", "size": [1920, 1080], "transparent": True, "face": FACE16, "layer": "behind"}
    f = run(ctx, "CC.frame()")
    assert f["side"] == "behind" and f["layer"] == "behind"
    assert f["anchor"][0] == pytest.approx(0.48 * 1920)
    assert f["anchor"][1] == pytest.approx((0.30 + 0.22) * 1080)
    s, b = f["safe"], f["sideBox"]
    assert b["x"] == pytest.approx(s["x"]) and b["w"] == pytest.approx(s["w"])        # the whole safe width
    assert s["y"] <= b["y"] and b["y"] + b["h"] <= s["y"] + s["h"] + 1e-6
    assert run(ctx, "CC.clearOfFace({x: 900, y: 300, w: 100, h: 100})") is True          # the person covers it


@needs_node
def test_behind_portrait_uses_the_smaller_drop_and_stays_in_safe():
    ctx = {"format": "portrait", "size": [1080, 1920], "transparent": True, "layer": "behind",
           "face": {"x": 0.5, "y": 0.30, "w": 0.5, "h": 0.36}}
    f = run(ctx, "CC.frame()")
    assert f["side"] == "behind"
    assert f["anchor"][1] == pytest.approx((0.30 + 0.16) * 1920)
    assert f["anchor"][0] == pytest.approx(540)


@needs_node
def test_beside_and_no_face_behave_like_no_layer():
    base = {"format": "landscape", "size": [1920, 1080], "transparent": True, "face": FACE16}
    plain = run(base, "CC.frame()")
    beside = run({**base, "layer": "beside"}, "CC.frame()")
    assert beside["side"] == plain["side"] == "right" and beside["anchor"] == plain["anchor"]
    assert beside["layer"] is None
    noface = run({"format": "landscape", "size": [1920, 1080], "transparent": True, "layer": "behind"}, "CC.frame()")
    assert noface["side"] == "center" and noface["layer"] is None
    assert run({**base, "layer": "beside"}, "CC.clearOfFace({x: 900, y: 300, w: 100, h: 100})") is False


@needs_node
def test_colour_and_time_helpers():
    out = run({"fps": 25}, "[CC.luma('#FFFFFF'), CC.luma('#000000'), CC.mix('#000000', '#FFFFFF', 0.5), "
                           "CC.landBy(2.0), CC.driftAt(2), CC.driftAt(1, 9), CC.fit(140, 700, 560, 96), CC.fit(140, 900, 300, 96)]")
    assert out[0] == pytest.approx(1) and out[1] == 0 and out[2] == "#808080"
    assert out[3] == pytest.approx(2.0 - 1.5 / 25)                 # complete 1.5 frames before the cue
    assert out[4] == pytest.approx(1.04) and out[5] == pytest.approx(1.03)    # the push clamps to 1.5..3 %/s
    assert out[6] == pytest.approx(112) and out[7] == 96            # fits the width, never under the floor


@needs_node
def test_tone_follows_the_picture_under_the_box():
    grid = {"cols": 2, "rows": 1, "values": [0.2, 0.9]}                # dark left half, light right half
    ctx = {"format": "landscape", "size": [1920, 1080], "transparent": True, "backdrop_luma": grid,
           "brand": {"colors": {"ink": "#111111", "paper": "#FFFFFF"}}}
    left = run(ctx, "CC.tone({x: 100, y: 100, w: 400, h: 200})")
    right = run(ctx, "CC.tone({x: 1300, y: 100, w: 400, h: 200})")
    assert left["fill"] == "#FFFFFF" and left["shade"] == "#111111"
    assert right["fill"] == "#111111" and right["onLight"] is True
    rows = [[0.2] * 8 + [0.9] * 8 for _ in range(9)]                     # the render path's 16x9 list of rows
    assert run({**ctx, "backdrop_luma": rows}, "CC.tone({x: 1300, y: 100, w: 400, h: 200}).fill") == "#111111"
    assert run({**ctx, "backdrop_luma": rows}, "CC.tone({x: 100, y: 100, w: 400, h: 200}).fill") == "#FFFFFF"
    assert run({**ctx, "backdrop_luma": None}, "CC.tone().fill") == "#FFFFFF"          # unknown: light type
    assert run({**ctx, "backdrop_luma": 0.7}, "CC.tone().fill") == "#111111"           # one number for the side
    full = run({"transparent": False, "brand": {"mg": {"ink": "#222222"}}}, "CC.tone().fill")
    assert full == "#222222"                                                             # full frame: the pack ink


@needs_node
def test_plates_pass_through_and_plate_lookup():
    plates = {"word": {"first": "/x/plates/word/0001.png", "frames": 90, "ready": True},
              "late": {"first": "/x/plates/late/0001.png", "frames": 90, "ready": False}}
    out = run({"plates": plates}, "[CC.plate('word'), CC.plate('late'), CC.plate('none'), CC.ctx().plates.word.frames]")
    assert out[0]["frames"] == 90 and out[1] is None and out[2] is None and out[3] == 90
    assert run(None, "CC.ctx().plates") == {}


@needs_node
def test_shape_background_preserves_silhouettes_and_skips_transparent_overlays():
    ctx = {'brand': {'mg': {'background': {'mode': 'shapes', 'layouts': {'landscape': [
        {'kind': 'ring', 'x': 0, 'y': 0.9, 'size': 0.5, 'thickness': 0.1, 'blur': 0.015, 'vx': 0.003},
        {'kind': 'plus', 'x': 0.9, 'y': 0.1, 'size': 0.15, 'spin': 1.5}]}}}}}
    expr = '''(function(){var shapes=[], keys=[], effects=[];
    EC={solid:function(){return 'ground';},shape:function(c,s){shapes.push(s);return shapes.length;},
        set:function(){},keys:function(c,id,p,k){keys.push([p,k]);},sw:function(){},fx:function(c,id,n,p){effects.push(p);}};
    var ids=CC.groundLayer('test');return {ids:ids,shapes:shapes,keys:keys,effects:effects};})()'''
    out = run(ctx, expr)
    assert len(out['ids']) == 4
    assert out['shapes'][0]['fillOpacity'] == 0 and out['shapes'][0]['strokeWidth'] == 108
    assert out['shapes'][1]['size'] == pytest.approx([162, 38.88])
    assert len(out['effects']) == 1
    assert any(k[0] == 'transform/rotation' and k[1][1][1] == 6 for k in out['keys'])
    ctx['transparent'] = True
    assert run(ctx, expr)['ids'] is None
    assert run(ctx, expr)['shapes'] == []
