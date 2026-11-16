"""Layout "proof-top" (portrait Shorts): where the layout comes from, place/fit/anchor, keyword chips left of the free
right strip, the stacked pieces (stage above, speaker below), the face-alone end, and one real ffmpeg run of a stacked
piece on tiny generated clips."""

import json
import shutil
import subprocess

import pytest
from render_helpers import FakeRunner, basic_plan

from crewcut import brand
from crewcut.render import assemble, media
from crewcut.render.plan import STAGE_HEIGHT, Plan, PlanError

FFMPEG = shutil.which("ffmpeg") and shutil.which("ffprobe")


def short_plan(**over) -> dict:
    """12 s portrait plan: a counter on the stage, a landscape clip as a card, a keyword over everything."""
    p = basic_plan(format="portrait", layout="proof-top", base="work/speaker.mp4", face=[0.5, 0.3])
    p["inserts"] = [
        {"id": "s1", "kind": "2d", "scene": "counter", "start": 1.0, "end": 3.0, "data": {"label": "Cost", "value": "30"}},
        {"id": "c1", "kind": "clip", "file": "broll/render3d.mp4", "start": 4.0, "end": 6.0, "fit": "contain"},
        {"id": "w1", "kind": "clip", "file": "broll/page.mp4", "start": 8.0, "end": 11.0, "anchor": "top"},
        {"id": "k1", "kind": "2d", "scene": "keyword", "start": 1.5, "end": 2.5, "transparent": True,
         "data": {"text": "30 CENTS"}},
    ]
    p.update(over)
    return p


@pytest.fixture
def short(episode):
    ep = episode.dir
    (ep / "broll").mkdir()
    for f in ("work/speaker.mp4", "broll/render3d.mp4", "broll/page.mp4"):
        (ep / f).write_bytes(b"x")
    return episode


def test_layout_comes_from_plan_then_pack_and_is_portrait_only(short, studio):
    assert Plan(short(basic_plan())).layout == "full"                                  # landscape
    assert Plan(short(basic_plan(format="portrait"), "plan-v002.json")).layout == "full"  # neutral pack: full
    plan = Plan(short(short_plan(), "plan-v003.json"))
    assert plan.layout == "proof-top" and plan.summary()["layout"] == "proof-top"
    assert [(x.id, x.place) for x in plan.inserts] == [("s1", "top"), ("c1", "top"), ("w1", "top"), ("k1", "full")]
    assert (plan.by_id("c1").fit, plan.by_id("w1").anchor, plan.by_id("s1").fit) == ("contain", "top", "cover")
    with pytest.raises(PlanError, match="for portrait plans"):
        Plan(short(basic_plan(layout="proof-top"), "plan-v004.json"))
    with pytest.raises(PlanError, match="layout must be"):
        Plan(short(basic_plan(format="portrait", layout="split"), "plan-v005.json"))
    bad = basic_plan(format="portrait")
    bad["inserts"][0]["place"] = "top"
    with pytest.raises(PlanError, match="needs layout proof-top"):
        Plan(short(bad, "plan-v006.json"))
    bad = short_plan()
    bad["inserts"][0]["fit"] = "stretch"
    with pytest.raises(PlanError, match="fit must be"):
        Plan(short(bad, "plan-v007.json"))
    # a pack that wants proof-top for Shorts: portrait plans follow it, landscape plans stay full
    (studio / "brand").mkdir()
    (studio / "brand" / "brand.json").write_text(json.dumps({"name": "Mine"}))
    (studio / "brand" / "edit-style.json").write_text(json.dumps({"shorts": {"layout": "proof-top", "end_face_s": 3}}))
    pack = brand.load()
    assert Plan(short(basic_plan(format="portrait"), "plan-v008.json"), pack=pack).layout == "proof-top"
    assert Plan(short(basic_plan(format="portrait"), "plan-v008.json"), pack=pack).end_face_s == 3.0
    assert Plan(short(basic_plan(), "plan-v009.json"), pack=pack).layout == "full"
    assert Plan(short(basic_plan(format="portrait", layout="full"), "plan-v010.json"), pack=pack).layout == "full"


def test_keyword_chips_stay_left_of_the_free_strip(short):
    full = Plan(short(basic_plan(format="portrait")))
    k = full.by_id("k1").data
    assert k["x"] == 0.41 and k["max_width"] == 0.74 and "y" not in k       # (1 - 0.18) / 2, 0.82 - 2 x 0.04
    assert not full.warnings
    top = Plan(short(short_plan(), "plan-v002.json"))
    assert top.by_id("k1").data["y"] == STAGE_HEIGHT / 1920                  # on the seam between stage and face
    p = basic_plan(format="portrait")
    p["inserts"][1]["data"] = {"words": [{"text": "A"}, {"text": "B", "x": 0.9}]}
    plan = Plan(short(p, "plan-v003.json"))
    assert [w["x"] for w in plan.by_id("k1").data["words"]] == [0.41, 0.9]
    assert any("right 18%" in w for w in plan.warnings)
    land = Plan(short(basic_plan(), "plan-v004.json")).by_id("k1").data
    assert "x" not in land and "max_width" not in land                       # landscape keeps the template's place


def test_stacked_pieces_and_face_alone_end(short):
    plan = Plan(short(short_plan(speaker=[{"at": 5.0, "zoom": 1.1}])))
    ps = assemble.pieces(plan, base_end=300, end=300)
    by = {(p.a, p.b): p for p in ps}
    s1 = by[(25, 38)]
    assert s1.label == "s1 (stage)" and s1.size == (1080, STAGE_HEIGHT) and s1.overlays == []
    assert s1.vf == "scale=1080:960:force_original_aspect_ratio=increase:flags=lanczos,crop=1080:960:(iw-1080)/2:(ih-960)/2,"
    low = s1.low
    assert low.source == "base" and low.size == (1080, 960) and low.seek == 1.0
    # face at 0.3 of 1920 = 576; the 960 px part around it starts at 576 - 480 = 96
    assert low.vf.endswith("crop=1080:960:(iw-1080)*0.5:96,")
    assert by[(38, 62)].overlays                                             # the keyword lies over the stack
    c1 = by[(100, 125)]
    assert "force_original_aspect_ratio=decrease" in c1.vf and "pad=1080:960:(ow-iw)/2:(oh-ih)/2:color=0xF1F1EF," in c1.vf
    assert "scale=iw*1.1:-2" in by[(125, 150)].low.vf and by[(125, 150)].low.vf.endswith(":153,")
    w1 = by[(200, 250)]
    assert w1.vf.endswith("crop=1080:960:(iw-1080)/2:0,")                   # anchor top keeps the top of the page
    # the last 2 s (end_face) show the face alone: w1 (8-11 s) stops at 10 s
    end = by[(250, 300)]
    assert end.low is None and end.source == "base" and end.label == "speaker x1.1"
    assert assemble.stage_notes(plan, 300) == ["w1: the stage stops at 10.00 s, the last 2 s show the face alone"]
    assert [s["what"] for s in assemble.shots(plan, 300, 300)][-2:] == ["w1", "speaker"]
    assert assemble.shots(plan, 300, 300)[-1]["frame"] == 250


def test_stacked_command_and_cache_key(short):
    plan = Plan(short(short_plan()))
    ps = assemble.pieces(plan, 300, 300)
    piece = next(p for p in ps if p.a == 38)                                 # stage + speaker + keyword overlay
    cmd = assemble.piece_cmd(plan, piece, short.dir / "x.mkv")
    assert cmd.count("-i") == 3
    ins = [cmd[i + 1] for i, c in enumerate(cmd) if c == "-i"]
    assert ins == [str(plan.by_id("s1").clip), str(short.dir / "work" / "speaker.mp4"), str(plan.by_id("k1").clip)]
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert "[st];[1:v]scale=1080:1920" in fc and "[lo];[st][lo]vstack=inputs=2[b0]" in fc
    assert ";[2:v]fps=25,tpad=stop_mode=clone:stop_duration=1[u0];[b0][u0]overlay=format=auto[b1]" in fc
    assert fc.endswith("[b1]format=yuv420p[v]")
    flat = assemble.Piece(piece.index, piece.a, piece.b, piece.label, piece.source, piece.path, piece.seek, piece.vf,
                          piece.overlays)
    assert assemble.piece_key(flat) != assemble.piece_key(piece)            # the speaker part is in the key
    # a generated background under the stage is a colour source of the part's size
    col = Plan(short(short_plan(base={"color": "soft", "seconds": 12}), "plan-v002.json"))
    p = next(x for x in assemble.pieces(col, 300, 300) if x.a == 25)
    cmd = assemble.piece_cmd(col, p, short.dir / "y.mkv")
    assert cmd[cmd.index("lavfi") + 2].startswith("color=c=0xF1F1EF:s=1080x960:r=25:")


def test_full_layout_has_no_stack(short):
    plan = Plan(short(basic_plan(format="portrait", base="work/speaker.mp4")))
    ps = assemble.pieces(plan, 300, 300)
    assert all(p.low is None for p in ps) and next(p for p in ps if p.label == "s1").vf == ""
    assert "vstack" not in " ".join(assemble.piece_cmd(plan, ps[1], short.dir / "z.mkv"))


def test_cut_reports_layout_and_stage_notes(short):
    plan = Plan(short(short_plan(base={"color": "soft", "seconds": 12})))
    for ins in plan.inserts:
        if ins.kind == "2d":
            ins.out_dir.mkdir(parents=True, exist_ok=True)
            for i in range(ins.render_frames):
                (ins.out_dir / f"{i:04d}.png").write_bytes(b"x")
            ins.clip.write_bytes(b"clip")
    info = assemble.cut(plan, FakeRunner(lufs=-16.0, peaks=[-2.0]), log=lambda *a: None)
    assert info["layout"] == "proof-top" and any("face alone" in n for n in info["notes"])


@pytest.mark.skipif(not FFMPEG, reason="ffmpeg is not installed")
def test_stacked_piece_runs_in_ffmpeg(short):
    ff, ep = shutil.which("ffmpeg"), short.dir
    subprocess.run([ff, "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=1080x1920:r=25:d=0.4", "-pix_fmt",
                    "yuv420p", str(ep / "work" / "speaker.mp4")], check=True)
    subprocess.run([ff, "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=s=640x360:r=25:d=0.4", "-pix_fmt",
                    "yuv420p", str(ep / "broll" / "render3d.mp4")], check=True)
    p = short_plan(speaker=[{"at": 0.12, "zoom": 1.1}], end_face=0.0)
    p["inserts"] = [{"id": "c1", "kind": "clip", "file": "broll/render3d.mp4", "start": 0.0, "end": 0.2, "fit": "contain"},
                    {"id": "c2", "kind": "clip", "file": "broll/render3d.mp4", "start": 0.2, "end": 0.4}]
    plan = Plan(short(p))
    for piece in assemble.pieces(plan, 10, 10):
        out = ep / f"piece{piece.index}.mkv"
        rc, text = media.run(assemble.piece_cmd(plan, piece, out))
        assert rc == 0, text
        size = subprocess.run([shutil.which("ffprobe"), "-v", "error", "-show_entries", "stream=width,height",
                               "-of", "csv=p=0", str(out)], capture_output=True, text=True).stdout.strip()
        assert size == "1080,1920" and piece.low is not None
