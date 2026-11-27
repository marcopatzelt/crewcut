"""`crewcut render ...`: the edit plan workbench on the command line.

    crewcut render plan    <plan.json>
    crewcut render 2d      <plan.json> [--ids a,b] [--images-only]
    crewcut render motion  <plan.json> [--ids a,b] [--draft] [--local | --rented] [--max-usd X]
    crewcut render 3d      <plan.json> [--local | --rented] [--gpus N] [--ids a,b] [--samples N] [--draft] [--max-usd X]
    crewcut render probe   <plan.json> [<id>,<id>] [--frame N[,N]] [--local | --rented] [--samples N]
    crewcut render cut     <plan.json>
    crewcut render shown   <plan.json>
    crewcut render all     <plan.json> [--local | --rented] [--gpus N]     (2d, motion, 3d, cut)
    crewcut render slides  <plan.json> [--video FILE] [--ids a,b]       (the slide check of the full-frame inserts)
    crewcut render measure <image.png> [--pack DIR]
    crewcut render samples [--out DIR] [--formats landscape,portrait] [--frame -1] [--pack DIR]
    crewcut render capture <episode> --url URL | --html FILE | --terminal FILE [--seconds S] [--scroll KEYS]
                           [--size full|stage] [--zoom 2.5] [--name NAME]
    crewcut render music-bed <voice.wav> --music TRACK [--start S] [--punch T,T] [--source INFO.json] [--licence L]
                           [--out FILE]
    crewcut render sfx-sheet [--out DIR] [--voice WAV --start S --seconds N]   the effect set to listen to, its id
    crewcut render sfx-approve <set id> [--source "who, when"]                the user's yes (never inside a crew job)
    crewcut render assets fetch <spec> [<spec> ...] [--res 2k]   CC0 HDRIs and materials (polyhaven:hdri/<id>,
                           polyhaven:tex/<id>, ambientcg:<id>) into the cache; `assets list` shows it

Plain text by default, --json for machine output. Exit codes: 0 ok, 1 error, 2 usage, 3 waiting for or refused by the
user (a card is open, the cap is reached), 4 missing login or key.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .. import brand
from . import assemble, capture, measure, music, sfx_events, workbench
from .plan import Plan, PlanError

COMMANDS = ("plan", "2d", "motion", "3d", "probe", "cut", "shown", "all", "slides", "measure", "samples", "capture",
            "music-bed", "sfx-sheet", "sfx-approve", "assets")


def _ids(s: str | None) -> list[str] | None:
    return [x.strip() for x in s.split(",") if x.strip()] if s else None


def _floats(s: str | None, what: str) -> list[float]:
    try:
        return [float(x) for x in (s or "").split(",") if x.strip()]
    except ValueError as e:
        raise PlanError(f"{what} takes seconds separated by commas, got {s!r}") from e


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
    p.add_argument("--no-gate", action="store_true", help="tests only: skip the motion plan and style-frame gates")
    p = plan_cmd("motion", "render the motion graphics inserts with EffectCraft")
    p.add_argument("--ids", help="only these inserts, comma separated")
    p.add_argument("--draft", action="store_true", help="8 motion blur samples, into its own folder (never cut)")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--local", action="store_true", help="render here (needs effectcraft-cli)")
    g.add_argument("--rented", action="store_true", help="render on one rented machine (asks for a yes first)")
    p.add_argument("--max-usd", type=float, help="money cap for this rented run (default $2 a video, $0.50 a Short)")
    p.add_argument("--no-gate", action="store_true", help="tests only: skip the motion plan and style-frame gates")
    p = plan_cmd("plates", "Blender plates of the motion inserts: here with an own GPU, else one rented RTX 4090")
    p.add_argument("--ids", help="only the plates of these inserts, comma separated")
    p.add_argument("--probe", action="store_true", help="one half-size still per plate first")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--local", action="store_true", help="render here")
    g.add_argument("--rented", action="store_true", help="render on one rented GPU (asks for a yes first)")
    p.add_argument("--max-usd", type=float, help="money cap (default $2 a video, $0.50 a Short)")
    p = plan_cmd("matte", "person matte for overlays behind the speaker, on a rented GPU (asks for a yes first)")
    p.add_argument("--ids", help="only these inserts, comma separated")
    p.add_argument("--max-usd", type=float, help="money cap (default $2 a video, $0.50 a Short)")
    sub.add_parser("motion-review", help="the Critic's review bundle of the motion inserts (see --help)", add_help=False)
    p = plan_cmd("3d", "render the 3D inserts with Blender")
    p.add_argument("--ids", help="only these inserts, comma separated")
    way(p)
    p.add_argument("--no-gate", action="store_true", help="tests only: skip the motion plan and style-frame gates")
    p = plan_cmd("probe", "still frames at half size")
    p.add_argument("ids", nargs="?", help="inserts, comma separated (default: every 3D insert)")
    p.add_argument("--frame", help="frame numbers inside the insert, comma separated (default: after the last cue)")
    way(p)
    plan_cmd("cut", "the finished video with sound")
    plan_cmd("shown", "lock the output after someone has seen it")
    p = plan_cmd("all", "2d, motion, 3d and cut")
    way(p)
    p.add_argument("--no-gate", action="store_true", help="tests only: skip the motion plan and style-frame gates")
    p = plan_cmd("slides", "the slide check: does a full-frame insert of the video stand still and look flat?")
    p.add_argument("--video", help="the video (default: the plan's output)")
    p.add_argument("--ids", help="only these inserts, comma separated")
    p.add_argument("--crop-top", type=float, default=0.0,
                   help="share of the height to leave out at the top (a review reel with a label bar)")
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
    p = sub.add_parser("capture", help="record a web page or a terminal transcript upright (Shorts), into broll/")
    p.add_argument("episode", help="episode id or folder; the video goes to its broll/ as <name>-vNNN.mp4")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--url", help="an http(s) address")
    src.add_argument("--html", help="a local HTML file")
    src.add_argument("--terminal", help="a terminal transcript: '$ cmd' lines are typed, '[+1.5]' waits 1.5 s")
    p.add_argument("--seconds", type=float, help="length (required for pages; terminal: until the last line + 2 s)")
    p.add_argument("--scroll", help="scroll keys second:position, e.g. 0:0,1.5:0,8:end (position: px, end, 40%%)")
    p.add_argument("--size", choices=sorted(capture.SIZES), default="full",
                   help="full 1080x1920 (default) or stage 1080x960 (the proof-top layout's stage)")
    p.add_argument("--zoom", type=float, default=capture.ZOOM, help="device scale; the page is 1080/zoom CSS px wide "
                   "(default 2.5: a 432 px phone layout)")
    p.add_argument("--fps", type=int, help="frames per second (default: the episode's)")
    p.add_argument("--wait", type=float, default=capture.WAIT_S, help="seconds after loading before the first frame")
    p.add_argument("--hide-overlays", action="store_true", help="hide dialogs and big fixed layers (cookie banners)")
    p.add_argument("--name", help="file name (default from the address or file)")
    p.add_argument("--keep-frames", action="store_true", help="keep the PNG frames in render/capture/")
    p.add_argument("--line-delay", type=float, default=capture.LINE_DELAY_S, help="terminal: seconds between lines")
    p.add_argument("--type-speed", type=float, default=capture.TYPE_CPS, help="terminal: typed characters per second")
    p.add_argument("--font-px", type=int, default=capture.FONT_PX, help="terminal: font size")
    p.add_argument("--pack", help="a style pack folder (default: the active pack)")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("music-bed", help="a licensed music track under a Short's voice, with a music source file")
    p.add_argument("voice", help="the Short's voice (WAV)")
    p.add_argument("--music", required=True, help="the music track")
    p.add_argument("--start", type=float, default=0.0, help="seconds into the track (default 0)")
    p.add_argument("--punch", help="punchline times in seconds, comma separated: a music hole before each")
    p.add_argument("--source", help="the track's source info (JSON); default <track stem>.source.json next to it")
    p.add_argument("--licence", help="the track's licence (wins over the source info)")
    p.add_argument("--credit", help="credit text for the video description")
    p.add_argument("--made", help="how the track was made (author, model, recording)")
    p.add_argument("--out", help="result WAV (default <voice stem>-bed-vNNN.wav next to the voice)")
    p.add_argument("--music-db", type=float, help="music level below the voice (default: pack shorts.music_db)")
    p.add_argument("--hole", type=float, help="music hole before a punchline, seconds (default: pack shorts.music_hole_s)")
    p.add_argument("--tail", type=float, help="seconds after the voice (default: pack shorts.end_tail_s)")
    p.add_argument("--lufs", type=float, help="loudness target (default: pack shorts.loudness_lufs)")
    p.add_argument("--pack", help="a style pack folder (default: the active pack)")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("sfx-sheet", help="the effect layer's sound set as a listening page, with the id to approve")
    p.add_argument("--out", help="folder (default: <studio>/library/sfx-sets/<set id>/)")
    p.add_argument("--voice", help="a voice recording to hear the effects under (WAV or any sound file)")
    p.add_argument("--start", type=float, default=0.0, help="seconds into the voice (default 0)")
    p.add_argument("--seconds", type=float, default=19.0, help="length of the demo (default 19)")
    p.add_argument("--pack", help="a style pack folder (default: the active pack)")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("sfx-approve", help="the user's yes to one effect set (refused inside a crew job)")
    p.add_argument("set_id", help="the id from `crewcut render sfx-sheet`")
    p.add_argument("--source", default="the user, after listening", help="who said yes, and when")
    p.add_argument("--pack", help="the style pack folder (default: the studio's brand/)")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("assets", help="CC0 3D assets: Poly Haven HDRIs and textures, ambientCG materials (cached)")
    p.add_argument("action", choices=("fetch", "list"))
    p.add_argument("specs", nargs="*", help="polyhaven:hdri/<id>, polyhaven:tex/<id> or ambientcg:<id>")
    p.add_argument("--res", default="2k", help="1k, 2k, 4k or 8k (default 2k)")
    p.add_argument("--json", action="store_true")
    return ap


def _rows_ok(rows: list[dict]) -> bool:
    return all(r.get("frames_ok") and r.get("clip_ok") is not False for r in rows)


def _print_plan(s: dict) -> None:
    print(f"Plan {s['plan']}  format {s['format']}  {s['fps']} fps  episode {s['episode']}")
    for x in s["inserts"]:
        cues = ", ".join(f"{k} {v}" for k, v in x["cues"].items()) or "-"
        scene = str(x["scene"]) + (f"@{x['version']}" if x.get("version") else "")
        more = "".join(f"  ({w})" for w in (
            "overlay" if x["transparent"] else None, x.get("source") and f"comp {x['source']}",
            x.get("backdrop") and f"backdrop {x['backdrop']}", x.get("layer") and f"layer {x['layer']}",
            x.get("sound") and "sound", x.get("format") == "stage" and "stage") if w)
        print(f"  {x['id']:<10} {x['kind']:<6} {scene:<14} {x['start']:7.2f}-{x['end']:7.2f} s "
              f"{x['frames']:4d} frames  cues {cues}  missing {x['missing']}{more}")
    for w in s["warnings"]:
        print(f"  warning: {w}")
    for n in s.get("notes") or []:
        print(f"  note: {n}")
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
    if a.cmd == "capture":
        r = capture.capture(a.episode, url=a.url, html_file=a.html, terminal=a.terminal, seconds=a.seconds,
                            size=a.size, zoom=a.zoom, fps=a.fps, scroll=a.scroll, wait=a.wait,
                            hide_overlays=a.hide_overlays, name=a.name, keep_frames=a.keep_frames,
                            line_delay=a.line_delay, type_cps=a.type_speed, font_px=a.font_px,
                            pack=brand.load(a.pack) if a.pack else None, log=log)
        out.update(r)
        if not a.json:
            print(f"Captured: {r['output']}  {r['size']}  {r['seconds']} s  ({r['frames']} frames)")
        return 0
    if a.cmd == "music-bed":
        pack = brand.load(a.pack) if a.pack else brand.load()
        track = Path(a.music).expanduser().resolve()
        if not track.is_file():
            raise PlanError(f"music track not found: {a.music}")
        src = music.source_info(track, Path(a.source).expanduser().resolve() if a.source else None,
                                licence=a.licence, credit=a.credit, made=a.made)
        bed = music.Bed.from_pack(pack, music_db=a.music_db, hole_s=a.hole, tail_s=a.tail, lufs=a.lufs)
        r = music.music_bed(Path(a.voice).expanduser(), track, Path(a.out).expanduser() if a.out else None,
                            punches=_floats(a.punch, "--punch"), start=a.start, bed=bed, source=src, log=log)
        out.update(r)
        if not a.json:
            print(f"Music bed: {r['output']}  {r['seconds']} s  {r['lufs']} LUFS, true peak {r['true_peak']} dBTP")
            print(f"Source: {r['music_source']}  licence {r['licence']}" + (f"  credit: {r['credit']}" if r['credit'] else ""))
            for line in r["listen"]:
                print(f"  listen: {line}")
        return 0
    if a.cmd == "sfx-sheet":
        from .. import paths
        pack = brand.load(a.pack) if a.pack else brand.load()
        sid = sfx_events.set_info(pack)["id"]
        dest = Path(a.out).expanduser() if a.out else paths.studio_root() / "library" / "sfx-sets" / sid
        r = sfx_events.listening_sheet(dest, pack, Path(a.voice).expanduser() if a.voice else None, a.start,
                                       a.seconds)
        approved = pack.value("edit_style.sfx.approved_set") == r["id"]
        out.update({**r, "approved": approved})
        if not a.json:
            print(f"Effect set {r['id']}: {r['sheet']}")
            for n, lv in r["levels_db"].items():
                print(f"  {n:<12} {lv:g} dB")
            print("  approved: " + ("yes" if approved else f"no (the user listens, then `crewcut render sfx-approve "
                                                          f"{r['id']}`)"))
        return 0
    if a.cmd == "assets":
        from . import assets3d
        if a.action == "list":
            rows = assets3d.cached()
            out["cache"], out["assets"] = str(assets3d.cache_dir()), rows
            if not a.json:
                print(f"Cache {assets3d.cache_dir()}")
                for r in rows:
                    print(f"  {r.get('spec'):<36} {r.get('resolution'):<4} {', '.join(r.get('files') or {})}  "
                          f"{r.get('licence')}  {r.get('source')}")
                if not rows:
                    print("  empty")
            return 0
        if not a.specs:
            raise PlanError("name at least one asset, e.g. polyhaven:hdri/studio_small_09")
        got = []
        for spec in a.specs:
            try:
                got.append(assets3d.fetch(spec, a.res))
            except assets3d.lib().AssetError as e:
                raise PlanError(str(e)) from e
        out["assets"] = got
        if not a.json:
            for r in got:
                print(f"{r['spec']} {r['resolution']}: {', '.join(f'{k} {v}' for k, v in r['paths'].items())}")
        return 0
    if a.cmd == "sfx-approve":
        from .. import paths
        pack_dir = Path(a.pack).expanduser() if a.pack else paths.brand_dir()
        try:
            r = sfx_events.approve(a.set_id, pack_dir, a.source)
        except PermissionError as e:
            print(str(e), file=sys.stderr)
            return 3
        except ValueError as e:
            raise PlanError(str(e)) from e
        out.update(r)
        if not a.json:
            print(f"Approved effect set {r['approved_set']} in {r['file']}")
        return 0
    plan = Plan(a.plan)
    mode = "local" if getattr(a, "local", False) else ("rented" if getattr(a, "rented", False) else None)
    if a.cmd == "plan":
        s = plan.summary()
        s["notes"] = workbench.motion_notes(plan)
        if any(workbench.needs_style_frame(x) for x in plan.inserts) or plan.of_kind("motion"):
            s["notes"] += [f"waits: {x}" for x in workbench.insert_gates(plan)]
        out.update(s)
        if not a.json:
            _print_plan(s)
        return 0
    if a.cmd == "2d":
        rows = workbench.render_2d(plan, _ids(a.ids), a.images_only, log=log, gate=not a.no_gate)
        out["rows"] = rows
        if not a.json:
            _print_rows("2d", rows)
        return 0 if all(r["frames_ok"] for r in rows) and (a.images_only or _rows_ok(rows)) else 1
    if a.cmd == "motion":
        r = workbench.render_motion(plan, _ids(a.ids), a.draft, mode, max_usd=a.max_usd, log=log, gate=not a.no_gate)
        out.update(r)
        if not a.json:
            _print_rows("motion", r["rows"])
        return 0 if _rows_ok(r["rows"]) else 1
    if a.cmd == "plates":
        r = workbench.render_plates(plan, _ids(a.ids), a.probe, mode, max_usd=a.max_usd, log=log)
        out.update(r)
        if not a.json:
            for row in r["rows"]:
                print(f"plate {row['insert']}/{row['plate']}: {'ok' if row['ok'] else 'failed'}  {row['dir']}")
        return 0 if all(row["ok"] for row in r["rows"]) else 1
    if a.cmd == "matte":
        r = workbench.render_matte(plan, _ids(a.ids), max_usd=a.max_usd, log=log)
        out.update(r)
        if not a.json:
            for row in r["rows"]:
                print(f"matte {row['id']}: {row.get('place') or 'failed'}"
                      + (f"  ({row['reason']})" if row.get("reason") else ""))
        return 0 if all(row.get("place") for row in r["rows"]) else 1
    if a.cmd == "3d":
        r = workbench.render_3d(plan, mode, a.gpus, _ids(a.ids), a.samples, a.draft, a.max_usd, log=log,
                                gate=not a.no_gate)
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
    if a.cmd == "slides":
        from . import slide
        video = Path(a.video).expanduser() if a.video else plan.output
        if not video.is_file():
            raise PlanError(f"video not found: {video}; build it first (crewcut render cut) or give --video")
        ids = _ids(a.ids)
        rows = [{"id": x.id, "kind": x.kind, "start": x.start_s, "end": x.end_s, "full": not x.transparent}
                for x in plan.inserts if not ids or x.id in ids]
        found = slide.check(str(video), rows, crop_top=a.crop_top)
        out["findings"] = found
        out["counts"] = {lv: sum(1 for f in found if f["level"] == lv) for lv in ("ERROR", "CHECK", "OK")}
        if not a.json:
            for f in found:
                print(f"{f['level']:<5} {f['text']}")
            c = out["counts"]
            print(f"Slide check: {c['ERROR']} ERROR, {c['CHECK']} CHECK, {c['OK']} OK of {len(found)} full-frame inserts")
        return 1 if out["counts"]["ERROR"] else 0
    if a.cmd == "all":
        r = workbench.render_all(plan, mode, a.gpus, a.samples, a.draft, a.max_usd, log=log, gate=not a.no_gate)
        out.update({k: v for k, v in r.items() if k != "ok"})
        if r["ok"] and not a.json:
            print(f"Cut: {out['cut']['output']}")
        return 0 if r["ok"] else 1
    return 2


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["motion-review"]:
        from ..motion import review
        return review.main(argv[1:])
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
