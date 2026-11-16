"""`crewcut render ...`: the edit plan workbench on the command line.

    crewcut render plan    <plan.json>
    crewcut render 2d      <plan.json> [--ids a,b] [--images-only]
    crewcut render 3d      <plan.json> [--local | --rented] [--gpus N] [--ids a,b] [--samples N] [--draft] [--max-usd X]
    crewcut render probe   <plan.json> [<id>,<id>] [--frame N[,N]] [--local | --rented] [--samples N]
    crewcut render cut     <plan.json>
    crewcut render shown   <plan.json>
    crewcut render all     <plan.json> [--local | --rented] [--gpus N]
    crewcut render measure <image.png> [--pack DIR]
    crewcut render samples [--out DIR] [--formats landscape,portrait] [--frame -1] [--pack DIR]

Plain text by default, --json for machine output. Exit codes: 0 ok, 1 error, 2 usage, 3 waiting for or refused by the
user (a card is open, the cap is reached), 4 missing login or key.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .. import brand
from . import assemble, measure, workbench
from .plan import Plan, PlanError

COMMANDS = ("plan", "2d", "3d", "probe", "cut", "shown", "all", "measure", "samples")


def _ids(s: str | None) -> list[str] | None:
    return [x.strip() for x in s.split(",") if x.strip()] if s else None


def _ints(s: str | None) -> list[int] | None:
    if not s:
        return None
    try:
        return [int(x) for x in s.split(",") if x.strip()]
    except ValueError as e:
        raise PlanError(f"--frame takes whole numbers separated by commas, got {s!r}") from e


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="crewcut render", description="Render inserts and cut the video from an edit plan.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def plan_cmd(name: str, help_: str) -> argparse.ArgumentParser:
        p = sub.add_parser(name, help=help_)
        p.add_argument("plan", help="the edit plan, e.g. episodes/003-x/edit/plan-v001.json")
        p.add_argument("--json", action="store_true", help="machine output")
        return p

    def way(p: argparse.ArgumentParser) -> None:
        g = p.add_mutually_exclusive_group()
        g.add_argument("--local", action="store_true", help="3D on this machine (CPU or its own GPU); always works")
        g.add_argument("--rented", action="store_true", help="3D on rented GPUs (asks for a yes before spending)")
        p.add_argument("--gpus", type=int, default=2, help="rented GPUs (default 2)")
        p.add_argument("--samples", type=int, help="Cycles samples (default from the style pack)")
        p.add_argument("--draft", action="store_true", help="draft quality: 32 samples with denoising")
        p.add_argument("--max-usd", type=float, help="money cap for this rented run")

    plan_cmd("plan", "show inserts, frames, cues and what is rendered")
    p = plan_cmd("2d", "render the 2D inserts with Chromium")
    p.add_argument("--ids", help="only these inserts, comma separated")
    p.add_argument("--images-only", action="store_true", help="PNG frames only, no encoding")
    p = plan_cmd("3d", "render the 3D inserts with Blender")
    p.add_argument("--ids", help="only these inserts, comma separated")
    way(p)
    p = plan_cmd("probe", "still frames at half size")
    p.add_argument("ids", nargs="?", help="inserts, comma separated (default: every 3D insert)")
    p.add_argument("--frame", help="frame numbers inside the insert, comma separated (default: after the last cue)")
    way(p)
    plan_cmd("cut", "the finished video with sound")
    plan_cmd("shown", "lock the output after someone has seen it")
    p = plan_cmd("all", "2d, 3d and cut")
    way(p)
    p = sub.add_parser("measure", help="measure a still against the style pack")
    p.add_argument("image")
    p.add_argument("--pack", help="a style pack folder (default: the active pack)")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("samples", help="one frame of every 2D scene's example, both formats (for screenshots)")
    p.add_argument("--out", default="render-out/samples", help="output folder (default render-out/samples)")
    p.add_argument("--formats", default="landscape,portrait")
    p.add_argument("--frame", type=int, default=-1, help="frame to render; -1 is the last (default)")
    p.add_argument("--pack", help="a style pack folder (default: the active pack)")
    p.add_argument("--json", action="store_true")
    return ap


def _rows_ok(rows: list[dict]) -> bool:
    return all(r.get("frames_ok") and r.get("clip_ok") is not False for r in rows)


def _print_plan(s: dict) -> None:
    print(f"Plan {s['plan']}  format {s['format']}  {s['fps']} fps  episode {s['episode']}")
    for x in s["inserts"]:
        cues = ", ".join(f"{k} {v}" for k, v in x["cues"].items()) or "-"
        print(f"  {x['id']:<10} {x['kind']:<4} {str(x['scene']):<12} {x['start']:7.2f}-{x['end']:7.2f} s "
              f"{x['frames']:4d} frames  cues {cues}  missing {x['missing']}{'  (overlay)' if x['transparent'] else ''}")
    for w in s["warnings"]:
        print(f"  warning: {w}")
    print(f"Output {s['output']}{'  (shown, locked)' if s['shown'] else ''}")


def _print_rows(title: str, rows: list[dict]) -> None:
    for r in rows:
        state = "ok" if r.get("frames_ok") and r.get("clip_ok") is not False else f"missing {r.get('missing')}"
        print(f"{title} {r['id']:<10} {str(r.get('scene')):<12} {state}  {r.get('clip')}")


def run(a: argparse.Namespace, out: dict) -> int:
    log = (lambda *x: print(*x, file=sys.stderr)) if a.json else print
    if a.cmd == "measure":
        m = measure.measure(a.image, brand.load(a.pack) if a.pack else brand.load())
        out.update(m)
        if not a.json:
            print("\n".join(measure.lines(m)))
        return 0
    if a.cmd == "samples":
        rows = workbench.samples(Path(a.out), tuple(x for x in a.formats.split(",") if x), a.frame,
                                 brand.load(a.pack) if a.pack else None, log=log)
        out["samples"] = rows
        return 0 if all(r["ok"] for r in rows) else 1
    plan = Plan(a.plan)
    mode = "local" if getattr(a, "local", False) else ("rented" if getattr(a, "rented", False) else None)
    if a.cmd == "plan":
        s = plan.summary()
        out.update(s)
        if not a.json:
            _print_plan(s)
        return 0
    if a.cmd == "2d":
        rows = workbench.render_2d(plan, _ids(a.ids), a.images_only, log=log)
        out["rows"] = rows
        if not a.json:
            _print_rows("2d", rows)
        return 0 if all(r["frames_ok"] for r in rows) and (a.images_only or _rows_ok(rows)) else 1
    if a.cmd == "3d":
        r = workbench.render_3d(plan, mode, a.gpus, _ids(a.ids), a.samples, a.draft, a.max_usd, log=log)
        out.update(r)
        if not a.json:
            _print_rows("3d", r["rows"])
        return 0 if _rows_ok(r["rows"]) else 1
    if a.cmd == "probe":
        samples = a.samples or (32 if a.draft else 64)
        r = workbench.probe(plan, _ids(a.ids), _ints(a.frame), rented=mode == "rented", samples=samples, log=log)
        out.update(r)
        if not a.json:
            print(f"Stills in {r['dir']}: {len(r['stills'])}")
        return 0 if r["stills"] else 1
    if a.cmd == "cut":
        r = workbench.cut(plan, log=log)
        out.update(r)
        if not a.json:
            print(f"Cut: {r['output']}  {len(r['shots'])} shots  {r['seconds']} s  loudness {r['lufs']} LUFS "
                  f"(target {r['target_lufs']}), true peak {r['true_peak']} dBTP")
        return 0
    if a.cmd == "shown":
        r = workbench.shown(plan)
        out.update(r)
        if not a.json:
            print(f"Locked: {r['output']}  sha256 {r['sha256'][:16]}")
        return 0
    if a.cmd == "all":
        rows2 = workbench.render_2d(plan, log=log)
        if not _rows_ok(rows2):
            out["2d"] = rows2
            log("2D inserts failed; not cutting")
            return 1
        r3 = workbench.render_3d(plan, mode, a.gpus, None, a.samples, a.draft, a.max_usd, log=log)
        out.update({"2d": rows2, "3d": r3})
        if not _rows_ok(r3["rows"]):
            log("3D inserts are not complete; not cutting")
            return 1
        out["cut"] = workbench.cut(Plan(a.plan), log=log)
        if not a.json:
            print(f"Cut: {out['cut']['output']}")
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
    except workbench.Waiting as e:
        out.update({"waiting": str(e), "card": e.card_id})
        print(str(e), file=sys.stderr)
        code = 3
    except assemble.ShownError as e:
        out["error"] = str(e)
        print(str(e), file=sys.stderr)
        code = 1
    except (PlanError, FileNotFoundError, RuntimeError) as e:
        out["error"] = str(e)
        print(f"Error: {e}", file=sys.stderr)
        code = int(getattr(e, "exit_code", 1) or 1)
    except Exception as e:
        ec = getattr(e, "exit_code", None)
        if not isinstance(ec, int):
            raise
        out["error"] = str(e)
        print(str(e), file=sys.stderr)
        code = ec
    if getattr(a, "json", False):
        out["exit"] = code
        print(json.dumps(out, ensure_ascii=False, default=str))
    return code


if __name__ == "__main__":
    sys.exit(main())
