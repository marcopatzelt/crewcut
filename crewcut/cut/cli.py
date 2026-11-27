"""Command line for `crewcut ingest`, `crewcut transcribe` and `crewcut cut ...` (see docs/recording.md).

Shorts (Clip mode): `cut candidates` lists passages of a finished episode, `cut short` cuts the pieces again from the
originals in 9:16, `cut short-check` is the Critic's rule set for Shorts.

Exit codes: 0 ok, 1 error, 2 usage or a check that found something to fix (plan problems, doubled starts, a failed
cut check, loudness off target), 3 waiting for or refused by the user, 4 missing key (rented path).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

from . import (
    audio,
    build,
    candidates,
    doubles,
    grade,
    ingest,
    islands,
    media,
    plan,
    short,
    shortcheck,
    srt,
    takes,
    transcribe,
    verify,
)
from .common import (
    CutError,
    Waiting,
    episode_dir,
    episode_of_file,
    frame_size,
    inside,
    next_version,
    project,
    read_json,
    rel,
    resolve_input,
    version_in,
    write_new,
    write_new_json,
    write_replace,
)


def _out(args, result, text: str | None = None) -> None:
    if getattr(args, "json", False):
        print(json.dumps(result, ensure_ascii=False, indent=1, default=str))
    elif text is not None:
        print(text)


def _engine(args) -> transcribe.Engine:
    return transcribe.Engine(model=getattr(args, "model", None), device=getattr(args, "device", None),
                             language=getattr(args, "language", None))


def _source(ep_dir: Path, arg: str) -> str:
    """A source given relative to the episode (originals/x.MP4) or as any path inside it."""
    if (ep_dir / arg).is_file():
        return Path(arg).as_posix()
    return rel(ep_dir, resolve_input(arg, ep_dir))


def _version_of(path: Path, data: dict) -> str:
    return data.get("version") or version_in(path.name) or "v001"


# ---- ingest and transcribe ---------------------------------------------------------------------------------------
def cmd_ingest(args) -> int:
    if args.imported:
        from .legacy import register
        if args.files or args.inbox:
            raise CutError("Use --imported without other files or --inbox.")
        report = register(args.episode)
        _out(args, report, ingest.describe(report))
        return 0
    files = [resolve_input(f) for f in args.files]
    if args.inbox or not files:
        files += ingest.inbox_files(args.episode)
    if not files:
        print(f"nothing to ingest: name files, or drop them into inbox/{args.episode}/", file=sys.stderr)
        return 2
    report = ingest.ingest(args.episode, files)
    _out(args, {k: v for k, v in report.items() if k != "files"} | {
        "files": [{k: v for k, v in f.items() if k != "probe"} for f in report["files"]]}, ingest.describe(report))
    return 0


def cmd_transcribe(args) -> int:
    src = resolve_input(args.file)
    out, ep_dir = transcribe.output_path(src, args.out, args.episode)
    if args.rented:
        if ep_dir is None:
            raise CutError("the rented path needs an episode (--episode): the yes is asked on a card there")
        eng = _engine(args)
        result = transcribe.transcribe_rented(src, out, ep_dir, eng.model_name, eng.language, args.channel,
                                              wait=args.wait, force=args.force)
    else:
        result = transcribe.transcribe_local(src, out, _engine(args), args.channel, force=args.force)
    if ep_dir is not None:
        result["out"] = rel(ep_dir, Path(result["out"]))
    lines = [f"{result['words']} words -> {result['out']}"]
    if "seconds_taken" in result:
        lines.append(f"{result['audio_seconds']} s of sound read in {result['seconds_taken']} s "
                     f"({result['model']}, {result['device']}, {result['language']})")
    if result.get("gain_db"):
        lines.append(f"the recording is very quiet: +{result['gain_db']:g} dB before recognition")
    for s in result.get("suspects", []):
        lines.append(f"listen at {s['at']:.1f} s: «{s['text']}» is often invented by the recognizer")
    lines.append("Whole-file recognition can leave out sentences: `crewcut cut islands ... --words` lists the gaps.")
    if ep_dir is not None:
        from .. import stylegate
        try:   # the words of a finished voice cut: the Critic reviews what was said against the cue sheet
            after = stylegate.after_transcript(ep_dir.name, Path(out))
        except Exception as e:  # noqa: BLE001 - the transcript is written; the review is a bonus
            after = None
            lines.append(f"(the review of what was said did not start: {e})")
        if after:
            result["review"] = after
            lines.append(f"The Critic reviews what was said against the cue sheet (job {after['job']}); a cut list "
                         "for the edit follows.")
    _out(args, result, "\n".join(lines))
    return 0


# ---- cut ---------------------------------------------------------------------------------------------------------
def cmd_islands(args) -> int:
    ep = episode_dir(args.episode)
    source = _source(ep, args.source)
    words = resolve_input(args.words, ep) if args.words else None
    r = islands.build(ep, source, args.start, args.end, args.channel, words, args.fill, lambda: _engine(args))
    lines = [f"{x['start']:8.2f}-{x['end']:8.2f}  {x['text']}" for x in r["rows"]]
    if r["gaps"]:
        lines.append(f"{len(r['gaps'])} islands over 1 s have no words (the fast way left them out). Read them with "
                     "--fill, or: " + ", ".join(f"--from {g['start']:.1f} --to {g['end']:.1f}" for g in r["gaps"][:5]))
    if r["unplaced_words"]:
        lines.append(f"{r['unplaced_words']} words fit no island (said in a pause? check the pause list)")
    lines.append(f"islands: {r['islands']}")
    _out(args, r, "\n".join(lines))
    return 0


def _ranges(items: list[str]) -> list[tuple[float, float]]:
    out = []
    for r in items:
        try:
            a, b = (float(v) for v in r.split("-", 1))
        except ValueError as exc:
            raise CutError(f"a range is START-END in seconds, got {r!r}") from exc
        if b <= a:
            raise CutError(f"range {r}: end must be after start")
        out.append((a, b))
    return out


def cmd_probe(args) -> int:
    ep = episode_dir(args.episode)
    wav, _, _ = islands.prepare(ep, _source(ep, args.source))
    x, rate = islands.read_wav(wav)
    eng = _engine(args)
    rows = [{"start": a, "end": b, "text": eng.text(x[int(a * rate):int(b * rate)])} for a, b in _ranges(args.ranges)]
    _out(args, rows, "\n".join(f"{r['start']:8.2f}-{r['end']:8.2f}  {r['text']}" for r in rows))
    return 0


def cmd_dips(args) -> int:
    ep = episode_dir(args.episode)
    wav, _, _ = islands.prepare(ep, _source(ep, args.source))
    x, rate = islands.read_wav(wav)
    series = islands.rms_series(x, rate, args.start, args.end)
    dips = islands.usable_dips(series, args.below, args.min)
    text = " ".join(f"{t:.2f}:{db:.0f}" for t, db in series)
    text += f"\nusable dips (below {args.below:g} dB for {args.min:g} s or more): "
    text += ", ".join(f"{d['start']:.2f}-{d['end']:.2f} ({d['min_db']:.0f} dB)" for d in dips) or "none"
    _out(args, {"series": series, "dips": dips}, text)
    return 0


def _default_takes(ep: Path) -> list[str]:
    """Islands that exist, in recording order (from the ingest reports), else by name."""
    have = {p.name[:-len("-islands.json")]: p for p in (ep / "work").glob("*-islands.json")}
    order = []
    for f in ingest.previous_entries(ep):
        stem = Path(f["file"]).stem
        if stem in have and f["file"] not in [o[1] for o in order]:
            order.append((f.get("created") or "", f["file"]))
    if order:
        return [f for _, f in sorted(order)]
    return [read_json(p).get("source") for _, p in sorted(have.items())]


def cmd_takes(args) -> int:
    ep = episode_dir(args.episode)
    if args.script:
        script = resolve_input(args.script, ep)
    else:
        found = sorted((ep / "brief").glob("SCRIPT-v*.md"))
        if not found:
            raise CutError("no script: give --script brief/SCRIPT-vNNN.md")
        script = found[-1]
    sources = [_source(ep, t) for t in args.take] if args.take else _default_takes(ep)
    if not sources:
        raise CutError("no islands yet: run crewcut cut islands for every recording first")
    ids = takes.take_ids(len(sources))
    result = takes.choose(script.read_text(encoding="utf-8"), [(t, islands.load(ep, s)) for t, s in zip(ids, sources,
                                                                                                         strict=True)])
    version = args.version or next_version(ep / "edit", "selects")
    sel = takes.selects_file(version, sources, result, takes.script_path_label(script, ep))
    sel_path = write_new_json(ep / "edit" / f"selects-{version}.json", sel)
    rep_path = write_replace(ep / "review" / f"takes-{version}.json",
                             json.dumps(result, ensure_ascii=False, indent=1) + "\n")
    result |= {"selects_file": rel(ep, sel_path), "report": rel(ep, rep_path),
               "takes": dict(zip(ids, sources, strict=True))}
    text = takes.describe(result) + f"\nselects (draft, check before building): {result['selects_file']}"
    _out(args, result, text)
    return 0


def cmd_plan(args) -> int:
    path = resolve_input(args.selects)
    _, ep = episode_of_file(path)
    cfg = read_json(path)
    cfg.setdefault("version", _version_of(path, cfg))
    sil, chans = {}, {}
    for name, t in cfg["takes"].items():
        _, sil[name], _ = islands.prepare(ep, t["source"], cfg.get("mic_channel"))
        if cfg.get("mic_channel") is None:
            chans[name] = transcribe.mic_channel_of(inside(ep, t["source"]))
    result, problems = plan.make_plan(cfg, sil, project(ep), plan.mic_for_takes(cfg, chans))
    if problems:
        for p in problems:
            print(f"PROBLEM: {p}", file=sys.stderr)
        return 2
    result["selects"] = rel(ep, path)
    dest = write_new_json(ep / "edit" / f"cut-plan-{cfg['version']}.json", result)
    out = {"plan": rel(ep, dest), "cuts": len(result["cuts"]), "seconds": result["estimated_seconds"]}
    _out(args, out, f"{out['cuts']} cuts, about {out['seconds']} s -> {out['plan']}")
    return 0


def cmd_build(args) -> int:
    path = resolve_input(args.plan)
    _, ep = episode_of_file(path)
    log = (lambda m: print(m, file=sys.stderr)) if args.json else print
    r = build.build(path, ep, resume=args.resume, reuse=args.reuse, log=log)
    _out(args, r, f"{r['clips']} clips, {r['frames']} frames ({r['seconds']} s)\nspeaker: {r['speaker']}\n"
                  f"voice: {r['voice']}\ndecisions: {r['manifest']}\nNext: crewcut cut verify {r['manifest']}")
    return 0


def cmd_verify(args) -> int:
    path = resolve_input(args.decisions)
    _, ep = episode_of_file(path)
    log = (lambda m: print(m, file=sys.stderr)) if args.json else print
    r = verify.verify(path, ep, _engine(args), log=log)
    _out(args, r, verify.describe(r))
    return 2 if r["status"] == "review_needed" else 0


def cmd_doubles(args) -> int:
    path = resolve_input(args.selects)
    _, ep = episode_of_file(path)
    cfg = read_json(path)
    version = _version_of(path, cfg)
    if args.fast:
        rows = []
        for s in cfg["selects"]:
            src = cfg["takes"][s["take"]]["source"]
            wf = ep / "work" / transcribe.words_name(Path(src))
            if not wf.exists():
                raise CutError(f"no words for {src}: run crewcut transcribe first, or drop --fast")
            rows += [{**r, "select": s["id"]} for r in doubles.in_words(read_json(wf), s["start"], s["end"])]
    else:
        by_take = {t: islands.load(ep, v["source"]) for t, v in cfg["takes"].items()}
        wavs: dict[str, tuple] = {}
        eng = _engine(args)

        def read(take: str, a: float, b: float) -> str:
            if take not in wavs:
                wav, _, _ = islands.prepare(ep, cfg["takes"][take]["source"])
                wavs[take] = islands.read_wav(wav)
            x, rate = wavs[take]
            return eng.text(x[int(a * rate):int(b * rate)])
        rows = doubles.check(cfg, by_take, read)
    out = write_replace(ep / "review" / f"doubles-{version}.json", json.dumps(
        {"selects": rel(ep, path), "fast": args.fast, "rows": rows}, ensure_ascii=False, indent=1) + "\n")
    found = [r for r in rows if r["double"]]
    _out(args, {"rows": rows, "doubles": len(found), "report": rel(ep, out)},
         doubles.describe(rows) + f"\nreport: {rel(ep, out)}")
    return 2 if found else 0


def cmd_grade(args) -> int:
    ep = episode_dir(args.episode)
    pic = inside(ep, _source(ep, args.picture))
    vf = args.filter or grade.base_filter()
    if args.action == "apply":
        if args.out:
            out = inside(ep, args.out)
        else:
            v = version_in(pic.name)
            out = ep / "work" / (f"speaker-graded-{v}.mov" if v else f"{pic.stem}-graded.mov")
        if out.exists():
            raise CutError(f"{rel(ep, out)} exists already. Use a new version.")
        out.parent.mkdir(parents=True, exist_ok=True)
        media.run(grade.apply_cmd(pic, vf, out))
        from . import prune
        prune.after_write(ep, lambda m: print(m, file=sys.stderr))
        _out(args, {"graded": rel(ep, out), "filter": vf}, f"graded: {rel(ep, out)}")
        return 0
    times = [float(t) for t in args.times.split(",") if t.strip()]
    try:
        wall, skin = grade.parse_rect(args.wall), grade.parse_rect(args.skin)
    except ValueError as exc:
        raise CutError(str(exc)) from exc
    r = grade.check(ep, pic, times, vf, frame_size(project(ep)), wall, skin)
    r["sheet"] = rel(ep, r["sheet"])
    dest = write_replace(ep / "review" / "grade" / f"{pic.stem}-check.json",
                         json.dumps(r, ensure_ascii=False, indent=1) + "\n")
    lines = [f"filter: {vf}"]
    for row in r["rows"]:
        lines.append(f"{row['t']:g} s  before {row['before']['frame']}  after {row['after']['frame']}")
        lines += [f"    miss: {m}" for m in row["misses"]]
    lines += r["notes"] + [f"sheet: {r['sheet']}", f"report: {rel(ep, dest)}",
                           "All targets met." if r["ok"] else "Adjust the filter and check again."]
    _out(args, r, "\n".join(lines))
    return 0


def cmd_srt(args) -> int:
    path = resolve_input(args.decisions)
    eid, ep = episode_of_file(path)
    manifest = read_json(path)
    version = manifest.get("version") or version_in(path.name)
    words_path = resolve_input(args.words, ep) if args.words else ep / "work" / f"words-{version}.json"
    words = read_json(words_path) if words_path.exists() else None
    cue_list = srt.cues(manifest, words)
    out = inside(ep, args.out) if args.out else ep / "export" / f"{eid}-{version}.srt"
    write_new(out, srt.render(cue_list))
    r = {"srt": rel(ep, out), "cues": len(cue_list), "words": rel(ep, words_path) if words else None}
    _out(args, r, f"{len(cue_list)} cues -> {r['srt']}" + ("" if words else " (no words file: times spread by "
                                                                            "characters)")
         + "\nCheck three cues (start, middle, end) against the sound of the finished video.")
    return 0


def cmd_audio(args) -> int:
    src = resolve_input(args.file)
    info = media.probe(src)
    mic, tail = ingest.check_sound(src, info)
    r = {"file": src.name, "summary": media.summary(info), "mic_check": mic, "sound_to_end": tail}
    text = "no sound track" if mic is None else f"{mic['message']}\n{tail['message']}"
    _out(args, r, text)
    return 0


def cmd_loudness(args) -> int:
    src = resolve_input(args.file)
    m = audio.measure_loudness(src)
    problems = audio.loudness_problems(m, args.target, args.max_peak)
    r = {**m, "problems": problems}
    text = f"{m['integrated_lufs']} LUFS, true peak {m['true_peak_dbtp']} dBTP, range {m['lra_lu']} LU"
    _out(args, r, "\n".join([text] + [f"off: {p}" for p in problems]))
    return 2 if problems else 0


# ---- shorts ------------------------------------------------------------------------------------------------------
def cmd_short(args) -> int:
    path = resolve_input(args.spec)
    _, ep = episode_of_file(path)
    log = (lambda m: print(m, file=sys.stderr)) if args.json else print
    p = short.prepare(path, ep)
    if args.dry_run:
        _out(args, {k: v for k, v in p.items() if k not in ("words", "source_dir", "spec")}, short.describe_plan(p))
        return 2 if p["soft"] and not args.accept_soft else 0
    for m in p["soft"]:
        print(f"SOFT: {m}", file=sys.stderr)
    if p["soft"] and not args.accept_soft:
        print("Nothing built. Tell the user before building; build anyway with --accept-soft.", file=sys.stderr)
        return 2
    if args.words == "new" and importlib.util.find_spec("faster_whisper") is None:
        raise CutError("new word times need faster-whisper (in the image it is; elsewhere pip install "
                       "'crewcut[speech]'), or use --words carry")
    r = short.build_short(p, ep, args.words, lambda: _engine(args), log=log)
    _out(args, r, short.describe(r))
    return 0


def cmd_candidates(args) -> int:
    if not (args.episode or args.episode_opt):
        print("name the finished episode: crewcut cut candidates <episode>", file=sys.stderr)
        return 2
    ep = episode_dir(args.episode or args.episode_opt)
    r = candidates.find(ep, resolve_input(args.words, ep) if args.words else None,
                        resolve_input(args.plan, ep) if args.plan else None,
                        resolve_input(args.retention, ep) if args.retention else None,
                        args.min, args.max, args.sentences, args.limit)
    out = candidates.write(ep, r)
    r["report"] = rel(ep, out)
    _out(args, r, candidates.describe(r) + f"\nreport: {r['report']}")
    return 0


def cmd_short_check(args) -> int:
    path = resolve_input(args.video)
    _, ep = episode_of_file(path)
    r = shortcheck.check(ep, path, resolve_input(args.cut, ep) if args.cut else None,
                         resolve_input(args.plan, ep) if args.plan else None)
    _out(args, r, shortcheck.describe(r))
    return 0 if r["ok"] else 2


# ---- parser ------------------------------------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", help="machine-readable output")
    speech = argparse.ArgumentParser(add_help=False)
    speech.add_argument("--model", help="speech model (default from config/speech.toml)")
    speech.add_argument("--device", choices=["auto", "cpu", "cuda"])
    speech.add_argument("--language", help="language code (default: the style pack's channel.language)")

    ap = argparse.ArgumentParser(prog="crewcut", description="Recording to speaker cut.")
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("ingest", parents=[common], help="save recordings into an episode and check their sound")
    p.add_argument("episode")
    p.add_argument("files", nargs="*", help="recordings; none = everything in inbox/<episode>/")
    p.add_argument("--inbox", action="store_true", help="also take the files dropped into inbox/<episode>/")
    p.add_argument("--imported", action="store_true", help="register verified legacy recordings without starting work")
    p.set_defaults(fn=cmd_ingest)

    p = sub.add_parser("transcribe", parents=[common, speech], help="words with times (faster-whisper)")
    p.add_argument("file")
    p.add_argument("--episode", help="needed when the file is not inside an episode folder")
    p.add_argument("--out", help="words file (default work/words-<name>.json)")
    p.add_argument("--channel", type=int, help="microphone channel (default: found by the level check)")
    p.add_argument("--force", action="store_true", help="read again and replace the words file")
    p.add_argument("--rented", action="store_true", help="run on a rented GPU (asks for a yes on a card first)")
    p.add_argument("--wait", type=float, help="with --rented: wait this many seconds for the yes")
    p.set_defaults(fn=cmd_transcribe)

    cut = sub.add_parser("cut", help="speaker cut tools").add_subparsers(dest="tool", required=True)

    p = cut.add_parser("islands", parents=[common, speech], help="speech pieces between pauses, with text")
    p.add_argument("episode")
    p.add_argument("source", help="the recording, e.g. originals/<sha12>-C0001.MP4")
    p.add_argument("--from", dest="start", type=float, default=0.0)
    p.add_argument("--to", dest="end", type=float, default=1e9)
    p.add_argument("--channel", type=int, help="microphone channel (default: found by the level check)")
    p.add_argument("--words", help="words of the whole file (fast way); without: every island is read alone")
    p.add_argument("--fill", action="store_true", help="with --words: read the islands that have no words")
    p.set_defaults(fn=cmd_islands)

    p = cut.add_parser("probe", parents=[common, speech], help="read ranges on their own to check cut edges")
    p.add_argument("episode")
    p.add_argument("source")
    p.add_argument("ranges", nargs="+", help="START-END in seconds")
    p.set_defaults(fn=cmd_probe)

    p = cut.add_parser("dips", parents=[common], help="level every 20 ms, to find the gap between two words")
    p.add_argument("episode")
    p.add_argument("source")
    p.add_argument("start", type=float)
    p.add_argument("end", type=float)
    p.add_argument("--below", type=float, default=-40.0, help="a usable dip is under this level (dB)")
    p.add_argument("--min", type=float, default=0.06, help="... for at least this long (s)")
    p.set_defaults(fn=cmd_dips)

    p = cut.add_parser("takes", parents=[common], help="draft selects: the attempt of each sentence to use")
    p.add_argument("episode")
    p.add_argument("--script", help="default: the newest brief/SCRIPT-vNNN.md")
    p.add_argument("--take", action="append", help="recording in recording order (repeat); default: all with islands")
    p.add_argument("--version", help="selects version (default: the next free one)")
    p.set_defaults(fn=cmd_takes)

    p = cut.add_parser("plan", parents=[common], help="cut plan from a selects file")
    p.add_argument("selects")
    p.set_defaults(fn=cmd_plan)

    p = cut.add_parser("build", parents=[common], help="build the speaker cut and the clean voice")
    p.add_argument("plan")
    p.add_argument("--resume", action="store_true", help="continue an interrupted build (keeps finished clips)")
    p.add_argument("--reuse", help="hard-link unchanged clips of this older version (e.g. v007)")
    p.set_defaults(fn=cmd_build)

    p = cut.add_parser("verify", parents=[common, speech], help="check the built cut (words, edges, joins, channels)")
    p.add_argument("decisions", help="work/edit-decisions-vNNN.json")
    p.set_defaults(fn=cmd_verify)

    p = cut.add_parser("doubles", parents=[common, speech], help="doubled sentence starts inside selects")
    p.add_argument("selects")
    p.add_argument("--fast", action="store_true", help="use the words files only (quick, may miss doubles)")
    p.set_defaults(fn=cmd_doubles)

    p = cut.add_parser("grade", parents=[common], help="colour: check with stills, then apply")
    p.add_argument("action", choices=["check", "apply"])
    p.add_argument("episode")
    p.add_argument("picture", help="e.g. work/speaker-v001.mov")
    p.add_argument("--times", default="3", help="check: seconds, comma separated")
    p.add_argument("--filter", help="ffmpeg filter (default: the style pack's grade_filter or the base look)")
    p.add_argument("--wall", help="check: wall patch x,y,w,h")
    p.add_argument("--skin", help="check: skin patch x,y,w,h")
    p.add_argument("--out", help="apply: output inside the episode (default work/speaker-graded-vNNN.mov)")
    p.set_defaults(fn=cmd_grade)

    p = cut.add_parser("srt", parents=[common], help="SRT subtitles from the cut and the selects' text")
    p.add_argument("decisions")
    p.add_argument("--out", help="default export/<episode>-vNNN.srt")
    p.add_argument("--words", help="words of the finished voice (default work/words-vNNN.json when present)")
    p.set_defaults(fn=cmd_srt)

    p = cut.add_parser("audio", parents=[common], help="sound check of one file: channels and sound to the end")
    p.add_argument("file")
    p.set_defaults(fn=cmd_audio)

    p = cut.add_parser("short", parents=[common, speech],
                       help="Short (Clip mode): cut pieces of a finished episode again from the originals in 9:16")
    p.add_argument("spec", help="the pieces spec in the short's episode, e.g. edit/pieces-v001.json")
    p.add_argument("--words", choices=["new", "carry"], default="new",
                   help="new: recognize the Short's voice again (default); carry: take the episode's word times "
                        "and check them against the level")
    p.add_argument("--accept-soft", action="store_true", help="build although the crop is smaller than the output")
    p.add_argument("--dry-run", action="store_true", help="resolve and check the pieces, build nothing")
    p.set_defaults(fn=cmd_short)

    p = cut.add_parser("candidates", parents=[common], help="stand-alone passages of a finished episode for Shorts")
    p.add_argument("episode", nargs="?", help="the finished episode")
    p.add_argument("--episode", dest="episode_opt", help="the same, as an option")
    p.add_argument("--words", help="word record of the final cut (default: the edit plan's, else the newest)")
    p.add_argument("--plan", help="edit plan with the graphics (default: the newest edit/plan-vNNN.json)")
    p.add_argument("--retention", help="retention curve, CSV or JSON (default: review/retention.json or .csv)")
    p.add_argument("--min", type=float, default=20.0, help="shortest passage in seconds")
    p.add_argument("--max", type=float, default=55.0, help="longest passage in seconds")
    p.add_argument("--sentences", type=int, default=12, help="most whole sentences in one passage")
    p.add_argument("--limit", type=int, default=30, help="how many passages to list")
    p.set_defaults(fn=cmd_candidates)

    p = cut.add_parser("short-check", parents=[common], help="the Critic's rule set for Shorts, contact sheet and "
                                                             "listening list")
    p.add_argument("video", help="the rendered Short or the rough cut (work/speaker-vNNN.mov)")
    p.add_argument("--cut", help="report of crewcut cut short (default: found from the plan or the version)")
    p.add_argument("--plan", help="edit plan of the video (default: the plan whose output is the video)")
    p.set_defaults(fn=cmd_short_check)

    p = cut.add_parser("loudness", parents=[common], help="integrated loudness and true peak (EBU R128)")
    p.add_argument("file")
    p.add_argument("--target", type=float, help="LUFS (default: the style pack's loudness_lufs)")
    p.add_argument("--max-peak", type=float, help="dBTP (default: the style pack's true_peak_db)")
    p.set_defaults(fn=cmd_loudness)
    return ap


ALIASES = {("cut", "islands", "dips"): ["cut", "dips"], ("cut", "islands", "probe"): ["cut", "probe"]}


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if tuple(argv[:3]) in ALIASES:                 # `crewcut cut islands dips ...` = `crewcut cut dips ...`
        argv = ALIASES[tuple(argv[:3])] + argv[3:]
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2
    try:
        return int(args.fn(args) or 0)
    except Waiting as exc:
        print(f"waiting: {exc}", file=sys.stderr)
        return 3
    except (CutError, FileNotFoundError, FileExistsError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        code = getattr(exc, "exit_code", None)
        if code is None:
            raise
        print(f"error: {exc}", file=sys.stderr)
        return int(code)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
