"""crewcut render motion: argument lists with a fake engine backend, fonts, chunks and naming, encode, cache, draft,
speaker backdrop, the location setting, the rented path with a fake compute session, render all and the CLI.
Nothing here runs effectcraft-cli or ffmpeg."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from motion_helpers import FakeCompute, NeedsApproval, backend_factory, install
from render_helpers import FakeRunner, basic_plan

from crewcut.render import cli, motion, workbench
from crewcut.render.plan import Plan, PlanError


def plan_with(episode, studio, *inserts, **over) -> Plan:
    install(studio)
    p = basic_plan(inserts=list(inserts), **over)
    return Plan(episode(p))


ROLL = {"id": "m1", "kind": "motion", "scene": "number_roll", "start": 1.0, "end": 4.0,
        "cues": {"landAt": {"word": "thirty"}}, "data": {"value": "30", "unit": "cents"}, "sound": True}
POP = {"id": "k2", "kind": "motion", "scene": "keyword_pop", "start": 6.0, "end": 7.5, "data": {"words": ["Thirty"]}}


@pytest.fixture
def no_engine(monkeypatch):
    monkeypatch.delenv("EFFECTCRAFT_CLI", raising=False)
    monkeypatch.setattr(motion, "engine_available", lambda cli=None: False)


def test_local_render_argument_lists_frames_and_encode(episode, studio, monkeypatch):
    monkeypatch.setattr(motion, "jobs", lambda: 2)
    plan = plan_with(episode, studio, ROLL)
    x = plan.by_id("m1")
    calls, run = [], FakeRunner()
    r = motion.render_motion(plan, backend=backend_factory(calls), runner=run, log=lambda *a: None)
    assert r["way"] == "local" and r["frames"] == 77 and r["rows"][0]["frames_ok"] and r["rows"][0]["clip_ok"]
    proj, script, *renders = calls
    comp = proj["steps"][0]["params"]
    assert proj["steps"][0]["command"] == "comp.new"
    assert comp == {"name": "Main", "width": 1920, "height": 1080, "frameRate": 25.0, "duration": 77 / 25,
                    "background": "#F1F1EF", "shutterAngle": 180.0, "motionBlurSamples": 16}
    assert proj["steps"][1]["params"] == {"comp": "Main", "switch": "motionBlur", "value": True}
    assert proj["save_as"].endswith(f"render/motion-work/m1-{x.hash}/insert.ecproj")
    code = script["code"]
    assert code.startswith("var CC_CTX = ") and "var EC = " in code and "var CC = " in code
    ctx = json.loads(code.split("var CC_CTX = ", 1)[1].split(";\n", 1)[0])
    assert ctx["format"] == "landscape" and ctx["duration"] == 3.0 and ctx["backdrop"] is None
    assert 'return number_roll({"comp": "Main", "value": "30", "unit": "cents", "label": "", "landAt": 1.0});' in code
    assert len(renders) == 4                                         # 77 frames in chunks of 25
    spans = sorted((c["start"], c["end"]) for c in renders)          # chunks after the first run in parallel
    assert spans == [(0.0, 0.99), (0.99, 1.99), (1.99, 2.99), (2.99, 3.07)]
    assert all(c["fmt"] == "png" and c["out"].endswith("/f_[#####].png") and c["extra"] == [] for c in renders)
    fonts = studio / "episodes" / "001-test" / "render" / "motion-work" / "fonts"
    assert all(c["env"]["EFFECTCRAFT_FONT_DIRS"].split(":")[0] == str(fonts) for c in calls)
    assert sorted(p.name for p in x.out_dir.iterdir())[:2] == ["0000.png", "0001.png"]
    assert plan.missing(x) == [] and len(list(x.out_dir.glob("*.png"))) == 77
    enc = run.find("libx264")[0]
    assert enc[enc.index("-crf") + 1] == "14" and enc[enc.index("-i") + 1].endswith("%04d.png")
    calls2 = []
    r2 = motion.render_motion(plan, backend=backend_factory(calls2), runner=FakeRunner(), log=lambda *a: None)
    assert r2["way"] == "none" and calls2 == [] and r2["rows"][0]["clip_ok"]          # cached: nothing renders


def test_overlay_keeps_alpha_and_becomes_a_mov(episode, studio):
    plan = plan_with(episode, studio, POP)
    calls, run = [], FakeRunner()
    motion.render_motion(plan, backend=backend_factory(calls), runner=run, log=lambda *a: None)
    comp = calls[0]["steps"][0]["params"]
    assert "background" not in comp
    assert all(c["extra"] == ["--channels", "rgba"] for c in calls if c["cmd"] == "render")
    enc = run.find("qtrle")[0]
    assert enc[-1].endswith(".mov") and enc[enc.index("-pix_fmt") + 1] == "argb"


def test_only_a_changed_insert_renders_again(episode, studio):
    plan = plan_with(episode, studio, ROLL, POP)
    motion.render_motion(plan, backend=backend_factory([]), runner=FakeRunner(), log=lambda *a: None)
    raw = json.loads(plan.path.read_text())
    raw["inserts"][1]["data"]["words"] = ["Cents"]
    plan.path.write_text(json.dumps(raw))
    calls = []
    r = motion.render_motion(Plan(plan.path), backend=backend_factory(calls), runner=FakeRunner(), log=lambda *a: None)
    assert {c["cmd"] for c in calls} == {"project", "script", "render"}
    assert '"words": ["Cents"]' in next(c["code"] for c in calls if c["cmd"] == "script")
    assert [row["where"] for row in r["rows"]] == ["cached", "here"]


def test_draft_uses_8_samples_and_its_own_folder(episode, studio):
    plan = plan_with(episode, studio, ROLL)
    calls = []
    r = motion.render_motion(plan, draft=True, backend=backend_factory(calls), runner=FakeRunner(),
                             log=lambda *a: None)
    assert calls[0]["steps"][0]["params"]["motionBlurSamples"] == 8
    assert '"draft": true' in calls[1]["code"]
    assert r["rows"][0]["draft"] and r["rows"][0]["clip"] != str(plan.by_id("m1").clip)
    assert plan.missing(plan.by_id("m1"))                              # the cut's insert is not a draft


def test_pack_fonts_are_copied_and_found(episode, studio, monkeypatch):
    install(studio)
    font = studio / "brand" / "fonts" / "Brand-Bold.ttf"
    font.parent.mkdir()
    font.write_bytes(b"font")
    (studio / "brand" / "brand.json").write_text(json.dumps(
        {"fonts": {"display": {"family": "Brand", "weight": 700, "files": ["fonts/Brand-Bold.ttf"]}}}))
    monkeypatch.setenv("EFFECTCRAFT_FONT_DIRS", "/usr/share/myfonts")
    plan = Plan(episode(basic_plan(inserts=[ROLL])))
    calls = []
    motion.render_motion(plan, backend=backend_factory(calls), runner=FakeRunner(), log=lambda *a: None)
    folder = plan.episode_dir / "render" / "motion-work" / "fonts"
    assert (folder / "Brand-Bold.ttf").read_bytes() == b"font"
    assert calls[0]["env"]["EFFECTCRAFT_FONT_DIRS"] == f"{folder}:/usr/share/myfonts"
    ctx = json.loads(calls[1]["code"].split("var CC_CTX = ", 1)[1].split(";\n", 1)[0])
    assert ctx["brand"]["fonts"]["display"] == {"family": "Brand", "weight": 700}       # no file paths in the context
    assert motion.font_env("/a") == {"EFFECTCRAFT_FONT_DIRS": "/a:/usr/share/myfonts"}


def test_speaker_backdrop_is_cut_for_the_span(episode, studio):
    (episode.dir / "work" / "speaker-v001.mp4").write_bytes(b"speaker")
    e = {**ROLL, "scene": "prompt_bar", "cues": {}, "data": {"text": "what I asked"}, "backdrop": "speaker",
         "start": 6.0, "end": 10.0}
    plan = plan_with(episode, studio, e, base="work/speaker-v001.mp4", speaker=[{"at": 5.0, "zoom": 1.1}])
    calls, run = [], FakeRunner()
    motion.render_motion(plan, backend=backend_factory(calls), runner=run, log=lambda *a: None)
    cmd = run.find("prores_ks")[0]
    x = plan.by_id("m1")
    assert cmd[cmd.index("-ss") + 1] == "5.996" and cmd[cmd.index("-i") + 1].endswith("work/speaker-v001.mp4")
    assert "-an" in cmd and cmd[cmd.index("-frames:v") + 1] == str(x.render_frames)
    assert "scale=iw*1.1:-2" in cmd[cmd.index("-vf") + 1]            # the zoom the cut shows at 6 s
    ctx = json.loads(calls[1]["code"].split("var CC_CTX = ", 1)[1].split(";\n", 1)[0])
    assert ctx["backdrop"] == str(motion.work_dir(plan, x) / "backdrop.mov")
    assert ctx["face"] == {"x": 0.5, "y": 0.38, "w": 0.32, "h": 0.28}


def test_engine_missing_is_one_clear_sentence(episode, studio, no_engine, capsys):
    plan = plan_with(episode, studio, ROLL)
    with pytest.raises(motion.EngineMissing, match=r"effectcraft-cli is missing here, so the motion graphics "
                                                   r"inserts m1 cannot render \(everything else works\)"):
        motion.render_motion(plan, runner=FakeRunner(), log=lambda *a: None)
    assert cli.main(["motion", str(plan.path)]) == 1
    assert "render.location = \"rented\"" in capsys.readouterr().err


def test_render_all_skips_motion_only_when_the_plan_says_so(episode, studio, no_engine, monkeypatch, capsys):
    import crewcut.render.media as media_mod
    monkeypatch.setattr(media_mod, "run", FakeRunner())
    monkeypatch.setattr(workbench.media, "run", media_mod.run)
    plan = plan_with(episode, studio, {**ROLL, "start": 7.0, "end": 10.0, "cues": {}},
                     sound={"hits": [2.0, "m1"]})                        # "m1" goes with the left-out insert
    assert cli.main(["all", str(plan.path), "--local", "--json"]) == 1           # default: a clear failure
    raw = json.loads(plan.path.read_text())
    raw["motion_without_engine"] = "skip"
    plan.path.write_text(json.dumps(raw))
    capsys.readouterr()
    code = cli.main(["all", str(plan.path), "--local", "--json"])
    out = json.loads(capsys.readouterr().out)
    assert code == 0 and out["motion"]["skipped"] == ["m1"], out.get("error")
    notes = json.loads((plan.episode_dir / "export" / "out-v001.cut.json").read_text())["notes"]
    assert any(n.startswith("m1: left out of this cut") for n in notes)


def test_location_setting(studio):
    assert motion.location() == "local"
    (studio / "config").mkdir()
    (studio / "config" / "crewcut.toml").write_text('[render]\nlocation = "rented"\n')
    assert motion.location() == "rented" and motion.location("local") == "local"
    (studio / "config" / "crewcut.toml").write_text('[render]\nlocation = "cloud"\n')
    with pytest.raises(PlanError, match="render.location must be"):
        motion.location()


def test_rented_run_uploads_only_code_fonts_and_images(episode, studio, tmp_path):
    install(studio)
    shot = episode.dir / "broll" / "shot.png"
    shot.parent.mkdir()
    from PIL import Image
    Image.new("RGB", (8, 8)).save(shot)
    e = {"id": "r1", "kind": "motion", "scene": "ranking", "start": 6.0, "end": 12.0,
         "data": {"image": "broll/shot.png"}}
    plan = Plan(episode(basic_plan(inserts=[ROLL, e, POP], motion_cap_usd=1.25)))
    compute, run, lines = FakeCompute(tmp_path), FakeRunner(), []
    r = motion.render_motion(plan, location="rented", compute=compute, runner=run, log=lines.append)
    assert r["way"] == "rented" and r["cap_usd"] == 1.25 and all(x["frames_ok"] and x["clip_ok"] for x in r["rows"])
    kw, session = compute.sessions[0]
    assert kw == {"episode": "001-test", "step": "edit", "purpose": "motion graphics", "cap_usd": 1.25}
    assert session.destroyed and session.rented[0] == 1
    m = compute.machines[0]
    assert m.puts == [(["motion"], "/work/")]
    up = m.root / "work" / "motion"
    sent = sorted(str(p.relative_to(up)) for p in up.rglob("*") if p.is_file() and "out" not in p.parts)
    assert "r1/assets/00-shot.png" in sent and "r1/script.jsx" in sent and "m1/project.json" in sent
    assert not [s for s in sent if s.endswith((".mp4", ".mov", ".wav"))]
    script = (up / "r1" / "script.jsx").read_text()
    assert '"image": "/work/motion/r1/assets/00-shot.png"' in script and str(shot) not in script
    assert 'var EC_ASSETS = "/work/motion/r1/ec_assets";' in script
    sh = (up / "m1" / "render.sh").read_text()
    assert "export EFFECTCRAFT_FONT_DIRS=/work/motion/fonts" in sh and "xargs -d '\\n' -P \"$J\"" in sh
    assert '"$BIN" --empty run --commands project.json --save-as insert.ecproj --json' in sh
    chunk = (up / "k2" / "chunks.txt").read_text().splitlines()[0]
    assert "--format png --channels rgba --json" in chunk and "/work/motion/out/k2/c00000/f_[#####].png" in chunk
    assert m.runs[0].startswith("test -x /usr/local/bin/effectcraft-cli")
    assert m.runs[1] == "sh /work/motion/m1/render.sh /usr/local/bin/effectcraft-cli"
    x = plan.by_id("k2")
    assert plan.missing(x) == [] and x.clip.suffix == ".mov" and run.find("qtrle")
    assert any("rented machine released" in s for s in lines)


def test_rented_cap_defaults_and_refusals(episode, studio, tmp_path):
    plan = plan_with(episode, studio, ROLL)
    assert motion.cap_usd(plan) == 2.0 and motion.cap_usd(plan, 0.7) == 0.7
    short = plan_with(episode, studio, ROLL, format="portrait", motion_cap_usd=9.0)
    assert motion.cap_usd(short) == 0.5                              # a plan may lower the cap, never raise it
    (episode.dir / "work" / "speaker-v001.mp4").write_bytes(b"speaker")
    bd = plan_with(episode, studio, {**ROLL, "scene": "prompt_bar", "cues": {}, "data": {}, "backdrop": "speaker",
                                     "start": 6.0, "end": 10.0}, base="work/speaker-v001.mp4")
    compute = FakeCompute(tmp_path)
    with pytest.raises(motion.MotionError, match="recordings never go to a rented machine"):
        motion.render_motion(bd, location="rented", compute=compute, runner=FakeRunner(), log=lambda *a: None)
    assert compute.sessions == []                                    # refused before anything was rented
    clip = episode.dir / "broll" / "screen.mp4"
    clip.parent.mkdir()
    clip.write_bytes(b"video")
    fp = plan_with(episode, studio, {"id": "r1", "kind": "motion", "scene": "ranking", "start": 6.0, "end": 12.0,
                                     "data": {"image": "broll/screen.mp4"}})
    with pytest.raises(motion.MotionError, match="footage"):
        motion.render_motion(fp, location="rented", compute=compute, runner=FakeRunner(), log=lambda *a: None)


def test_rented_without_engine_in_the_image(episode, studio, tmp_path, monkeypatch):
    plan = plan_with(episode, studio, ROLL)
    binary = tmp_path / "effectcraft-cli"
    binary.write_bytes(b"\x7fELF")
    monkeypatch.setattr(motion, "_local_binary_for_upload", lambda: binary)
    compute = FakeCompute(tmp_path / "a", engine=False)
    lines = []
    motion.render_motion(plan, location="rented", compute=compute, runner=FakeRunner(), log=lines.append)
    m = compute.machines[0]
    assert (["effectcraft-cli"], "/work/motion/bin/") in m.puts
    assert "sh /work/motion/m1/render.sh /work/motion/bin/effectcraft-cli" in m.runs
    assert any("sent this computer's binary" in s for s in lines)
    monkeypatch.setattr(motion, "_local_binary_for_upload", lambda: None)
    plan2 = plan_with(episode, studio, {**ROLL, "data": {"value": "31"}})
    compute = FakeCompute(tmp_path / "b", engine=False)
    with pytest.raises(motion.MotionError, match="rented machine has no effectcraft-cli and this computer cannot"):
        motion.render_motion(plan2, location="rented", compute=compute, runner=FakeRunner(), log=lambda *a: None)
    assert compute.sessions[0][1].destroyed


def test_rented_spend_card_is_exit_3(episode, studio, tmp_path, monkeypatch, capsys):
    plan = plan_with(episode, studio, ROLL)
    compute = FakeCompute(tmp_path, block=NeedsApproval(5))
    with pytest.raises(workbench.Waiting) as e:
        workbench.render_motion(plan, location="rented", compute=compute, runner=FakeRunner(), log=lambda *a: None)
    assert e.value.card_id == 5
    monkeypatch.setattr(workbench, "load_compute", lambda: FakeCompute(tmp_path, block=NeedsApproval(6)))
    assert cli.main(["motion", str(plan.path), "--rented", "--json"]) == 3
    assert '"card": 6' in capsys.readouterr().out


def test_behind_hook(episode, studio, monkeypatch):
    import sys
    import types
    plan = plan_with(episode, studio, {**POP, "layer": "behind"})
    lines = []
    r = motion.render_motion(plan, backend=backend_factory([]), runner=FakeRunner(), log=lines.append)
    assert r["rows"][0]["clip_ok"] and any("laid over the speaker for now" in s for s in lines)
    seen = []
    fake = types.ModuleType("crewcut.motion.matte")
    fake.composite_behind = lambda plan, ins, runner=None, log=None: seen.append(ins.id) or True
    monkeypatch.setitem(sys.modules, "crewcut.motion.matte", fake)
    assert motion.behind_hook(plan, plan.by_id("k2")) and seen == ["k2"]


def test_failed_chunk_reports_and_keeps_the_rest(episode, studio):
    plan = plan_with(episode, studio, ROLL)
    lines = []
    r = motion.render_motion(plan, backend=backend_factory([], fail_render=True), runner=FakeRunner(),
                             log=lines.append)
    assert not r["rows"][0]["frames_ok"] and r["rows"][0]["clip_ok"] is False
    assert any("simulated failure" in s for s in lines)


def test_chunks_spans_and_jobs():
    assert motion.chunks(list(range(77)), 25) == [(0, 24), (25, 49), (50, 74), (75, 76)]
    assert motion.chunks([3, 4, 30], 25) == [(3, 4), (30, 30)]
    assert motion.chunk_span(0, 24, 25) == (0.0, 0.99) and motion.chunk_span(25, 49, 25) == (0.99, 1.99)
    assert motion.jobs() >= 1 and motion.cpu_count() >= 1


def test_cli_plan_lists_motion_inserts_and_notes(episode, studio, monkeypatch, capsys):
    monkeypatch.setattr(motion, "engine_available", lambda cli=None: True)
    plan = plan_with(episode, studio, ROLL, {**POP, "layer": "behind"},
                     {"id": "s1", "kind": "2d", "scene": "counter", "start": 10.0, "end": 12.0, "data": {"value": "9"}})
    assert cli.main(["plan", str(plan.path)]) == 0
    out = capsys.readouterr().out
    assert "m1         motion number_roll" in out and "(overlay)  (layer behind)" in out
    assert "note: motion graphics render here (render.location = local)" in out
    assert "note: s1: the pack prefers motion graphics (motion.prefer); number_roll does what the 2D counter does" in out
    a = cli.parser().parse_args(["motion", "p.json", "--ids", "m1", "--draft", "--rented", "--max-usd", "1"])
    assert (a.ids, a.draft, a.rented, a.local, a.max_usd) == ("m1", True, True, False, 1.0)
    assert cli.main(["motion", "p.json", "--local", "--rented"]) == 2


def test_rows_paths_are_strings(episode, studio):
    plan = plan_with(episode, studio, ROLL)
    r = motion.render_motion(plan, backend=backend_factory([]), runner=FakeRunner(), log=lambda *a: None)
    assert Path(r["rows"][0]["clip"]).name == plan.by_id("m1").clip.name
