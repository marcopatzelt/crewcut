"""The Critic's review bundle for motion inserts (crewcut/motion/review.py) and the machine checks
(skills/cut-check/scripts/motion_check.py). Frames are made with Pillow and numpy; the engine is a fake."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFilter

from crewcut import brand
from crewcut.motion import density as dens
from crewcut.motion import review as rv

APP = Path(__file__).resolve().parents[2]
NEUTRAL = APP / "packs" / "neutral"
W, H, FPS = 320, 180, 25
PALETTE = [(228, 87, 46), (47, 111, 222), (242, 184, 75), (59, 165, 139)]


def _script(rel: str, name: str):
    path = APP / "skills" / rel
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


mc = _script("cut-check/scripts/motion_check.py", "review_motion_check")
sc = _script("cut-check/scripts/style_check.py", "review_style_check")

CLEAN_JSX = """/* @template gpu_handoff
   @description Four jobs leave the laptop, one card lights up.
   @kind full
   @formats ["landscape", "portrait", "stage"]
   @version 1
   @params {"comp": "Main", "jobs": 4, "landAt": 1.2}
   @end */
function gpu_handoff(P) {
  var F = CC.frame(), f = CC.font("display");
  var t = EC.text(P.comp, {text: "GPU", font: f.font, style: f.style, size: CC.px(140), fill: CC.ink(),
                           position: [F.safe.x + F.safe.w / 2, F.safe.y + F.safe.h / 2]});
  var ring = EC.shape(P.comp, {kind: "ellipse", size: [CC.px(300), CC.px(300)], fillOpacity: 0, stroke: CC.color(1)});
  return {comp: P.comp, layers: [t, ring]};
}
"""

BOXED_JSX = """/* @template boxed
   @params {"comp": "Main", "word": "offline"}
   @end */
function boxed(P) {
  var w = EC.text(P.comp, {text: P.word, size: CC.px(140), font: CC.font().font});
  var chip = EC.shape(P.comp, {kind: "rect", size: [400, 160], roundness: 40, fill: CC.color(0), parent: w});
  var back = EC.solid(P.comp, {name: "bg", color: "#ffffff", w: 1920, h: 200});
  EC.parent(P.comp, back, w);
  EC.fx(P.comp, w, "Temporal Motion Blur", {});
  var t2 = EC.text(P.comp, {text: "x", font: "Manrope", size: 30});
  return {comp: P.comp};
}
"""


# ---------------------------------------------------------------- synthetic episode


def ground_frame(i: int, w: int = W, h: int = H) -> Image.Image:
    """A calm full frame: light ground, four colour blocks of equal size, fine type-like marks, a slow push."""
    im = Image.new("RGB", (w, h), (241, 241, 239))
    d = ImageDraw.Draw(im)
    s = i % 7
    for k, c in enumerate(PALETTE):
        x = 20 + k * 72 + s
        d.rectangle([x, 50, x + 50, 110], fill=c)
    for k in range(12):
        d.line([30 + k * 22 + s, 130, 40 + k * 22 + s, 150], fill=(20, 20, 20), width=2)
    d.text((40 + s, 20), "four jobs leave", fill=(17, 17, 17))
    return im


def overlay_frame(i: int, box: tuple[int, int, int, int], w: int = W, h: int = H) -> Image.Image:
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    x0, y0, x1, y1 = box
    s = i % 5
    d.rectangle([x0 + s, y0, x1 + s, y1], fill=(255, 255, 255, 255))
    d.text((x0 + 4 + s, y0 + 4), "runs offline", fill=(17, 17, 17, 255))
    return im


def write_frames(ep: Path, iid: str, images: list[Image.Image], h: str = "abcdef1234") -> Path:
    d = ep / "render" / "inserts" / f"{iid}-{h}"
    d.mkdir(parents=True, exist_ok=True)
    for k, im in enumerate(images):
        im.save(d / f"{k:04d}.png")
    return d


def words_for(seconds: float) -> list[dict]:
    """A sentence every 8 s: 'Point N here.' with three words."""
    out, t, n = [], 1.0, 0
    while t < seconds:
        n += 1
        out += [{"w": "Point", "s": t, "e": t + 0.3}, {"w": f"n{n}", "s": t + 0.4, "e": t + 0.7},
                {"w": "here.", "s": t + 0.8, "e": t + 1.1}]
        t += 8.0
    return out


def episode(tmp_path: Path, inserts: list[dict], seconds: float = 120.0, jsx: dict | None = None,
            name: str = "003-demo", **plan_extra) -> Path:
    ep = tmp_path / name
    (ep / "edit").mkdir(parents=True)
    (ep / "work").mkdir()
    (ep / "work" / "words.json").write_text(json.dumps(words_for(seconds)))
    for rel, src in (jsx or {}).items():
        p = ep / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(src)
    plan = {"format": "landscape", "fps": FPS, "words": "work/words.json", "face": [0.5, 0.38], "tail": 1.0,
            "inserts": inserts, **plan_extra}
    p = ep / "edit" / "plan-v001.json"
    p.write_text(json.dumps(plan))
    return p


def clean_insert(iid: str = "m1", start: float = 24.0, end: float = 28.0) -> dict:
    return {"id": iid, "kind": "motion", "source": f"motion/{iid}/comp.jsx", "start": start, "end": end,
            "transparent": False, "data": {"jobs": 4}, "cues": {"landAt": {"word": "n4"}}, "beat": 4, "column": "b"}


def pack():
    return brand.load(NEUTRAL)


def build(plan: Path, **kw):
    kw.setdefault("backend", False)
    kw.setdefault("log", lambda *_: None)
    return rv.build_bundle(plan, pack=pack(), **kw)


def levels(summary: dict, insert: str | None = None) -> dict[str, str]:
    return {f["id"]: f["level"] for f in summary["findings"] if insert is None or f.get("insert") == insert}


def errors(summary: dict) -> list[str]:
    return [f["id"] for f in summary["findings"] if f["level"] == "ERROR"]


# ---------------------------------------------------------------- the clean insert and the file list


def test_clean_insert_passes_and_bundle_has_every_file(tmp_path):
    plan = episode(tmp_path, [clean_insert()], jsx={"motion/m1/comp.jsx": CLEAN_JSX})
    ep = plan.parent.parent
    write_frames(ep, "m1", [ground_frame(i) for i in range(100)])
    s = build(plan)
    assert errors(s) == []
    b = Path(s["bundle"])
    assert b == ep / "review" / "motion-v001"
    files = sorted(p.relative_to(b).as_posix() for p in b.rglob("*") if p.is_file())
    web = [f"m1/web-look/{k:02d}.jpg" for k in range(1, 9)]
    assert files == sorted(["bundle.json", "critic.md", "m1/compare.jpg", "m1/density.json", "m1/hue.json",
                            "m1/lint.json", "m1/sharp.json", "m1/sheet.jpg", "m1/text.json", "m1/web-look.md", *web])
    # no engine: the strips and text sizes are skipped with a clear line
    assert s["engine"] is False and "--no-engine" in s["engine_note"]
    assert any("strips" in x for x in s["inserts"][0]["skipped"])
    lv = levels(s, "m1")
    assert lv["frozen:m1"] == "OK" and lv["sharp:m1"] == "OK" and lv["hue:m1"] == "OK"
    assert lv["lint:m1"] == "OK"
    with Image.open(b / "m1" / "sheet.jpg") as im:     # 4 s every 0.25 s = 16 cells, 4 columns
        assert im.width == 4 * rv.CELL_W + 3 * 4
    hue = json.loads((b / "m1" / "hue.json").read_text())
    assert [r["t"] for r in hue["times"]] == [0.4, 1.2, 2.0, 2.8, 3.6]
    sharp = json.loads((b / "m1" / "sharp.json").read_text())
    assert sharp["frames"] == 100 and len(sharp["per_frame"]) == 100
    dj = json.loads((b / "m1" / "density.json").read_text())
    assert dj["counts"]["motion"] == 1 and dj["this"]["id"] == "m1"
    assert dj["limits_from"].startswith("neutral")
    md = (b / "m1" / "web-look.md").read_text()
    for q in rv.WEB_QUESTIONS:
        assert md.count(q) == 8
    critic = (b / "critic.md").read_text()
    assert "What the reference still does better (required" in critic
    assert "What I cannot check: sound" in critic and "0:24.0  m1 in" in critic
    assert "0:25.4  m1 cue landAt" in critic
    assert rv.RATCHET in critic and "never reviews its own work" in critic
    assert "compare.jpg shows ours only" in " ".join(s["inserts"][0]["skipped"])
    # motion_check on the plan and on the bundle: no ERROR
    assert mc.main([str(plan), "--pack", str(NEUTRAL)]) == 0
    assert mc.main([str(b)]) == 0
    assert (b / "motion-check.json").is_file()


def test_bundle_numbering_and_ids(tmp_path):
    plan = episode(tmp_path, [clean_insert("m1"), clean_insert("m2", 60.0, 64.0)],
                   jsx={"motion/m1/comp.jsx": CLEAN_JSX, "motion/m2/comp.jsx": CLEAN_JSX})
    ep = plan.parent.parent
    s1 = build(plan)
    assert Path(s1["bundle"]).name == "motion-v001" and [r["id"] for r in s1["inserts"]] == ["m1", "m2"]
    s2 = build(plan, ids="m2")
    assert Path(s2["bundle"]).name == "motion-v002" and [r["id"] for r in s2["inserts"]] == ["m2"]
    assert s2["rounds"] == {"m2": 2}
    (ep / "review" / "motion-v007").mkdir()
    assert Path(build(plan, ids=["m1"])["bundle"]).name == "motion-v008"
    assert rv.next_version(ep / "review") == 9
    with pytest.raises(rv.ReviewError, match="no motion insert with id zz"):
        build(plan, ids=["zz"])
    # no frames: only lint, text and density; a CHECK says why
    lv = levels(s1, "m1")
    assert lv["frames:m1"] == "CHECK"
    assert sorted(s1["inserts"][0]["files"]) == ["density.json", "lint.json", "text.json"]


def test_cue_outside_the_insert(tmp_path):
    ins = clean_insert()
    ins["cues"] = {"landAt": {"word": "n6"}}                     # 41.4 s, the insert ends at 28 s
    plan = episode(tmp_path, [ins], jsx={"motion/m1/comp.jsx": CLEAN_JSX})
    assert levels(build(plan))["cue:m1:landAt"] == "CHECK"


def test_rounds_over_three_ask_the_user(tmp_path):
    plan = episode(tmp_path, [clean_insert()], jsx={"motion/m1/comp.jsx": CLEAN_JSX})
    for _ in range(3):
        build(plan)
    s = build(plan)
    assert s["rounds"]["m1"] == 4 and levels(s)["rounds:m1"] == "CHECK"
    assert "the Showrunner asks the user" in (Path(s["bundle"]) / "critic.md").read_text()


def test_main_writes_the_bundle(tmp_path, capsys):
    plan = episode(tmp_path, [clean_insert()], jsx={"motion/m1/comp.jsx": CLEAN_JSX})
    assert rv.main([str(plan), "--no-engine"]) == 0
    out = capsys.readouterr().out
    assert "motion-v001" in out and "Result:" in out
    assert rv.main([str(plan), "--no-engine", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["version"] == "v002"
    assert rv.main([str(plan), "--ids", "nope", "--no-engine"]) == 2


def test_missing_engine_is_a_clear_line(tmp_path, monkeypatch):
    class NoEngine:
        @property
        def binary(self):
            raise rv.BackendError("not found")

    monkeypatch.setattr(rv, "Backend", NoEngine)
    plan = episode(tmp_path, [clean_insert()], jsx={"motion/m1/comp.jsx": CLEAN_JSX})
    s = rv.build_bundle(plan, pack=pack(), log=lambda *_: None)
    assert s["engine_note"] == rv.ENGINE_SKIP and "effectcraft-cli not found" in rv.ENGINE_SKIP
    assert rv.ENGINE_SKIP in (Path(s["bundle"]) / "critic.md").read_text()
    text = json.loads((Path(s["bundle"]) / "m1" / "text.json").read_text())
    assert text["engine"] is False and text["note"] == rv.ENGINE_SKIP


# ---------------------------------------------------------------- planted faults


def test_frozen_hold(tmp_path):
    plan = episode(tmp_path, [clean_insert()], jsx={"motion/m1/comp.jsx": CLEAN_JSX})
    ep = plan.parent.parent
    frames = [ground_frame(i) for i in range(100)]
    for k in range(40, 56):                        # 16 identical frames = 0.6 s at 25 fps
        frames[k] = ground_frame(40)
    write_frames(ep, "m1", frames)
    s = build(plan)
    fz = [f for f in s["findings"] if f["id"].startswith("frozen:m1@")]
    assert len(fz) == 1 and fz[0]["level"] == "ERROR" and "the camera stopped" in fz[0]["text"]
    assert fz[0]["time"] == pytest.approx(24.0 + 40 / FPS)
    sharp = json.loads((Path(s["bundle"]) / "m1" / "sharp.json").read_text())
    assert sharp["frozen"] == [{"first": 40, "last": 55, "from": 1.6, "to": 2.2}]


def test_frozen_runs_unit():
    d = [1.0] * 5 + [0.0] * 13 + [1.0] * 5
    assert rv.frozen_runs(d, [True] * 24, 25) == [(5, 18)]
    assert rv.frozen_runs([0.0] * 12, [True] * 13, 25) == []          # 0.48 s: not yet
    assert rv.frozen_runs([0.0] * 20, [False] * 21, 25) == []         # an overlay before it enters


def test_blurry_frame_run(tmp_path):
    plan = episode(tmp_path, [clean_insert()], jsx={"motion/m1/comp.jsx": CLEAN_JSX})
    ep = plan.parent.parent
    frames = [ground_frame(i) for i in range(100)]
    for k in range(50, 56):                        # 6 blurry frames in the hold
        frames[k] = frames[k].filter(ImageFilter.GaussianBlur(4))
    frames[70] = frames[70].filter(ImageFilter.GaussianBlur(4))   # one dip: look at it
    write_frames(ep, "m1", frames)
    s = build(plan)
    lv = levels(s, "m1")
    assert lv["sharp:m1@2.00"] == "ERROR"
    assert lv["sharp:m1@2.80"] == "CHECK"
    # inside the entrance window blur is expected
    frames2 = [ground_frame(i) for i in range(100)]
    for k in range(0, 8):
        frames2[k] = frames2[k].filter(ImageFilter.GaussianBlur(4))
    write_frames(ep, "m1", frames2, h="bbbbbb2222")
    assert not [f for f in build(plan)["findings"] if f["id"].startswith("sharp:m1@")]


def test_one_hue_frame_and_natural_exemption(tmp_path):
    blue = []
    for i in range(100):
        im = Image.new("RGB", (W, H), (30, 60, 200))
        ImageDraw.Draw(im).rectangle([20 + i % 5, 20, 80, 60], fill=(228, 87, 46))
        blue.append(im)
    ins = clean_insert()
    plan = episode(tmp_path, [ins], jsx={"motion/m1/comp.jsx": CLEAN_JSX})
    ep = plan.parent.parent
    write_frames(ep, "m1", blue)
    s = build(plan)
    hue = [f for f in s["findings"] if f["id"].startswith("hue:m1@")]
    assert len(hue) == 5 and {f["level"] for f in hue} == {"ERROR"}
    assert json.loads((Path(s["bundle"]) / "m1" / "hue.json").read_text())["times"][0]["dominant_share"] > 0.3
    ins["data"]["natural"] = True
    plan.write_text(json.dumps({**json.loads(plan.read_text()), "inserts": [ins]}))
    s2 = build(plan)
    assert {f["level"] for f in s2["findings"] if f["id"].startswith("hue:m1@")} == {"NOTE"}


def test_overlay_on_the_face_box(tmp_path):
    ov = {"id": "k1", "kind": "motion", "scene": "keyword_pop", "start": 20.0, "end": 22.0, "transparent": True,
          "data": {"words": ["runs", "offline"]}}
    plan = episode(tmp_path, [ov])
    ep = plan.parent.parent
    face = (int(0.42 * W), int(0.28 * H), int(0.58 * W), int(0.48 * H))     # on the face (0.5, 0.38)
    write_frames(ep, "k1", [overlay_frame(i, face) for i in range(50)])
    s = build(plan)
    f = [x for x in s["findings"] if x["id"] == "face:k1"]
    assert f and f[0]["level"] == "ERROR"
    px = json.loads((Path(s["bundle"]) / "k1" / "text.json").read_text())["pixels"]
    assert px["face_share_max"] > 0.3
    # the same overlay on the free side passes
    side = (int(0.72 * W), int(0.55 * H), int(0.92 * W), int(0.70 * H))
    write_frames(ep, "k1", [overlay_frame(i, side) for i in range(50)], h="cccccc3333")
    s2 = build(plan)
    assert "face:k1" not in levels(s2) and "safe:k1" not in levels(s2)
    assert levels(s2)["frozen:k1"] == "OK"


def test_empty_frames(tmp_path):
    plan = episode(tmp_path, [clean_insert()], jsx={"motion/m1/comp.jsx": CLEAN_JSX})
    ep = plan.parent.parent
    frames = [ground_frame(i) for i in range(100)]
    for k in range(30, 33):
        frames[k] = Image.new("RGB", (W, H), (241, 241, 239))
    write_frames(ep, "m1", frames)
    lv = levels(build(plan), "m1")
    assert lv["empty:m1@1.20"] == "ERROR"


def test_text_sizes_from_a_fake_engine(tmp_path):
    """The engine is a fake: it writes the project and PNG strips, and answers the text probe with a 30 px label."""

    class FakeEngine:
        def __init__(self):
            self.scripts, self.frames = [], []

        def run_steps(self, steps, project=None, save=True, save_as=None):
            Path(save_as).write_text("{}")
            return {"ok": True}

        def script(self, code, project=None, save=True, save_as=None, name="x.jsx", keep=None):
            self.scripts.append(code)
            if "sourceRectAtTime" in code:
                layers = [
                    {"name": "label", "text": "per month", "samples": [
                        {"t": 1.0, "px": 30.0, "opacity": 100, "box": [1300, 700, 300, 40]},
                        {"t": 2.0, "px": 31.0, "opacity": 100, "box": [1300, 700, 300, 40]}]},
                    {"name": "hero", "text": "30", "samples": [
                        {"t": 0.1, "px": 12.0, "opacity": 100, "box": [800, 400, 300, 160]},   # entrance: ignored
                        {"t": 3.0, "px": 150.0, "opacity": 100, "box": [800, 400, 300, 160]}]},
                    {"name": "edge", "text": "cut off", "samples": [
                        {"t": 2.0, "px": 60.0, "opacity": 100, "box": [1800, 1000, 300, 60]}]},
                ]
                return {"result": json.dumps({"comp": "Main", "size": [1920, 1080], "precomps": 0,
                                              "layers": layers})}
            return {"result": json.dumps({"comp": "Main"})}

        def render_frame(self, project, out, comp=None, time=None, frame=None, max_side=None, transparent=False):
            self.frames.append(time)
            ground_frame(int(time * 60)).save(out)
            return {"ok": True}

    fake = FakeEngine()
    ins = clean_insert()
    ins["transitions"] = [2.0]
    plan = episode(tmp_path, [ins], jsx={"motion/m1/comp.jsx": CLEAN_JSX})
    write_frames(plan.parent.parent, "m1", [ground_frame(i) for i in range(100)])
    s = build(plan, backend=fake)
    b = Path(s["bundle"]) / "m1"
    lv = levels(s, "m1")
    assert lv["text-small:m1:label"] == "ERROR"
    assert lv["text-safe:m1:edge"] == "ERROR"
    assert "text-small:m1:hero" not in lv
    text = json.loads((b / "text.json").read_text())
    assert text["engine"] is True
    assert {x["name"]: x["min_px"] for x in text["layers"]} == {"label": 30.0, "hero": 150.0, "edge": 60.0}
    # the comp is built at 60 fps from the episode's comp.jsx with CC_CTX
    assert any("var CC_CTX" in c and '"fps": 60' in c and "gpu_handoff(" in c for c in fake.scripts)
    # strips: in, out, the declared transition and the cue, 15 frames each (60 fps, every 2nd frame)
    files = s["inserts"][0]["files"]
    assert {"strip-in.jpg", "strip-out.jpg", "strip-t1.jpg", "strip-cue-landAt.jpg"} <= set(files)
    assert all((b / f).is_file() for f in files if f.endswith(".jpg"))
    assert fake.frames[:15] == pytest.approx([k / 60 for k in range(0, 30, 2)])
    assert s["engine"] is True and s["engine_note"] is None


def test_flat_file_shows_grey_under_an_overlay(tmp_path):
    f = tmp_path / "000.png"
    overlay_frame(0, (10, 10, 60, 40)).save(f)
    with Image.open(rv.flat_file(f)) as im:
        assert im.mode == "RGB" and abs(im.getpixel((300, 170))[0] - 128) <= 2


def test_overlay_text_over_face_from_engine():
    probe = {"size": [1920, 1080], "layers": [{"name": "w", "text": "offline", "samples": [
        {"t": 1.0, "px": 140, "opacity": 100, "box": [880, 300, 200, 140]}]}]}
    safe = rv.safe_box("landscape", True)
    face = rv.face_box([0.5, 0.38])
    layers, bad = rv.text_check(probe, 40, (1920, 1080), safe, face, True, [])
    assert [b["rule"] for b in bad] == ["text-face"]
    _, bad_full = rv.text_check(probe, 40, (1920, 1080), safe, face, False, [])
    assert bad_full == []


# ---------------------------------------------------------------- lint


def test_lint_finds_the_planted_faults():
    hits = rv.lint_jsx(BOXED_JSX)
    by = {}
    for h in hits:
        by.setdefault(h["rule"], []).append(h)
    assert by["rounded-text"][0]["candidate"] is True and by["rounded-text"][0]["level"] == "CHECK"
    assert by["box-behind-text"][0]["candidate"] is True          # the solid parented to the word
    assert by["size-literal"][0]["level"] == "ERROR" and by["size-literal"][0]["line"] == 7
    assert by["temporal-blur"][0]["level"] == "ERROR"
    assert by["font-name"][0]["level"] == "ERROR" and "Manrope" in by["font-name"][0]["text"]
    assert rv.lint_jsx(CLEAN_JSX) == []


def test_lint_rules_one_by_one():
    assert [h["rule"] for h in rv.lint_jsx('var x = 1920 / 2;')] == ["size-literal"]
    assert rv.lint_jsx('var u = H / 1080.0;')[0]["rule"] == "size-literal"
    assert rv.lint_jsx('// 1920 x 1080 in a comment\nvar c = "#108080";') == []
    assert rv.lint_jsx('EC.text(c, {text: "a", font: "Inter"});')[0]["rule"] == "font-name"
    assert rv.lint_jsx('var p = {"family": "Helvetica"};')[0]["rule"] == "font-name"
    assert rv.lint_jsx('EC.fx(c, l, "shatter", {});')[0]["rule"] == "shatter"
    assert rv.lint_jsx('var t = EC.text(c, {text: "w"});\nvar g = CC.glass(c, {under: t, radius: 30});') == []
    # a stroke-only outline next to a word is fine; a filled pill sized from the word is a candidate
    stroke = 'var t = EC.text(c, {text: "w"});\nvar o = EC.shape(c, {kind: "rect", fillOpacity: 0, parent: t});'
    assert rv.lint_jsx(stroke) == []
    pill = 'var t = EC.text(c, {text: "w"});\nvar d = EC.dims(c, t);\nvar p = EC.shape(c, {size: [d.width, 90], fill: "#fff", roundness: CC.brand().shape.radius});'
    assert [h["rule"] for h in rv.lint_jsx(pill)] == ["rounded-text"]
    assert rv.lint_jsx("x", {"font": "Manrope", "width": 1920})[0]["line"] == 0
    assert {h["rule"] for h in rv.lint_jsx("x", {"font": "Manrope", "width": 1920})} == {"font-name", "size-literal"}


def test_lint_through_the_bundle_and_motion_check(tmp_path, capsys):
    plan = episode(tmp_path, [clean_insert()], jsx={"motion/m1/comp.jsx": BOXED_JSX})
    s = build(plan)
    lint = json.loads((Path(s["bundle"]) / "m1" / "lint.json").read_text())
    assert lint["candidates"] >= 2 and lint["errors"] >= 3 and "the Critic decides" in lint["note"]
    assert mc.main([str(plan), "--pack", str(NEUTRAL)]) == 1
    out = capsys.readouterr().out
    assert "ERROR" in out and "[candidate: the Critic decides]" in out
    assert "Candidates from the lint" in out
    text = json.loads((Path(s["bundle"]) / "m1" / "text.json").read_text())
    assert [x["size"] for x in text["static"]] == [30.0]       # written in the source; the engine measures it


def test_static_text_sizes():
    src = '@params {"size": 30}\nEC.text(c, {size: CC.px(24)});\nEC.text(c, {size: 140});\nEC.shape(c, {size: [10, 10]});'
    assert [x["size"] for x in rv.static_text_sizes(src, 40)] == [30.0, 24.0]


# ---------------------------------------------------------------- geometry and pixels


def test_safe_and_face_boxes_match_cc_frame():
    assert rv.safe_box("landscape", True) == pytest.approx((0.05, 0.05, 0.90, 0.87))
    assert rv.safe_box("landscape", False) == pytest.approx((0.05, 0.05, 0.90, 0.90))
    assert rv.safe_box("portrait", True, 0.18) == pytest.approx((0.06, 0.10, 0.76, 0.70))
    assert rv.safe_box("stage", True) == pytest.approx((0.05, 0.05, 0.90, 0.89))
    assert rv.face_box([0.5, 0.38]) == pytest.approx((0.34, 0.24, 0.32, 0.28))
    assert rv.face_box({"x": 0.5, "y": 0.4, "w": 0.4, "h": 0.2}) == pytest.approx((0.3, 0.26, 0.4, 0.28))
    assert rv.face_box(None) is None


def test_pixel_measures():
    sharp = np.asarray(ground_frame(0).convert("RGBA"))
    blur = np.asarray(ground_frame(0).filter(ImageFilter.GaussianBlur(4)).convert("RGBA"))
    assert rv.laplace_var(rv.gray(rv.flat(blur))) < 0.35 * rv.laplace_var(rv.gray(rv.flat(sharp)))
    assert rv.frame_diff(sharp, sharp) == 0.0
    empty = np.zeros((H, W, 4), np.uint8)
    assert rv.content_share(empty, True) == 0.0
    ov = np.asarray(overlay_frame(0, (10, 10, 60, 40)))
    assert rv.content_share(ov, True) > 0.01
    assert rv.box_share(ov, (0.0, 0.0, 0.25, 0.25)) > 0.4
    assert rv.outside_share(ov, (0.5, 0.5, 0.5, 0.5)) == 1.0
    mean, runs = rv.low_runs([10.0, 10.0, 1.0, 1.0, 10.0], [True] * 5)
    assert runs == [(2, 3)] and mean == pytest.approx(6.4)
    _, none = rv.low_runs([10.0, 10.0, 1.0, 1.0, 10.0], [True, True, False, False, True])
    assert none == []


def test_word_anchored_start_and_cues(tmp_path):
    ins = clean_insert()
    ins["start"] = {"word": "n3", "offset": -0.6}
    ins["end"] = {"word": "n4", "offset": 2.0}
    plan = episode(tmp_path, [ins], jsx={"motion/m1/comp.jsx": CLEAN_JSX})
    ctx = rv.load(plan, pack())
    m = rv.moments(ctx)[0]
    assert m.start == pytest.approx(17.4 - 0.6) and m.end == pytest.approx(25.4 + 2.0)
    assert m.cues == {"landAt": pytest.approx(25.4 - 16.8)}
    s = build(plan)
    assert "cue:m1:landAt" not in levels(s)
    ins["start"] = {"word": "missing"}
    plan.write_text(json.dumps({**json.loads(plan.read_text()), "inserts": [ins]}))
    m2 = rv.moments(rv.load(plan, pack()))[0]
    assert m2.start is None and any("cannot be resolved" in n for n in m2.notes)


# ---------------------------------------------------------------- density


def _plan(inserts, seconds=120.0, fmt="landscape", sound=None):
    p = {"format": fmt, "inserts": inserts, "tail": 0.0}
    if sound:
        p["sound"] = sound
    return p, words_for(seconds)


def _m(iid, s, e, scene="number_roll", tr=False, **kw):
    return {"id": iid, "kind": "motion", "scene": scene, "start": s, "end": e, "transparent": tr, **kw}


def test_density_counts():
    L = dens.limits(json.loads((NEUTRAL / "edit-style.json").read_text()))
    plan, words = _plan([_m("a", 9.0, 13.0), _m("b", 14.0, 15.0, "keyword_pop", True, sound=True),
                         _m("c", 17.2, 19.0, "keyword_pop", True, sound=True), _m("r1", 40.0, 46.0, "ranking"),
                         _m("r2", 60.0, 66.0, "ranking"), _m("x", 1.0, 3.5),
                         {"id": "k", "kind": "2d", "scene": "keyword", "start": 80, "end": 82, "transparent": True,
                          "data": {"text": "LOCAL"}}],
                        sound={"whooshes": ["a", "a@value"], "hits": []})
    r = dens.count(plan, words, L, {"keyword_pop": 1})
    lv = {f["id"]: f["level"] for f in r["findings"]}
    assert lv["motion-gap:a-b"] == "ERROR"                     # 5 s apart
    assert lv["motion-sentence:0:09.0"] == "ERROR"             # a and b in the sentence at 9 s
    assert lv["motion-heroes"] == "ERROR"                      # ranking twice
    assert lv["motion-sounds:a"] == "ERROR"                    # 2 whooshes on a
    assert lv["motion-pop-sound:c"] == "ERROR"                 # two keyword_pop in a row with sound
    assert lv["motion-open:x"] == "ERROR"                      # the first 3 s are the speaker's
    assert lv["motion-length:b"] == "ERROR"                    # a 1 s overlay
    assert r["counts"]["keywords"] == 3                        # keyword + 2 keyword_pop
    assert r["counts"]["big"] == 4 and r["counts"]["overlays"] == 2


def test_density_sentence_and_short_rules():
    L = dens.limits({})
    plan, words = _plan([_m("a", 9.0, 13.0), _m("b", 9.5, 11.0, "keyword_pop", True)])
    lv = {f["id"]: f["level"] for f in dens.count(plan, words, L)["findings"]}
    assert lv["motion-sentence:0:09.0"] == "ERROR"
    plan, words = _plan([_m(f"s{k}", 4.0 + 5 * k, 7.5 + 5 * k) for k in range(3)], seconds=40.0, fmt="portrait")
    r = dens.count(plan, words, L)
    lv = {f["id"]: f["level"] for f in r["findings"]}
    assert lv["motion-big"] == "ERROR"                         # 3 full-frame moments in a Short (at most 2)
    assert not any(k.startswith("motion-gap") for k in lv)     # the 6 s gap rule is for long videos
    assert r["short"] is True


def test_density_uses_the_pack_motion_block():
    L = dens.limits({"motion": {"min_gap_s": 3.0, "big_moments": [1, 2]}})
    assert L["min_gap_s"] == 3.0 and L["per_minute_max"] == 2.0 and L["source"] == "edit-style.json motion"
    plan, words = _plan([_m("a", 9.0, 13.0), _m("b", 25.0, 29.0), _m("c", 41.0, 45.0)])
    lv = {f["id"]: f["level"] for f in dens.count(plan, words, L)["findings"]}
    assert lv["motion-big"] == "ERROR"


def test_style_check_counts_motion(tmp_path):
    words = [{"word": w["w"], "start": w["s"]} for w in words_for(120.0)]
    ins = sc.plan_inserts({"inserts": [
        {"id": "k1", "kind": "2d", "scene": "keyword", "start": 10, "end": 11, "transparent": True,
         "data": {"words": [{"text": "ONE"}, "TWO"]}},
        {"id": "p1", "kind": "motion", "scene": "keyword_pop", "start": {"word": "n3"}, "end": 20.0,
         "transparent": True, "data": {"words": ["runs", "offline"]}},
        {"id": "l1", "kind": "motion", "scene": "lower_third", "start": 30.0, "end": 34.0, "transparent": True,
         "data": {"text": "Name"}},
        {"id": "gone", "kind": "motion", "scene": "keyword_pop", "start": {"word": "nowhere"}, "end": 50.0,
         "transparent": True, "data": {"words": ["x"]}},
    ]}, words, 25)
    assert [i["id"] for i in ins] == ["k1", "p1", "l1"]
    assert ins[1]["start_f"] == round(17.4 * 25)
    assert sc.mix_counts(ins, 25)["keywords"] == ["ONE", "TWO", "runs offline"]
    # the whole plan check gets the density lines
    plan = episode(tmp_path, [_m("a", 9.0, 13.0), _m("b", 14.0, 18.0)], seconds=120.0)
    assert sc.main([str(plan), "--no-media", "--pack", str(NEUTRAL)]) == 1
    rep = json.loads((plan.parent.parent / "review" / "cut-check-v001.json").read_text())
    lv = {f["id"]: f["level"] for f in rep["findings"]}
    assert lv["motion-gap:a-b"] == "ERROR" and lv["motion-speaker:a-b"] == "ERROR"
