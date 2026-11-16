"""Always the newest engine, with a way back.

Every version lives in its own folder (`/opt/engine/versions/<engine>/<version>/`); a link
`/opt/engine/current/<engine>` points at the active one, so switching and rolling back are one atomic link swap.
At start (and once a day when no job runs) Crewcut asks npm for the newest version on the chosen channel, installs it
next to the current one, runs a short smoke test, and only then switches. A version that fails the smoke test is not
used. If two jobs in a row fail with an engine error right after a switch, Crewcut goes back to the last version that
passed (`last_good`) and says so. Claude Code never updates itself in the middle of a run (DISABLE_AUTOUPDATER=1);
Crewcut does the swap between jobs.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from collections.abc import Callable
from pathlib import Path

PACKAGES = {"claude": "@anthropic-ai/claude-code", "codex": "@openai/codex"}
BINARIES = {"claude": "claude", "codex": "codex"}
REQUIRED_FLAGS = {"claude": ["--output-format", "--verbose", "--append-system-prompt", "--resume"],
                  "codex": ["exec"]}
ENGINE_ERROR = re.compile(r"(unknown option|unknown argument|unrecognized (option|argument)|cannot find module|"
                          r"syntaxerror|segmentation fault|command not found|is not a function|unexpected token|"
                          r"invalid value for '--|error: option)", re.I)

Runner = Callable[[list[str], int], tuple[int, str]]


def _run(cmd: list[str], timeout: int = 60) -> tuple[int, str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except (OSError, subprocess.TimeoutExpired) as e:
        return 124, f"{type(e).__name__}: {e}"


def prefix() -> Path:
    return Path(os.environ.get("CREWCUT_ENGINE_PREFIX", "/opt/engine"))


def state_path() -> Path:
    return prefix() / "state.json"


def read_state() -> dict:
    try:
        return json.loads(state_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def write_state(s: dict) -> None:
    p = state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(s, indent=1), encoding="utf-8")
    tmp.replace(p)


def version_dir(engine: str, version: str) -> Path:
    return prefix() / "versions" / engine / version


def current_link(engine: str) -> Path:
    return prefix() / "current" / engine


def current_version(engine: str) -> str | None:
    link = current_link(engine)
    if link.is_symlink():
        return Path(os.readlink(link)).name
    return read_state().get(engine, {}).get("current")


def installed(engine: str) -> list[str]:
    d = prefix() / "versions" / engine
    return sorted((p.name for p in d.iterdir() if (p / "bin" / BINARIES[engine]).exists()), key=_vkey) \
        if d.is_dir() else []


def _vkey(v: str) -> tuple:
    return tuple(int(x) if x.isdigit() else 0 for x in re.split(r"[.\-+]", v))


def channel(engine: str) -> str:
    from .. import config
    return str(config.get("crewcut", f"engine.{engine}.channel", "latest") or "latest")


def latest_version(engine: str, chan: str | None = None, run: Runner = _run) -> str | None:
    """The version behind a channel ("latest", "stable") or a fixed version. None when npm cannot answer (offline)."""
    chan = chan or channel(engine)
    if re.fullmatch(r"\d+\.\d+\.\d+.*", chan):
        return chan
    code, out = run(["npm", "view", f"{PACKAGES[engine]}@{chan}", "version"], 20)
    v = out.strip().splitlines()[-1].strip() if code == 0 and out.strip() else ""
    return v if re.fullmatch(r"\d+\.\d+\.\d+[\w.\-+]*", v) else None


def install(engine: str, version: str, run: Runner = _run) -> tuple[bool, str]:
    d = version_dir(engine, version)
    if (d / "bin" / BINARIES[engine]).exists():
        return True, "already installed"
    d.mkdir(parents=True, exist_ok=True)
    code, out = run(["npm", "install", "-g", "--prefix", str(d), "--no-audit", "--no-fund",
                     f"{PACKAGES[engine]}@{version}"], 900)
    ok = code == 0 and (d / "bin" / BINARIES[engine]).exists()
    if not ok:
        shutil.rmtree(d, ignore_errors=True)
    return ok, out.strip()[-400:]


def switch(engine: str, version: str) -> None:
    """Point `current/<engine>` at a version, atomically."""
    link = current_link(engine)
    link.parent.mkdir(parents=True, exist_ok=True)
    tmp = link.with_name(f".{engine}.tmp")
    if tmp.is_symlink() or tmp.exists():
        tmp.unlink()
    tmp.symlink_to(version_dir(engine, version))
    os.replace(tmp, link)
    s = read_state()
    e = s.setdefault(engine, {})
    e.update(current=version, switched_at=time.time(), engine_failures=0)
    write_state(s)


def smoke(engine: str, version: str, run: Runner = _run, with_login: bool = True) -> tuple[bool, list[str]]:
    """Short test of a version: it starts, knows the flags Crewcut needs and, with a login, answers one tiny call."""
    exe = str(version_dir(engine, version) / "bin" / BINARIES[engine])
    notes = []
    code, out = run([exe, "--version"], 30)
    if code != 0:
        return False, [f"--version failed: {out[-200:]}"]
    notes.append("version: " + out.strip().splitlines()[0][:60])
    code, out = run([exe, "--help"], 30)
    missing = [f for f in REQUIRED_FLAGS[engine] if f not in out]
    if missing:
        return False, notes + [f"help lacks {', '.join(missing)}"]
    notes.append("flags: ok")
    if with_login and engine == "claude" and (os.environ.get("CLAUDE_CODE_OAUTH_TOKEN") or
                                              os.environ.get("ANTHROPIC_API_KEY")):
        code, out = run([exe, "-p", "Reply with the single word: ok", "--output-format", "stream-json", "--verbose"],
                        180)
        kinds = set()
        session = False
        for line in out.splitlines():
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            kinds.add(ev.get("type"))
            session = session or bool(ev.get("session_id"))
        if code != 0 or not {"assistant", "result"} <= kinds or not session:
            return False, notes + [f"stream test failed (exit {code}, events {sorted(k for k in kinds if k)})"]
        notes.append("stream: ok")
    return True, notes


def update(engine: str, chan: str | None = None, run: Runner = _run, with_login: bool = True) -> dict:
    """Bring the newest version of the channel in, if it passes the smoke test. Never removes the current one."""
    s = read_state().get(engine, {})
    cur = current_version(engine)
    want = latest_version(engine, chan, run)
    result = {"engine": engine, "current": cur, "wanted": want, "changed": False, "notes": []}
    if want is None:
        result["notes"].append("npm did not answer (offline?): keeping " + (cur or "nothing"))
        return result
    if want == cur:
        result["notes"].append("already on the newest version")
        return result
    if want in (s.get("bad") or []) and not (chan and re.fullmatch(r"\d+\.\d+\.\d+.*", chan)):
        result["notes"].append(f"{want} failed before; staying on {cur}")
        return result
    ok, out = install(engine, want, run)
    if not ok:
        result["notes"].append(f"install of {want} failed: {out}")
        return result
    passed, notes = smoke(engine, want, run, with_login)
    result["notes"] += notes
    st = read_state()
    e = st.setdefault(engine, {})
    if not passed:
        e["bad"] = sorted(set((e.get("bad") or []) + [want]))
        write_state(st)
        result["notes"].append(f"{want} failed the smoke test; staying on {cur}")
        return result
    if cur:
        e["previous"] = cur
    write_state(st)
    switch(engine, want)
    st = read_state()
    st[engine]["last_good"] = want
    st[engine]["checked_at"] = time.time()
    write_state(st)
    result.update(changed=True, current=want)
    return result


def note_job(engine: str, ok: bool, error: str = "", exit_code: int = 0) -> str | None:
    """Count engine failures after a switch. Two in a row: roll back. Returns a sentence for the user, or None."""
    st = read_state()
    e = st.setdefault(engine, {})
    if ok:
        e["engine_failures"] = 0
        write_state(st)
        return None
    if exit_code in (4,) or not (exit_code == 127 or ENGINE_ERROR.search(error or "")):
        return None  # a content or login problem, not the engine
    e["engine_failures"] = int(e.get("engine_failures") or 0) + 1
    write_state(st)
    if e["engine_failures"] >= 2:
        return rollback(engine)
    return None


def rollback(engine: str) -> str | None:
    st = read_state()
    e = st.get(engine, {})
    cur = current_version(engine)
    back = e.get("previous") if e.get("previous") and e.get("previous") != cur else None
    back = back or (e.get("last_good") if e.get("last_good") != cur else None)
    if not back or not (version_dir(engine, back) / "bin" / BINARIES[engine]).exists():
        return None
    switch(engine, back)
    st = read_state()
    st[engine]["bad"] = sorted(set((st[engine].get("bad") or []) + ([cur] if cur else [])))
    st[engine]["last_good"] = back
    write_state(st)
    label = "Claude Code" if engine == "claude" else "Codex"
    return f"{label} {cur} failed twice. Back on {back}. I will try a newer one again tomorrow."


def due(engine: str, every_s: int = 86400) -> bool:
    return time.time() - float(read_state().get(engine, {}).get("checked_at") or 0) > every_s


def status(engine: str) -> dict:
    e = read_state().get(engine, {})
    return {"engine": engine, "channel": channel(engine), "current": current_version(engine),
            "last_good": e.get("last_good"), "installed": installed(engine), "bad": e.get("bad") or []}
