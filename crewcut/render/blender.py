"""3D inserts with Blender (Cycles): on this machine (CPU or an own GPU) or on rented GPUs through crewcut.compute.

Rented: the frames are split into small batches. Every machine takes the next batch; a fast machine takes more.
A batch that runs longer than 1.5 x the median goes to a second machine. Each batch has a time limit of 3 x the median
(at the start 150 s per frame + 240 s). A machine stops after three failed batches. Only scene code, scene data and
font files go to a rented machine, never recordings or keys.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import statistics
import threading
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from .. import paths
from . import html, media
from .plan import Insert, Plan

REMOTE_BLENDER = "/opt/blender/blender"
REMOTE_WORK = "/work"
WAIT = "wait"


class RenderError(RuntimeError):
    pass


# ---- programs and commands --------------------------------------------------------------------------------------
def blender_bin() -> str:
    if os.environ.get("CREWCUT_BLENDER"):
        return os.environ["CREWCUT_BLENDER"]
    found = shutil.which("blender")
    if found:
        return found
    return REMOTE_BLENDER if Path(REMOTE_BLENDER).is_file() else "blender"


def local_gpu(runner: media.Runner = media.run) -> bool:
    """An NVIDIA card Blender can use here. Env CREWCUT_GPU=1 or 0 decides without asking nvidia-smi."""
    env = os.environ.get("CREWCUT_GPU")
    if env is not None:
        return env.strip().lower() in ("1", "true", "yes", "on")
    if not shutil.which("nvidia-smi"):
        return False
    rc, out = runner(["nvidia-smi", "-L"], timeout=20)
    return rc == 0 and "GPU" in out


def scene_cmd(blender: str, scene: str, data: str, tokens: str, out: str, *, frm: int | None = None,
              to: int | None = None, frame: int | None = None, samples: int = 128, gpu: bool = False,
              scale: int | None = None) -> list[str]:
    """Blender in the background with a scene script from templates/3d/. Animation range or one still frame."""
    cmd = [blender, "-b", "--factory-startup", "--python", scene, "--", "--data", data, "--brand", tokens,
           "--out", out, "--samples", str(samples)]
    if frame is not None:
        cmd += ["--frame", str(frame)]
    else:
        cmd += ["--anim", "--from", str(frm), "--to", str(to)]
    if scale:
        cmd += ["--scale", str(scale)]
    if gpu:
        cmd.append("--gpu")
    return cmd


def runs(frames: Iterable[int], size: int) -> list[tuple[int, int]]:
    """Split frame numbers into consecutive runs of at most `size` frames: [(first, last), ...]."""
    out: list[tuple[int, int]] = []
    cur: list[int] = []
    for f in sorted(set(frames)):
        if cur and (f != cur[-1] + 1 or len(cur) >= size):
            out.append((cur[0], cur[-1]))
            cur = []
        cur.append(f)
    if cur:
        out.append((cur[0], cur[-1]))
    return out


def frames_ok(plan: Plan, ins: Insert, first: int, last: int, scale: float = 1.0) -> bool:
    w, h = plan.size
    size = (round(w * scale), round(h * scale))
    return all(media.valid_png(ins.out_dir / f"{i:04d}.png", size) for i in range(first, last + 1))


def default_probe_frame(ins: Insert) -> int:
    """A frame after the last cue (the scene has done its thing), else the middle."""
    cues = [c for c in ins.cues.values() if 0 <= c < ins.frames]
    return min(max(cues) + 12, ins.frames - 1) if cues else ins.frames // 2


# ---- measured local speed (for compute.estimate) ----------------------------------------------------------------
def _timings_path() -> Path:
    return paths.state_dir() / "render" / "timings.json"


def record_timing(sec_per_frame: float, gpu: bool) -> None:
    p = _timings_path()
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        d = {}
    key = "blender_gpu" if gpu else "blender_cpu"
    d[key] = (d.get(key, []) + [round(sec_per_frame, 2)])[-20:]
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, indent=1) + "\n", encoding="utf-8")


def local_sec_per_frame(gpu: bool) -> float | None:
    """Median seconds per full frame measured on this machine (last 20 batches), or None."""
    try:
        vals = json.loads(_timings_path().read_text(encoding="utf-8")).get("blender_gpu" if gpu else "blender_cpu")
    except (FileNotFoundError, ValueError):
        return None
    return float(statistics.median(vals)) if vals else None


# ---- local ------------------------------------------------------------------------------------------------------
def render_local(plan: Plan, ids: list[str] | None = None, samples: int | None = None, gpu: bool | None = None,
                 runner: media.Runner = media.run, log: Callable = print, batch: int = 10,
                 progress: Callable | None = None) -> list[dict]:
    """Render the missing frames of every 3D insert here, in batches (an interrupted run keeps what is done)."""
    gpu = local_gpu(runner) if gpu is None else gpu
    samples = int(samples or plan.tokens.get("stage3d", {}).get("samples") or 128)
    tokens = str(html.tokens_file(plan))
    blender = blender_bin()
    todo = [x for x in plan.of_kind("3d", ids)]
    total = sum(len(plan.missing(x)) for x in todo)
    done_n = 0
    rows = []
    for ins in todo:
        miss = plan.missing(ins)
        ok = True
        if miss:
            ins.out_dir.mkdir(parents=True, exist_ok=True)
            data = str(html.write_data(ins))
            for first, last in runs(miss, batch):
                t0 = time.monotonic()
                cmd = scene_cmd(blender, str(ins.template), data, tokens, str(ins.out_dir), frm=first, to=last,
                                samples=samples, gpu=gpu)
                rc, out = runner(cmd, timeout=max(3600, (last - first + 1) * 3600))
                if rc or not frames_ok(plan, ins, first, last):
                    log(f"3d {ins.id} ({ins.scene}) frames {first}-{last}: failed: {media.tail(out, 500)}")
                    ok = False
                    break
                n = last - first + 1
                record_timing((time.monotonic() - t0) / n, gpu)
                done_n += n
                log(f"3d {ins.id} ({ins.scene}) frames {first}-{last}: {(time.monotonic() - t0) / n:.0f} s per frame")
                if progress:
                    progress(f"Rendering 3D here: {done_n} of {total} frames", done_n / max(1, total))
        enc = html.encode(plan, ins, runner, log) if ok else False
        rows.append({"id": ins.id, "scene": ins.scene, "frames_ok": ok and not plan.missing(ins), "clip_ok": enc,
                     "clip": str(ins.clip), "missing": len(plan.missing(ins)), "where": "gpu here" if gpu else "cpu here"})
    return rows


# ---- rented: the batch queue --------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Batch:
    ins_id: str
    first: int
    last: int

    @property
    def n(self) -> int:
        return self.last - self.first + 1


class BatchQueue:
    """Hands out batches to machines. Thread-safe. `still_missing(batch)` says whether any frame of it is missing."""

    def __init__(self, batches: list[Batch], still_missing: Callable[[Batch], bool],
                 clock: Callable[[], float] = time.monotonic, first_sec_per_frame: float = 150.0,
                 floor: float = 240.0, factor: float = 3.0, stuck_factor: float = 1.5, max_failures: int = 3,
                 default_median: float = 300.0):
        self.queue = list(batches)
        self.still_missing = still_missing
        self.clock = clock
        self.first_sec_per_frame, self.floor, self.factor = first_sec_per_frame, floor, factor
        self.stuck_factor, self.max_failures, self.default_median = stuck_factor, max_failures, default_median
        self.running: dict[Batch, list] = {}       # batch -> [started, set of workers]
        self.durations: list[float] = []
        self.failures: dict[int, int] = {}
        self.taken: dict[int, int] = {}            # worker -> batches taken (a fast machine takes more)
        self.lock = threading.Lock()

    def median(self) -> float | None:
        return statistics.median(self.durations) if self.durations else None

    def limit(self, b: Batch) -> int:
        """Seconds a machine may spend on this batch."""
        med = self.median()
        return int(max(self.floor, self.factor * med)) if med is not None else int(self.first_sec_per_frame * b.n + self.floor)

    def take(self, worker: int) -> Batch | str | None:
        """The next batch, WAIT (others are still running; maybe one hangs later), or None (nothing left)."""
        with self.lock:
            while self.queue:
                b = self.queue.pop(0)
                if self.still_missing(b):
                    self.running[b] = [self.clock(), {worker}]
                    self.taken[worker] = self.taken.get(worker, 0) + 1
                    return b
            med = self.median() or self.default_median
            now = self.clock()
            for b, (started, who) in sorted(self.running.items(), key=lambda kv: kv[1][0]):
                if worker not in who and len(who) < 2 and now - started > self.stuck_factor * med and self.still_missing(b):
                    who.add(worker)
                    self.taken[worker] = self.taken.get(worker, 0) + 1
                    return b
            return WAIT if self.running else None

    def finish(self, worker: int, b: Batch, ok: bool, seconds: float) -> bool:
        """Report a batch. Returns False when this machine has failed too often and should stop."""
        with self.lock:
            entry = self.running.get(b)
            if ok:
                self.durations.append(seconds)
                self.running.pop(b, None)
                return True
            self.failures[worker] = self.failures.get(worker, 0) + 1
            if entry:
                entry[1].discard(worker)
                if not entry[1]:
                    self.running.pop(b, None)
                    if self.still_missing(b) and b not in self.queue:
                        self.queue.append(b)
            return self.failures[worker] < self.max_failures


def remote_cmd(ins: Insert, b: Batch, limit: int, samples: int, worker: int) -> str:
    out = f"{REMOTE_WORK}/out/{ins.out_dir.name}"
    inner = scene_cmd(REMOTE_BLENDER, f"{REMOTE_WORK}/3d/{ins.template.name}", f"{REMOTE_WORK}/data/{ins.id}.json",
                      f"{REMOTE_WORK}/data/tokens.json", out, frm=b.first, to=b.last, samples=samples, gpu=True)
    return (f"mkdir -p {shlex.quote(out)} && timeout {int(limit)} {shlex.join(inner)} "
            f"> {REMOTE_WORK}/log-{worker}.txt 2>&1")


def stage_upload(plan: Plan, inserts: list[Insert]) -> list[Path]:
    """Folder with only what a rented machine needs: scene code (3d/), scene data and tokens (data/), fonts (fonts/)."""
    root = plan.episode_dir / "render" / "remote"
    if root.exists():
        shutil.rmtree(root)
    code, data, fonts = root / "3d", root / "data", root / "fonts"
    for d in (code, data, fonts):
        d.mkdir(parents=True)
    for ins in inserts:
        for f in (ins.template, *ins.shared):
            shutil.copy2(f, code / f.name)
        (data / f"{ins.id}.json").write_text(json.dumps(ins.data, ensure_ascii=False), encoding="utf-8")
    tokens = json.loads(json.dumps(plan.tokens))

    def remote_font(p: str | None) -> str | None:
        if not p or not Path(p).is_file():
            return None
        shutil.copy2(p, fonts / Path(p).name)
        return f"{REMOTE_WORK}/fonts/{Path(p).name}"

    stage = tokens.get("stage3d") or {}
    stage["font"] = remote_font(stage.get("font"))
    for spec in (tokens.get("fonts") or {}).values():
        spec["files"] = [x for x in (remote_font(f) for f in spec.get("files", [])) if x]
    tokens["logo"] = {}
    (data / "tokens.json").write_text(json.dumps(tokens, ensure_ascii=False), encoding="utf-8")
    return [code, data, fonts]


def _blocking(e: Exception) -> bool:
    """A refusal (cap reached, rights, privacy: exit 3) or a missing key (exit 4) stops every machine, not one batch."""
    return getattr(e, "exit_code", None) in (3, 4)


def _worker(n: int, machine, q: BatchQueue, plan: Plan, samples: int, log: Callable, stop: threading.Event,
            sleep: Callable[[float], None] = time.sleep, left: Callable[[], int] = lambda: 0,
            abort: list | None = None) -> None:
    while not stop.is_set():
        b = q.take(n)
        if b is None:
            return
        if b == WAIT:
            sleep(5)
            continue
        ins = plan.by_id(b.ins_id)
        limit = q.limit(b)
        t0 = q.clock()
        try:
            _, out = machine.run(remote_cmd(ins, b, limit, samples, n), timeout=limit + 60)
        except Exception as e:          # a dropped connection counts as a failed batch
            if _blocking(e):
                if abort is not None:
                    abort.append(e)
                stop.set()
                return
            out = str(e)
        try:
            machine.get(f"{REMOTE_WORK}/out/{ins.out_dir.name}/", ins.out_dir)
        except Exception as e:
            if _blocking(e):
                if abort is not None:
                    abort.append(e)
                stop.set()
                return
            log(f"  GPU {n + 1}: fetching {ins.id} {b.first}-{b.last} failed: {e}")
        ok = frames_ok(plan, ins, b.first, b.last)
        go_on = q.finish(n, b, ok, q.clock() - t0)
        log(f"  GPU {n + 1}: {ins.id} {b.first}-{b.last} {'ok' if ok else 'failed, back in the queue'} "
            f"in {q.clock() - t0:.0f} s{'' if ok else ' (' + media.tail(out, 120) + ')'}, {left()} frames left")
        if not go_on and not ok:
            log(f"  GPU {n + 1}: three failed batches, this machine stops")
            return


def render_rented(plan: Plan, compute, ids: list[str] | None = None, gpus: int = 2, samples: int | None = None,
                  cap_usd: float = 2.0, max_minutes: int = 90, batch: int = 6, log: Callable = print,
                  runner: media.Runner = media.run, sleep: Callable[[float], None] = time.sleep,
                  clock: Callable[[], float] = time.monotonic, progress: Callable | None = None) -> list[dict]:
    """Render the missing 3D frames on rented GPUs. Leaving the compute session destroys every machine.

    Raises compute.NeedsApproval / compute.Refused from the session (the caller turns them into exit code 3).
    """
    samples = int(samples or plan.tokens.get("stage3d", {}).get("samples") or 128)
    todo = [x for x in plan.of_kind("3d", ids) if plan.missing(x)]
    rows = []
    if todo:
        for ins in todo:
            ins.out_dir.mkdir(parents=True, exist_ok=True)
        batches = [Batch(ins.id, a, b) for ins in todo for a, b in runs(plan.missing(ins), batch)]
        q = BatchQueue(batches, lambda b: any(i in set(plan.missing(plan.by_id(b.ins_id)))
                                              for i in range(b.first, b.last + 1)), clock=clock)
        total = sum(len(plan.missing(x)) for x in todo)
        log(f"3d: {total} frames in {len(batches)} batches on {gpus} rented GPU{'s' if gpus != 1 else ''}")
        upload = stage_upload(plan, todo)
        stop = threading.Event()
        abort: list[Exception] = []
        with compute.session(episode=plan.episode, step="edit", purpose="3D scenes", cap_usd=cap_usd) as s:
            machines = s.rent(gpus=gpus, max_minutes=max_minutes)
            ready = []
            for i, m in enumerate(machines or []):
                try:
                    m.put(upload, f"{REMOTE_WORK}/")
                    ready.append(m)
                except Exception as e:
                    if _blocking(e):
                        raise
                    log(f"GPU {i + 1}: upload failed ({e}); it gets no work")
            if not ready:
                raise RenderError("no rented GPU is ready; nothing was rendered")
            def left() -> int:
                return sum(len(plan.missing(x)) for x in todo)

            threads = [threading.Thread(target=_worker, args=(i, m, q, plan, samples, log, stop, sleep, left, abort),
                                        daemon=True) for i, m in enumerate(ready)]
            for t in threads:
                t.start()
            try:
                while any(t.is_alive() for t in threads):
                    n_left = left()
                    if progress:
                        progress(f"Rendering 3D on {len(ready)} rented GPUs: {total - n_left} of {total} frames",
                                 (total - n_left) / max(1, total))
                    if not n_left or abort:
                        break               # all there (do not wait for batches handed out twice), or stopped
                    for t in threads:
                        t.join(timeout=2)
            finally:
                stop.set()
        log(f"3d: rented machines released; batches per GPU: {dict(sorted((k + 1, v) for k, v in q.taken.items()))}")
        if abort and any(plan.missing(x) for x in todo):
            raise abort[0]
    for ins in plan.of_kind("3d", ids):
        enc = html.encode(plan, ins, runner, log)
        rows.append({"id": ins.id, "scene": ins.scene, "frames_ok": not plan.missing(ins), "clip_ok": enc,
                     "clip": str(ins.clip), "missing": len(plan.missing(ins)), "where": "rented"})
    return rows


# ---- probe: stills at half size ---------------------------------------------------------------------------------
def probe_local(plan: Plan, items: list[tuple[Insert, int]], samples: int = 64, gpu: bool | None = None,
                runner: media.Runner = media.run, log: Callable = print) -> list[Path]:
    gpu = local_gpu(runner) if gpu is None else gpu
    out_dir = plan.episode_dir / "render" / "probe"
    out_dir.mkdir(parents=True, exist_ok=True)
    tokens = str(html.tokens_file(plan))
    got = []
    for ins, frame in items:
        dst = out_dir / f"{ins.id}-{frame:04d}.png"
        t0 = time.monotonic()
        cmd = scene_cmd(blender_bin(), str(ins.template), str(html.write_data(ins)), tokens, str(dst), frame=frame,
                        samples=samples, gpu=gpu, scale=50)
        rc, out = runner(cmd, timeout=3600)
        ok = rc == 0 and dst.is_file()
        log(f"probe {dst.name}: {'ok' if ok else 'failed'} in {time.monotonic() - t0:.0f} s"
            + ("" if ok else f" ({media.tail(out, 200)})"))
        if ok:
            got.append(dst)
    return got


def probe_rented(plan: Plan, items: list[tuple[Insert, int]], compute, samples: int = 64, cap_usd: float = 0.5,
                 log: Callable = print) -> list[Path]:
    """All stills on one rented GPU; each still is fetched right after it is rendered."""
    out_dir = plan.episode_dir / "render" / "probe"
    out_dir.mkdir(parents=True, exist_ok=True)
    got = []
    upload = stage_upload(plan, sorted({ins.id: ins for ins, _ in items}.values(), key=lambda x: x.id))
    with compute.session(episode=plan.episode, step="edit", purpose="3D probe stills", cap_usd=cap_usd) as s:
        machines = s.rent(gpus=1, max_minutes=30)
        if not machines:
            raise RenderError("no rented GPU for the probe")
        m = machines[0]
        m.put(upload, f"{REMOTE_WORK}/")
        for ins, frame in items:
            name = f"{ins.id}-{frame:04d}.png"
            remote = f"{REMOTE_WORK}/out/probe/{name}"
            inner = scene_cmd(REMOTE_BLENDER, f"{REMOTE_WORK}/3d/{ins.template.name}", f"{REMOTE_WORK}/data/{ins.id}.json",
                              f"{REMOTE_WORK}/data/tokens.json", remote, frame=frame, samples=samples, gpu=True, scale=50)
            t0 = time.monotonic()
            try:
                _, out = m.run(f"mkdir -p {REMOTE_WORK}/out/probe && timeout 400 {shlex.join(inner)} 2>&1 | tail -4",
                               timeout=460)
                m.get(remote, out_dir)          # rsync puts the file into this folder
            except Exception as e:
                out = str(e)
            ok = (out_dir / name).is_file()
            log(f"probe {name}: {'ok' if ok else 'missing'} in {time.monotonic() - t0:.0f} s"
                + ("" if ok else f" ({media.tail(out, 200)})"))
            if ok:
                got.append(out_dir / name)
    return got
