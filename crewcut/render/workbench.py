"""The edit plan workbench: every render step for one plan (ported from the author's earlier studio).

    plan    show inserts, frames, cues and what is already rendered
    2d      render the 2D inserts (Chromium) and encode them
    3d      render the 3D inserts: here (--local) or on rented GPUs (--rented); without a flag the estimate decides,
            and a card asks the user before any money is spent
    probe   still frames at half size, to look at before the big render
    cut     the finished video with sound
    shown   lock the output right after someone has seen it
    all     2d, 3d, cut
"""

from __future__ import annotations

import importlib
import os
from collections.abc import Callable
from pathlib import Path

from .. import approvals, db, events, paths
from . import assemble, blender, html, measure, media
from .plan import Plan, PlanError

RENT_FOR = "render-3d"


class Waiting(Exception):
    """The user has to answer first (a card is open), or the spend was refused. Exit code 3."""

    def __init__(self, message: str, card_id: int | None = None):
        super().__init__(message)
        self.card_id = card_id


def load_compute():
    return importlib.import_module("crewcut.compute")


def progress_fn(plan: Plan) -> Callable[[str, float | None], None]:
    """Updates the running job's 'doing' line in the right column when the conductor started us (CREWCUT_JOB)."""
    job = os.environ.get("CREWCUT_JOB", "")

    def report(text: str, fraction: float | None = None) -> None:
        if not job.isdigit():
            return
        try:
            db.update("jobs", int(job), doing=text, progress=None if fraction is None else round(fraction, 3))
            events.emit("activity", episode=plan.episode, identity=os.environ.get("CREWCUT_IDENTITY"), text=text,
                        data={"job": int(job), "doing": text, "progress": fraction})
        except Exception:       # the render must not fail because the UI could not be told
            pass
    return report


# ---- 2D -----------------------------------------------------------------------------------------------------------
def render_2d(plan: Plan, ids: list[str] | None = None, images_only: bool = False,
              runner: media.Runner = media.run, log: Callable = print) -> list[dict]:
    return html.render_2d(plan, ids, images_only, runner, log)


# ---- 3D: here or rented ------------------------------------------------------------------------------------------
def rent_decision(plan: Plan) -> tuple[str | None, dict | None]:
    """The user's last answer for this episode on the 'rent a GPU for 3D' card: open, accepted, declined or None."""
    cards = [c for c in approvals.list_cards(episode=plan.episode)
             if c.get("kind") == "spend" and (c.get("data") or {}).get("for") == RENT_FOR and c.get("status") != "expired"]
    if not cards:
        return None, None
    last = max(cards, key=lambda c: c["id"])
    return last["status"], last


def choose_way(plan: Plan, frames: int, gpus: int, compute=None, log: Callable = print) -> str:
    """'local' or 'rented'. Raises Waiting when a card asks the user (never chooses money silently)."""
    status, card = rent_decision(plan)
    if status == "open":
        raise Waiting(f"Waiting for your answer on card {card['id']}: {card['title']}", card["id"])
    if status == "accepted":
        return "rented"
    if status == "declined":
        log("3d: rendering here, as you said for this episode")
        return "local"
    if blender.local_gpu():
        log("3d: this machine has its own GPU; rendering here")
        return "local"
    try:
        compute = compute or load_compute()
    except ImportError:
        log("3d: renting is not available in this build; rendering here")
        return "local"
    est = compute.estimate(kind="blender", frames=frames, local_sec_per_frame=blender.local_sec_per_frame(False),
                           gpus=gpus)
    if not est.get("suggest_rent"):
        log(f"3d: {est.get('sentence', '')} Rendering here.".strip())
        return "local"
    title = "Rent a GPU for the 3D scenes"
    body = f"{est.get('sentence', '')} Local is fine too: say so and it renders here.".strip()
    data = {"for": RENT_FOR, "plan": plan.path.name, "step": "edit", "frames": frames, "estimate": est,
            "referral": est.get("referral"), "cap_usd": est.get("rented_usd_worst")}
    try:
        ok, card_id, reason = approvals.require_spend(plan.episode, float(est.get("rented_usd") or 0), title, body=body,
                                                      data=data)
    except approvals.RightsError:
        # this crew member may not spend; the card still asks the user, someone who may spend rents after a yes
        amount = float(est.get("rented_usd") or 0)
        card = approvals.propose(plan.episode, "edit", "spend", title, body=body,
                                 data={**data, "amount_usd": round(amount, 4),
                                       "budget_usd": round(float(est.get("rented_usd_worst") or amount), 2)})
        raise Waiting(f"Posted card {card['id']}: {body}", card["id"]) from None
    if ok:
        log("3d: renting is inside the budget you approved")
        return "rented"
    if card_id:
        raise Waiting(f"Posted card {card_id}: {body}", card_id)
    log(f"3d: {reason} Rendering here.")
    return "local"


def _compute_error(compute, e: Exception) -> Exception | None:
    """Map the compute module's exceptions: NeedsApproval/Refused -> Waiting; anything with exit_code passes."""
    for name in ("NeedsApproval", "Refused"):
        cls = getattr(compute, name, None)
        if isinstance(cls, type) and isinstance(e, cls):
            card = getattr(e, "card_id", None) or (e.args[0] if e.args and isinstance(e.args[0], int) else None)
            msg = f"Waiting for your yes on card {card} before renting" if name == "NeedsApproval" else f"Renting refused: {e}"
            return Waiting(msg, card)
    return None


def render_3d(plan: Plan, mode: str | None = None, gpus: int = 2, ids: list[str] | None = None,
              samples: int | None = None, draft: bool = False, max_usd: float | None = None, compute=None,
              runner: media.Runner = media.run, log: Callable = print) -> dict:
    todo = [x for x in plan.of_kind("3d", ids) if plan.missing(x)]
    frames = sum(len(plan.missing(x)) for x in todo)
    if draft:
        samples = samples or 32
    report = progress_fn(plan)
    if not todo:
        rows = [{"id": x.id, "scene": x.scene, "frames_ok": True, "clip_ok": html.encode(plan, x, runner, log),
                 "clip": str(x.clip), "missing": 0} for x in plan.of_kind("3d", ids)]
        return {"way": "none", "frames": 0, "rows": rows}
    if mode is None:
        mode = choose_way(plan, frames, gpus, compute, log)
    if mode == "local":
        rows = blender.render_local(plan, ids, samples, runner=runner, log=log, progress=report)
        return {"way": "local", "frames": frames, "rows": rows}
    compute = compute or load_compute()
    est = compute.estimate(kind="blender", frames=frames, local_sec_per_frame=blender.local_sec_per_frame(False),
                           gpus=gpus)
    cap = float(max_usd) if max_usd else round(max(0.05, float(est.get("rented_usd_worst") or 1.0) * 1.25), 2)
    minutes = int(min(240, float(est.get("rented_seconds") or 3600) / 60 * 1.5 + 15))
    try:
        rows = blender.render_rented(plan, compute, ids, gpus, samples, cap_usd=cap, max_minutes=minutes, log=log,
                                     runner=runner, progress=report)
    except Exception as e:
        mapped = _compute_error(compute, e)
        if mapped:
            raise mapped from e
        raise
    return {"way": "rented", "frames": frames, "gpus": gpus, "cap_usd": cap, "rows": rows}


# ---- probe ---------------------------------------------------------------------------------------------------------
def probe(plan: Plan, ids: list[str] | None = None, frames: list[int] | None = None, rented: bool = False,
          samples: int = 64, compute=None, runner: media.Runner = media.run, log: Callable = print) -> dict:
    """Stills at half size. Default: every 3D insert at a frame after its last cue. 2D inserts only when named."""
    picked = [x for x in plan.inserts if x.kind in ("2d", "3d") and (x.id in ids if ids else x.kind == "3d")]
    if ids:
        unknown = [i for i in ids if not any(x.id == i for x in plan.inserts)]
        if unknown:
            raise PlanError(f"no insert with id {', '.join(unknown)}")
    items = [(x, min(max(0, f), x.render_frames - 1)) for x in picked
             for f in (frames or [blender.default_probe_frame(x)])]
    out_dir = plan.episode_dir / "render" / "probe"
    got: list[Path] = []
    for ins, f in (i for i in items if i[0].kind == "2d"):
        p = html.still(plan, ins, f, out_dir, runner)
        log(f"probe {ins.id}-{f:04d}.png: {'ok' if p else 'failed'}")
        if p:
            got.append(p)
    three = [i for i in items if i[0].kind == "3d"]
    if three:
        if rented:
            compute = compute or load_compute()
            try:
                got += blender.probe_rented(plan, three, compute, samples=samples, log=log)
            except Exception as e:
                mapped = _compute_error(compute, e)
                if mapped:
                    raise mapped from e
                raise
        else:
            got += blender.probe_local(plan, three, samples=samples, runner=runner, log=log)
    measured = []
    for p in got:
        if any(p.name.startswith(ins.id + "-") for ins, _ in three):
            m = measure.measure(p, plan.pack)
            measured.append(m)
            for line in measure.lines(m):
                log(line)
    return {"stills": [str(p) for p in got], "measured": measured, "dir": str(out_dir)}


# ---- cut, shown, all ---------------------------------------------------------------------------------------------
def cut(plan: Plan, runner: media.Runner = media.run, log: Callable = print) -> dict:
    return assemble.cut(plan, runner, log, progress=progress_fn(plan))


def shown(plan: Plan) -> dict:
    return assemble.shown(plan)


# ---- samples of every 2D scene (for CI screenshots and the docs) ---------------------------------------------------
def scenes_2d() -> list[str]:
    d = paths.templates_dir() / "2d"
    skip = {"base", "motion", "scene"}
    return sorted(p.stem for p in d.glob("*.html") if p.stem not in skip)


def samples(out_dir: Path, formats: tuple[str, ...] = ("landscape", "portrait"), frame: int = -1,
            pack=None, runner: media.Runner = media.run, log: Callable = print) -> list[dict]:
    """Render one frame of every 2D scene's built-in example in each format, in the given (or active) pack."""
    import json

    from .. import brand
    from .plan import render_tokens
    pack = pack or brand.load()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    tokens = out_dir / "brand.json"
    tokens.write_text(json.dumps(render_tokens(pack), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    rows = []
    for scene in scenes_2d():
        for fmt in formats:
            data = out_dir / f"{scene}-{fmt}.data.json"
            data.write_text(json.dumps({"example": True, "format": fmt}) + "\n", encoding="utf-8")
            work = out_dir / f".{scene}-{fmt}"
            cmd = html.render_cmd(paths.templates_dir() / "2d" / f"{scene}.html", work, data, tokens,
                                  transparent=scene == "keyword", frm=frame, to=frame)
            rc, out = runner(cmd, timeout=600)
            pngs = sorted(work.glob("*.png")) if work.is_dir() else []
            dst = out_dir / f"{scene}-{fmt}.png"
            if rc == 0 and pngs:
                pngs[-1].replace(dst)
                for p in pngs[:-1]:
                    p.unlink()
                work.rmdir()
            ok = rc == 0 and dst.is_file()
            log(f"{scene} {fmt}: {'ok' if ok else 'failed: ' + media.tail(out, 300)}")
            rows.append({"scene": scene, "format": fmt, "ok": ok, "png": str(dst) if ok else None})
    return rows
