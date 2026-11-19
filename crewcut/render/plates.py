"""Blender plates for motion inserts: image sequences a comp lays in (plan sections 3.2 and 3.4).

A motion insert may list plates: `"plates": [{"id": "gpu", "script": "motion/m3/plates/gpu3d.py",
"args": {"t0": 0.0, "tin": 1.2}, "frames": 120}]`. Each plate is a Blender script of the episode (or of a library
template) that takes `--out DIR --frames A-B` plus its own arguments, with times in the comp's seconds: frame `f`
shows comp time `t0 + (f - 1) / fps`. It renders PNG (RGBA) frames `0001.png ...` into
`render/plates/<insert>-<plate>-<hash>/`; the hash covers the script, its args, the look tokens and the fonts, so a
changed plate renders again and an unchanged one never does.

Where: a computer with its own NVIDIA GPU renders here; every other computer rents one RTX 4090 through
`crewcut.compute` after a spend card (only the plate scripts, their args and font files go up). `--probe` makes one
half-size still per plate first. The comp gets the plates through `CC_CTX.plates` (`CC.plate(id)` in a template).
"""

from __future__ import annotations

import hashlib
import json
import shlex
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from . import blender, media
from .plan import Insert, Plan, PlanError

REMOTE = "/work/plates"


@dataclass
class Plate:
    insert_id: str
    id: str
    script: Path
    args: dict
    frames: int
    hash: str
    out_dir: Path
    quality: dict = field(default_factory=dict)
    source_root: Path | None = None

    def done(self) -> int:
        if not self.out_dir.is_dir():
            return 0
        return sum(1 for p in self.out_dir.iterdir() if p.suffix in (".png", ".jpg") and p.stem.isdigit())

    @property
    def complete(self) -> bool:
        try:
            receipt = json.loads((self.out_dir / "complete.json").read_text())
            return (receipt.get("profile") == self.quality and receipt.get("frames") == self.frames
                    and all((self.out_dir / f"{n:04d}.png").is_file() for n in range(1, self.frames + 1)))
        except (OSError, ValueError):
            return False

    @property
    def first(self) -> Path:
        return self.out_dir / "0001.png"


def _fonts(plan: Plan) -> list[Path]:
    out = []
    for spec in (plan.tokens.get("fonts") or {}).values():
        for f in (spec or {}).get("files") or []:
            p = Path(f)
            if p.is_file():
                out.append(p)
    return out


def plate_hash(plan: Plan, script: Path, args: dict, frames: int) -> str:
    h = hashlib.sha1()
    h.update(script.read_bytes())
    for source in sorted(code_root(plan, script).rglob("*.py")):
        root = code_root(plan, script)
        if source.is_symlink() or root.resolve() not in source.resolve().parents:
            raise PlanError("Plate code dependencies must stay inside their source folder.")
        h.update(source.relative_to(root).as_posix().encode() + source.read_bytes())
    h.update(json.dumps({"args": args, "frames": frames, "fps": plan.fps}, sort_keys=True).encode())
    h.update(json.dumps(quality_profile(plan), sort_keys=True).encode())
    h.update(json.dumps({k: plan.tokens.get(k) for k in ("colors", "motion_graphics")}, sort_keys=True,
                        default=str).encode())
    for f in _fonts(plan):
        h.update(f.name.encode() + str(f.stat().st_size).encode())
    return h.hexdigest()[:10]


def code_root(plan: Plan, script: Path) -> Path:
    motion = plan.episode_dir / "motion"
    if script.is_relative_to(motion) and len(script.relative_to(motion).parts) > 1:
        return motion / script.relative_to(motion).parts[0]
    return script.parent


def quality_profile(plan: Plan) -> dict:
    from ..compute import settings
    return {"version": 1, "size": list(plan.size),
            "samples": int(plan.tokens.get("stage3d", {}).get("samples") or settings.get("render3d.samples") or 128)}


def plates_of(plan: Plan, ins: Insert) -> list[Plate]:
    """The plates of one motion insert, resolved inside the episode folder."""
    out = []
    for p in ins.plates or []:
        script = plan.local(p["script"])
        if not script.is_file():
            raise PlanError(f"insert {ins.id}: plate {p['id']}: script {p['script']} not found")
        args = dict(p.get("args") or {})
        frames = int(p.get("frames") or 0)
        if frames < 1:
            raise PlanError(f"insert {ins.id}: plate {p['id']}: frames must be 1 or more")
        h = plate_hash(plan, script, args, frames)
        source_root = code_root(plan, script)
        out.append(Plate(ins.id, str(p["id"]), script, args, frames, h,
                         plan.episode_dir / "render" / "plates" / f"{ins.id}-{p['id']}-{h}", quality_profile(plan), source_root))
    return out


def all_plates(plan: Plan, ids: list[str] | None = None) -> list[Plate]:
    return [pl for ins in plan.inserts if ins.kind == "motion" and (not ids or ins.id in ids)
            for pl in plates_of(plan, ins)]


def context_plates(plan: Plan, ins: Insert) -> dict:
    """CC_CTX.plates of an insert: {id: {"first": path of 0001.png, "frames": n, "ready": bool}}. A plate whose script
    is missing is listed as not ready (the plan still parses; `render plates` names the missing script)."""
    try:
        return {pl.id: {"first": str(pl.first), "frames": pl.frames, "ready": pl.complete}
                for pl in plates_of(plan, ins)}
    except PlanError:
        return {str(p.get("id")): {"first": None, "frames": int(p.get("frames") or 0), "ready": False}
                for p in ins.plates or []}


def arg_list(args: dict) -> list[str]:
    out = []
    for k, v in sorted(args.items()):
        flag = "--" + str(k).replace("_", "-")
        if v is True:
            out.append(flag)
        elif v is False or v is None:
            continue
        else:
            out += [flag, ",".join(str(x) for x in v) if isinstance(v, (list, tuple)) else str(v)]
    return out


def blender_cmd(binary: str, script: str, out: str, frames: str, args: dict, half: bool = False,
                quality: dict | None = None, gpu: bool = False) -> list[str]:
    from . import plate_quality
    setup = ["--python-exit-code", "23", "--python-expr", plate_quality.bootstrap(quality, out, half, gpu)] if quality else []
    return [binary, "-b", "--factory-startup", *setup, "--python", script, "--", "--out", out, "--frames", frames,
            *arg_list(args), *(["--half"] if half else [])]


def render_local(plan: Plan, plates: list[Plate], probe: bool = False, runner: media.Runner = media.run,
                 log: Callable = print) -> list[dict]:
    rows = []
    from . import plate_quality
    gpu = blender.local_gpu(runner)
    for pl in plates:
        target = pl.out_dir / "probe" if probe else pl.out_dir
        target.mkdir(parents=True, exist_ok=True)
        frames = f"{max(1, pl.frames // 2)}-{max(1, pl.frames // 2)}" if probe else f"1-{pl.frames}"
        rc, out = runner(blender_cmd(blender.blender_bin(), str(pl.script), str(target), frames, pl.args,
                                     half=probe, quality=pl.quality, gpu=gpu), timeout=24 * 3600)
        ok, reason = plate_quality.verify(target, pl.frames, pl.quality, probe=probe, gpu=gpu) if rc == 0 else (False, out)
        log(f"plate {pl.insert_id}/{pl.id}: {'ok' if ok else 'failed: ' + media.tail(out, 300)}")
        rows.append({"insert": pl.insert_id, "plate": pl.id, "ok": ok, "dir": str(target), "where": "local", "quality": reason})
    return rows


def remote_script(pl: Plate, probe: bool) -> str:
    frames = f"{max(1, pl.frames // 2)}-{max(1, pl.frames // 2)}" if probe else f"1-{pl.frames}"
    d = f"{REMOTE}/{pl.insert_id}-{pl.id}"
    script = pl.script.relative_to(pl.source_root or pl.script.parent).as_posix()
    cmd = blender_cmd(blender.REMOTE_BLENDER, f"{d}/{script}", f"{d}/out", frames, pl.args, half=probe,
                      quality=pl.quality, gpu=True)
    return f"mkdir -p {d}/out && cd {d} && " + " ".join(shlex.quote(c) for c in cmd)


def render_rented(plan: Plan, plates: list[Plate], compute, cap_usd: float, probe: bool = False,
                  log: Callable = print) -> list[dict]:
    """One rented GPU for every plate of the plan (spend card first; the session's exit destroys the machine)."""
    stage = plan.episode_dir / "render" / "plates-remote"
    if stage.exists():
        import shutil
        shutil.rmtree(stage)
    uploads = []
    for pl in plates:
        d = stage / f"{pl.insert_id}-{pl.id}"
        d.mkdir(parents=True)
        root = pl.source_root or pl.script.parent
        for source in root.rglob("*.py"):
            if source.is_symlink() or root.resolve() not in source.resolve().parents:
                raise PlanError("Plate code dependencies must stay inside their source folder.")
            target = d / source.relative_to(root)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())
        uploads.append(d)
    fonts = _fonts(plan)
    rows = []
    from . import plate_quality
    with compute.session(episode=plan.episode, step="edit", purpose="motion plates", cap_usd=cap_usd) as s:
        m = s.rent(gpus=1, max_minutes=180)[0]
        m.put([*uploads, *fonts], f"{REMOTE}/")
        if fonts:
            m.run(f"mkdir -p /usr/share/fonts/truetype/crewcut && cp {REMOTE}/*.[ot]tf /usr/share/fonts/truetype/crewcut/"
                  " 2>/dev/null; fc-cache -f > /dev/null 2>&1 || true", timeout=120)
        for pl in plates:
            rc, out = m.run(remote_script(pl, probe), timeout=6 * 3600, doing=f"Blender plate {pl.insert_id}/{pl.id}")
            if rc == 0:
                target = pl.out_dir / "probe" if probe else pl.out_dir
                target.mkdir(parents=True, exist_ok=True)
                m.get(f"{REMOTE}/{pl.insert_id}-{pl.id}/out/", target)
            else:
                target = pl.out_dir
            ok, reason = plate_quality.verify(target, pl.frames, pl.quality, probe=probe, gpu=True) if rc == 0 else (False, out)
            log(f"plate {pl.insert_id}/{pl.id} (rented): {'ok' if ok else 'failed: ' + media.tail(out, 300)}")
            rows.append({"insert": pl.insert_id, "plate": pl.id, "ok": ok, "dir": str(target), "where": "rented", "quality": reason})
    return rows


def render_plates(plan: Plan, ids: list[str] | None = None, probe: bool = False, location: str | None = None,
                  compute=None, max_usd: float | None = None, runner: media.Runner = media.run,
                  log: Callable = print) -> dict:
    """Every missing plate: here with an own NVIDIA GPU (or `location="local"`), else on one rented RTX 4090."""
    todo = [pl for pl in all_plates(plan, ids) if probe or not pl.complete]
    if not todo:
        return {"way": "none", "rows": []}
    way = location or ("local" if blender.local_gpu(runner) else "rented")
    if way == "local":
        return {"way": "local", "rows": render_local(plan, todo, probe, runner, log)}
    if compute is None:
        import importlib
        compute = importlib.import_module("crewcut.compute")
    from .behind import cap_usd
    cap = cap_usd(plan, max_usd)
    return {"way": "rented", "cap_usd": cap, "rows": render_rented(plan, todo, compute, cap, probe, log)}
