"""`crewcut doctor`: what is there, what is missing, what to do. Runs at every container start."""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys

from . import __version__, brand, db, engines, paths, team

OK, NOTE, WARN, ERROR = "ok", "note", "warn", "error"


def _run(cmd: list[str], timeout: int = 20) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return (r.stdout or r.stderr).strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def _first_line(s: str) -> str:
    return s.splitlines()[0][:100] if s else ""


def read_pin() -> dict:
    """The EffectCraft pin of this app: upstream commit and the number of patch files (third_party/effectcraft)."""
    root = paths.app_root() / "third_party" / "effectcraft"
    out = {"commit": "", "patches": 0}
    try:
        for line in (root / "PIN").read_text(encoding="utf-8").splitlines():
            k, _, v = line.partition(" ")
            if k in ("commit", "sha256"):
                out[k] = v.strip()
    except OSError:
        return out
    out["patches"] = len(list((root / "patches").glob("*.patch")))
    return out


def motion_engine_status() -> tuple[str, str, str]:
    """(status, detail, fix) for the motion engine line. Without the binary only `kind: "motion"` inserts fail."""
    exe = os.environ.get("EFFECTCRAFT_CLI") or shutil.which("effectcraft-cli")
    pin = read_pin()
    pin_txt = f"pin {pin['commit'][:12] or '?'}, patches {pin['patches']}"
    if not exe or not os.path.isfile(exe):
        return (NOTE, f"effectcraft-cli missing ({pin_txt}): motion graphics inserts cannot render here; "
                "everything else works", "Use the Crewcut image, or set render.location = rented in config/crewcut.toml.")
    version = ""
    raw = _run([exe, "--empty", "info", "--json"], 30)
    try:
        info = json.loads(raw) if raw.startswith("{") else {}
        version = str(info.get("version") or info.get("engine", {}).get("version") or "")
    except ValueError:
        info = {}
    if not raw:
        return (WARN, f"effectcraft-cli at {exe} does not start ({pin_txt})", "Rebuild the image.")
    return (OK, f"effectcraft-cli {version or '(version not reported)'}, {pin_txt}", "")


def checks(ci: bool = False, probe: bool = False) -> list[dict]:
    out: list[dict] = []

    def add(status: str, name: str, detail: str, fix: str = "") -> None:
        out.append({"status": status, "name": name, "detail": detail, "fix": fix})

    add(OK, "crewcut", f"{__version__} on Python {platform.python_version()}, {platform.machine()}")

    # app files
    skills = sorted(p.parent.name for p in paths.skills_dir().glob("*/SKILL.md"))
    add(OK if skills else ERROR, "skills", f"{len(skills)} skills: {', '.join(skills)}" if skills else "none found",
        "" if skills else "The image is incomplete; rebuild it.")
    crew = team.all_identities()
    add(OK if len(crew) >= 7 else ERROR, "crew", f"{len(crew)} identities: {', '.join(x['id'] for x in crew)}")
    t2 = sorted(p.stem for p in (paths.templates_dir() / "2d").glob("*.html"))
    t3 = sorted(p.stem for p in (paths.templates_dir() / "3d").glob("*.py") if p.stem != "stage")
    add(OK if t2 else WARN, "2D scenes", ", ".join(t2) or "none")
    add(OK if t3 else WARN, "3D scenes", ", ".join(t3) or "none")
    web = (paths.web_dist_dir() / "index.html").is_file()
    add(OK if web else (NOTE if ci else WARN), "web UI", "built" if web else "not built",
        "" if web else "Build it: cd web && npm ci && npm run build")

    # style pack
    pack = brand.load()
    problems = brand.check(pack)
    add(OK if not problems else ERROR, "style pack",
        ("neutral default" if pack.is_neutral else f"user pack in {pack.dir.name}/") +
        ("" if not problems else ": " + "; ".join(problems)))

    # programs
    for prog, why in (("ffmpeg", "cut, sound, encoding"), ("ffprobe", "media checks"), ("node", "2D renderer"),
                      ("rsync", "rented GPUs"), ("ssh", "rented GPUs")):
        path = shutil.which(prog)
        ver = _first_line(_run([prog, "-version" if prog.startswith("ff") else "--version"])) if path else ""
        add(OK if path else (WARN if prog in ("rsync", "ssh") else ERROR), prog, ver or ("missing: " + why))
    chromium = os.environ.get("CHROMIUM_PATH") or shutil.which("chromium") or shutil.which("chromium-browser")
    pw = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    has_pw = bool(pw and os.path.isdir(pw) and any(n.startswith("chromium") for n in os.listdir(pw)))
    add(OK if chromium or has_pw else ERROR, "chromium", chromium or (f"Playwright browsers in {pw}" if has_pw else
        "missing: 2D graphics need it"))
    blender = shutil.which("blender")
    if blender:
        add(OK, "blender", _first_line(_run([blender, "--version"], 60)) or blender)
    elif platform.machine() in ("aarch64", "arm64"):
        add(NOTE, "blender", "not in the arm64 image (no official Linux arm64 build). 3D runs on a rented GPU; "
            "the bridge to Blender on the Mac itself is planned.")
    else:
        add(WARN, "blender", "missing: 3D scenes only on a rented GPU")
    st_motion, detail_motion, fix_motion = motion_engine_status()
    add(st_motion, "motion engine", detail_motion, fix_motion)
    fonts = _run(["fc-list", ":family"], 20)
    add(OK if "Inter" in fonts else WARN, "font Inter", "installed" if "Inter" in fonts else "missing (neutral pack)")
    try:
        import faster_whisper  # noqa: F401
        add(OK, "speech recognition", "faster-whisper")
    except ImportError:
        add(WARN, "speech recognition", "faster-whisper missing: transcription only on a rented GPU")

    # engine: the one the user chose (Claude Code by default, Codex beta)
    eng = engines.current()
    other = engines.get("codex" if eng.name == "claude" else "claude")
    tag = " (beta)" if eng.beta else ""
    from .engines import versions
    vs = versions.status(eng.name)
    add(OK if vs["current"] else NOTE, "engine version",
        f"{vs['current'] or 'none yet'} (channel {vs['channel']}, last good {vs['last_good'] or '-'}"
        + (f", skipped as broken: {', '.join(vs['bad'])}" if vs["bad"] else "") + ")")
    from . import extskills, voice
    for s in extskills.configured():
        cur = extskills.current(s["name"])
        add(OK if cur else NOTE, f"skill {s['name']}",
            f"{cur['version']} from github.com/{s['repo']} ({s.get('license')})" if cur else
            f"not installed yet (github.com/{s['repo']}); the container fetches the newest version at start",
            "" if cur else "Run `crewcut skills update` when the machine is online.")
    if extskills.humanizer_enabled():
        n = len(voice.samples())
        add(OK if n else NOTE, "voice sample", f"{n} of your own videos in brand/voice/" if n else
            "none yet: the Humanizer pass runs without your spoken words",
            "" if n else "Say \"use my video <link> as voice sample\" or run `crewcut brand voice add <link>`.")
    if not eng.installed():
        add(NOTE if ci else ERROR, f"engine {eng.label}{tag}", "not installed yet",
            "The container installs Claude Code at the first start; Codex when you say \"use Codex\". "
            "Or run `crewcut engine install " + eng.name + "`.")
    else:
        add(OK, f"engine {eng.label}{tag}", _first_line(_run([eng.binary(), "--version"])) or eng.binary())
    ok, why = eng.login_status() if eng.installed() or eng.name == "claude" else (False, "not installed")
    if not ok:
        fix = ("Run `claude setup-token` once on a computer with a browser, put the value into .env, restart."
               if eng.name == "claude" else "Say \"use Codex\" in the chat or run `crewcut engine login codex`.")
        add(NOTE if ci else ERROR, "engine login", why, fix)
    else:
        add(OK, "engine login", why)
        cred = os.path.expanduser("~/.claude/.credentials.json")
        if eng.name == "claude" and os.environ.get("CLAUDE_CODE_OAUTH_TOKEN") and os.path.exists(cred):
            add(WARN, "old credentials", "~/.claude/.credentials.json exists and can hide the token",
                "Remove that file or do not mount an old ~/.claude into the container.")
        if probe:
            pok, detail = eng.probe()
            db.kv_set("engine_probe", json.dumps({"ok": pok, "engine": eng.name, "detail": detail, "at": db.now()}))
            add(OK if pok else ERROR, "engine probe", detail,
                "" if pok else ("Make a new token with `claude setup-token`; some containers reject old ones (401)."
                                if eng.name == "claude" else "Log in to Codex again: `crewcut engine login codex`."))
    add(NOTE, "other engine", f"{other.label}{' (beta)' if other.beta else ''}: "
        + ("installed" if other.installed() else "not installed") + "; say \"use " + other.label + "\" to switch")

    # the user's own Claude Code settings in <studio>/.claude: hooks or MCP servers that call missing programs
    user_settings = paths.studio_root() / ".claude" / "settings.json"
    if user_settings.is_file():
        try:
            st = json.loads(user_settings.read_text(encoding="utf-8"))
        except ValueError:
            st = {}
            add(WARN, "your Claude settings", ".claude/settings.json is not valid JSON")
        missing = set()
        for groups in (st.get("hooks") or {}).values():
            for g in groups or []:
                for h in g.get("hooks") or []:
                    exe = str(h.get("command", "")).split()[:1]
                    if exe and not exe[0].startswith("$") and not shutil.which(exe[0]) and not os.path.exists(exe[0]):
                        missing.add(exe[0])
        add(WARN if missing else OK, "your Claude settings",
            ("hooks call programs this container does not have: " + ", ".join(sorted(missing))) if missing else
            "in use (.claude/ in the studio folder)")

    # GPU, keys, disk
    smi = _first_line(_run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"])) \
        if shutil.which("nvidia-smi") else ""
    add(OK if smi else NOTE, "local GPU", smi or "none: heavy work runs on the CPU here, or on a rented GPU")
    add(OK if os.environ.get("VAST_API_KEY") else NOTE, "rented GPUs",
        "Vast.ai key present" if os.environ.get("VAST_API_KEY") else "no Vast.ai key: everything runs locally")
    yt = paths.studio_root() / "config" / "youtube-client.json"
    add(OK if yt.is_file() else NOTE, "YouTube", "client file present" if yt.is_file() else
        "not connected yet; say \"connect YouTube\" (Claude in Chrome sets it up) or follow docs/youtube.md")
    if not yt.is_file():
        from .youtube import connect
        blocker = connect.why_not()
        add(OK if not blocker else NOTE, "YouTube setup through Chrome", "ready: helper, Claude Code and Chrome found"
            if not blocker else blocker)
    try:
        st = shutil.disk_usage(paths.studio_root() if paths.studio_root().exists() else os.getcwd())
        free_gb = st.free / 1e9
        add(OK if free_gb > 20 else WARN, "disk", f"{free_gb:.0f} GB free in the studio folder")
    except OSError as e:
        add(ERROR, "studio folder", str(e))
    try:
        t = paths.state_dir() / ".write-test"
        t.write_text("ok")
        t.unlink()
        add(OK, "studio folder", f"{paths.studio_root()} is writable")
    except OSError as e:
        add(ERROR, "studio folder", f"not writable: {e}", "Mount a folder you own at /studio.")
    return out


def main(as_json: bool = False, ci: bool = False, probe: bool = False) -> int:
    res = checks(ci=ci, probe=probe)
    errors = [r for r in res if r["status"] == ERROR]
    if as_json:
        print(json.dumps({"ok": not errors, "checks": res}, indent=1))
    else:
        for r in res:
            mark = {"ok": "  ok  ", "note": " note ", "warn": " WARN ", "error": "ERROR "}[r["status"]]
            print(f"{mark} {r['name']:<20} {r['detail']}")
            if r["fix"] and r["status"] != OK:
                print(f"{'':7}{'':21}-> {r['fix']}")
        print("doctor: " + ("all good" if not errors else f"{len(errors)} problem(s) to fix"))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main(as_json="--json" in sys.argv, ci="--ci" in sys.argv, probe="--probe" in sys.argv))
