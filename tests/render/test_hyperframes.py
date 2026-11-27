"""HyperFrames building blocks without HyperFrames: templates, the studio style in the built project, the plan's 2D
inserts with scene hf-<name>, the frames a fake renderer writes. No browser, no Node."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from PIL import Image
from render_helpers import FakeRunner

from crewcut import brand
from crewcut.render import html
from crewcut.render import hyperframes as hf
from crewcut.render.plan import Plan, PlanError

TYPES = {"keyword": "a", "card": "b", "chapter": "c", "diagram": "d", "snippet": "e"}


def pack_with_palette(tmp_path: Path, highlight: str = "#FFE600") -> brand.Pack:
    d = tmp_path / "brand"
    d.mkdir(exist_ok=True)
    (d / "brand.json").write_text(json.dumps({"colors": {"ink": "#141413", "paper": "#FAF9F5", "accent": "#2320D6"}}))
    (d / "channel.json").write_text(json.dumps({"graphics": {"palette": {
        "ink": "#141413", "paper": "#FAF9F5", "accent": "#2320D6", "highlight": highlight}}}))
    (d / "edit-style.json").write_text(json.dumps({"graphics": {"safe_area": {
        "portrait": {"top": 288, "bottom": 672, "left": 48, "right": 192}}, "text": {"min_px_short": 48}},
        "min_text_px": 54}))
    return brand.load(d)


def test_five_templates_one_per_graphic_type():
    rows = {r["name"]: r for r in hf.listing()}
    assert {n: r["type"] for n, r in rows.items() if n in TYPES} == TYPES
    for n, r in rows.items():
        assert r["scene"] == f"hf-{n}" and r["kind"] in hf.KINDS
        assert set(r["formats"]) == {"landscape", "portrait"}
        folder = hf.find(n)
        src = (folder / "index.html").read_text()
        assert "<!--CC:HEAD-->" in src and 'data-composition-id="main"' in src and 'class="clip"' in src
        assert "Date.now" not in src and "Math.random" not in src and "fetch(" not in src
        # no icon look, no foreign font names, no fixed brand colours inside a template
        assert not re.search(r"#[0-9A-Fa-f]{6}\b", src.split("<script>")[-1]), n
        assert "Manrope" not in src and "<svg" not in src.split("<script>")[0]


def test_build_project_inlines_the_studio_style(tmp_path):
    pack = pack_with_palette(tmp_path)
    folder = hf.find("keyword", pack)
    ctx = hf.context(fmt="portrait", size=(1080, 1920), fps=25, frames=52, transparent=True, cues={"land": 0.8},
                     face={"x": 0.4, "y": 0.3, "w": 0.3, "h": 0.25}, pack=pack)
    out = hf.build_project(folder, tmp_path / "p", hf.merge_params(hf.manifest(folder), {"words": ["Kosten"]}), ctx, pack)
    page = (out / "index.html").read_text()
    assert "<!--CC:HEAD-->" not in page
    assert 'data-width="1080"' in page and 'data-height="1920"' in page and 'data-duration="2.08"' in page
    assert "--cc-highlight: #FFE600;" in page and "--cc-accent: #2320D6;" in page
    assert "cubic-bezier(0.2, 0, 0, 1)" in page and "cubic-bezier(0.3, 0, 0.8, 0.15)" in page
    data = json.loads(re.search(r"window\.CC_DATA = (\{.*?\});</script>", page, re.S).group(1))
    assert data["data"]["words"] == ["Kosten"] and data["cues"] == {"land": 0.8} and data["min_text_px"] == 48
    # the Short's safe zone in pixels: 48 left, 192 right, 288 top, 672 bottom
    assert data["safe"] == {"x": 48, "y": 288, "w": 1080 - 48 - 192, "h": 1920 - 288 - 672}
    assert "window.CC = CC" in page and "gsap.timeline" in page


def test_overlay_keeps_the_player_bar_free_in_16_9(tmp_path):
    pack = pack_with_palette(tmp_path)
    opaque = hf.safe_box("landscape", (1920, 1080), pack=pack)
    over = hf.safe_box("landscape", (1920, 1080), pack=pack, transparent=True)
    assert opaque["x"] == 96 and opaque["y"] == 54 and over["y"] + over["h"] == 1080 - round(0.08 * 1080)


def test_fonts_of_the_pack_are_copied_with_font_face(tmp_path):
    pack = pack_with_palette(tmp_path)
    (pack.dir / "fonts").mkdir()
    (pack.dir / "fonts" / "Display.otf").write_bytes(b"font")
    bj = json.loads((pack.dir / "brand.json").read_text())
    bj["fonts"] = {"display": {"family": "Manrope", "weight": 800, "files": ["fonts/Display.otf"]}}
    (pack.dir / "brand.json").write_text(json.dumps(bj))
    pack = brand.load(pack.dir)
    folder = hf.find("chapter", pack)
    ctx = hf.context(fmt="landscape", size=(1920, 1080), fps=25, frames=80, transparent=False, pack=pack)
    out = hf.build_project(folder, tmp_path / "p", hf.merge_params(hf.manifest(folder), {}), ctx, pack)
    assert (out / "assets" / "fonts" / "Display.otf").is_file()
    page = (out / "index.html").read_text()
    assert '@font-face { font-family: "Manrope"; font-weight: 800;' in page and 'url("assets/fonts/Display.otf")' in page


def test_unknown_params_are_refused():
    m = hf.manifest(hf.find("card"))
    with pytest.raises(hf.HyperFramesError, match="titel"):
        hf.merge_params(m, {"titel": "typo"})
    assert hf.merge_params(m, {"title": "A", "format": "landscape", "frames": 9})["title"] == "A"


def plan_with(episode, **ins) -> Path:
    e = {"id": "k1", "kind": "2d", "scene": "hf-keyword", "start": 1.0, "end": 3.0, "transparent": True,
         "cues": {"land": {"word": "thirty"}}, "data": {"words": ["30 Cent"]}}
    e.update(ins)
    return episode({"words": "work/words-v001.json", "base": {"color": "soft", "seconds": 12}, "inserts": [e],
                    "sound": {}, "output": "export/out-v001.mp4"})


def test_a_plan_uses_a_template_as_a_2d_insert(episode):
    plan = Plan(plan_with(episode))
    ins = plan.by_id("k1")
    assert ins.kind == "2d" and ins.scene == "hf-keyword" and ins.transparent and hf.is_hf(ins)
    assert ins.template.name == "index.html" and ins.template.parent.name == "keyword"
    assert ins.cues == {"land": 25} and ins.clip.suffix == ".mov"
    assert any(p.name == "cc.js" for p in ins.shared)


def test_the_hash_follows_the_template_and_the_style(episode, monkeypatch):
    h1 = Plan(plan_with(episode)).by_id("k1").hash
    assert Plan(plan_with(episode)).by_id("k1").hash == h1
    assert Plan(plan_with(episode, data={"words": ["31 Cent"]})).by_id("k1").hash != h1
    monkeypatch.setattr(hf, "pinned_version", lambda: "9.9.9")
    assert Plan(plan_with(episode)).by_id("k1").hash != h1


@pytest.mark.parametrize("bad, why", [
    ({"scene": "hf-nothing"}, "no HyperFrames template"),
    ({"data": {"wrods": ["x"]}}, "wrods"),
    ({"cues": {"later": 3}}, "cue later"),
])
def test_plan_errors_name_the_problem(episode, bad, why):
    with pytest.raises(PlanError, match=why):
        Plan(plan_with(episode, **bad))


class HFRunner(FakeRunner):
    """Writes HyperFrames' frame_000001.png ... into the -o folder (RGBA when transparent is asked)."""

    def __init__(self, frames_out: int | None = None, **kw):
        super().__init__(**kw)
        self.frames_out = frames_out

    def __call__(self, cmd, timeout=600, cwd=None):
        cmd = [str(c) for c in cmd]
        if len(cmd) > 1 and cmd[1] == "render" and "--format" in cmd:
            self.calls.append(cmd)
            project, out = Path(cmd[2]), Path(cmd[cmd.index("-o") + 1])
            page = (project / "index.html").read_text()
            data = json.loads(re.search(r"window\.CC_DATA = (\{.*?\});</script>", page, re.S).group(1))
            n = self.frames_out if self.frames_out is not None else data["frames"]
            if "--start" in cmd:
                n = 1
            out.mkdir(parents=True, exist_ok=True)
            for i in range(n):
                Image.new("RGBA", tuple(data["size"]), (0, 0, 0, 0)).save(out / f"frame_{i + 1:06d}.png")
            return 0, "Render complete"
        return super().__call__(cmd, timeout, cwd)


def test_render_writes_the_frames_and_encodes_an_alpha_clip(episode, monkeypatch):
    monkeypatch.setattr(hf, "cli", lambda: "/fake/hyperframes")
    plan = Plan(plan_with(episode))
    r = HFRunner()
    rows = html.render_2d(plan, runner=r, log=lambda *a: None)
    ins = plan.by_id("k1")
    assert rows[0]["frames_ok"] and rows[0]["clip_ok"] and not plan.missing(ins)
    render = r.find("/fake/hyperframes")[0]
    assert render[render.index("--format") + 1] == "png-sequence" and render[render.index("--fps") + 1] == "25"
    enc = r.find("qtrle")[0]
    assert "argb" in enc and enc[-1].endswith(".mov")
    project = Path(render[2])
    assert "#FFE600" not in (project / "index.html").read_text()      # the neutral pack has no highlight of its own


def test_a_dropped_last_frame_is_held_and_too_few_frames_fail(episode, monkeypatch):
    monkeypatch.setattr(hf, "cli", lambda: "/fake/hyperframes")
    plan = Plan(plan_with(episode))
    ins = plan.by_id("k1")
    assert html.render_insert(plan, ins, HFRunner(frames_out=ins.render_frames - 1), log=lambda *a: None)
    plan2 = Plan(plan_with(episode, data={"words": ["neu"]}))
    ins2 = plan2.by_id("k1")
    lines = []
    assert not html.render_insert(plan2, ins2, HFRunner(frames_out=3), log=lines.append)
    assert "3 of" in lines[-1]


def test_without_hyperframes_one_sentence_and_the_rest_still_renders(episode, monkeypatch):
    monkeypatch.delenv("CREWCUT_HYPERFRAMES", raising=False)
    monkeypatch.setattr(hf, "tool_dir", lambda: Path("/nowhere"))
    monkeypatch.setattr(hf.shutil, "which", lambda name: None)
    assert not hf.available()
    plan = Plan(plan_with(episode))
    lines = []
    assert not html.render_insert(plan, plan.by_id("k1"), HFRunner(), log=lines.append)
    assert "HyperFrames is not installed here" in lines[-1]


def test_still_renders_one_frame(episode, monkeypatch, tmp_path):
    monkeypatch.setattr(hf, "cli", lambda: "/fake/hyperframes")
    plan = Plan(plan_with(episode))
    r = HFRunner()
    p = html.still(plan, plan.by_id("k1"), 20, tmp_path, runner=r)
    assert p and p.is_file() and Image.open(p).size == (960, 540)
    cmd = r.find("/fake/hyperframes")[0]
    assert float(cmd[cmd.index("--start") + 1]) == pytest.approx(0.8)


def test_env_turns_off_telemetry_and_names_the_browser(monkeypatch, tmp_path):
    fake = tmp_path / "chrome-headless-shell"
    fake.write_text("")
    monkeypatch.setenv("HYPERFRAMES_BROWSER_PATH", str(fake))
    e = hf.env()
    assert e["HYPERFRAMES_NO_TELEMETRY"] == "1" and e["DO_NOT_TRACK"] == "1" and e["HYPERFRAMES_NO_UPDATE_CHECK"] == "1"
    assert e["HYPERFRAMES_BROWSER_PATH"] == str(fake) and e["HYPERFRAMES_CHROME_SANDBOX"] == "0"


def test_the_pin_is_exact():
    v = hf.pinned_version()
    assert re.fullmatch(r"\d+\.\d+\.\d+", v), v
    lock = json.loads((hf.tool_dir() / "package-lock.json").read_text())
    assert lock["packages"]["node_modules/hyperframes"]["version"] == v


def test_director_knows_the_templates_as_2d_scenes():
    from crewcut.motion import director
    sc = director.scenes()
    assert sc["hf-keyword"] == {"render": "2d", "kind": "overlay", "library": "hyperframes"}
    assert sc["hf-chapter"]["kind"] == "full"
