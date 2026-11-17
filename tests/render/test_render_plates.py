"""Blender plates of motion inserts: hash, context, where they render, the spend card path."""

from __future__ import annotations

import pytest
from motion_helpers import FakeCompute, NeedsApproval, install
from render_helpers import FakeRunner, basic_plan

from crewcut.render import plates, workbench
from crewcut.render.plan import Plan, motion_context

SCRIPT = "import sys\nprint('plate')\n"


def make(episode, studio, **over):
    install(studio)
    e = {"id": "m3", "kind": "motion", "scene": "number_roll", "start": 1.0, "end": 4.0, "data": {"value": "3"},
         "plates": [{"id": "gpu", "script": "motion/m3/plates/gpu3d.py", "args": {"t0": 0.0, "tin": 1.2},
                     "frames": 4}]}
    e.update(over)
    path = episode(basic_plan(inserts=[e]))
    script = path.parent.parent / "motion" / "m3" / "plates" / "gpu3d.py"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(SCRIPT)
    return Plan(path), script


def test_hash_context_and_the_comp_sees_the_plate(episode, studio):
    plan, script = make(episode, studio)
    ins = plan.by_id("m3")
    [pl] = plates.plates_of(plan, ins)
    assert pl.out_dir.name.startswith("m3-gpu-") and not pl.complete
    ctx = motion_context(plan, ins)
    assert ctx["plates"]["gpu"] == {"first": str(pl.first), "frames": 4, "ready": False}
    h1 = ins.hash
    script.write_text(SCRIPT + "# changed\n")
    plan2 = Plan(plan.path)
    assert plates.plates_of(plan2, plan2.by_id("m3"))[0].hash != pl.hash and plan2.by_id("m3").hash != h1


def test_blender_command_takes_times_in_comp_seconds():
    cmd = plates.blender_cmd("blender", "s.py", "out", "1-120", {"t0": 0.0, "tin": 1.2, "half": False, "names": ["a", "b"]})
    assert cmd[:5] == ["blender", "-b", "--factory-startup", "--python", "s.py"]
    assert cmd[cmd.index("--t0") + 1] == "0.0" and cmd[cmd.index("--tin") + 1] == "1.2"
    assert "--half" not in cmd and cmd[cmd.index("--names") + 1] == "a,b"


def test_local_with_own_gpu(episode, studio, monkeypatch):
    plan, _ = make(episode, studio)
    monkeypatch.setattr(plates.blender, "local_gpu", lambda runner=None: True)

    class Runner(FakeRunner):
        def __call__(self, cmd, timeout=600, cwd=None):
            out = cmd[cmd.index("--out") + 1]
            from pathlib import Path
            for i in range(1, 5):
                (Path(out) / f"{i:04d}.png").write_bytes(b"png")
            return 0, ""

    r = plates.render_plates(plan, runner=Runner(), log=lambda s: None)
    assert r["way"] == "local" and r["rows"][0]["ok"]
    assert plates.render_plates(Plan(plan.path), log=lambda s: None)["way"] == "none"   # cached by hash


def test_a_plate_never_rents_without_the_spend_card(episode, studio, monkeypatch, tmp_path):
    plan, _ = make(episode, studio)
    monkeypatch.setattr(plates.blender, "local_gpu", lambda runner=None: False)
    fake = FakeCompute(tmp_path, block=NeedsApproval(7))
    with pytest.raises(workbench.Waiting):
        workbench.render_plates(plan, compute=fake, log=lambda s: None)
    assert fake.machines == [] and fake.sessions == []


def test_missing_script_is_named_but_the_plan_parses(episode, studio):
    plan, _ = make(episode, studio, plates=[{"id": "x", "script": "motion/m3/plates/none.py", "frames": 2}])
    assert motion_context(plan, plan.by_id("m3"))["plates"]["x"]["ready"] is False
    with pytest.raises(Exception, match="none.py not found"):
        plates.render_plates(plan, location="local", log=lambda s: None)

