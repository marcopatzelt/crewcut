"""The `crewcut` command. Agents use it from inside the container; humans rarely need it.

Exit codes: 0 ok, 1 error, 2 usage, 3 waiting for or refused by the user, 4 missing login or key.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from . import __version__

DELEGATED = {
    "full-auto": ("crewcut.full_auto", False),
    "media": ("crewcut.desktop_media", False),
    "workspace": ("crewcut.workspaces", False),
    "compute": ("crewcut.compute.cli", False),
    "render": ("crewcut.render.cli", True),
    "ingest": ("crewcut.cut.cli", True),
    "transcribe": ("crewcut.cut.cli", True),
    "cut": ("crewcut.cut.cli", True),
    "motion": ("crewcut.motion.cli", False),
    "formats": ("crewcut.showformats", False),
    "ideas": ("crewcut.ideas", False),
    "voice": ("crewcut.voicecheck", False),
    "lernstand": ("crewcut.lernstand", False),
}
HEAVY = {"render": {"2d", "3d", "probe", "cut", "all", "capture", "music-bed"}, "transcribe": None,
         "cut": {"build", "grade", "islands", "probe", "verify", "doubles", "takes", "short", "short-check"}}


def _env_episode(a) -> str | None:
    return getattr(a, "episode", None) or os.environ.get("CREWCUT_EPISODE") or None


def _identity() -> str:
    return os.environ.get("CREWCUT_IDENTITY") or "showrunner"


def _job() -> int | None:
    j = os.environ.get("CREWCUT_JOB", "")
    return int(j) if j.isdigit() else None


def _plan_path(given: str, episode: str | None):
    """An edit plan from a path (absolute, from here, or inside the episode) or an episode id (its newest plan)."""
    import re
    from pathlib import Path

    from . import paths
    p = Path(given).expanduser()
    if p.is_file():
        return p.resolve()
    if episode and not p.is_absolute():
        q = paths.inside(paths.episode_dir(episode), given)
        if q.is_file():
            return q
    d = paths.episode_dir(given) / "edit"
    if d.is_dir():
        plans = sorted((x for x in d.glob("plan-v*.json") if re.fullmatch(r"plan-v\d+\.json", x.name)),
                       key=lambda x: int(re.sub(r"\D", "", x.stem)))
        if plans:
            return plans[-1]
    raise FileNotFoundError(f"no edit plan {given!r} (give a plan file or an episode id with edit/plan-vNNN.json)")


def _print(obj, as_json: bool) -> None:
    if as_json:
        print(json.dumps(obj, ensure_ascii=False, indent=1, default=str))
    elif isinstance(obj, str):
        print(obj)
    else:
        print(json.dumps(obj, ensure_ascii=False, indent=1, default=str))


def _delegate(cmd: str, argv: list[str]) -> int:
    import importlib
    modname, with_cmd = DELEGATED[cmd]
    try:
        mod = importlib.import_module(modname)
    except ImportError as e:
        print(f"crewcut {cmd}: this part is not installed ({e}).", file=sys.stderr)
        return 1
    args = [cmd, *argv] if modname == "crewcut.cut.cli" else argv
    heavy = HEAVY.get(cmd, set())
    sub = argv[0] if argv else ""
    if cmd in HEAVY and (heavy is None or sub in heavy) and "--help" not in argv and "-h" not in argv:
        local_only = "--rented" not in argv
        if local_only:
            from .conductor import lanes
            with lanes.heavy(f"{cmd} {sub}".strip()):
                return int(mod.main(args) or 0)
    return int(mod.main(args) or 0)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="crewcut", description="A crew of AI agents that makes a whole YouTube video.")
    p.add_argument("--version", action="version", version=f"crewcut {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("doctor", help="check programs, fonts, templates, engine login, GPU, disk")
    d.add_argument("--json", action="store_true")
    d.add_argument("--ci", action="store_true", help="no login probe; missing login is a note, not an error")
    d.add_argument("--probe", action="store_true", help="also prove the engine login with a tiny call")

    op = sub.add_parser("open", help="open Crewcut in its own app window once it answers (on your computer); "
                        "prints the address. CREWCUT_OPEN=app|browser|none")
    op.add_argument("url", nargs="?", help="default http://localhost:<CREWCUT_PORT or 4747>")
    op.add_argument("--no-open", action="store_true", help="only print the address")
    op.add_argument("--timeout", type=float, default=None, help="seconds to wait for the server (default 900)")

    s = sub.add_parser("serve", help="start the web UI, the API and the teleprompter")
    s.add_argument("--host", default=os.environ.get("CREWCUT_HOST", "127.0.0.1"))
    s.add_argument("--port", type=int, default=None)
    s.add_argument("--prompter-host", default=os.environ.get("CREWCUT_PROMPTER_HOST", "0.0.0.0"))
    s.add_argument("--prompter-port", type=int, default=None)

    e = sub.add_parser("episode", help="create and inspect episodes")
    esub = e.add_subparsers(dest="ecmd", required=True)
    en = esub.add_parser("new")
    en.add_argument("title")
    en.add_argument("--source")
    en.add_argument("--short", choices=["clip", "original"], help="a Short: a clip of a finished episode, or an original")
    en.add_argument("--from", dest="from_", help="clip: the episode it comes from")
    es = esub.add_parser("status")
    es.add_argument("episode", nargs="?")
    es.add_argument("--json", action="store_true")
    cover = esub.add_parser("refresh-cover", help="fill a missing card preview without approving a thumbnail")
    cover.add_argument("episode")
    cover.add_argument("--youtube-id")
    cover.add_argument("--image", help="existing image path inside this episode")
    ei = esub.add_parser("import", help="bring earlier work (script, B-roll, plan) into a new episode")
    ei.add_argument("source", help="a folder the container can read, e.g. /import/episodes/S017-ki-beirat")
    ei.add_argument("--title", required=True)
    ei.add_argument("--format", choices=["landscape", "portrait"])
    ei.add_argument("--script", help="script file (default: the newest SCRIPT-*.md in the folder)")
    ei.add_argument("--broll", action="extend", nargs="+",
                    help="B-roll files (default: everything in 04-broll/ or broll/)")
    ei.add_argument("--plan", help="an earlier edit plan to translate (German studio keys are understood)")
    ei.add_argument("--done", help="steps already done, comma separated (default: idea,title,proof and script if any)")
    ei.add_argument("--skip", default="upload", help="steps switched off, comma separated (default: upload)")
    ei.add_argument("--no-start", action="store_true", help="do not start the first open step yet")
    est = esub.add_parser("step")
    est.add_argument("episode")
    est.add_argument("step")
    est.add_argument("status", choices=["open", "working", "waiting", "done", "skipped"])
    est.add_argument("--next")
    el = esub.add_parser("lifecycle", help="organize or resume an episode without starting work or granting approval")
    el.add_argument("episode")
    el.add_argument("lifecycle", choices=["active", "planned", "parked", "archived"])
    recording = esub.add_parser("recording-script", help="select an existing recording text without approving it")
    recording.add_argument("episode")
    recording.add_argument("file")
    recording.add_argument("--partial", action="store_true")

    iv = sub.add_parser("interview", help="the interview before the first script draft ([steps] interview)")
    ivsub = iv.add_subparsers(dest="ivcmd", required=True)
    iva = ivsub.add_parser("ask", help="the Writer posts its 5 to 8 numbered questions; the episode waits for answers")
    iva.add_argument("episode")
    iva.add_argument("text", nargs="?", help="the questions (or --file)")
    iva.add_argument("--file", help="a file in the episode with the questions, e.g. work/interview-questions.md")
    ivw = ivsub.add_parser("answer", help="voice files from the episode inbox, transcribed on this machine")
    ivw.add_argument("episode")
    ivw.add_argument("--audio", action="append", required=True)
    for name, text in (("skip", "no interview for this episode (the creator decides)"),
                       ("done", "the answers are complete (the creator decides)"), ("status", "show the interview")):
        x = ivsub.add_parser(name, help=text)
        x.add_argument("episode")

    sy = sub.add_parser("say", help="a message in the main chat, from the running crew member")
    sy.add_argument("--episode")
    sy.add_argument("--channel", action="store_true")
    sy.add_argument("--cite", help="one short line: the method and its source")
    sy.add_argument("--preview", help="a video or image in the episode to show under the message")
    sy.add_argument("--fact", action="append", default=[], help='a row of a small table: "Loudness=-14.1 LUFS"')
    sy.add_argument("--to", help="a crew member: crew talk instead of the chat (only when crew talk is on)")
    sy.add_argument("--for", dest="relay_for", action="append", default=[],
                    help="a running crew member that gets this chat message at its next step (the Showrunner relays)")
    sy.add_argument("--about", help="crew talk: the file (or time stamp) the message is about")
    sy.add_argument("--kind", choices=["fix", "question", "notice"], help="crew talk: what the message is")
    sy.add_argument("--expects", choices=["reply", "none"], default=None)
    sy.add_argument("--topic")
    sy.add_argument("--reply-to", type=int)
    sy.add_argument("text")

    cr = sub.add_parser("crew", help="crew settings")
    crsub = cr.add_subparsers(dest="crcmd", required=True)
    crt = crsub.add_parser("talk", help="crew talk on or off (the user says it: 'no crew chat')")
    crt.add_argument("state", choices=["on", "off", "status"])

    dg = sub.add_parser("doing", help="what the running crew member does right now (Crew column)")
    dg.add_argument("--episode")
    dg.add_argument("--progress", type=float)
    dg.add_argument("text")

    ch = sub.add_parser("chat", help="print the recent chat of an episode")
    ch.add_argument("--episode")
    ch.add_argument("--channel", action="store_true")
    ch.add_argument("--last", type=int, default=12)

    c = sub.add_parser("card", help="ask the user for one yes")
    csub = c.add_subparsers(dest="ccmd", required=True)
    cp = csub.add_parser("propose")
    cp.add_argument("--episode")
    cp.add_argument("--step")
    cp.add_argument("--kind", required=True)
    cp.add_argument("--title", required=True)
    cp.add_argument("--body", default="")
    cp.add_argument("--file")
    cp.add_argument("--preview")
    cp.add_argument("--option", action="append", default=[])
    cp.add_argument("--data", help="JSON object with extra fields (spend: amount_usd, cap_usd, local and rented)")
    cp.add_argument("--json", action="store_true")
    cw = csub.add_parser("wait")
    cw.add_argument("card", type=int)
    cw.add_argument("--timeout", type=float)
    ca = csub.add_parser("accept", help="the Showrunner records a yes the user gave in words")
    ca.add_argument("card", type=int)
    ca.add_argument("--choice", type=int)
    cd = csub.add_parser("decline")
    cd.add_argument("card", type=int)
    cd.add_argument("--reason", default="")
    cl = csub.add_parser("list")
    cl.add_argument("--episode")
    cl.add_argument("--status")

    r = sub.add_parser("rule", help="propose a learned rule (the user accepts with one yes)")
    rsub = r.add_subparsers(dest="rcmd", required=True)
    rp = rsub.add_parser("propose")
    rp.add_argument("--step", required=True)
    rp.add_argument("--rule", required=True)
    rp.add_argument("--source", required=True)
    rp.add_argument("--episode")

    j = sub.add_parser("job", help="give work to a crew member")
    jsub = j.add_subparsers(dest="jcmd", required=True)
    ja = jsub.add_parser("add")
    ja.add_argument("--episode")
    ja.add_argument("--identity", required=True)
    ja.add_argument("--step")
    ja.add_argument("--heavy", action="store_true")
    ja.add_argument("task")

    b = sub.add_parser("brand", help="the style pack")
    bsub = b.add_subparsers(dest="bcmd", required=True)
    bs = bsub.add_parser("show")
    bs.add_argument("--json", action="store_true")
    bsub.add_parser("check")
    bp = bsub.add_parser("preview")
    bp.add_argument("rest", nargs=argparse.REMAINDER)
    bi = bsub.add_parser("init", help="make a pack your own: studio/brand from the neutral pack or --from a pack")
    bi.add_argument("--from", dest="from_", help="a style pack folder, e.g. /app/examples/striq")
    bi.add_argument("--font", action="append", default=[], help="ROLE=FILE, e.g. display=/import/fonts/X.otf")
    bi.add_argument("--logo", help="a logo file (SVG or PNG) from your own files")
    bi.add_argument("--accept", action="store_true", help="the user chose this pack: onboarding is done")
    bv = bsub.add_parser("voice", help="the user's own spoken words: the voice sample of the Humanizer pass")
    bvsub = bv.add_subparsers(dest="vcmd", required=True)
    bva = bvsub.add_parser("add", help="a link to one of the user's own videos (captions) or a recording of them")
    bva.add_argument("source")
    bvsub.add_parser("list")

    sg = sub.add_parser("style-gate", help="the studio's style checker on the newest scripts (crewcut/stylegate.py)")
    sg.add_argument("episode")
    sg.add_argument("--file", action="append", default=[], help="check this file instead (repeatable), e.g. "
                    "brief/SCRIPT-v009.md or work/words-v012.json")
    sg.add_argument("--json", action="store_true")

    gg = sub.add_parser("graphics-gate", help="the style pack's graphic system on an edit plan (crewcut/graphicsgate.py)")
    gg.add_argument("plan", help="an edit plan (episodes/<id>/edit/plan-vNNN.json, or edit/plan-vNNN.json with "
                    "--episode) or an episode id (its newest plan)")
    gg.add_argument("--episode", help="the episode the plan path is relative to")
    gg.add_argument("--json", action="store_true")

    hz = sub.add_parser("humanize", help="the Humanizer pass over a script draft (blader/humanizer)")
    hzsub = hz.add_subparsers(dest="hcmd", required=True)
    hzr = hzsub.add_parser("record", help="record what the pass changed, for the script card")
    hzr.add_argument("--episode")
    hzr.add_argument("--draft", required=True, help="the draft before the pass, e.g. work/script-draft-v003.md")
    hzr.add_argument("--final", required=True, help="the script after the pass, e.g. brief/SCRIPT-v003.md")
    hzr.add_argument("--why", default="", help="the sections that applied, e.g. '§1 not X but Y; §6 lists of three'")
    hzr.add_argument("--json", action="store_true")

    sh = sub.add_parser("shorts", help="Shorts: standing approval, the next free slot, results")
    shsub = sh.add_subparsers(dest="shcmd", required=True)
    shs = shsub.add_parser("standing", help="publish Shorts without a card: on, off or status (never the default)")
    shs.add_argument("state", choices=["on", "off", "status"])
    shl = shsub.add_parser("slot", help="the next free publishing time for a Short")
    shl.add_argument("--episode")
    shr = shsub.add_parser("results", help="48-hour numbers of a published Short, one row of studio/shorts.tsv")
    shr.add_argument("--episode")
    shsub.add_parser("table", help="all rows of studio/shorts.tsv")

    sk = sub.add_parser("skills", help="skills from other projects (Humanizer, always the newest version) and your own "
                        "skills from the studio folder")
    sksub = sk.add_subparsers(dest="skcmd", required=True)
    sks = sksub.add_parser("status")
    sks.add_argument("--json", action="store_true")
    sko = sksub.add_parser("own", help="your own skills (<studio>/skills, [[skills.own]] in config/crewcut.toml)")
    sko.add_argument("--json", action="store_true")
    sku = sksub.add_parser("update")
    sku.add_argument("name", nargs="?")

    o = sub.add_parser("onboard", help="fetch brand facts from links (Brand identity)")
    o.add_argument("links", nargs="+")
    o.add_argument("--json", action="store_true")

    t = sub.add_parser("thumbnail", help="make thumbnail images")
    tsub = t.add_subparsers(dest="tcmd", required=True)
    tm = tsub.add_parser("make")
    tm.add_argument("--episode")
    tm.add_argument("--prompt", required=True, help="file with the complete prompt")
    tm.add_argument("--ref", action="append", default=[])
    tm.add_argument("--way", choices=["codex", "api"], default=None)
    tm.add_argument("--variants", type=int, default=1)
    tm.add_argument("--out", help="folder in the episode, default graphics/thumbnail")
    tm.add_argument("--format", help="format id of the variant (default: from the round's SET.json)")
    tm.add_argument("--control", action="store_true", help="the control variant in the channel's proven style")
    tm.add_argument("--edit", help="edit this image (in the episode) instead of a new image: it keeps the person's face")
    tm.add_argument("--tries", type=int, help="tries per image when the face check finds the wrong face")
    tm.add_argument("--no-face-check", action="store_true", help="skip the face check right after each image")
    tf = tsub.add_parser("formats", help="the format library of the style pack")
    tf.add_argument("formats_cmd", nargs="?", choices=["list", "show"], default="list")
    tf.add_argument("id", nargs="?")
    tf.add_argument("--kind", choices=["house", "pro"])
    tf.add_argument("--strong", action="store_true", help="only the formats marked strong for this channel")
    tf.add_argument("--json", action="store_true")
    ts = tsub.add_parser("set", help="check an A/B set for real variety, or put it on one card")
    ts.add_argument("setcmd", choices=["check", "card"])
    ts.add_argument("round", help="the round folder in the episode, e.g. graphics/thumbnail/v2-formats")
    ts.add_argument("--episode")
    ts.add_argument("--plan-only", action="store_true", help="check SET.json before the images exist")
    ts.add_argument("--json", action="store_true")
    ts.add_argument("--title")
    ts.add_argument("--body")
    ts.add_argument("--preview", help="optional preview image for the card (e.g. the 160 px sheet)")
    from .thumbnail import identity as _identity
    _identity.add_parser(tsub)

    y = sub.add_parser("youtube", help="YouTube Data API: sign in, upload, status")
    ysub = y.add_subparsers(dest="ycmd", required=True)
    yc = ysub.add_parser("connect", help="one card: Claude in Chrome sets up the YouTube API for you, then you sign in")
    yc.add_argument("--episode")
    yc.add_argument("--state", action="store_true", help="what is there: helper, Claude Code and Chrome on the computer")
    ysub.add_parser("auth")
    yu = ysub.add_parser("upload", help="upload the approved package once (never a second copy of the episode)")
    yu.add_argument("--episode")
    yu.add_argument("--package", help="upload package JSON, default export/upload.json")
    yu.add_argument("--schedule", help="ISO time to publish; without it the video stays private")
    yu.add_argument("--dry-run", action="store_true")
    yu.add_argument("--new-video", action="store_true",
                    help="only at the terminal: a second video of this episode next to the one on YouTube (another "
                         "video file; the same file never goes up twice)")
    ycm = ysub.add_parser("comment", help="post the Short's approved link comment once YouTube has processed it "
                          "(never twice; pinning has no API)")
    ycm.add_argument("episode")
    ycm.add_argument("--package", help="upload package JSON, default: the one of the upload")
    ycm.add_argument("--wait", type=float, default=0, help="seconds to wait for YouTube's processing")
    ysub.add_parser("status")
    yv = ysub.add_parser("verify", help="compare uploaded metadata with the package (read-only)")
    yv.add_argument("episode")
    yv.add_argument("--package", default="export/upload.json")
    results = ysub.add_parser("results", help="read video analytics for an explicit calendar-day period")
    results.add_argument("episode")
    results.add_argument("--start", help="inclusive date YYYY-MM-DD (with --first: the publication day)")
    results.add_argument("--end", help="inclusive date YYYY-MM-DD")
    results.add_argument("--first", type=int, choices=(7, 28), help="the first 7 or 28 days from the publication "
                         "(the scoreboard compares these windows)")
    results.add_argument("--video", help="video ID for an earlier publication")
    yr = ysub.add_parser("retention", help="audience retention of a published video around its motion moments "
                         "(YouTube Analytics, read-only)")
    yr.add_argument("episode")
    yr.add_argument("--video", help="video id (default: export/upload-result.json)")
    yr.add_argument("--json", action="store_true")

    rt = sub.add_parser("retention", help="audience retention of a published video per content unit (read-only)")
    rtsub = rt.add_subparsers(dest="rtcmd", required=True)
    ru = rtsub.add_parser("units", help="retention per content unit (hook, retain, reward), the sentence where each "
                          "steepest drop starts, and one lesson block in library/learnings/retention-units.md")
    ru.add_argument("episode")
    ru.add_argument("--video", help="video id (default: analytics/versions.json or export/upload-result.json)")
    ru.add_argument("--words", help="words file of the published edit (default: analytics/versions.json, else the "
                    "newest edit plan's words)")
    ru.add_argument("--duration", type=float, help="length of that version in seconds (default: from YouTube)")
    ru.add_argument("--since", help="first day YYYY-MM-DD (default: the upload day)")
    ru.add_argument("--until", help="last day YYYY-MM-DD (default: today)")
    ru.add_argument("--clips", type=int, default=0, metavar="N",
                    help="cut the N steepest drops from the local export into analytics/drops/")
    ru.add_argument("--saved", action="store_true",
                    help="measure again from the curve in analytics/retention-units.json, without the API")
    ru.add_argument("--no-learnings", action="store_true", help="do not add the block to the learnings file")
    ru.add_argument("--json", action="store_true")

    en = sub.add_parser("engine", help="the engine: Claude Code (default) or Codex (beta), both on your subscription")
    ensub = en.add_subparsers(dest="encmd", required=True)
    ens = ensub.add_parser("status")
    ens.add_argument("--json", action="store_true")
    enu = ensub.add_parser("use", help="switch the engine for all new work")
    enu.add_argument("name")
    eni = ensub.add_parser("install")
    eni.add_argument("name")
    enp = ensub.add_parser("update", help="bring in the newest version of the channel if it passes a smoke test")
    enp.add_argument("name", nargs="?")
    enp.add_argument("--channel", help="latest (default), stable, or a fixed version like 2.1.325")
    enp.add_argument("--no-login-test", action="store_true")
    enr = ensub.add_parser("rollback", help="go back to the previous good version")
    enr.add_argument("name", nargs="?")
    enc = ensub.add_parser("connect", help="sign in without a terminal: prints the sign-in link (Claude) or the "
                           "device link and code (Codex) as JSON lines; Claude then reads the code from stdin")
    enc.add_argument("name")
    enc.add_argument("--print-token", action="store_true",
                     help="Claude: print the token for the desktop app (which keeps it in the keychain) instead of "
                          "storing it in the engine volume")
    end = ensub.add_parser("disconnect", help="forget the login made with connect")
    end.add_argument("name")
    ena = ensub.add_parser("auth", help="Claude: show or switch the login of new work, the subscription or an API key")
    ena.add_argument("mode", nargs="?", choices=["subscription", "api-key", "api_key"])
    enk = ensub.add_parser("api-key", help="Claude: save an Anthropic API key (read from stdin, never an argument)")
    enk.add_argument("--stdin", action="store_true", help="read the key from stdin")
    enk.add_argument("--use", action="store_true", help="also switch new work to the API key")
    enk.add_argument("--forget", action="store_true", help="remove the stored key")
    enl = ensub.add_parser("login", help="Codex: device-code login, the link and code appear in the chat")
    enl.add_argument("name")
    enl.add_argument("--episode", help="which chat gets the link (default: the onboarding chat)")

    hk = sub.add_parser("hook", help="hooks that Claude Code calls (from the Crewcut plugin)")
    hk.add_argument("event", choices=["pre-tool"])
    pl = sub.add_parser("plugin", help="build the Crewcut plugin for Claude Code (skills, crew agents, hooks)")
    pl.add_argument("--out", help="folder to write (default: <studio>/.crewcut/plugin/crewcut)")

    pr = sub.add_parser("prompter", help="print the phone link and QR code of the teleprompter")
    pr.add_argument("episode")
    pr.add_argument("--desktop", action="store_true", help="request the approved script on the desktop's chosen screen")
    pr.add_argument("--desktop-status", metavar="ID", help="read the result of a desktop request")

    # handled by _delegate before parsing; listed here so `crewcut --help` shows it
    sub.add_parser("motion", add_help=False, help="motion graphics with EffectCraft (crewcut motion --help)")
    sub.add_parser("workspace", add_help=False, help="persistent research and coding projects")
    sub.add_parser("media", add_help=False, help="browse and import computer media through the desktop app")
    sub.add_parser("full-auto", add_help=False, help="episode automation status and assigned Critic reviews")
    return p


def _script_job_allowed(episode: str, identity: str) -> None:
    """Raise ValueError for script-step work that would run on a guess: a Writer before the test result of a format
    episode with a test plan, a Critic review of a script that still has placeholders (docs/formats.md)."""
    from . import showformats, stylegate
    try:
        pending = showformats.test_pending(episode)
    except (FileNotFoundError, ValueError):
        return
    if identity == "writer" and pending:
        raise ValueError(f"{episode}: the script waits for the test result (brief/TESTERGEBNIS-vNNN.md or "
                         "MESSKARTE-vNNN.md). Run the test plan first; the conductor starts the Writer when the result "
                         "is there (crewcut formats test <episode>).")
    if identity == "critic":
        for p in stylegate.subjects(episode):
            r = stylegate.placeholder_result(p, stylegate.fmt_of(episode, p))
            if r:
                raise ValueError(f"{episode}: {p.name} still has {r['placeholders']} placeholder(s); no Critic "
                                 "reviews a script before every number is measured. "
                                 + ("The test result is missing: run the test first." if pending else
                                    "Fill them from the test result first."))


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in DELEGATED:
        return _delegate(argv[0], argv[1:])
    if argv[:2] == ["brand", "preview"]:
        try:
            from .render import preview
        except ImportError as e:
            print(f"crewcut brand preview: the render part is not installed ({e}).", file=sys.stderr)
            return 1
        from .conductor import lanes
        with lanes.heavy("brand preview"):
            return int(preview.main(argv[2:]) or 0)
    a = build_parser().parse_args(argv)
    if a.cmd == "open":  # host side: nothing of the studio is touched
        from . import opener
        return opener.main(a.url, no_open=a.no_open, timeout=a.timeout)
    if a.cmd == "engine" and a.encmd in ("connect", "disconnect"):  # runs as the studio's owner, before any db access
        from .engines import connect
        try:
            return connect.cli_connect(a.name, a.print_token) if a.encmd == "connect" else connect.cli_disconnect(a.name)
        except ValueError as e:
            print(json.dumps({"step": "error", "text": str(e)}), flush=True)
            return 2
    if a.cmd == "engine" and a.encmd in ("auth", "api-key"):  # the key file belongs to the studio's owner, as the token
        from .engines import connect
        return (connect.cli_auth(a.mode) if a.encmd == "auth" else
                connect.cli_api_key(a.stdin, a.use, a.forget))
    try:
        code = int(_run(a) or 0)
        _deliver_news(a)
        return code
    except PermissionError as e:
        print(str(e), file=sys.stderr)
        return 3
    except (FileNotFoundError, ValueError, KeyError) as e:
        print(f"crewcut: {e}", file=sys.stderr)
        return 1


NEWS_AT = {"doing", "say", "chat"}   # frequent calls of a running crew member: new chat messages come with them


def _deliver_news(a) -> None:
    """Print the user's chat messages that reached the episode after this job started (conductor/deliver.py)."""
    jid = _job()
    if not jid or not (a.cmd in NEWS_AT or (a.cmd == "card" and getattr(a, "ccmd", None) == "propose")):
        return
    from .conductor import deliver
    try:
        msgs = deliver.take(jid)
    except Exception as e:  # noqa: BLE001 - delivery must never break the command it rides on
        print(f"crewcut: could not check for new chat messages ({type(e).__name__}).", file=sys.stderr)
        return
    msgs = [m for m in msgs if m["id"] not in getattr(a, "_shown", set())]   # `crewcut chat` printed those already
    if msgs:
        print("\n" + deliver.block(msgs), flush=True)


def _run(a) -> int:
    from . import approvals, brand, db, episodes, events, paths
    from .conductor import flow, queue
    from .engines import connect
    connect.load_stored_token()  # a Claude login made in the web UI (engine volume), unless the environment has one

    if a.cmd == "doctor":
        from . import doctor
        return doctor.main(as_json=a.json, ci=a.ci, probe=a.probe)
    if a.cmd == "serve":
        from . import config
        from .server.app import serve
        port = a.port or int(os.environ.get("CREWCUT_PORT") or config.get("crewcut", "server.port", 4747))
        pport = a.prompter_port or int(os.environ.get("CREWCUT_PROMPTER_PORT") or
                                       config.get("crewcut", "server.prompter_port", 4748))
        print(f"Crewcut {__version__} on http://localhost:{port} (teleprompter port {pport})")
        serve(a.host, port, a.prompter_host, pport)
        return 0
    if a.cmd == "episode":
        if a.ecmd == "new":
            try:
                p = episodes.create(a.title, source=a.source, kind="short" if a.short else "episode", mode=a.short,
                                    source_episode=a.from_)
            except (ValueError, FileNotFoundError) as e:
                print(f"crewcut episode new: {e}", file=sys.stderr)
                return 2
            print(p["id"])
            return 0
        if a.ecmd == "status":
            eid = a.episode or _env_episode(a) or (episodes.list_ids() or [None])[0]
            if not eid:
                print("No episodes yet.")
                return 0
            s = episodes.summary(eid)
            if a.json:
                _print({**s, "project": episodes.read(eid)}, True)
            else:
                print(f"{s['id']}  {s['title']}")
                for st in s["steps"]:
                    print(f"  {st['n']:>2} {st['label']:<10} {st['status']}")
                print(f"Next: {s.get('next_action') or '-'}")
            return 0
        if a.ecmd == "import":
            from pathlib import Path

            from . import importer
            listed = lambda v: [x.strip() for x in v.split(",") if x.strip()] if v is not None else None  # noqa: E731
            p = importer.import_episode(
                Path(a.source), a.title, fmt=a.format, script=Path(a.script) if a.script else None,
                broll=[Path(b) for b in a.broll] if a.broll else None, plan=Path(a.plan) if a.plan else None,
                skip=listed(a.skip), done=listed(a.done), start=not a.no_start)
            print(p["id"])
            for line in p.get("imported", {}).get("files", []):
                print("  " + line)
            print("  steps: " + ", ".join(f"{k} {v['status']}" for k, v in p["steps"].items()))
            return 0
        if a.ecmd == "step":
            gated = {("script", "done"): "script", ("script", "skipped"): "script", ("record", "working"): "record",
                     ("record", "waiting"): "record", ("edit", "working"): "edit"}.get((a.step, a.status))
            if gated:
                from . import stylegate
                try:
                    stylegate.guard_advance(a.episode, gated)
                except stylegate.Blocked as e:
                    print(str(e), file=sys.stderr)
                    return 3
            episodes.set_step(a.episode, a.step, a.status, next_action=a.next)
            print(f"{a.episode}: {a.step} {a.status}")
            return 0
        if a.ecmd == "refresh-cover":
            from .covers import refresh
            _print(refresh(a.episode, a.youtube_id, a.image), True)
            return 0
        if a.ecmd == "lifecycle":
            episodes.set_lifecycle(a.episode, a.lifecycle)
            print(f"{a.episode}: {a.lifecycle}. No work was started.")
            return 0
        if a.ecmd == "recording-script":
            from . import prompter
            print(json.dumps(prompter.select_script(a.episode, a.file, a.partial)))
            return 0
    if a.cmd == "interview":
        from . import interview
        p = episodes.read(a.episode)
        job = db.get("jobs", _job()) if _job() else None
        if a.ivcmd == "ask":
            if a.file:
                text = paths.inside(paths.episode_dir(a.episode), a.file).read_text(encoding="utf-8")
            elif a.text:
                text = a.text
            else:
                print("crewcut interview ask: give the questions as text or --file.", file=sys.stderr)
                return 2
            mid = interview.ask(a.episode, text, author=_identity() if _identity() != "showrunner" else "writer",
                                job=_job())
            print(f"Asked in message {mid}. The episode waits for the answers; stop now.")
            return 0
        if a.ivcmd == "answer":
            if job and job.get("kind") == "agent":
                print("Only the creator answers the interview (the chat, or a voice file dropped into it).",
                      file=sys.stderr)
                return 3
            print(interview.answer_audio(a.episode, a.audio))
            return 0
        if a.ivcmd in ("skip", "done"):
            if job and job.get("kind") == "agent":
                print("Only the creator skips or ends the interview: the button, or the words in the chat.",
                      file=sys.stderr)
                return 3
            if a.ivcmd == "skip":
                interview.skip(a.episode, "the creator, on the command line")
            elif interview.state(p).get("status") != "waiting":
                print("The interview is not waiting for answers.", file=sys.stderr)
                return 1
            else:
                interview.finish(a.episode)
            _print(interview.summary(episodes.read(a.episode)) or {"status": "none"}, True)
            return 0
        _print(interview.state(p) or {"status": "none", "enabled": interview.enabled()}, True)
        return 0
    if a.cmd == "say":
        facts = [{"label": fact.split("=", 1)[0].strip(), "value": fact.split("=", 1)[1].strip()}
                 for fact in a.fact if "=" in fact]
        channel_target = a.channel or (not a.episode and os.environ.get("CREWCUT_CONVERSATION_SCOPE") == "channel")
        if channel_target:
            if a.episode or a.to or a.preview:
                print("Channel messages cannot use --episode, --to or --preview.", file=sys.stderr)
                return 2
            flow.post("_channel", a.text, author=_identity(), cite=a.cite, job=_job(), facts=facts or None)
            return 0
        ep = _env_episode(a)
        if not ep:
            print("crewcut say: which episode? Use --episode.", file=sys.stderr)
            return 2
        if a.to:
            from . import crewtalk
            kind = a.kind or ("fix" if _identity() == "critic" else "question")
            try:
                m = crewtalk.send(ep, _identity(), a.to, kind, a.about or "", a.text,
                                  expects=a.expects or ("none" if a.reply_to else "reply"), topic=a.topic,
                                  reply_to=a.reply_to, sender_job=_job())
            except crewtalk.Refused as e:
                print(str(e), file=sys.stderr)
                return 3
            if m["route"] == "live":
                print(f"{a.to} is running now: also send it with your SendMessage tool to "
                      f"'{crewtalk.session_name(a.to, ep)}' so it sees it at once (logged as #{m['id']}).")
            elif m["route"] == "collected":
                print(f"note #{m['id']} kept for {a.to}'s next start")
            else:
                print(f"message #{m['id']} delivered: {a.to} continues its last session with it")
            return 0
        if a.preview:
            paths.inside(paths.episode_dir(ep), a.preview)
        from . import team
        unknown = [x for x in a.relay_for if team.get(x) is None]
        if unknown:
            print(f"crewcut say: no crew member called {', '.join(unknown)}.", file=sys.stderr)
            return 2
        flow.post(ep, a.text, author=_identity(), cite=a.cite, job=_job(), preview=a.preview, facts=facts or None,
                  relay_for=a.relay_for or None)
        return 0
    if a.cmd == "doing":
        jid = _job()
        if jid:
            queue.set_doing(jid, a.text, a.progress)
        else:
            events.emit("activity", episode=_env_episode(a), identity=_identity(), text=a.text)
        return 0
    if a.cmd == "chat":
        if a.channel and a.episode:
            print("Choose --channel or --episode.", file=sys.stderr)
            return 2
        ep = "_channel" if a.channel or (not a.episode and os.environ.get("CREWCUT_CONVERSATION_SCOPE") == "channel") else _env_episode(a)
        from . import channel
        history = channel.recent(a.last) if ep == channel.TRANSPORT else flow.messages(ep)[-a.last:]
        a._shown = {m["id"] for m in history} if ep == os.environ.get("CREWCUT_EPISODE") else set()
        for m in history:
            who = "user" if m["author"] == "user" else m["author"]
            card = f" [card #{m['card']}]" if m.get("card") else ""
            print(f"{m['at']} {who}: {m['text']}{card}")
        return 0
    if a.cmd == "card":
        if a.ccmd == "propose":
            data = json.loads(a.data) if a.data else None
            if a.kind == "spend":
                print("Spend cards come from the tool that spends (crewcut compute rent, render 3d --rented).",
                      file=sys.stderr)
                return 2
            if a.kind in approvals.MOTION_KINDS:
                print("Motion cards come from their commands: crewcut motion plan --card, style-frame, promote, report.",
                      file=sys.stderr)
                return 2
            from . import humanize, spoken, stylegate, titlepairs
            from .cut import tilt
            try:
                card = approvals.propose(_env_episode(a), a.step, a.kind, a.title, body=a.body, file=a.file,
                                         options=a.option or None, data=data, identity=_identity(), preview=a.preview)
            except (humanize.Missing, spoken.Unspeakable, tilt.Tilted, stylegate.Blocked, titlepairs.Unchecked) as e:
                print(str(e), file=sys.stderr)
                return 4
            _print(card if a.json else f"card #{card['id']} is open: {card['title']}", a.json)
            return 0
        if a.ccmd == "wait":
            st = approvals.wait(a.card, timeout=a.timeout)
            print(st)
            return 0 if st == "accepted" else 3
        if a.ccmd in ("accept", "decline"):
            card = approvals.get(a.card)
            if card is None:
                print(f"No card {a.card}.", file=sys.stderr)
                return 1
            if a.ccmd == "accept":
                human = not os.environ.get("CREWCUT_IDENTITY")  # a person at the terminal, not a crew member
                if not human and card["kind"] in ("spend", "publish", "final"):
                    print("This card needs the user's button (money, publishing or the final version).",
                          file=sys.stderr)
                    return 3
                if not human and _identity() != "showrunner":
                    print("Only the Showrunner records a yes the user gave in words.", file=sys.stderr)
                    return 3
                from . import stylegate
                try:
                    approvals.decide(a.card, True, choice=a.choice,
                                     reason="accepted at the terminal" if human else "the user said so in the chat")
                except stylegate.Blocked as e:
                    print(str(e), file=sys.stderr)
                    return 3
            else:
                approvals.decide(a.card, False, reason=a.reason or None)
            print(f"card #{a.card} {a.ccmd}ed")
            return 0
        if a.ccmd == "list":
            for c in approvals.list_cards(episode=_env_episode(a), status=a.status):
                print(f"#{c['id']} {c['status']:<9} {c['kind']:<9} {c['episode'] or '-'}  {c['title']}")
            return 0
    if a.cmd == "rule":
        card = approvals.propose_rule(a.step, a.rule, a.source, episode=_env_episode(a), identity=_identity())
        print(f"card #{card['id']} is open: {card['title']}")
        return 0
    if a.cmd == "job":
        from . import stylegate
        try:
            if a.step == "edit" and a.identity != "critic" and _env_episode(a):
                stylegate.guard_advance(_env_episode(a), "edit")   # no cut of a failing script before a recording
            if a.step == "script" and _env_episode(a):
                _script_job_allowed(_env_episode(a), a.identity)   # test first, then the script; no review of a guess
            jid = queue.add(_env_episode(a), a.identity, a.step, a.task, heavy=a.heavy, parent=_job())
        except (ValueError, FileNotFoundError) as error:
            print(str(error), file=sys.stderr)
            return 3
        print(f"job #{jid} queued for {a.identity}")
        return 0
    if a.cmd == "brand":
        pack = brand.load()
        if a.bcmd == "show":
            if a.json:
                _print({"dir": str(pack.dir), "neutral": pack.is_neutral, "brand": pack.brand,
                        "edit_style": pack.edit_style, "channel": pack.channel, "thumbnail": pack.thumbnail,
                        "rules": pack.all_rules()}, True)
            else:
                print(f"Style pack: {'neutral default' if pack.is_neutral else pack.dir}")
                for r in brand.profile_rows(pack):
                    print(f"  {r['label']:<18} {r['value']}  ({r['source'] or 'no source'})")
            return 0
        if a.bcmd == "check":
            problems = brand.check(pack)
            for x in problems:
                print("ERROR " + x)
            print("ok" if not problems else f"{len(problems)} problem(s)")
            return 0 if not problems else 1
        if a.bcmd == "init":
            from pathlib import Path

            from . import importer
            fonts = {}
            for spec in a.font:
                role, _, f = spec.partition("=")
                if not f:
                    print(f"--font needs ROLE=FILE, got {spec!r}", file=sys.stderr)
                    return 2
                fonts[role.strip()] = Path(f.strip())
            d = importer.init_pack(Path(a.from_) if a.from_ else None, fonts=fonts or None,
                                   logo=Path(a.logo) if a.logo else None, accept=a.accept)
            print(f"style pack: {d}" + (" (accepted)" if a.accept else ""))
            return 0
        if a.bcmd == "voice":
            from . import voice
            if a.vcmd == "list":
                for s in voice.samples():
                    print(s.relative_to(paths.studio_root()))
                return 0
            try:
                out = voice.add(a.source)
            except voice.VoiceError as e:
                print(f"crewcut brand voice: {e}", file=sys.stderr)
                return 1
            print(f"voice sample: {out.relative_to(paths.studio_root())}")
            return 0
    if a.cmd == "style-gate":
        from pathlib import Path

        from . import stylegate
        try:
            episodes.read(a.episode)
            files = [paths.inside(paths.episode_dir(a.episode), f) if not Path(f).is_absolute() else Path(f)
                     for f in a.file] or None
        except (FileNotFoundError, ValueError) as e:
            print(f"crewcut style-gate: {e}", file=sys.stderr)
            return 2
        v = stylegate.check(a.episode, files=files)
        if a.json:
            _print(v, True)
        else:
            print(f"Style gate ({v['mode']}): {'PASS' if v['pass'] else 'BLOCK' if v['mode'] == 'block' else 'FAIL'}"
                  + (f", checker {v['checker']}" if v.get("checker") else ""))
            print(stylegate.text(v))
        if v.get("skipped"):
            print("warning: " + v["skipped"], file=sys.stderr)
        return 0 if v["pass"] else 1
    if a.cmd == "graphics-gate":
        from . import graphicsgate
        try:
            plan = _plan_path(a.plan, a.episode or os.environ.get("CREWCUT_EPISODE"))
        except (FileNotFoundError, ValueError) as e:
            print(f"crewcut graphics-gate: {e}", file=sys.stderr)
            return 2
        v = graphicsgate.check_plan(plan)
        v["mode"] = graphicsgate.settings()["mode"]
        if a.json:
            _print(v, True)
        else:
            print(f"Graphics gate ({v['mode']}): " + ("skipped" if v.get("skipped") else "PASS" if v["pass"] else
                                                      "BLOCK" if v["mode"] == "block" else "FAIL"))
            print(graphicsgate.text(v, limit=40))
        return 0 if v["pass"] else 1
    if a.cmd == "humanize":
        from . import humanize
        eid = _env_episode(a)
        if not eid:
            print("crewcut humanize: which episode? (--episode)", file=sys.stderr)
            return 2
        try:
            rec = humanize.record(paths.episode_dir(eid), a.draft, a.final, a.why)
        except (FileNotFoundError, ValueError) as e:
            print(f"crewcut humanize: {e}", file=sys.stderr)
            return 1
        _print(rec if a.json else f"humanized {a.final}: {rec['count']} change(s), mode {rec['mode']}", a.json)
        return 0
    if a.cmd == "shorts":
        from . import shorts
        if a.shcmd == "standing":
            if a.state == "on":
                if os.environ.get("CREWCUT_IDENTITY"):
                    # a crew member never switches it on itself: the user's yes on one card does
                    card = approvals.propose(_env_episode(a) or "_onboarding", "upload", "other",
                                             "Publish Shorts without asking?",
                                             body="Only Shorts, only after the Critic's Short check found 0 errors, "
                                                  "never with someone else's material, and not the first Short after "
                                                  "your style changes. Each Short goes up private first, is read back, "
                                                  "then goes public. Say \"ask me again for Shorts\" to switch it off.",
                                             data={"standing": "shorts", "button": "Publish Shorts without asking"})
                    print(f"card #{card['id']} is open: {card['title']}")
                    return 0
                approvals.grant_standing("shorts")
            elif a.state == "off":
                approvals.revoke_standing("shorts")
            print(shorts.standing_line())
            return 0
        eid = _env_episode(a)
        if a.shcmd == "table":
            for r in shorts.table():
                print("\t".join(str(r.get(k, "")) for k in shorts.TABLE_COLUMNS))
            return 0
        if not eid:
            print("crewcut shorts: which Short? (--episode)", file=sys.stderr)
            return 2
        if a.shcmd == "slot":
            print(shorts.next_slot(eid))
            return 0
        row = shorts.results(eid)
        print(f"{eid}: {row['views']} views, {row['average_view_percentage']} % watched on average")
        return 0
    if a.cmd == "skills":
        from . import extskills
        if a.skcmd == "own":
            from . import ownskills
            own = [{k: s[k] for k in ("name", "steps", "roles", "replaces", "folder", "adapter", "ok", "problem")}
                   for s in ownskills.configured()]
            if a.json:
                _print(own, True)
            else:
                for r in own:
                    print(f"{r['name']:<20} {'ok' if r['ok'] else 'NOT USABLE: ' + str(r['problem'])}  steps "
                          f"{','.join(r['steps']) or '-'}  roles {','.join(r['roles']) or 'all'}"
                          + (f"  over {','.join(r['replaces'])}" if r["replaces"] else "")
                          + ("  +adapter" if r["adapter"] else ""))
                if not own:
                    print("No own skills. Put them in <studio>/skills/<name>/SKILL.md and name them under "
                          "[[skills.own]] in config/crewcut.toml (docs/own-skills.md).")
            return 0
        if a.skcmd == "update":
            for r in extskills.update(a.name):
                print(f"{r['name']}: {r['current'] or 'not installed'}" + (" (new)" if r["changed"] else "")
                      + "".join(f"\n  {n}" for n in r["notes"]))
            return 0
        rows = []
        for s in extskills.configured():
            cur = extskills.current(s["name"])
            rows.append({"name": s["name"], "repo": s["repo"], "license": s.get("license"),
                         "version": cur["version"] if cur else None, "steps": s.get("steps") or []})
        if a.json:
            _print(rows, True)
        else:
            for r in rows:
                print(f"{r['name']:<12} {r['version'] or 'not installed':<10} github.com/{r['repo']} ({r['license']})")
        return 0
    if a.cmd == "onboard":
        from .onboarding import fetch
        facts = fetch.gather(a.links)
        out = approvals.ensure_user_pack() / "fetched.json"
        out.write_text(json.dumps(facts, ensure_ascii=False, indent=1), encoding="utf-8")
        _print(facts if a.json else fetch.summary(facts) + f"\nSaved: {out}", a.json)
        return 0
    if a.cmd == "thumbnail":
        if a.tcmd == "formats":
            from .thumbnail import formats
            return formats.cli(a)
        if a.tcmd == "set":
            from .thumbnail import variety
            return variety.cli(a)
        if a.tcmd == "face":
            from .thumbnail import identity
            return identity.cli(a)
        from .thumbnail import make
        return make.cli(a)
    if a.cmd == "youtube":
        from .youtube import cli as ycli
        return ycli.main(a)
    if a.cmd == "retention":
        from .youtube import units
        return units.main(a)
    if a.cmd == "engine":
        from . import engines
        if a.encmd == "status":
            rows = []
            for key in engines.ENGINES:
                e = engines.get(key)
                ok, why = e.login_status() if e.installed() or key == "claude" else (False, "not installed")
                from .engines import versions
                rows.append({"engine": key, "label": e.label, "beta": e.beta, "chosen": key == engines.current_name(),
                             "installed": e.installed(), "logged_in": ok, "detail": why, **versions.status(key)})
            if a.json:
                _print(rows, True)
            else:
                for r in rows:
                    print(f"{'*' if r['chosen'] else ' '} {r['label']:<12}{' beta' if r['beta'] else '     '} "
                          f"version: {r['current'] or '-'} (channel {r['channel']}, last good {r['last_good'] or '-'})"
                          f"  login: {r['detail']}")
            return 0
        if a.encmd == "use":
            e = engines.use(a.name)
            if not e.installed():
                print(f"Installing {e.label}...")
                ok, out = e.install()
                if not ok:
                    print(f"Could not install {e.label}: {out}")
                    return 1
            ok, why = e.login_status()
            print(f"New work runs on {e.label}{' (beta)' if e.beta else ''}. Login: {why}")
            return 0 if ok else 4
        if a.encmd == "update":
            from .engines import versions
            name = engines.normalize(a.name) if a.name else engines.current_name()
            res = versions.update(name, a.channel, with_login=not a.no_login_test)
            print(f"{name}: " + (f"now on {res['current']}" if res["changed"] else f"stays on {res['current']}"))
            for n in res["notes"]:
                print("  " + n)
            return 0
        if a.encmd == "rollback":
            from .engines import versions
            name = engines.normalize(a.name) if a.name else engines.current_name()
            msg = versions.rollback(name)
            print(msg or "No earlier good version to go back to.")
            return 0 if msg else 1
        if a.encmd == "install":
            e = engines.get(a.name)
            ok, out = e.install()
            print(f"{e.label}: " + ("installed" if ok else f"install failed: {out}"))
            return 0 if ok else 1
        if a.encmd == "login":
            import subprocess
            e = engines.get(a.name)
            chat = a.episode or _env_episode(a) or flow.ONBOARDING
            if not e.installed():
                ok, out = e.install()
                if not ok:
                    print(f"Could not install {e.label}: {out}")
                    return 1
            log = open(paths.logs_dir() / f"engine-login-{e.name}.log", "a", encoding="utf-8")
            subprocess.Popen([sys.executable, "-m", "crewcut.engines.login_bg", e.name, chat], stdout=log,
                             stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
            print(f"The {e.label} login link and code will appear in the chat in a few seconds.")
            return 0
    if a.cmd == "crew":
        from . import crewtalk
        if a.state in ("on", "off"):
            crewtalk.set_enabled(a.state == "on")
        st = crewtalk.settings()
        print(f"crew talk: {'on' if st['enabled'] else 'off'} (at most {st['max_rounds']} rounds per topic, "
              f"{st['max_fix_rounds']} fix rounds, {st['max_per_episode']} messages per episode)")
        return 0
    if a.cmd == "hook":
        from . import plugin
        try:
            payload = json.loads(sys.stdin.read() or "{}")
        except ValueError:
            return 0
        ok, reason = plugin.guard_decision(payload, os.environ.get("CREWCUT_IDENTITY"))
        if not ok:
            print(reason, file=sys.stderr)
            return 2  # Claude Code blocks the tool call and shows the reason to the agent
        return 0
    if a.cmd == "plugin":
        from pathlib import Path

        from . import plugin
        print(plugin.build(Path(a.out) if a.out else None))
        return 0
    if a.cmd == "prompter":
        if a.desktop or a.desktop_status:
            from . import desktop_prompter
            try:
                result = desktop_prompter.status(a.desktop_status) if a.desktop_status else desktop_prompter.request_open(a.episode)
                print(json.dumps(result))
                return 0 if result.get("status") != "failed" else 1
            except (ValueError, FileNotFoundError) as error:
                print(str(error), file=sys.stderr)
                return 1
        from . import prompter
        url = prompter.url_for(a.episode)
        print(url)
        print(prompter.terminal_qr(url))
        return 0
    _ = db
    return 2


if __name__ == "__main__":
    sys.exit(main())
