"""Blender plates of motion inserts: the jobs, their cache folders, and renting a GPU for them (motion plan 3.2, 3.4).

A plate is a Blender job a comp needs before it renders: ``{"id", "script", "args", "frames"}`` in a motion insert's
``plates``. Each plate has its own hash (script, args, tokens) and lives in ``render/plates/<id>-<hash>/``. Only the
plate scripts, their args, the tokens and the pack's font files go to a rented machine: never footage, voice or keys.

Renting follows the compute rule: nothing is rented before a ``spend`` card has the user's yes. The cap of that card is
the number from the approved motion plan (``cap_usd``). The Blender run itself is a function the caller passes
(``run_job``); the render path owns it.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .. import brand, paths

HASH_LEN = 10


def tokens(pack: Any = None) -> dict:
    t = (pack or brand.load()).render_tokens()
    return {k: t.get(k) for k in ("colors", "fonts", "shape", "stage3d", "motion_graphics") if t.get(k) is not None}


def plate_hash(script: Path, args: dict, toks: dict) -> str:
    h = hashlib.sha256()
    h.update(script.read_bytes())
    h.update(json.dumps(args or {}, sort_keys=True).encode())
    h.update(json.dumps(toks or {}, sort_keys=True, default=str).encode())
    return h.hexdigest()[:HASH_LEN]


def jobs(episode_dir: Path | str, plan_json: dict, ids: list[str] | None = None, pack: Any = None) -> list[dict]:
    """The plate jobs of the plan's motion inserts (only ``ids`` when given): ``{"insert", "id", "script", "args",
    "frames", "hash", "out", "missing"}``. ``missing`` is True until ``out`` holds ``frames`` PNG files."""
    ep_dir = Path(episode_dir)
    toks = tokens(pack)
    out = []
    for e in (plan_json or {}).get("inserts") or []:
        if not isinstance(e, dict) or e.get("kind") != "motion" or (ids and str(e.get("id")) not in ids):
            continue
        for pl in e.get("plates") or []:
            if not isinstance(pl, dict) or not pl.get("id") or not pl.get("script"):
                raise ValueError(f"insert {e.get('id')}: a plate needs an id and a script")
            script = paths.inside(ep_dir, str(pl["script"]))
            if not script.is_file():
                raise ValueError(f"insert {e.get('id')}: plate script {pl['script']} not found")
            h = plate_hash(script, pl.get("args") or {}, toks)
            folder = ep_dir / "render" / "plates" / f"{pl['id']}-{h}"
            frames = int(pl.get("frames") or 1)
            have = len(list(folder.glob("*.png"))) if folder.is_dir() else 0
            out.append({"insert": str(e.get("id")), "id": str(pl["id"]), "script": script,
                        "args": pl.get("args") or {}, "frames": frames, "hash": h, "out": folder,
                        "missing": have < frames})
    return out


def cap_for(episode_dir: Path | str) -> float:
    """The money cap for this video's rented work: the approved motion plan's cap, else the default ($2 long-form,
    $0.50 a Short)."""
    from . import director
    ep_dir = Path(episode_dir)
    acc, _ = director._plan_cards(ep_dir.name)
    plan, _why = director._card_plan(ep_dir, acc)
    if plan and plan.get("cap_usd"):
        return float(plan["cap_usd"])
    short = False
    try:
        pj = json.loads((ep_dir / "project.json").read_text(encoding="utf-8"))
        short = pj.get("kind") == "short" or pj.get("format") == "portrait"
    except (OSError, ValueError):
        pass
    return director._cap(short)


def rent(episode: str, todo: list[dict], run_job: Callable[[Any, dict], Any], compute: Any = None,
         cap_usd: float | None = None, gpus: int = 1, max_minutes: float = 60, log: Callable = print,
         **session_kw: Any) -> list[dict]:
    """Render the missing plates on a rented GPU. Raises the compute session's ``NeedsApproval`` (exit 3) until the
    ``spend`` card has a yes, ``Refused`` when money or rights say no. Leaving the session deletes every machine.
    Returns ``[{"plate", "insert", "result"}]``."""
    if compute is None:
        from .. import compute as compute_mod
        compute = compute_mod
    missing = [j for j in todo if j.get("missing", True)]
    if not missing:
        return []
    cap = float(cap_usd if cap_usd is not None else cap_for(paths.episode_dir(episode)))
    rows = []
    with compute.session(episode=episode, step="edit", purpose="motion graphics plates", cap_usd=cap,
                         **session_kw) as s:
        machines = s.rent(gpus=gpus, max_minutes=max_minutes)
        log(f"plates: {len(missing)} job(s) on {len(machines)} rented GPU(s), cap ${cap:.2f}")
        for i, job in enumerate(missing):
            m = machines[i % len(machines)]
            rows.append({"plate": job["id"], "insert": job["insert"], "result": run_job(m, job)})
    return rows
