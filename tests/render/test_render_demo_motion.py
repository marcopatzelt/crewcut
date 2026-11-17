"""The demo episode (examples/demo) with its two motion graphics: the plan keeps the density rules, `render all`
passes without the engine (the plan says motion_without_engine: skip), and renders motion with an engine.
Stand-in templates in the studio's pack stand for keyword_pop and number_roll; no program runs."""

from __future__ import annotations

import json
import shutil

import pytest
from motion_helpers import backend_factory, install
from render_helpers import FakeRunner

from crewcut import paths
from crewcut.render import motion, workbench
from crewcut.render.plan import Plan


@pytest.fixture
def demo(studio):
    install(studio, ["keyword_pop", "number_roll"])
    ep = studio / "episodes" / "000-demo"
    shutil.copytree(paths.app_root() / "examples" / "demo", ep)
    return ep / "edit" / "plan-v001.json"


def test_demo_plan_has_two_motion_graphics_inside_the_rules(demo):
    plan = Plan(demo)
    m1, m2 = plan.of_kind("motion")
    assert (m1.id, m1.scene, m1.start_s, m1.end_s, m1.transparent) == ("m1", "number_roll", 22.0, 25.5, False)
    assert (m2.id, m2.scene, m2.start_s, m2.end_s, m2.transparent) == ("m2", "keyword_pop", 28.4, 30.4, True)
    assert len(plan.of_kind("2d")) == 6
    w = "\n".join(plan.warnings)
    for rule in ("apart", "Speaker only", "in the sentence", "the first", "the last", " runs ", "keywords"):
        assert rule not in w, w
    events, _ = plan.motion_sounds()
    assert events["hits"] == [23.0, 28.4]                       # stand-ins: number_roll lands at 1 s, keyword_pop in
    assert plan.sound_entries("hits") == ["c1@value", "g1@end", 23.0, 28.4]


def test_demo_render_all_passes_without_the_engine(demo, monkeypatch):
    monkeypatch.setattr(motion, "engine_available", lambda cli=None: False)
    run = FakeRunner()
    out = workbench.render_all(Plan(demo), "local", runner=run, log=lambda *a: None, gate=False)
    assert out["ok"] and out["motion"]["skipped"] == ["m1", "m2"]
    notes = json.loads((demo.parent.parent / "export" / "demo-v001-preview.cut.json").read_text())["notes"]
    assert any(n.startswith("m1: left out of this cut") for n in notes)
    assert out["cut"]["seconds"] == 34.0
    assert not run.find("prores_ks")                                   # nothing of the motion inserts was made
    raw = json.loads(demo.read_text())
    del raw["motion_without_engine"]
    demo.write_text(json.dumps(raw))
    with pytest.raises(motion.EngineMissing):                          # a real plan stops with one sentence
        workbench.render_all(Plan(demo), "local", runner=FakeRunner(), log=lambda *a: None, gate=False)


def test_demo_motion_renders_with_an_engine(demo):
    plan = Plan(demo)
    calls = []
    r = motion.render_motion(plan, location="local", backend=backend_factory(calls), runner=FakeRunner(),
                             log=lambda *a: None)
    assert [row["id"] for row in r["rows"]] == ["m1", "m2"] and all(row["clip_ok"] for row in r["rows"])
    assert plan.by_id("m1").clip.suffix == ".mp4" and plan.by_id("m2").clip.suffix == ".mov"
