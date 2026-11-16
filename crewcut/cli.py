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
    "compute": ("crewcut.compute.cli", False),
    "render": ("crewcut.render.cli", True),
    "ingest": ("crewcut.cut.cli", True),
    "transcribe": ("crewcut.cut.cli", True),
    "cut": ("crewcut.cut.cli", True),
}
HEAVY = {"render": {"2d", "3d", "probe", "cut", "all"}, "transcribe": None,
         "cut": {"build", "grade", "islands", "probe", "verify", "doubles", "takes"}}


def _env_episode(a) -> str | None:
    return getattr(a, "episode", None) or os.environ.get("CREWCUT_EPISODE") or None


def _identity() -> str:
    return os.environ.get("CREWCUT_IDENTITY") or "showrunner"


def _job() -> int | None:
    j = os.environ.get("CREWCUT_JOB", "")
    return int(j) if j.isdigit() else None


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
    es = esub.add_parser("status")
    es.add_argument("episode", nargs="?")
    es.add_argument("--json", action="store_true")
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

    sy = sub.add_parser("say", help="a message in the main chat, from the running crew member")
    sy.add_argument("--episode")
    sy.add_argument("--cite", help="one short line: the method and its source")
    sy.add_argument("--preview", help="a video or image in the episode to show under the message")
    sy.add_argument("--fact", action="append", default=[], help='a row of a small table: "Loudness=-14.1 LUFS"')
    sy.add_argument("text")

    dg = sub.add_parser("doing", help="what the running crew member does right now (Crew column)")
    dg.add_argument("--episode")
    dg.add_argument("--progress", type=float)
    dg.add_argument("text")

    ch = sub.add_parser("chat", help="print the recent chat of an episode")
    ch.add_argument("--episode")
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

    y = sub.add_parser("youtube", help="YouTube Data API: sign in, upload, status")
    ysub = y.add_subparsers(dest="ycmd", required=True)
    ysub.add_parser("auth")
    yu = ysub.add_parser("upload")
    yu.add_argument("--episode")
    yu.add_argument("--package", help="upload package JSON, default export/upload.json")
    yu.add_argument("--schedule", help="ISO time to publish; without it the video stays private")
    yu.add_argument("--dry-run", action="store_true")
    ysub.add_parser("status")

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
    enl = ensub.add_parser("login", help="Codex: device-code login, the link and code appear in the chat")
    enl.add_argument("name")
    enl.add_argument("--episode", help="which chat gets the link (default: the onboarding chat)")

    hk = sub.add_parser("hook", help="hooks that Claude Code calls (from the Crewcut plugin)")
    hk.add_argument("event", choices=["pre-tool"])
    pl = sub.add_parser("plugin", help="build the Crewcut plugin for Claude Code (skills, crew agents, hooks)")
    pl.add_argument("--out", help="folder to write (default: <studio>/.crewcut/plugin/crewcut)")

    pr = sub.add_parser("prompter", help="print the phone link and QR code of the teleprompter")
    pr.add_argument("episode")
    return p


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
    try:
        return int(_run(a) or 0)
    except PermissionError as e:
        print(str(e), file=sys.stderr)
        return 3
    except (FileNotFoundError, ValueError, KeyError) as e:
        print(f"crewcut: {e}", file=sys.stderr)
        return 1


def _run(a) -> int:
    from . import approvals, brand, db, episodes, events, paths
    from .conductor import flow, queue

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
            p = episodes.create(a.title, source=a.source)
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
            episodes.set_step(a.episode, a.step, a.status, next_action=a.next)
            print(f"{a.episode}: {a.step} {a.status}")
            return 0
    if a.cmd == "say":
        ep = _env_episode(a)
        if not ep:
            print("crewcut say: which episode? Use --episode.", file=sys.stderr)
            return 2
        facts = [{"label": f.split("=", 1)[0].strip(), "value": f.split("=", 1)[1].strip()} for f in a.fact if "=" in f]
        if a.preview:
            paths.inside(paths.episode_dir(ep), a.preview)
        flow.post(ep, a.text, author=_identity(), cite=a.cite, job=_job(), preview=a.preview, facts=facts or None)
        return 0
    if a.cmd == "doing":
        jid = _job()
        if jid:
            queue.set_doing(jid, a.text, a.progress)
        else:
            events.emit("activity", episode=_env_episode(a), identity=_identity(), text=a.text)
        return 0
    if a.cmd == "chat":
        ep = _env_episode(a)
        for m in flow.messages(ep)[-a.last:]:
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
            card = approvals.propose(_env_episode(a), a.step, a.kind, a.title, body=a.body, file=a.file,
                                     options=a.option or None, data=data, identity=_identity(), preview=a.preview)
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
                approvals.decide(a.card, True, choice=a.choice,
                                 reason="accepted at the terminal" if human else "the user said so in the chat")
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
        jid = queue.add(_env_episode(a), a.identity, a.step, a.task, heavy=a.heavy, parent=_job())
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
    if a.cmd == "onboard":
        from .onboarding import fetch
        facts = fetch.gather(a.links)
        out = approvals.ensure_user_pack() / "fetched.json"
        out.write_text(json.dumps(facts, ensure_ascii=False, indent=1), encoding="utf-8")
        _print(facts if a.json else fetch.summary(facts) + f"\nSaved: {out}", a.json)
        return 0
    if a.cmd == "thumbnail":
        from .thumbnail import make
        return make.cli(a)
    if a.cmd == "youtube":
        from .youtube import cli as ycli
        return ycli.main(a)
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
        from . import prompter
        url = prompter.url_for(a.episode)
        print(url)
        print(prompter.terminal_qr(url))
        return 0
    _ = db
    return 2


if __name__ == "__main__":
    sys.exit(main())
