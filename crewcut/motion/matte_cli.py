"""Graphics behind the speaker on the command line (wired into `crewcut motion matte ...` by the main CLI).

    python -m crewcut.motion.matte_cli export <source> --episode ID --id SHOT --start S --end E [--fps N]
                                             [--face X,Y,W,H] [--margin 0.5]
    python -m crewcut.motion.matte_cli run   --episode ID --shots SHOT[,SHOT] --cap USD [--minutes 45] [--every N]
                                             [--no-check]
    python -m crewcut.motion.matte_cli check --episode ID --id SHOT [--face X,Y,W,H] [--every N] [--keep-frames]
    python -m crewcut.motion.matte_cli check --frames DIR --alpha DIR --out DIR [--face X,Y,W,H] [--every N]

`export` cuts the picture of one span (no sound) into <episode>/render/matte/<shot>.mp4. `run` mattes the shots on one
rented RTX 4090 (after a yes on the spend card, which says the shots' picture goes there) and checks the edges here.
`check` runs the edge gate again and writes decision.json: "behind", or "beside" with the reason.

Plain text by default, --json for machine output. Exit codes: 0 ok (also when the gate sends the graphic beside the
speaker: that fallback is the normal outcome of a failed check), 1 error, 2 usage, 3 waiting for or refused by the user
(a spend card is open, the cap is reached, the privacy rule), 4 missing key.
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path

from .. import paths
from . import matte

COMMANDS = ("export", "run", "check")


def _face(s: str | None) -> tuple[int, int, int, int] | None:
    if not s:
        return None
    try:
        v = tuple(int(float(x)) for x in s.split(","))
    except ValueError as e:
        raise ValueError(f"--face takes X,Y,W,H in pixels, got {s!r}") from e
    if len(v) != 4 or v[2] <= 0 or v[3] <= 0:
        raise ValueError(f"--face takes X,Y,W,H in pixels, got {s!r}")
    return v  # type: ignore[return-value]


def episode_dir(arg: str) -> Path:
    """An episode id (under the studio) or an episode folder."""
    p = Path(arg).expanduser()
    if p.is_dir():
        return p.resolve()
    d = paths.episode_dir(arg)
    if not d.is_dir():
        raise FileNotFoundError(f"no episode {arg}")
    return d


def shot_from_clip(ep: Path, shot_id: str, face=None) -> matte.Shot:
    """A Shot rebuilt from <episode>/render/matte/<shot>.json (written by export)."""
    clip = ep / "render" / "matte" / f"{matte._safe_id(shot_id)}{matte.CLIP_SUFFIX}"
    meta = matte.read_meta(clip)
    if not clip.is_file():
        raise FileNotFoundError(f"no clip for shot {shot_id}: run export first ({clip})")
    f = face or (tuple(meta["face"]) if meta.get("face") else None)
    return matte.Shot(shot_id, ep, Path(meta["source"]) if meta.get("source") else None,
                      float(meta.get("start_s") or 0), float(meta.get("end_s") or 0), meta.get("fps"), f)


def load_compute():
    return importlib.import_module("crewcut.compute")


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="crewcut motion matte", description="Graphics behind the speaker: matte, check, "
                                 "decide.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("export", help="cut the picture of one span (no sound) into render/matte/")
    p.add_argument("source", help="the speaker recording")
    p.add_argument("--episode", required=True, help="episode id or folder")
    p.add_argument("--id", required=True, help="shot id (letters, digits, . _ -)")
    p.add_argument("--start", type=float, required=True, help="span start in the source, seconds")
    p.add_argument("--end", type=float, required=True, help="span end in the source, seconds")
    p.add_argument("--fps", type=float, help="the episode's frame rate (default: the source's)")
    p.add_argument("--margin", type=float, default=matte.MARGIN_S, help="extra seconds each side (default 0.5)")
    p.add_argument("--face", help="face box X,Y,W,H in source pixels (used by the check)")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("run", help="matte the shots on one rented GPU (asks for a yes first), then check them here")
    p.add_argument("--episode", required=True)
    p.add_argument("--shots", required=True, help="shot ids, comma separated (export them first)")
    p.add_argument("--cap", type=float, required=True, help="money cap for this rented run, USD")
    p.add_argument("--minutes", type=float, default=45, help="machine deadline in minutes (default 45)")
    p.add_argument("--every", type=int, help=f"check every Nth frame (default {matte.THRESHOLDS['every']})")
    p.add_argument("--no-check", action="store_true", help="fetch only; run check later")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("check", help="the edge gate and the decision for one shot")
    p.add_argument("--episode")
    p.add_argument("--id")
    p.add_argument("--frames", help="numbered PNGs of the picture (instead of --episode/--id)")
    p.add_argument("--alpha", help="numbered alpha PNGs")
    p.add_argument("--out", help="folder for edge-check.json, the crops and edges-200.jpg")
    p.add_argument("--face", help="face box X,Y,W,H in pixels")
    p.add_argument("--every", type=int)
    p.add_argument("--keep-frames", action="store_true", help="keep the decoded frames in render/matte/<shot>/frames/")
    p.add_argument("--json", action="store_true")
    return ap


def _print_check(r: dict) -> None:
    d = r.get("decision") or matte.decide(r).to_dict()
    print(f"Edge check: {'passed' if r['passed'] else 'failed'} on {r.get('frames_checked', 0)} frames "
          f"(every {r.get('every')})  ->  graphic {d['place']}" + (f" ({d['side']} side)" if d.get("side") else ""))
    for reason in r.get("reasons") or []:
        print(f"  {reason}")
    if r.get("sheet"):
        print(f"  200 % crops: {r['sheet']}")


def run(a: argparse.Namespace, out: dict) -> int:
    log = (lambda *x: print(*x, file=sys.stderr)) if a.json else print
    if a.cmd == "export":
        ep = episode_dir(a.episode)
        face = _face(a.face)
        clip = matte.export_shot(Path(a.source).expanduser(), a.start, a.end,
                                 ep / "render" / "matte" / f"{matte._safe_id(a.id)}{matte.CLIP_SUFFIX}",
                                 fps=a.fps, margin_s=a.margin)
        meta = matte.read_meta(clip)
        if face:
            meta["face"] = list(face)
            matte.meta_path(clip).write_text(json.dumps(meta, indent=2), encoding="utf-8")
        out.update({"clip": str(clip), **meta})
        if not a.json:
            print(f"Clip: {clip}  {meta.get('width')}x{meta.get('height')}  {meta.get('seconds')} s  picture only")
        return 0
    if a.cmd == "run":
        if a.cap <= 0:
            raise ValueError("--cap must be above 0")
        ep = episode_dir(a.episode)
        shots = [shot_from_clip(ep, s.strip()) for s in a.shots.split(",") if s.strip()]
        results = matte.matte_rented(shots, load_compute(), a.cap, log=log, max_minutes=a.minutes,
                                     check=not a.no_check, every=a.every)
        out["shots"] = [r.to_dict() for r in results]
        if not a.json:
            for r in results:
                d = r.decision or {}
                print(f"{r.id:<12} {'ok' if r.ok else 'failed':<7} {r.frames:5d} frames  "
                      f"{d.get('place', '-')}" + (f": {d['reason']}" if d.get("place") == "beside" else ""))
        return 0 if all(r.ok for r in results) else 1
    if a.cmd == "check":
        face = _face(a.face)
        if a.frames or a.alpha:
            if not (a.frames and a.alpha and a.out):
                raise ValueError("check with --frames needs --alpha and --out too")
            r = matte.edge_check(Path(a.frames), Path(a.alpha), Path(a.out), face, every=a.every)
            r["decision"] = matte.write_decision(Path(a.out), r)
        else:
            if not (a.episode and a.id):
                raise ValueError("check needs --episode and --id (or --frames, --alpha and --out)")
            shot = shot_from_clip(episode_dir(a.episode), a.id, face)
            r = matte.check_shot(shot, every=a.every, keep_frames=a.keep_frames)
        out.update({k: r.get(k) for k in ("passed", "reasons", "decision", "checks", "every", "frames_checked",
                                           "sheet", "crops", "size", "face")})
        if not a.json:
            _print_check(r)
        return 0
    return 2


def main(argv: list[str] | None = None) -> int:
    try:
        a = parser().parse_args(argv)
    except SystemExit as e:
        return 0 if e.code == 0 else 2
    out: dict = {}
    code = 1
    try:
        code = run(a, out)
    except Exception as e:
        ec = getattr(e, "exit_code", None)
        card = getattr(e, "card_id", None)
        if card is not None:
            out.update({"waiting": f"Waiting for your yes on card {card} before renting", "card": card})
            print(out["waiting"], file=sys.stderr)
            code = 3
        elif isinstance(ec, int):
            out["error"] = str(e)
            print(str(e), file=sys.stderr)
            code = ec
        elif isinstance(e, (ValueError, FileNotFoundError, matte.MatteError)):
            out["error"] = str(e)
            print(f"Error: {e}", file=sys.stderr)
            code = 1
        else:
            raise
    if getattr(a, "json", False):
        out["exit"] = code
        print(json.dumps(out, ensure_ascii=False, default=str))
    return code


if __name__ == "__main__":
    sys.exit(main())
