"""2D rendering commands, encode freshness, the brand preview, measuring a still, the samples command."""

import json
import os
import time

import numpy as np
from PIL import Image
from render_helpers import FakeRunner, basic_plan

from crewcut import paths
from crewcut.render import html, measure, preview, workbench
from crewcut.render.plan import Plan


def test_render_and_encode_commands(episode):
    plan = Plan(episode(basic_plan()))
    run = FakeRunner()
    rows = html.render_2d(plan, runner=run, log=lambda *a: None)
    assert [r["id"] for r in rows] == ["s1", "k1"] and all(r["frames_ok"] and r["clip_ok"] for r in rows)
    node = [c for c in run.calls if c[1].endswith("render_html.js")]
    s1, k1 = plan.by_id("s1"), plan.by_id("k1")
    assert node[0][2:4] == [str(s1.template), str(s1.out_dir)]
    assert node[0][node[0].index("--frames") + 1] == "52" and node[0][node[0].index("--to") + 1] == "51"
    assert "--transparent" not in node[0] and "--transparent" in node[1]
    tokens = json.loads(open(node[0][node[0].index("--brand") + 1]).read())
    assert tokens["css"]["--c-accent"] == "#E4572E" and tokens["stage3d"]["background"] == "#EFEFEC"
    data = json.loads(s1.data_file.read_text())
    assert data["cues"]["value"] == 25 and data["label"] == "Per million"
    enc = [c for c in run.calls if "-framerate" in c]
    assert enc[0][enc[0].index("-c:v") + 1] == "libx264" and enc[0][-1].endswith(".tmp.mp4")
    assert enc[1][enc[1].index("-c:v") + 1] == "qtrle" and "argb" in enc[1] and enc[1][-1].endswith(".tmp.mov")
    assert s1.clip.is_file() and k1.clip.is_file()
    # nothing changed: nothing runs again
    run2 = FakeRunner()
    html.render_2d(plan, runner=run2, log=lambda *a: None)
    assert run2.calls == []
    # one new frame: only the encode runs again
    time.sleep(0.01)
    (s1.out_dir / "0003.png").write_bytes(b"new")
    os.utime(s1.out_dir / "0003.png")
    run3 = FakeRunner()
    html.render_2d(plan, runner=run3, log=lambda *a: None)
    assert len(run3.calls) == 1 and "-framerate" in run3.calls[0]


def test_partial_frames_render_only_the_gap(episode):
    plan = Plan(episode(basic_plan()))
    s1 = plan.by_id("s1")
    s1.out_dir.mkdir(parents=True)
    for i in range(20):
        (s1.out_dir / f"{i:04d}.png").write_bytes(b"x")
    run = FakeRunner()
    html.render_2d(plan, ids=["s1"], images_only=True, runner=run, log=lambda *a: None)
    assert len(run.calls) == 1
    c = run.calls[0]
    assert c[c.index("--from") + 1] == "20" and c[c.index("--to") + 1] == "51"


def test_failed_render_is_reported(episode):
    plan = Plan(episode(basic_plan()))
    lines = []
    rows = html.render_2d(plan, runner=FakeRunner(fail="counter.html"), log=lines.append)
    assert rows[0]["frames_ok"] is False and rows[0]["clip_ok"] is None and rows[1]["frames_ok"]
    assert "failed" in lines[0]


def test_preview_plan_uses_pack_and_caches(studio):
    from crewcut import brand
    pack = brand.load()
    d = preview.plan_data(pack)
    assert [i["scene"] for i in d["inserts"]] == ["headline", "counter", "keyword"]
    assert d["base"] == {"color": "soft", "seconds": 10.0} and d["inserts"][-1]["transparent"]
    run = FakeRunner(frames=250)
    out = preview.build(pack, studio / "p.mp4", runner=run, log=lambda *a: None)
    assert out.is_file() and out == (studio / "p.mp4").resolve()
    assert len([c for c in run.calls if c[1].endswith("render_html.js")]) == 3
    lavfi = [c for c in run.calls if "lavfi" in c]
    assert lavfi and "color=c=0xF1F1EF" in " ".join(lavfi[0])        # plain background in the pack's soft colour
    assert not [c for c in run.calls if "-stream_loop" in c]          # no music
    run2 = FakeRunner(frames=250)
    preview.build(pack, studio / "p2.mp4", runner=run2, log=lambda *a: None)
    assert run2.calls == [] and (studio / "p2.mp4").is_file()         # same pack: copied from the cache


def test_preview_cli_usage_and_json(studio, monkeypatch, capsys):
    assert preview.main(["--bogus"]) == 2
    monkeypatch.setattr(preview, "build", lambda pack, out, log=print: studio / "x.mp4")
    assert preview.main(["--json"]) == 0
    assert json.loads(capsys.readouterr().out)["out"].endswith("x.mp4")


def test_measure_against_pack(tmp_path, studio):
    im = np.zeros((540, 960, 3), dtype=np.uint8)
    im[:] = (0xEF, 0xEF, 0xEC)                     # the neutral stage background
    im[300:420, 380:580] = (0xE4, 0x57, 0x2E)      # accent block
    im[340:380, 420:540] = (0x9A, 0x3A, 0x1F)      # the accent in shadow still counts
    p = tmp_path / "s.png"
    Image.fromarray(im).save(p)
    m = measure.measure(p)
    assert m["size"] == [960, 540] and m["background"] == "#EFEFEC"
    assert abs(m["accent_share"] - 100 * 120 * 200 / (540 * 960)) < 0.1
    checks = {c["name"]: c for c in m["checks"]}
    assert checks["background brightness"]["ok"] and checks["background colour distance"]["ok"]
    assert checks["accent share %"]["ok"] is None             # the neutral pack sets no target
    im[:] = (40, 40, 40)
    Image.fromarray(im).save(p)
    assert not {c["name"]: c for c in measure.measure(p)["checks"]}["background brightness"]["ok"]
    assert "no target in the pack" in "\n".join(measure.lines(m))


def test_samples_command(tmp_path, studio):
    run = FakeRunner()
    rows = workbench.samples(tmp_path / "s", ("landscape",), runner=run, log=lambda *a: None)
    assert [r["scene"] for r in rows] == workbench.scenes_2d() and all(r["ok"] for r in rows)
    assert (tmp_path / "s" / "keyword-landscape.png").is_file()
    kw = next(c for c in run.calls if "keyword.html" in c[2])
    assert "--transparent" in kw and kw[kw.index("--from") + 1] == "-1"
    assert json.loads((tmp_path / "s" / "counter-landscape.data.json").read_text()) == {"example": True, "format": "landscape"}
    assert paths.templates_dir().joinpath("2d", "BLOCKS.md").is_file()
