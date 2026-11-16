"""One interface for the two engines Crewcut supports, both on the user's own subscription:
Claude Code (primary) and Codex (beta).

An engine starts a task (prompt, house rules, skills, working folder), streams events (step, tool, text, usage, session),
can be stopped, and can resume an earlier session. Secrets never appear in arguments or logs.
"""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

SECRET_ENV = ("CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_API_KEY", "CODEX_API_KEY", "VAST_API_KEY", "OPENAI_API_KEY",
              "GEMINI_API_KEY", "YOUTUBE_API_KEY", "CREWCUT_HOST_TOKEN")
# Values the crew never gets in its environment: the host helper's key signs requests only from Crewcut's own server.
SERVER_ONLY_ENV = ("CREWCUT_HOST_TOKEN",)
_PATTERNS = [
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{12,}"),
    re.compile(r"sk-[A-Za-z0-9_\-]{20,}"),
    re.compile(r"eyJ[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"),  # JWT-shaped access tokens
    re.compile(r"(?i)(authorization:\s*bearer\s+)[^\s\"']+"),
    re.compile(r"(?i)(\"(?:access_token|refresh_token|id_token)\"\s*:\s*\")[^\"]+"),
    re.compile(r"((?:CLAUDE_CODE_OAUTH_TOKEN|ANTHROPIC_API_KEY|CODEX_API_KEY|VAST_API_KEY|OPENAI_API_KEY|"
               r"GEMINI_API_KEY|YOUTUBE_API_KEY|CONTAINER_API_KEY)=)[^\s\"']+"),
]


def scrub(text: str) -> str:
    """Remove secrets from a text before it is logged or shown."""
    for name in SECRET_ENV:
        v = os.environ.get(name)
        if v and len(v) >= 8:
            text = text.replace(v, "[removed]")
    for p in _PATTERNS:
        text = p.sub(lambda m: (m.group(1) if m.re.groups else "") + "[removed]", text)
    return text


@dataclass
class Task:
    prompt: str
    system: str                    # what changes per job: house rules, episode state, step (not the identity)
    cwd: Path
    env: dict[str, str] = field(default_factory=dict)
    model: str | None = None       # empty = the engine's own default for the user's plan
    skills: list[Path] = field(default_factory=list)
    resume: str | None = None
    timeout_s: int = 3600
    log_path: Path | None = None
    extra_dirs: list[str] = field(default_factory=list)
    agent: str | None = None       # the crew member this run starts as (a real engine agent where the engine has them)
    effort: str | None = None      # passed through as --effort; empty = engine default
    extra_args: list[str] = field(default_factory=list)   # passed through unchanged, after Crewcut's own flags
    name: str | None = None        # a readable session name
    engine_options: dict = field(default_factory=dict)    # anything only one engine understands


@dataclass
class Event:
    kind: str          # step | tool | text | usage | session | error | result
    text: str = ""
    data: dict = field(default_factory=dict)


@dataclass
class RunResult:
    ok: bool
    exit_code: int
    text: str = ""
    cost_usd: float = 0.0          # API equivalent where the engine reports it (Claude Code); never real money here
    usage: dict = field(default_factory=dict)
    session: str | None = None     # resume id
    turns: int = 0
    seconds: float = 0.0
    error: str = ""
    timed_out: bool = False


class Engine:
    """Base class. Subclasses set name/label/beta and implement command(), parse() and the login checks."""

    name = "base"
    label = "Engine"
    beta = False
    binary_name = ""
    npm_package = ""

    # ---- what a subclass provides ------------------------------------------------------------------------------
    def command(self, task: Task) -> list[str]:
        raise NotImplementedError

    def parse(self, obj: dict, state: dict) -> list[Event]:
        raise NotImplementedError

    def login_status(self) -> tuple[bool, str]:
        raise NotImplementedError

    def probe(self, timeout_s: int = 120) -> tuple[bool, str]:
        raise NotImplementedError

    def env(self) -> dict[str, str]:
        return {}

    # ---- shared ---------------------------------------------------------------------------------------------------
    def binary(self) -> str | None:
        import shutil
        return shutil.which(self.binary_name)

    def installed(self) -> bool:
        return self.binary() is not None

    def install(self, version: str | None = None) -> tuple[bool, str]:
        """Install the newest version of the channel (or a given one) from the official npm package, then switch to it."""
        from . import versions
        if version is None:
            res = versions.update(self.name, with_login=False)
            if res["changed"] or res["current"]:
                return True, "; ".join(res["notes"])
            return False, "; ".join(res["notes"])
        ok, out = versions.install(self.name, version)
        if ok:
            versions.switch(self.name, version)
        return ok, scrub(out)

    def run(self, task: Task, on_event: Callable[[Event], None] | None = None,
            stop: threading.Event | None = None) -> RunResult:
        if not self.installed():
            return RunResult(False, 127, error=f"{self.label} is not installed in this container. Run `crewcut doctor`.")
        ok, why = self.login_status()
        if not ok:
            return RunResult(False, 4, error=f"{self.label} is not logged in: {why}")
        env = {k: v for k, v in os.environ.items() if k not in SERVER_ONLY_ENV}
        env.update(self.env())
        env.update(task.env)
        env.setdefault("DISABLE_AUTOUPDATER", "1")
        cmd = self.command(task)
        t0 = time.time()
        log = open(task.log_path, "a", encoding="utf-8") if task.log_path else None

        def write(line: str) -> None:
            if log:
                log.write(scrub(line).rstrip() + "\n")
                log.flush()

        def emit(ev: Event) -> None:
            ev.text = scrub(ev.text)
            if ev.kind in ("text", "tool", "step", "error", "subagent", "hook"):
                write(f"{ev.kind}: {ev.text}")
            elif ev.kind in ("raw", "init"):
                write(f"{ev.kind}: {ev.text} " + json.dumps(ev.data.get("raw", ev.data), default=str)[:600])
            if on_event:
                on_event(ev)

        write(f"--- start {time.strftime('%Y-%m-%d %H:%M:%S')} engine={self.name} model={task.model or 'default'}"
              + (f" agent={task.agent}" if task.agent else "") + (f" effort={task.effort}" if task.effort else "")
              + (f" resume={task.resume}" if task.resume else "")
              + (f" extra={' '.join(task.extra_args)}" if task.extra_args else ""))
        for note in (task.engine_options or {}).get("notes", []):
            write("note: " + note)
        proc = subprocess.Popen(cmd, cwd=str(task.cwd), env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, stdin=subprocess.DEVNULL, start_new_session=True)
        state: dict = {"texts": [], "usage": {}, "session": task.resume, "result": None, "cost": 0.0, "turns": 0,
                       "error": ""}
        timed_out = threading.Event()

        def killer() -> None:
            while proc.poll() is None:
                over = time.time() - t0 > task.timeout_s
                if over or (stop is not None and stop.is_set()):
                    if over:
                        timed_out.set()
                    try:
                        os.killpg(proc.pid, signal.SIGTERM)
                        time.sleep(5)
                        os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    return
                time.sleep(1)

        threading.Thread(target=killer, daemon=True).start()
        stderr_lines: list[str] = []

        def read_err() -> None:
            assert proc.stderr is not None
            for line in proc.stderr:
                stderr_lines.append(line)
                del stderr_lines[:-200]

        threading.Thread(target=read_err, daemon=True).start()
        assert proc.stdout is not None
        for raw in proc.stdout:
            raw = raw.strip()
            if not raw:
                continue
            try:
                obj = json.loads(raw)
            except ValueError:
                write(raw)
                continue
            for ev in self.parse(obj, state):
                emit(ev)
        code = proc.wait()
        err = "".join(stderr_lines).strip()
        if err:
            write("stderr: " + err[-2000:])
        write(f"--- end exit={code} seconds={time.time() - t0:.0f}")
        if log:
            log.close()
        ok = code == 0 and not state["error"] and not timed_out.is_set()
        text = state["result"] if state["result"] is not None else (state["texts"][-1] if state["texts"] else "")
        error = ""
        if not ok:
            error = ("time limit reached" if timed_out.is_set() else
                     state["error"] or err[-600:] or f"exit {code}")
        return RunResult(ok=ok, exit_code=code, text=scrub(str(text)), cost_usd=float(state["cost"] or 0.0),
                         usage=state["usage"], session=state["session"], turns=int(state["turns"] or 0),
                         seconds=time.time() - t0, error=scrub(error)[:600], timed_out=timed_out.is_set())
