"""Motion graphics inserts (kind "motion"): EffectCraft comps rendered to PNG frames, then encoded like 2D inserts.

Per insert with missing frames:
1. a work folder `render/motion-work/<id>-<hash>/` with the project: comp "Main" at the insert's size, fps and
   length, the pack's ground colour (none for overlays), motion blur 180 degrees with 16 samples (8 with --draft);
   with `"backdrop": "speaker"` also the speaker piece of exactly this span as picture-only ProRes;
2. the template run with its params and the insert's context (`CC_CTX`) in one engine process;
3. PNG frames in chunks of CHUNK_S seconds, one engine process per chunk and cores / 4 of them at a time (EffectCraft
   keeps a whole chunk in memory), into `render/inserts/<id>-<hash>/` as 0000.png, 0001.png, ... like 2D;
4. the 2D encoder (`html.encode`): H.264 CRF 14, or QuickTime Animation MOV with alpha for overlays.

The pack's font files are copied into `render/motion-work/fonts/` for every run and every engine process gets
`EFFECTCRAFT_FONT_DIRS` pointing there. Only a changed insert renders again (the hash, see plan.motion_hash).

Where (`render.location` in config/crewcut.toml, `--local` / `--rented` win):
- "local": here, on the CPU. Needs `effectcraft-cli` (the Crewcut image has it).
- "rented": one machine through `crewcut.compute` (spend card first, cap, destroyed at the end). Only the generated
  script, the project settings, font files and images the params name go up; never footage or keys. Inserts with a
  speaker backdrop need footage and are refused there.
"""

from __future__ import annotations

import importlib
import json
import os
import platform
import shlex
import shutil
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from .. import config
from ..motion import project as mproject
from ..motion import templates as mtemplates
from ..motion.backend import Backend, BackendError, find_effectcraft
from . import html, media
from .assemble import speaker_vf
from .blender import runs
from .plan import FOOTAGE_EXT, MOTION_CAP_USD, Insert, Plan, PlanError, font_files, motion_context

__all__ = ["CHUNK_S", "EngineMissing", "MotionError", "behind_hook", "engine_available", "location",
           "motion_context", "render_insert_local", "render_motion", "render_rented"]

CHUNK_S = 1.0                                   # seconds per engine process
COMP = "Main"                                   # the comp every template draws into (its "comp" param default)
LOCATIONS = ("local", "rented")
REMOTE = "/work/motion"
REMOTE_BIN = "/usr/local/bin/effectcraft-cli"   # in the Crewcut GPU image
SEQ = "f_[#####].png"                           # EffectCraft numbers sequence frames by comp frame


class MotionError(RuntimeError):
    """A motion insert cannot render as asked. The message is one sentence for the user."""


class EngineMissing(MotionError):
    """effectcraft-cli is not installed here; only motion inserts are affected."""

    def __init__(self, ids: list[str]):
        self.ids = list(ids)
        super().__init__(
            f"effectcraft-cli is missing here, so the motion graphics inserts {', '.join(ids)} cannot render "
            "(everything else works): use the Crewcut image, or set render.location = \"rented\" in "
            "config/crewcut.toml.")


# ---- settings ----------------------------------------------------------------------------------------------------
def location(choice: str | None = None) -> str:
    """Where motion comps render: `choice` (--local / --rented), else config/crewcut.toml [render] location."""
    v = choice or str(config.get("crewcut", "render.location", "local") or "local").strip().lower()
    if v not in LOCATIONS:
        raise PlanError(f"render.location must be \"local\" or \"rented\", got {v!r} (config/crewcut.toml)")
    return v


def engine_available(cli: str | None = None) -> bool:
    try:
        find_effectcraft(cli)
        return True
    except BackendError:
        return False


def cpu_count() -> int:
    """CPUs this process may use: the affinity mask, lowered by a cgroup limit (docker --cpus, compose.limits.yaml)."""
    try:
        n = len(os.sched_getaffinity(0))
    except (AttributeError, OSError):
        n = os.cpu_count() or 1
    try:
        quota, period = Path("/sys/fs/cgroup/cpu.max").read_text().split()[:2]
        if quota != "max":
            n = min(n, max(1, int(int(quota) / int(period))))
    except (OSError, ValueError):
        pass
    return max(1, n)


def jobs() -> int:
    """Engine processes at the same time: cores / 4, at least 1."""
    return max(1, cpu_count() // 4)


def cap_usd(plan: Plan, max_usd: float | None = None) -> float:
    """Money cap of one rented motion run: --max-usd, else the default per video (long-form, Short), lowered by the
    plan's `motion_cap_usd`."""
    if max_usd:
        return float(max_usd)
    cap = MOTION_CAP_USD.get(plan.format, MOTION_CAP_USD["landscape"])
    own = plan.p.get("motion_cap_usd")
    if isinstance(own, (int, float)) and not isinstance(own, bool) and own > 0:
        cap = min(cap, float(own))
    return cap


# ---- pieces of one insert ----------------------------------------------------------------------------------------
def work_dir(plan: Plan, ins: Insert) -> Path:
    return plan.episode_dir / "render" / "motion-work" / f"{ins.id}-{ins.hash}"


def font_dir(plan: Plan) -> Path:
    """A fresh per-run folder with the pack's font files (fonts.<role>.files)."""
    d = plan.episode_dir / "render" / "motion-work" / "fonts"
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    for f in font_files(plan.tokens):
        shutil.copy2(f, d / f.name)
    return d


def font_env(folder: Path | str) -> dict[str, str]:
    """EFFECTCRAFT_FONT_DIRS with the run's font folder first (folders already set by the user stay after it)."""
    have = os.environ.get("EFFECTCRAFT_FONT_DIRS", "")
    return {"EFFECTCRAFT_FONT_DIRS": os.pathsep.join(x for x in (str(folder), have) if x)}


def comp_params(plan: Plan, ins: Insert, draft: bool = False) -> dict[str, Any]:
    """comp.new parameters: size, fps, length (the insert plus its extra frames), ground, motion blur."""
    mg = plan.tokens.get("motion_graphics") or {}
    blur = mg.get("blur") or {}
    w, h = ins.size or plan.size
    return mproject.comp_params(COMP, profile=None, width=w, height=h, fps=plan.fps,
                                duration=ins.render_frames / plan.fps,
                                bg=None if ins.transparent else mg.get("ground"),
                                shutter_angle=float(blur.get("shutter", 180)),
                                samples=8 if draft else int(blur.get("samples", 16)))


def chunk_span(first: int, last: int, fps: int) -> tuple[float, float]:
    """Render times of frames first..last: a quarter frame before each edge, so rounding never adds or drops one
    (EffectCraft renders the frames that start inside [start, end))."""
    return max(0.0, (first - 0.25) / fps), (last + 0.75) / fps


def chunks(frames: list[int], fps: int, seconds: float = CHUNK_S) -> list[tuple[int, int]]:
    return runs(frames, max(1, round(seconds * fps)))


def render_args(ins: Insert) -> list[str]:
    """Extra arguments of the engine's `render` for this insert: overlays keep their alpha (no ground)."""
    return ["--channels", "rgba"] if ins.transparent else []


def collect(src: Path, ins: Insert, size: tuple[int, int]) -> list[int]:
    """Move EffectCraft's sequence frames (f_00025.png, at any depth) into the insert folder as 0025.png."""
    got = []
    ins.out_dir.mkdir(parents=True, exist_ok=True)
    for f in sorted(src.rglob("f_*.png")):
        try:
            n = int(f.stem[2:])
        except ValueError:
            continue
        if not 0 <= n < ins.render_frames or not media.valid_png(f, size):
            continue
        f.replace(ins.out_dir / f"{n:04d}.png")
        got.append(n)
    return got


def backdrop_cmd(plan: Plan, ins: Insert, out: Path) -> list[str]:
    """The speaker piece under a full-frame insert, exactly its span, as picture-only ProRes 422 HQ: the base (the
    graded speaker cut) with the zoom the cut shows at the insert's start, or the generated background colour."""
    fps, n = plan.fps, ins.render_frames
    W, H = plan.size
    color = plan.base_color()
    if color:
        src = ["-f", "lavfi", "-i", f"color=c=0x{color.lstrip('#')}:s={W}x{H}:r={fps}:d={n / fps + 0.2:.3f}"]
        vf = ""
    else:
        src = ["-ss", f"{max(0.0, ins.start / fps - 0.004):.3f}", "-i", str(plan.local(plan.p["base"]))]
        vf = speaker_vf(plan, plan.zoom_at(ins.start))
    if ins.size and tuple(ins.size) != (W, H):         # proof-top stage: the part of the frame the stage shows
        vf += f"scale={ins.size[0]}:{ins.size[1]}:force_original_aspect_ratio=increase:flags=lanczos," \
              f"crop={ins.size[0]}:{ins.size[1]},"
    return [media.ffmpeg(), "-y", "-loglevel", "error", *src, "-an",
            "-vf", f"{vf}fps={fps},setsar=1,tpad=stop_mode=clone:stop_duration=1,format=yuv422p10le",
            "-frames:v", str(n), "-c:v", "prores_ks", "-profile:v", "3", str(out)]


def behind_hook(plan: Plan, ins: Insert, runner: media.Runner = media.run, log: Callable = print) -> bool:
    """Hook for overlays with `"layer": "behind"`, called after the overlay clip is encoded.

    Compositing behind the speaker needs a person matte made on this computer (crewcut/motion/matte.py, see
    docs/motion-matte.md). Contract: `matte.composite_behind(plan, ins, runner=..., log=...) -> bool`; it may replace
    `ins.clip`. Until that module exists the overlay is laid over the speaker like any overlay."""
    try:
        matte = importlib.import_module("crewcut.motion.matte")
    except ImportError:
        matte = None
    fn = getattr(matte, "composite_behind", None)
    if fn is None:
        log(f"motion {ins.id}: layer \"behind\" is laid over the speaker for now (the matte step has no "
            "composite_behind yet; see docs/motion-matte.md)")
        return True
    return bool(fn(plan, ins, runner=runner, log=log))


def _finish(plan: Plan, ins: Insert, ok: bool, where: str, runner: media.Runner, log: Callable,
            draft: bool) -> dict:
    enc = html.encode(plan, ins, runner, log) if ok and not plan.missing(ins) else False
    if enc and ins.layer == "behind":
        enc = behind_hook(plan, ins, runner, log)
    return {"id": ins.id, "scene": ins.scene, "frames_ok": ok and not plan.missing(ins), "clip_ok": enc,
            "clip": str(ins.clip), "missing": len(plan.missing(ins)), "where": where, "draft": draft}


# ---- local ------------------------------------------------------------------------------------------------------
def render_insert_local(plan: Plan, ins: Insert, backend: Callable[[dict[str, str]], Any] | None = None,
                        draft: bool = False, runner: media.Runner = media.run, log: Callable = print,
                        fonts: Path | None = None, n_jobs: int | None = None,
                        progress: Callable[[int], None] | None = None) -> bool:
    """Render the missing frames of one motion insert here. True when no frame is missing afterwards.

    `backend(env)` makes the engine wrapper (default: crewcut.motion.backend.Backend with that environment)."""
    miss = plan.missing(ins)
    if not miss:
        return True
    make = backend or (lambda env: Backend(env=env))
    be = make(font_env(fonts if fonts is not None else font_dir(plan)))
    work = work_dir(plan, ins)
    work.mkdir(parents=True, exist_ok=True)
    size = tuple(ins.size or plan.size)
    backdrop = None
    if ins.backdrop == "speaker":
        bd = work / "backdrop.mov"
        if not bd.is_file():
            tmp = work / "backdrop.tmp.mov"
            rc, out = runner(backdrop_cmd(plan, ins, tmp), timeout=900)
            if rc or not tmp.is_file():
                log(f"motion {ins.id}: the speaker backdrop failed: {media.tail(out, 400)}")
                tmp.unlink(missing_ok=True)
                return False
            tmp.replace(bd)
        backdrop = str(bd)
    ctx = motion_context(plan, ins, draft=draft, backdrop=backdrop)
    proj = str(work / "insert.ecproj")
    try:
        code, _ = mtemplates.program_path(ins.template, ins.data, context=ctx)
        (work / "script.jsx").write_text(code, encoding="utf-8")
        mproject.create(be, proj, comp_params(plan, ins, draft), motion_blur=True, overwrite=True)
        be.script(code, project=proj, save=True, name=f"{ins.id}.jsx")
    except (BackendError, mtemplates.TemplateError, ValueError) as e:
        log(f"motion {ins.id} ({ins.scene}): {e}")
        return False
    parts = chunks(miss, plan.fps)
    extra = render_args(ins)

    def one(i_part: tuple[int, tuple[int, int]]) -> int:
        i, (first, last) = i_part
        d = work / "chunks" / f"{first:05d}"
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True)
        s, e = chunk_span(first, last, plan.fps)
        be.render(proj, str(d / SEQ), comp=COMP, start=s, end=e, fmt="png", extra=extra)
        got = collect(d, ins, size)
        shutil.rmtree(d, ignore_errors=True)
        if progress:
            progress(len(got))
        return len(got)

    t0 = time.monotonic()
    try:
        n0 = one((0, parts[0]))
        dt = time.monotonic() - t0
        rest = parts[1:]
        per = dt / max(1, n0)
        k = max(1, n_jobs or jobs())
        if rest:
            left = sum(b - a + 1 for a, b in rest)
            log(f"motion {ins.id} ({ins.scene}): first {n0} frames in {dt:.0f} s ({per:.1f} s per frame); about "
                f"{left * per / k / 60:.1f} min for the other {left} with {k} engine process{'es' if k != 1 else ''}")
            with ThreadPoolExecutor(max_workers=k) as ex:
                list(ex.map(one, enumerate(rest, 1)))
    except BackendError as e:
        log(f"motion {ins.id} ({ins.scene}): {e}")
        return False
    left = plan.missing(ins)
    if left:
        log(f"motion {ins.id} ({ins.scene}): {len(left)} frames missing after the render")
        return False
    log(f"motion {ins.id} ({ins.scene}): {len(miss)} frames in {time.monotonic() - t0:.0f} s")
    return True


# ---- rented ------------------------------------------------------------------------------------------------------
class _RemoteBackend(Backend):
    """Argument lists for a binary on a rented machine (never run here)."""

    @property
    def binary(self) -> str:
        return self.cli or "$BIN"


def _remote_paths(ins: Insert, stage: Path) -> tuple[dict, list[Path]]:
    """The insert's params with every local image path moved to the machine (files copied into the stage)."""
    mapping, files = {}, []
    for i, p in enumerate(ins.assets):
        if p.suffix.lower() in FOOTAGE_EXT:
            raise MotionError(f"motion {ins.id}: footage ({p.name}) never goes to a rented machine; render this "
                              "insert here (--local)")
        dst = stage / ins.id / "assets" / f"{i:02d}-{p.name}"
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, dst)
        mapping[str(p)] = f"{REMOTE}/{ins.id}/assets/{dst.name}"
        files.append(dst)

    def swap(v: Any) -> Any:
        if isinstance(v, dict):
            return {k: swap(x) for k, x in v.items()}
        if isinstance(v, list):
            return [swap(x) for x in v]
        return mapping.get(v, v) if isinstance(v, str) else v

    return swap(json.loads(json.dumps(ins.data))), files


def stage_remote(plan: Plan, inserts: list[Insert], draft: bool = False) -> Path:
    """`render/motion-remote/motion/`: what the rented machine gets, uploaded as /work/motion. Per insert: the
    generated script, the project settings (comp.new), the chunk commands, render.sh, images the params name and the
    template's assets; once: the pack's font files."""
    root = plan.episode_dir / "render" / "motion-remote"
    if root.exists():
        shutil.rmtree(root)
    stage = root / "motion"
    (stage / "fonts").mkdir(parents=True)
    for f in font_files(plan.tokens):
        shutil.copy2(f, stage / "fonts" / f.name)
    rb = _RemoteBackend()
    for ins in inserts:
        d = stage / ins.id
        d.mkdir(parents=True, exist_ok=True)
        params, _ = _remote_paths(ins, stage)
        own = ins.template.parent / "assets"
        shutil.copytree(own if own.is_dir() else mtemplates.assets_dir(), d / "ec_assets")
        ctx = motion_context(plan, ins, draft=draft)
        code, _ = mtemplates.program_path(ins.template, params, context=ctx, assets=f"{REMOTE}/{ins.id}/ec_assets")
        (d / "script.jsx").write_text(code, encoding="utf-8")
        comp = comp_params(plan, ins, draft)
        steps = [{"command": "comp.new", "params": comp},
                 {"command": "comp.setSwitch", "params": {"comp": COMP, "switch": "motionBlur", "value": True}}]
        (d / "project.json").write_text(json.dumps(steps), encoding="utf-8")
        out = f"{REMOTE}/out/{ins.id}"
        lines = []
        for first, last in chunks(plan.missing(ins), plan.fps):
            s, e = chunk_span(first, last, plan.fps)
            argv = rb.argv(["render", "--out", f"{out}/c{first:05d}/{SEQ}", "--comp", COMP, "--start", f"{s:.6f}",
                            "--end", f"{e:.6f}", "--format", "png", *render_args(ins)],
                           project=f"{REMOTE}/{ins.id}/insert.ecproj")
            lines.append(f"mkdir -p {out}/c{first:05d} && \"$BIN\" " + shlex.join(argv[1:])
                         + f" > {REMOTE}/{ins.id}/log-c{first:05d}.txt 2>&1")
        (d / "chunks.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        project = shlex.join(rb.argv(["run", "--commands", "project.json"], empty=True, save_as="insert.ecproj")[1:])
        script = shlex.join(rb.argv(["script", "script.jsx"], project="insert.ecproj", save=True)[1:])
        (d / "render.sh").write_text(
            "#!/bin/sh\n# One motion insert on a rented machine (written by crewcut/render/motion.py).\n"
            "BIN=\"$1\"\nexport BIN\n"
            f"cd {REMOTE}/{ins.id} || exit 1\nexport EFFECTCRAFT_FONT_DIRS={REMOTE}/fonts\nmkdir -p {out}\n"
            f"\"$BIN\" {project} > log-project.txt 2>&1 || {{ tail -5 log-project.txt; exit 1; }}\n"
            f"\"$BIN\" {script} > log-script.txt 2>&1 || {{ tail -5 log-script.txt; exit 1; }}\n"
            "if grep -q '\"error\"' log-script.txt; then tail -5 log-script.txt; exit 1; fi\n"
            "J=$(( $(nproc) / 4 )); [ \"$J\" -ge 1 ] || J=1\n"
            "xargs -d '\\n' -P \"$J\" -I CMD sh -c CMD < chunks.txt || { tail -n 3 log-c*.txt; exit 1; }\n",
            encoding="utf-8")
    return stage


def _local_binary_for_upload() -> Path | None:
    """This computer's effectcraft-cli when it can run on the rented machine (amd64), else None."""
    if platform.machine().lower() not in ("x86_64", "amd64"):
        return None
    try:
        return Path(find_effectcraft())
    except BackendError:
        return None


def build_gpus() -> int:
    """One machine for motion comps (`limits.build_max_gpus` in config/compute.toml)."""
    try:
        from ..compute import settings
        return max(1, int(settings.num("limits.build_max_gpus")))
    except Exception:       # noqa: BLE001 - the compute part is optional
        return 1


def render_rented(plan: Plan, inserts: list[Insert], compute, cap: float, draft: bool = False,
                  runner: media.Runner = media.run, log: Callable = print,
                  progress: Callable[[str, float | None], None] | None = None) -> None:
    """Render the missing frames of these inserts on one rented machine. Leaving the session destroys it.

    Raises compute.NeedsApproval / compute.Refused from the session (the workbench turns them into exit code 3)."""
    for ins in inserts:
        if ins.backdrop == "speaker":
            raise MotionError(f"motion {ins.id}: a speaker backdrop needs the recording, and recordings never go to "
                              "a rented machine; render it here (--local)")
    stage = stage_remote(plan, inserts, draft)
    total = sum(len(plan.missing(x)) for x in inserts)
    minutes = int(min(240, 20 + total * 2.0 / 60))
    log(f"motion: {total} frames of {len(inserts)} insert{'s' if len(inserts) != 1 else ''} on one rented machine "
        f"(cap ${cap:.2f})")
    with compute.session(episode=plan.episode, step="edit", purpose="motion graphics", cap_usd=cap) as s:
        machines = s.rent(gpus=build_gpus(), max_minutes=minutes)
        if not machines:
            raise MotionError("no rented machine is ready; nothing was rendered")
        m = machines[0]
        m.put([stage], "/work/")
        _, out = m.run(f"test -x {REMOTE_BIN} && echo engine-ok || echo engine-missing", timeout=60)
        binary = REMOTE_BIN
        if "engine-ok" not in out:
            local = _local_binary_for_upload()
            if local is None:
                raise MotionError("the rented machine has no effectcraft-cli and this computer cannot send one (it "
                                  "is not amd64 or has none); rent with the Crewcut GPU image ([vast] image in "
                                  "config/compute.toml)")
            m.put([local], f"{REMOTE}/bin/")
            binary = f"{REMOTE}/bin/{local.name}"
            m.run(f"chmod +x {shlex.quote(binary)}", timeout=60)
            log("motion: the rented machine has no effectcraft-cli; sent this computer's binary")
        done = 0
        for ins in inserts:
            n = len(plan.missing(ins))
            t0 = time.monotonic()
            rc, out = m.run(f"sh {REMOTE}/{ins.id}/render.sh {shlex.quote(binary)}",
                            timeout=max(900, ins.render_frames * 20), doing=f"rendering motion {ins.id}")
            work = work_dir(plan, ins) / "chunks"
            if work.exists():
                shutil.rmtree(work)
            m.get(f"{REMOTE}/out/{ins.id}/", work)
            got = collect(work, ins, tuple(ins.size or plan.size))
            shutil.rmtree(work, ignore_errors=True)
            done += n
            log(f"motion {ins.id} ({ins.scene}): {len(got)} of {n} frames on the rented machine in "
                f"{time.monotonic() - t0:.0f} s" + (f" ({media.tail(out, 300)})" if rc or len(got) < n else ""))
            if progress:
                progress(f"Rendering motion graphics on a rented machine: {done} of {total} frames",
                         done / max(1, total))
    log("motion: rented machine released")


# ---- the whole step ------------------------------------------------------------------------------------------------
def render_motion(plan: Plan, ids: list[str] | None = None, draft: bool = False, location: str | None = None,
                  compute=None, runner: media.Runner = media.run, log: Callable = print,
                  progress: Callable[[str, float | None], None] | None = None,
                  backend: Callable[[dict[str, str]], Any] | None = None, max_usd: float | None = None) -> dict:
    """Render every motion insert with missing frames (here or on a rented machine), then encode. One row per insert.

    Raises EngineMissing when the engine is not installed here and something has to render here."""
    where = _location(location)
    allx = plan.of_kind("motion", ids)
    if draft:
        allx = [plan.motion_draft(x) for x in allx]
    todo = [x for x in allx if plan.missing(x)]
    busy = {x.id for x in todo}
    frames = sum(len(plan.missing(x)) for x in todo)
    if not todo:
        return {"way": "none", "frames": 0,
                "rows": [_finish(plan, x, True, "cached", runner, log, draft) for x in allx]}
    if where == "rented":
        if compute is None:
            compute = importlib.import_module("crewcut.compute")
        render_rented(plan, todo, compute, cap_usd(plan, max_usd), draft, runner, log, progress)
        return {"way": "rented", "frames": frames, "cap_usd": cap_usd(plan, max_usd),
                "rows": [_finish(plan, x, not plan.missing(x), "rented" if x.id in busy else "cached", runner, log,
                                 draft) for x in allx]}
    if backend is None and not engine_available():
        raise EngineMissing([x.id for x in todo])
    fonts = font_dir(plan)
    done = [0]
    lock = threading.Lock()

    def tick(n: int) -> None:
        with lock:
            done[0] += n
            if progress:
                progress(f"Rendering motion graphics here: {done[0]} of {frames} frames", done[0] / max(1, frames))

    rows = []
    for x in allx:
        ok = render_insert_local(plan, x, backend, draft, runner, log, fonts, progress=tick) if x.id in busy else True
        rows.append(_finish(plan, x, ok, "here" if x.id in busy else "cached", runner, log, draft))
    return {"way": "local", "frames": frames, "rows": rows}


def _location(choice: str | None) -> str:
    return location(choice)
