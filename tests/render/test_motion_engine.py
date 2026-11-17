"""Motion inserts rendered by the real engine: a pack font file through EFFECTCRAFT_FONT_DIRS, the speaker backdrop's
first frame, an overlay MOV with alpha.

Skipped without effectcraft-cli ($EFFECTCRAFT_CLI or PATH) or ffmpeg. They run in the Crewcut image (CI), never on a
laptop without the engine:
    python -m pytest tests/render/test_motion_engine.py -v
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from motion_helpers import template_src
from PIL import Image, ImageChops, ImageStat
from render_helpers import basic_plan

from crewcut import brand
from crewcut.motion.backend import BackendError, find_effectcraft
from crewcut.render import assemble, media, motion
from crewcut.render.plan import Plan

try:
    find_effectcraft()
except BackendError:
    pytest.skip("effectcraft-cli not found ($EFFECTCRAFT_CLI or PATH)", allow_module_level=True)
if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
    pytest.skip("ffmpeg and ffprobe are needed", allow_module_level=True)

DEJAVU = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")

WORD = """var f = CC.frame(), font = CC.font("display");
  var id = EC.text(P.comp, {text: P.text, size: Math.round(160 * f.u), fill: "#000000", font: font.font,
                            style: font.style, justify: "center", name: "word"});
  EC.set(P.comp, id, "transform/position", [f.W / 2, f.H / 2]);
  return {font: font};"""

BACKDROP = """var k = CC.ctx();
  if (k.backdrop) EC.footage(P.comp, k.backdrop, {name: "speaker"});
  return {backdrop: k.backdrop};"""


def comp(episode_dir: Path, name: str, body: str, kind: str = "full", params: dict | None = None) -> str:
    rel = f"motion/{name}/comp.jsx"
    p = episode_dir / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(template_src(name, kind, ["landscape"], 1, None, params or {"comp": "Main"}, body=body))
    return rel


def ink_width(png: Path) -> int:
    im = Image.open(png).convert("L").point(lambda v: 255 if v < 110 else 0)
    box = im.getbbox()
    assert box, f"no ink in {png}"
    return box[2] - box[0]


def render(plan: Plan) -> dict:
    r = motion.render_motion(plan, location="local", runner=media.run, log=print)
    assert all(row["frames_ok"] and row["clip_ok"] for row in r["rows"]), r
    return r


def test_pack_font_file_changes_the_glyphs(episode, studio, tmp_path):
    if not DEJAVU.is_file():
        pytest.skip("fonts-dejavu-core is not installed")
    rel = comp(episode.dir, "word", WORD, params={"comp": "Main", "text": "Waterfall"})
    widths = {}
    for family, files in (("Inter", []), ("DejaVu Sans", ["fonts/DejaVuSans-Bold.ttf"])):
        pack = tmp_path / family.replace(" ", "")
        (pack / "fonts").mkdir(parents=True)
        if files:
            shutil.copy2(DEJAVU, pack / "fonts" / DEJAVU.name)
        (pack / "brand.json").write_text(json.dumps(
            {"fonts": {"display": {"family": family, "weight": 700, "files": files}}}))
        p = episode(basic_plan(inserts=[{"id": "w1", "kind": "motion", "source": rel, "start": 1.0, "end": 1.2}]),
                    name=f"plan-{family[:3].lower()}.json")
        plan = Plan(p, pack=brand.load(pack))
        render(plan)
        widths[family] = ink_width(plan.by_id("w1").out_dir / "0000.png")
    assert abs(widths["Inter"] - widths["DejaVu Sans"]) > 0.02 * widths["Inter"], widths


def test_speaker_backdrop_first_frame_is_the_speaker_frame(episode, studio):
    base = episode.dir / "work" / "speaker-v001.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=1920x1080:r=25:d=6",
                    "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p", str(base)], check=True)
    rel = comp(episode.dir, "backdrop_check", BACKDROP)
    p = basic_plan(base="work/speaker-v001.mp4", inserts=[
        {"id": "b1", "kind": "motion", "source": rel, "start": 2.0, "end": 3.0, "backdrop": "speaker"}])
    plan = Plan(episode(p))
    render(plan)
    ins = plan.by_id("b1")
    ref = episode.dir / "render" / "speaker-2.0.png"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "2.0", "-i", str(base), "-vf",
                    assemble.speaker_vf(plan, 1.0) + "format=rgb24", "-frames:v", "1", str(ref)], check=True)
    a, b = Image.open(ins.out_dir / "0000.png").convert("RGB"), Image.open(ref).convert("RGB")
    assert a.size == b.size == (1920, 1080)
    diff = sum(ImageStat.Stat(ImageChops.difference(a, b)).mean) / 3
    assert diff < 6.0, f"mean difference {diff:.2f} of 255"


def test_overlay_is_a_mov_with_alpha(episode, studio):
    rel = comp(episode.dir, "word_over", WORD, kind="overlay", params={"comp": "Main", "text": "Local"})
    plan = Plan(episode(basic_plan(inserts=[{"id": "o1", "kind": "motion", "source": rel, "start": 4.0,
                                             "end": 5.6}])))
    render(plan)
    ins = plan.by_id("o1")
    first = Image.open(ins.out_dir / "0000.png")
    assert first.mode == "RGBA" and first.getextrema()[3][0] == 0          # transparent around the word
    out = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
                          "stream=pix_fmt,codec_name,nb_read_frames", "-of", "json", str(ins.clip)],
                         capture_output=True, text=True, check=True).stdout
    s = json.loads(out)["streams"][0]
    assert s["codec_name"] == "qtrle" and s["pix_fmt"] == "argb" and int(s["nb_read_frames"]) == ins.render_frames
