"""Custom motion (motion plan 3.3): the piece's folder and comp skeleton, the style-frame card with two pictures side
by side per format, and the gate that keeps the animation from being built before the style frame's yes."""

from __future__ import annotations

import json
import shutil
import subprocess

import pytest
from flow_helpers import image, make_episode

from crewcut import approvals
from crewcut.conductor import queue
from crewcut.motion import custom, review
from crewcut.motion import templates as tp
from crewcut.motion.jsx import wrap_program


@pytest.fixture(autouse=True)
def quiet_queue(monkeypatch):
    monkeypatch.setattr(queue, "add", lambda *a, **k: 1)


@pytest.fixture
def piece(tmp_path):
    eid, ep = make_episode()
    brief = tmp_path / "brief.md"
    brief.write_text("# Show how the agent hands a render job to a rented GPU and gets frames back\n\n5 s, landscape "
                     "and portrait.\n")
    d = custom.new(eid, "handoff", brief)
    return eid, ep, d


# ---------------------------------------------------------------- check 2: the folder and the skeleton


def test_new_makes_the_folder_with_a_full_header(piece):
    eid, ep, d = piece
    assert d == ep / "motion" / "handoff"
    for name in ("brief.md", "beats.md", "notes.md", "comp.jsx"):
        assert (d / name).is_file(), name
    assert (d / "refs").is_dir() and (d / "review").is_dir()
    assert "rented GPU" in (d / "brief.md").read_text()
    src = (d / "comp.jsx").read_text()
    h = tp.parse_header(src)
    assert h["name"] == "handoff" and h["kind"] == "full" and h["version"] == 1
    assert h["formats"] == ["landscape", "portrait"] and h["defaults"] == {"comp": "Main"}
    assert "rented GPU" in h["description"]
    assert "CC.frame()" in src and "CC.ground()" in src and '"transform/scale"' in src
    assert "1920" not in src and "1080" not in src.replace("/ 1080", "")
    assert review.lint_jsx(src, h["defaults"]) == []


def test_new_never_overwrites_and_checks_the_id(piece, tmp_path):
    eid, _ep, d = piece
    with pytest.raises(custom.CustomError, match="never overwritten"):
        custom.new(eid, "handoff", d / "brief.md")
    with pytest.raises(custom.CustomError, match="insert id"):
        custom.new(eid, "../x", d / "brief.md")
    assert custom.function_name("gpu-handoff") == "gpu_handoff" and custom.function_name("3d") == "c_3d"


NODE_HARNESS = """
var __log = [], __n = 0;
var app = {run: function (id, p) { __log.push([id, p]); return id.indexOf("layer.new") === 0 ? {layer: ++__n} : {}; },
           beginUndoGroup: function () {}, endUndoGroup: function () {}};
%s
console.log(JSON.stringify({result: __R, log: __log}));
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
@pytest.mark.parametrize("fmt,size", [("landscape", [1920, 1080]), ("portrait", [1080, 1920])])
def test_skeleton_runs_as_a_script_in_both_formats(piece, tmp_path, fmt, size):
    """The skeleton as the harness builds it (context, helper library, the comp), run by node with a recording
    stand-in for the engine: an empty ground in the pack's colour and a slow push, sized from the format."""
    _eid, _ep, d = piece
    src = (d / "comp.jsx").read_text()
    ctx = {"format": fmt, "size": size, "fps": 25, "duration": 5.0, "transparent": False,
           "brand": {"mg": {"ground": "#F1F1EF", "drift_pct_per_s": 2.0}}}
    body = f"{src}\nreturn handoff({json.dumps({'comp': 'Main'})});"
    code = wrap_program(body, tp.context_source(ctx) + tp.lib_source() + "\nvar EC_ASSETS = \"\";\n")
    js = tmp_path / f"run-{fmt}.js"
    js.write_text(NODE_HARNESS % code)
    res = subprocess.run(["node", str(js)], capture_output=True, text=True, timeout=60)
    assert res.returncode == 0, res.stderr
    out = json.loads(res.stdout.strip().splitlines()[-1])
    log = out["log"]
    solid = next(p for i, p in log if i == "layer.newSolid")
    assert solid["color"] == "#F1F1EF" and solid["width"] >= size[0] and solid["height"] >= size[1]
    pos = [p["value"] for i, p in log if i == "prop.set" and p["path"] == "transform/position"]
    assert pos[0] == [size[0] / 2, size[1] / 2]
    keys = [p for i, p in log if i == "prop.addKey" and p["path"] == "transform/scale"]
    assert [k["time"] for k in keys] == [0, 5.0]
    assert keys[0]["value"] == [100, 100] and keys[1]["value"][0] == pytest.approx(110.0)
    assert out["result"]["comp"] == "Main" and len(out["result"]["layers"]) == 3


# ---------------------------------------------------------------- check 3: the style-frame card and the gate


def test_style_frame_card_has_two_pictures_per_format(piece, tmp_path):
    eid, ep, d = piece
    ours_l = image(tmp_path / "ours-l.png", (320, 180))
    ours_p = image(tmp_path / "ours-p.png", (180, 320))
    ref = image(tmp_path / "ref-l.png", (320, 180), colours=((20, 20, 20), (200, 30, 60), (30, 120, 200)))
    card = custom.style_frame(eid, "handoff", [str(ours_l), str(ours_p)], [str(ref)])
    assert card["kind"] == "style-frame" and card["status"] == "open"
    assert card["file"] == "motion/handoff/frame-v1-landscape.png" and card["sha256"]
    frames = card["data"]["frames"]
    assert [f["format"] for f in frames] == ["landscape", "portrait"]
    assert frames[0]["ours"] == "motion/handoff/frame-v1-landscape.png"
    assert frames[0]["ref"] == "motion/handoff/refs/ref-l.png", "a reference from outside is copied into refs/"
    assert frames[0]["ours_url"] == f"/api/files/{eid}/motion/handoff/frame-v1-landscape.png"
    assert frames[0]["ref_url"] == f"/api/files/{eid}/motion/handoff/refs/ref-l.png"
    assert frames[1]["ref"] == "motion/handoff/refs/ref-l.png", "one reference serves both formats"
    assert (d / "frame-v1-portrait.png").is_file() and card["data"]["insert"] == "handoff"
    assert len(card["data"]["images"]) >= 2
    again = custom.style_frame(eid, "handoff", [str(ours_l)])
    assert again["data"]["round"] == 2 and again["data"]["frames"][0]["ref_label"] == "reference"


def test_style_frame_refuses_one_hue_unless_natural(piece, tmp_path):
    eid, _ep, _d = piece
    green = image(tmp_path / "green.png", (320, 180), colours=((40, 160, 60),))
    with pytest.raises(custom.CustomError, match="one hue holds"):
        custom.style_frame(eid, "handoff", [str(green)])
    assert custom.style_frame(eid, "handoff", [str(green)], natural=True)["status"] == "open"


def test_style_frame_gate_until_the_yes(piece, tmp_path):
    eid, ep, _d = piece
    why = custom.style_frame_gate(ep, "handoff")
    assert why and "no style frame card yet" in why
    card = custom.style_frame(eid, "handoff", [str(image(tmp_path / "o.png"))])
    assert f"card #{card['id']}" in custom.style_frame_gate(ep, "handoff")
    approvals.decide(card["id"], False, reason="warmer light")
    assert "warmer light" in custom.style_frame_gate(ep, "handoff")
    card2 = custom.style_frame(eid, "handoff", [str(image(tmp_path / "o2.png"))])
    approvals.decide(card2["id"], True)
    assert custom.style_frame_gate(ep, "handoff") is None
    assert custom.pieces_state(ep) == {"handoff": "building"}


def test_style_frame_needs_the_piece(tmp_path):
    eid, _ep = make_episode()
    with pytest.raises(custom.CustomError, match="motion new"):
        custom.style_frame(eid, "nothing", [str(image(tmp_path / "o.png"))])
