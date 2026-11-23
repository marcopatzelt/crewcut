"""3D: batch queue logic, rented rendering through a fake compute session, local rendering, the rent-or-local card."""

import re
import shutil
import time
from pathlib import Path

import pytest
from PIL import Image
from render_helpers import FakeRunner, basic_plan

from crewcut import approvals
from crewcut.render import blender, cli, workbench
from crewcut.render.blender import WAIT, Batch, BatchQueue
from crewcut.render.plan import Plan


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def test_runs_split_into_batches():
    assert blender.runs([0, 1, 2, 3, 4, 7, 8, 20], 3) == [(0, 2), (3, 4), (7, 8), (20, 20)]
    assert blender.runs([], 6) == []


def test_queue_limits_stuck_batches_and_failures():
    clock, done = Clock(), set()
    b1, b2, b3 = Batch("d1", 0, 5), Batch("d1", 6, 11), Batch("d1", 12, 17)
    q = BatchQueue([b1, b2, b3], lambda b: b not in done, clock=clock)
    assert q.limit(b1) == 150 * 6 + 240                      # before any batch finished
    assert q.take(0) == b1 and q.take(1) == b2
    clock.t = 10
    done.add(b1)
    assert q.finish(0, b1, True, 10.0)
    assert q.median() == 10 and q.limit(b2) == 240           # 3 x median, at least 240 s
    assert q.take(0) == b3
    clock.t = 12
    assert q.take(2) == WAIT                                 # b2 runs 12 s; not yet 1.5 x median after the default
    clock.t = 20
    done.add(b3)
    q.finish(0, b3, True, 10.0)
    assert q.take(0) == b2                                   # b2 hangs on machine 1: machine 0 takes it as well
    assert q.take(2) == WAIT                                 # never more than two machines on one batch
    assert q.finish(1, b2, False, 30.0)                      # machine 1 fails, machine 0 still has it: not requeued
    assert b2 not in q.queue
    done.add(b2)
    q.finish(0, b2, True, 9.0)
    assert q.take(0) is None and q.take(1) is None
    assert q.taken == {0: 3, 1: 1}


def test_failed_batch_goes_back_and_machine_stops_after_three():
    clock = Clock()
    b = Batch("d1", 0, 5)
    q = BatchQueue([b], lambda x: True, clock=clock)
    assert q.take(0) == b
    assert q.finish(0, b, False, 5) is True and q.queue == [b]
    assert q.take(0) == b and q.finish(0, b, False, 5) is True
    assert q.take(0) == b and q.finish(0, b, False, 5) is False     # third failure: stop


def plan_3d(episode, frames_s=1.2):
    p = basic_plan()
    p["inserts"] = [{"id": "d1", "kind": "3d", "scene": "stack", "start": 6.0, "end": 6.0 + frames_s,
                     "cues": {"word": 10}, "data": {"word": "Rules", "count": 4}}]
    return Plan(episode(p))


class NeedsApproval(Exception):
    exit_code = 3

    def __init__(self, card_id):
        super().__init__(card_id)
        self.card_id = card_id


class Refused(Exception):
    exit_code = 3


class FakeMachine:
    """Renders by writing PNGs into its own 'remote' folder; `delay` seconds per batch; fails the first `fail` runs."""

    def __init__(self, root: Path, n: int, delay: float, fail: int = 0, refuse_after: int | None = None):
        self.remote, self.delay, self.fail, self.refuse_after = root / f"remote{n}", delay, fail, refuse_after
        self.puts, self.runs = [], []

    def put(self, paths, remote_dir):
        self.puts.append(([Path(p).name for p in paths], remote_dir))
        for p in paths:
            shutil.copytree(p, self.remote / Path(p).name, dirs_exist_ok=True)

    def run(self, cmd, timeout=600):
        self.runs.append(cmd)
        if self.refuse_after is not None and len(self.runs) > self.refuse_after:
            raise Refused("the session cap of $0.50 is reached; all machines were destroyed")
        if self.fail:
            self.fail -= 1
            return 1, "driver error"
        out = re.search(r"--out (\S+)", cmd).group(1)
        a, b = int(re.search(r"--from (\d+)", cmd).group(1)), int(re.search(r"--to (\d+)", cmd).group(1))
        d = self.remote / out.replace("/work/", "")
        d.mkdir(parents=True, exist_ok=True)
        time.sleep(self.delay)
        for i in range(a, b + 1):
            Image.new("RGB", (1920, 1080)).save(d / f"{i:04d}.png")
        return 0, "DONE"

    def get(self, remote, local):
        src = self.remote / remote.replace("/work/", "").rstrip("/")
        Path(local).mkdir(parents=True, exist_ok=True)
        for f in src.glob("*.png") if src.is_dir() else []:
            shutil.copy(f, Path(local) / f.name)


class FakeCompute:
    NeedsApproval = NeedsApproval
    Refused = Refused

    def __init__(self, root, delays=(0.0, 0.08), fails=(0, 0), suggest=True, block=None, refuse_after=None):
        self.root, self.delays, self.fails, self.suggest, self.block = root, delays, fails, suggest, block
        self.refuse_after = refuse_after
        self.sessions, self.estimates, self.machines = [], [], []

    def estimate(self, kind, frames, local_sec_per_frame=None, gpus=None):
        self.estimates.append((kind, frames, gpus))
        return {"kind": kind, "frames": frames, "local_seconds": frames * 144, "local_measured": False,
                "rented_seconds": frames * 40 / (gpus or 1) + 300, "rented_usd": 0.4, "rented_usd_worst": 0.8,
                "gpus": gpus, "price_per_hour": 0.45, "suggest_rent": self.suggest,
                "sentence": f"{frames} frames: about 2 h here, or about 9 min on {gpus} GPUs for about $0.40.",
                "referral": {"url": "https://example.invalid/ref", "note": "Referral link."}}

    def session(self, **kw):
        compute = self

        class S:
            destroyed = False

            def __enter__(self):
                if compute.block:
                    raise compute.block
                compute.sessions.append((kw, self))
                return self

            def rent(self, gpus, max_minutes, **kw):
                self.rented = (gpus, max_minutes)
                ms = [FakeMachine(compute.root, i, compute.delays[i % len(compute.delays)],
                                  compute.fails[i % len(compute.fails)], compute.refuse_after) for i in range(gpus)]
                compute.machines += ms
                return ms

            def __exit__(self, *exc):
                self.destroyed = True
                return False
        return S()


def test_rented_render_spreads_batches_and_releases_machines(episode, tmp_path):
    plan = plan_3d(episode, frames_s=2.0)                # 50 + 2 frames
    compute = FakeCompute(tmp_path, delays=(0.0, 0.25), fails=(0, 1))
    lines = []
    rows = blender.render_rented(plan, compute, gpus=2, cap_usd=1.0, max_minutes=30, batch=6, log=lines.append,
                                 runner=FakeRunner())
    ins = plan.by_id("d1")
    assert plan.missing(ins) == [] and rows[0]["frames_ok"] and rows[0]["clip_ok"]
    kw, session = compute.sessions[0]
    assert kw == {"episode": "001-test", "step": "edit", "purpose": "3D scenes", "cap_usd": 1.0}
    assert session.destroyed and session.rented == (2, 30)
    fast, slow = compute.machines
    assert len(fast.runs) > len(slow.runs)              # the fast machine takes more batches
    assert fast.puts == [(["3d", "data", "fonts"], "/work/")]
    sent = {p.name for p in (fast.remote / "3d").iterdir()} | {p.name for p in (fast.remote / "data").iterdir()}
    assert sent == {"stack.py", "stage.py", "d1.json", "tokens.json"}      # only scene code and data go out
    assert "/opt/blender/blender -b --factory-startup --python /work/3d/stack.py" in fast.runs[0]
    assert "--gpu" in fast.runs[0] and fast.runs[0].startswith("mkdir -p /work/out/") and "timeout 1140 " in fast.runs[0]
    assert any("failed, back in the queue" in x for x in lines)


def test_rented_needs_approval_becomes_waiting(episode, tmp_path):
    plan = plan_3d(episode)
    compute = FakeCompute(tmp_path, block=NeedsApproval(7))
    with pytest.raises(workbench.Waiting) as e:
        workbench.render_3d(plan, mode="rented", compute=compute, runner=FakeRunner(), log=lambda *a: None, gate=False)
    assert e.value.card_id == 7
    compute = FakeCompute(tmp_path, block=Refused("month cap reached"))
    with pytest.raises(workbench.Waiting, match="month cap"):
        workbench.render_3d(plan, mode="rented", compute=compute, runner=FakeRunner(), log=lambda *a: None, gate=False)


def test_local_render_batches_and_timings(episode, monkeypatch):
    monkeypatch.setenv("CREWCUT_BLENDER", "/opt/blender/blender")
    plan = plan_3d(episode)                              # 30 + 2 frames
    run = FakeRunner()
    r = workbench.render_3d(plan, mode="local", runner=run, log=lambda *a: None, gate=False)
    calls = [c for c in run.calls if c[0] == "/opt/blender/blender"]
    assert r["way"] == "local" and len(calls) == 4      # batches of 10 frames
    c = calls[0]
    assert c[:5] == ["/opt/blender/blender", "-b", "--factory-startup", "--python", str(plan.by_id("d1").template)]
    assert c[c.index("--from") + 1] == "0" and c[c.index("--to") + 1] == "9" and "--gpu" not in c
    assert c[c.index("--samples") + 1] == "128"         # from the neutral pack's stage3d
    assert blender.local_sec_per_frame(False) is not None
    assert r["rows"][0]["clip_ok"] and plan.by_id("d1").clip.is_file()
    run2 = FakeRunner()
    r2 = workbench.render_3d(plan, mode=None, runner=run2, log=lambda *a: None, gate=False)   # nothing missing: no decision needed
    assert r2["way"] == "none" and not [c for c in run2.calls if "blender" in c[0]]


def test_draft_lowers_samples(episode, monkeypatch):
    monkeypatch.setenv("CREWCUT_BLENDER", "blender")
    run = FakeRunner()
    workbench.render_3d(plan_3d(episode), mode="local", draft=True, runner=run, log=lambda *a: None, gate=False)
    c = next(c for c in run.calls if c[0] == "blender")
    assert c[c.index("--samples") + 1] == "32"


def test_rent_card_once_per_episode(episode, tmp_path):
    plan = plan_3d(episode)
    compute = FakeCompute(tmp_path)
    with pytest.raises(workbench.Waiting) as e:
        workbench.choose_way(plan, 32, 2, compute, log=lambda *a: None)
    card = approvals.get(e.value.card_id)
    assert card["kind"] == "spend" and card["status"] == "open" and card["data"]["for"] == "render-3d"
    assert card["data"]["estimate"]["rented_usd"] == 0.4 and card["data"]["budget_usd"] == 0.8
    assert card["data"]["referral"]["url"] == "https://example.invalid/ref"
    assert "Local is fine too" in card["body"] and "32 frames" in card["body"]
    with pytest.raises(workbench.Waiting):                       # still open: no second card
        workbench.choose_way(plan, 32, 2, compute, log=lambda *a: None)
    assert len([c for c in approvals.list_cards(episode="001-test") if c["kind"] == "spend"]) == 1
    approvals.decide(card["id"], accepted=False, reason="local is fine")
    assert workbench.choose_way(plan, 32, 2, compute, log=lambda *a: None) == "local"
    assert len(compute.estimates) == 1                           # not asked again in this episode


def test_rent_card_accepted_means_rented(episode, tmp_path):
    plan = plan_3d(episode)
    compute = FakeCompute(tmp_path)
    with pytest.raises(workbench.Waiting) as e:
        workbench.choose_way(plan, 32, 2, compute, log=lambda *a: None)
    approvals.decide(e.value.card_id, accepted=True)
    assert workbench.choose_way(plan, 32, 2, compute, log=lambda *a: None) == "rented"


def test_no_card_when_renting_does_not_pay_or_gpu_here(episode, tmp_path, monkeypatch):
    plan = plan_3d(episode)
    compute = FakeCompute(tmp_path, suggest=False)
    assert workbench.choose_way(plan, 32, 2, compute, log=lambda *a: None) == "local"
    monkeypatch.setenv("CREWCUT_GPU", "1")
    compute = FakeCompute(tmp_path)
    assert workbench.choose_way(plan, 32, 2, compute, log=lambda *a: None) == "local"
    assert compute.estimates == []
    assert approvals.list_cards(episode="001-test") == []


def test_cli_exit_3_while_the_card_is_open(episode, tmp_path, monkeypatch, capsys):
    plan = plan_3d(episode)
    monkeypatch.setattr(workbench, "load_compute", lambda: FakeCompute(tmp_path))
    code = cli.main(["3d", str(plan.path), "--json", "--no-gate"])
    out = capsys.readouterr().out
    assert code == 3 and '"exit": 3' in out and '"card": 1' in out


def test_cli_shapes():
    a = cli.parser().parse_args(["probe", "p.json", "d1,s1", "--frame", "5,40", "--rented"])
    assert (a.ids, a.frame, a.rented, a.local) == ("d1,s1", "5,40", True, False)
    a = cli.parser().parse_args(["3d", "p.json", "--local", "--gpus", "4"])
    assert a.local and a.gpus == 4
    assert cli.main(["3d", "p.json", "--local", "--rented"]) == 2
    assert cli.main(["nope"]) == 2


def test_probe_stills_2d_and_3d(episode, monkeypatch):
    monkeypatch.setenv("CREWCUT_BLENDER", "blender")
    p = basic_plan()
    p["inserts"].append({"id": "d1", "kind": "3d", "scene": "box", "start": 6.0, "end": 8.0, "cues": {"word": 20}})
    plan = Plan(episode(p))
    run = FakeRunner(real_png=True)
    r = workbench.probe(plan, ["d1", "s1"], [5], runner=run, log=lambda *a: None)
    names = sorted(Path(x).name for x in r["stills"])
    assert names == ["d1-0005.png", "s1-0005.png"]
    b = next(c for c in run.calls if c[0] == "blender")
    assert b[b.index("--frame") + 1] == "5" and b[b.index("--scale") + 1] == "50" and b[b.index("--samples") + 1] == "64"
    h = next(c for c in run.calls if any(x.endswith("render_html.js") for x in c))
    assert "--scale" not in h and h[h.index("--from") + 1] == "5"
    from PIL import Image
    assert Image.open(plan.episode_dir / "render" / "probe" / "s1-0005.png").size == (960, 540)
    assert len(r["measured"]) == 1 and r["measured"][0]["size"] == [960, 540]
    r = workbench.probe(plan, None, None, runner=FakeRunner(), log=lambda *a: None)    # default: 3D only, after the cue
    assert [Path(x).name for x in r["stills"]] == ["d1-0032.png"]


def test_cap_reached_mid_run_stops_every_machine(episode, tmp_path):
    plan = plan_3d(episode, frames_s=2.0)
    compute = FakeCompute(tmp_path, delays=(0.01, 0.01), refuse_after=1)
    with pytest.raises(workbench.Waiting, match="session cap"):
        workbench.render_3d(plan, mode="rented", gpus=2, compute=compute, runner=FakeRunner(), log=lambda *a: None, gate=False)
    assert compute.sessions[0][1].destroyed
    assert all(len(m.runs) <= 2 for m in compute.machines)          # nobody kept trying after the refusal
    assert plan.missing(plan.by_id("d1"))


def test_gpu_renders_of_graphics_shots_use_eevee_cpu_renders_cycles():
    from crewcut.render import blender
    gpu = blender.scene_cmd("blender", "stage.py", "d.json", "t.json", "out", frame=3, gpu=True)
    cpu = blender.scene_cmd("blender", "stage.py", "d.json", "t.json", "out", frame=3, gpu=False)
    assert "--engine" in gpu and gpu[gpu.index("--engine") + 1] == "eevee" and "--gpu" in gpu
    assert "--engine" not in cpu and cpu[cpu.index("--samples") + 1] == "128"
