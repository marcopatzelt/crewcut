"""What the web UI reads about motion (``GET /api/episodes/{id}/motion``): the motion plan with its three columns,
each motion piece on the film strip with its loop and state, and the motion report's three lines. Read-only."""

from __future__ import annotations

import json
from pathlib import Path

from .. import paths
from . import custom, director, library, ratchet

STATES = ("planned", "style frame", "building", "in review", "done")
VIDEO = (".mp4", ".mov", ".webm")


def _url(ep: str, p: Path, ep_dir: Path) -> str:
    return f"/api/files/{ep}/{p.relative_to(ep_dir).as_posix()}"


def _render_media(ep_dir: Path, iid: str) -> tuple[str | None, str | None, bool]:
    """(loop url, poster url, has frames) of an insert from ``render/inserts/<id>-<hash>``."""
    root = ep_dir / "render" / "inserts"
    if not root.is_dir():
        return None, None, False
    clips = sorted((f for f in root.glob(f"{iid}-*") if f.is_file() and f.suffix.lower() in VIDEO),
                   key=lambda f: f.stat().st_mtime)
    clips += sorted((f for d in root.glob(f"{iid}-*") if d.is_dir() for f in d.iterdir()
                     if f.suffix.lower() in VIDEO), key=lambda f: f.stat().st_mtime)
    frames = sorted((f for d in root.glob(f"{iid}-*") if d.is_dir() for f in d.glob("[0-9][0-9][0-9][0-9].png")),
                    key=lambda f: (f.stat().st_mtime, f.name))
    poster = frames[len(frames) // 2] if frames else None
    ep = ep_dir.name
    return (_url(ep, clips[-1], ep_dir) if clips else None, _url(ep, poster, ep_dir) if poster else None,
            bool(frames))


def _brief_line(ep_dir: Path, iid: str) -> str | None:
    p = ep_dir / "motion" / iid / "brief.md"
    if not p.is_file():
        return None
    return next((x.strip("# ").strip() for x in p.read_text(encoding="utf-8").splitlines() if x.strip()), None)


def pieces(ep_dir: Path) -> list[dict]:
    """Every motion piece of the episode: the motion inserts of the newest edit plan, plus custom pieces not in it."""
    plans = sorted((ep_dir / "edit").glob("plan-v*.json"), key=lambda p: (len(p.stem), p.stem))
    inserts = []
    if plans:
        try:
            data = json.loads(plans[-1].read_text(encoding="utf-8"))
            inserts = [e for e in data.get("inserts") or [] if isinstance(e, dict) and e.get("kind") == "motion"]
        except (OSError, ValueError):
            inserts = []
    custom_state = custom.pieces_state(ep_dir)
    out, seen = [], set()
    for e in inserts:
        iid = str(e.get("id"))
        src = str(e.get("source") or "")
        piece = src.split("/")[1] if src.startswith("motion/") and src.count("/") >= 2 else None
        loop, poster, has_frames = _render_media(ep_dir, iid)
        bundle, errors = library.last_bundle(ep_dir, iid)
        if piece:
            seen.add(piece)
            state = custom_state.get(piece, "planned")
            if state == "building" and bundle is not None:
                state = "done" if not errors else "in review"
        else:
            state = ("done" if bundle is not None and not errors else "in review" if bundle is not None
                     else "building" if has_frames else "planned")
        if poster is None and piece:
            frames = sorted((ep_dir / "motion" / piece).glob("frame-v*.png"))
            poster = _url(ep_dir.name, frames[-1], ep_dir) if frames else None
        out.append({"id": iid, "kind": "custom" if piece else "library", "scene": e.get("scene"), "source": src or None,
                    "beat": e.get("beat"), "column": e.get("column"), "state": state,
                    "brief": _brief_line(ep_dir, piece) if piece else None, "loop": loop, "poster": poster,
                    "start": e.get("start"), "end": e.get("end"), "transparent": bool(e.get("transparent"))})
    for piece, state in custom_state.items():
        if piece in seen:
            continue
        frames = sorted((ep_dir / "motion" / piece).glob("frame-v*.png"))
        out.append({"id": piece, "kind": "custom", "scene": None, "source": f"motion/{piece}/comp.jsx", "beat": None,
                    "column": None, "state": state, "brief": _brief_line(ep_dir, piece), "loop": None,
                    "poster": _url(ep_dir.name, frames[-1], ep_dir) if frames else None, "start": None, "end": None,
                    "transparent": False})
    return out


def plan_view(ep_dir: Path) -> dict | None:
    p = director.newest(ep_dir)
    if p is None:
        return None
    try:
        plan = director.load(p)
    except director.PlanError:
        return None
    cards = director.cards_for(ep_dir.name, p)
    card = cards[-1] if cards else None
    data = (card.get("data") or {}).get("motion_plan") if card else director.card_data(plan, p, ep_dir)["motion_plan"]
    return {"file": p.relative_to(ep_dir).as_posix(), "md_url": _url(ep_dir.name, director.md_of(p), ep_dir)
            if director.md_of(p).is_file() else None, "version": plan.get("version"),
            "card": {"id": card["id"], "status": card["status"]} if card else None,
            "approved": bool(card and card["status"] == "accepted"), **{k: data.get(k) for k in (
                "columns", "quiet", "density", "budget", "estimate_usd", "cap_usd", "bar", "short")}}


def episode(eid: str) -> dict:
    ep_dir = paths.episode_dir(eid)
    ret = None
    rp = ep_dir / "review" / "retention.json"
    if rp.is_file():
        try:
            r = json.loads(rp.read_text(encoding="utf-8"))
            ret = {"fetched": r.get("fetched"), "summary": r.get("summary"), "unproven": True}
        except (OSError, ValueError):
            ret = None
    return {"plan": plan_view(ep_dir), "pieces": pieces(ep_dir), "report": ratchet.report_lines(ep_dir),
            "retention": ret}
