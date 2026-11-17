"""Graphics behind the speaker: the matte step for overlays with `"layer": "behind"` and the composite after it.

    crewcut render matte <plan>     cut the speaker piece of each "behind" overlay (with a margin), make the person
                                    matte on a rented GPU (spend card first; never on this computer), run the edge
                                    check, write render/matte/<id>/decision.json
    crewcut render motion <plan>    renders the overlay; CC_CTX.layer is "behind" only when the decision says so,
                                    else "beside" (the template then places the graphic next to the person)
    after the overlay is encoded    composite: speaker piece -> graphic -> person on top, at the speaker's exact size,
                                    as <insert>-behind.mp4; the cut uses it as a full-frame insert

Docs: docs/motion-matte.md. The person matte is RobustVideoMatting (GPL-3.0), run on the rented machine as its own
program; nothing of it is shipped or imported here.
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Callable
from pathlib import Path

from ..motion import matte
from . import media
from .plan import Insert, Plan

CAP_LONG_USD, CAP_SHORT_USD = 2.0, 0.5          # the owner's default money caps per video (plan motion_cap_usd lowers)


def behind_inserts(plan: Plan, ids: list[str] | None = None) -> list[Insert]:
    """Motion overlays that ask to sit behind the speaker."""
    out = [x for x in plan.inserts if x.kind == "motion" and x.layer == "behind"]
    return [x for x in out if x.id in ids] if ids else out


def margin_frames(plan: Plan) -> int:
    return round(matte.MARGIN_S * plan.fps)


def shot_insert(plan: Plan, ins: Insert) -> Insert:
    """The insert's span with the matte margin on both sides (the recurrent model settles before the span starts)."""
    m = margin_frames(plan)
    a = max(0, ins.start - m)
    b = ins.end + m
    return dataclasses.replace(ins, start=a, end=b, start_s=a / plan.fps, end_s=b / plan.fps, backdrop="speaker")


def prepare_shot(plan: Plan, ins: Insert, runner: media.Runner = media.run, log: Callable = print) -> matte.Shot:
    """Cut the graded, zoomed speaker piece (what the cut shows) of the span plus margins into render/matte/<id>.mp4,
    picture only, and record where it starts in the video. Kept when the span did not change."""
    from .motion import backdrop_cmd
    shot = matte.Shot(ins.id, plan.episode_dir, fps=plan.fps)
    ext = shot_insert(plan, ins)
    meta = matte.read_meta(shot.clip)
    span = [round(ext.start_s, 3), round(ext.end_s, 3)]
    if shot.clip.is_file() and [meta.get("clip_start_s"), meta.get("clip_end_s")] == span:
        return shot
    shot.matte_dir.mkdir(parents=True, exist_ok=True)
    piece = shot.matte_dir / f".{ins.id}.piece.mov"
    rc, out = runner(backdrop_cmd(plan, ext, piece), timeout=1800)
    if rc != 0 or not piece.is_file():
        raise matte.MatteError(f"{ins.id}: the speaker piece could not be cut: {media.tail(out, 300)}")
    try:
        matte.export_shot(piece, 0.0, ext.frames / plan.fps, shot.clip, runner, fps=plan.fps, margin_s=0.0)
    finally:
        piece.unlink(missing_ok=True)
    meta = matte.read_meta(shot.clip)
    meta.update(source="speaker piece", clip_start_s=span[0], clip_end_s=span[1],
                start_s=round(ins.start_s, 3), end_s=round(ins.end_s, 3))
    matte.meta_path(shot.clip).write_text(json.dumps(meta, indent=2), encoding="utf-8")
    log(f"matte {ins.id}: speaker piece {span[0]:.2f}-{span[1]:.2f} s cut ({shot.clip.stat().st_size / 1e6:.1f} MB)")
    return shot


def cap_usd(plan: Plan, max_usd: float | None = None) -> float:
    cap = CAP_SHORT_USD if plan.format == "portrait" else CAP_LONG_USD
    lower = plan.p.get("motion_cap_usd")
    for v in (lower, max_usd):
        if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0:
            cap = min(cap, float(v))
    return cap


def render_matte(plan: Plan, ids: list[str] | None = None, compute=None, max_usd: float | None = None,
                 runner: media.Runner = media.run, log: Callable = print) -> dict:
    """The matte step for every "behind" overlay that has no decision yet (or whose span changed).

    Raises the compute module's NeedsApproval/Refused (the caller turns them into exit code 3)."""
    todo = []
    for ins in behind_inserts(plan, ids):
        shot = prepare_shot(plan, ins, runner, log)
        if plan.matte_decision(ins) and matte.read_meta(shot.clip).get("matted_sha256") == _sha(shot.clip):
            log(f"matte {ins.id}: done before ({plan.matte_decision(ins).get('place')})")
            continue
        todo.append((ins, shot))
    rows = [{"id": i.id, "place": (plan.matte_decision(i) or {}).get("place"), "done_before": True}
            for i in behind_inserts(plan, ids) if i.id not in {x.id for x, _ in todo}]
    if not todo:
        return {"rented": False, "rows": rows}
    if compute is None:
        import importlib
        compute = importlib.import_module("crewcut.compute")
    cap = cap_usd(plan, max_usd)
    results = matte.matte_rented([s for _, s in todo], compute, cap, log=log, runner=runner)
    for (ins, shot), r in zip(todo, results, strict=True):
        if r.ok:
            meta = matte.read_meta(shot.clip)
            meta["matted_sha256"] = _sha(shot.clip)
            matte.meta_path(shot.clip).write_text(json.dumps(meta, indent=2), encoding="utf-8")
        d = plan.matte_decision(ins) or {}
        place = d.get("place") or "beside"
        log(f"matte {ins.id}: {place}" + (f" ({d.get('reason')})" if d.get("reason") else ""))
        rows.append({"id": ins.id, "ok": r.ok, "place": place, "reason": d.get("reason") or r.error,
                     "frames": r.frames})
    return {"rented": True, "cap_usd": cap, "rows": rows}


def _sha(p: Path) -> str:
    from ..compute import privacy
    return privacy.sha256(p)


def composite_behind(plan: Plan, ins: Insert, runner: media.Runner = media.run, log: Callable = print) -> bool:
    """After the overlay clip is encoded: speaker piece -> graphic -> person on top, as <insert>-behind.mp4.
    Nothing to do (True) when the decision is "beside": the overlay then lies next to the person like any overlay."""
    if plan.layer_for(ins) != "behind":
        log(f"motion {ins.id}: beside the person ({(plan.matte_decision(ins) or {}).get('reason') or 'no matte yet'})")
        return True
    shot = matte.Shot(ins.id, plan.episode_dir, fps=plan.fps)
    meta = matte.read_meta(shot.clip)
    out = Path(str(ins.out_dir) + "-behind.mp4")
    if out.is_file() and out.stat().st_mtime >= ins.clip.stat().st_mtime:
        return True
    W, H = ins.size or plan.size
    tmp = out.with_name(f".{out.stem}.part.mp4")
    # the speaker piece starts at clip_start_s of the video: times relative to it
    t0 = float(meta.get("clip_start_s", ins.start_s))
    args = matte.composite_args(shot.clip, ins.clip, shot.out_dir, start_s=ins.start_s - t0, end_s=ins.end_s - t0,
                                clip_start_s=0.0, fps=plan.fps, place=matte.Place(W, H), out=tmp)
    rc, text = runner(args, timeout=1800)
    if rc != 0 or not tmp.is_file():
        tmp.unlink(missing_ok=True)
        log(f"motion {ins.id}: the composite behind the speaker failed: {media.tail(text, 300)}")
        return False
    tmp.replace(out)
    log(f"motion {ins.id}: behind the speaker ({out.name})")
    return True
