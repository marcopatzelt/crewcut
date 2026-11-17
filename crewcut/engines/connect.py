"""Connect Claude and Codex without a terminal: the official sign-in of each CLI, driven for the user.

Claude: `claude setup-token` runs in a pseudo-terminal with BROWSER=true, so it prints its sign-in link instead of
opening a browser (there is none in the container). The user opens the link (the desktop app opens it in the default
browser), signs in on Anthropic's own page and gets a code; Crewcut writes that code to the CLI, which prints a
long-lived token (one year). Crewcut never talks to Anthropic's sign-in itself and has no OAuth client of its own.
Where the token lives:
- the desktop app reads it from `crewcut engine connect claude --print-token` and keeps it in the system keychain
  (Electron safeStorage); the container gets it as CLAUDE_CODE_OAUTH_TOKEN, as with .env;
- the web UI (a server or a rented machine) stores it in the engine volume (`/opt/engine/secrets/`, mode 0600, never
  in the studio folder), and the server puts it into its environment.
A token in the environment (.env or the desktop app) always wins over the stored one.

Codex: `codex login --device-auth` (engines/codex.py); the link and the code are shown to the user, the login stays in
CODEX_HOME in the engine volume, where Codex refreshes it itself.
"""

from __future__ import annotations

import json
import os
import re
import select
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

SIGN_IN_HOSTS = ("claude.ai", "claude.com", "console.anthropic.com", "platform.claude.com")
URL_RE = re.compile(r"https://[^\s\"'<>\x1b]+")
TOKEN_RE = re.compile(r"sk-ant-oat\d\d-[A-Za-z0-9_\-]{20,}")
CODE_RE = re.compile(r"^[A-Za-z0-9_\-#.:]{8,1024}$")
ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b[=>]")
# character-set switches (ESC ( B, SI, SO) and other control bytes a terminal UI sends besides its text
CTRL_RE = re.compile(r"\x1b[()*+][0-9A-Za-z]|[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
# a line of the CLI that says what went wrong (never the echo of the pasted code, which it masks with asterisks)
ERROR_RE = re.compile(r"\b(error|invalid|failed|expired|denied|unauthori[sz]ed|not valid|try again)\b", re.I)
TOKEN_ENV = "CLAUDE_CODE_OAUTH_TOKEN"

_from_store = False  # True when the token in os.environ came from the stored file (so disconnect may remove it)


# ---------- where the web UI keeps the token ----------

def token_file() -> Path:
    prefix = os.environ.get("CREWCUT_ENGINE_PREFIX", "/opt/engine")
    return Path(prefix) / "secrets" / "claude-oauth-token"


def store_token(token: str) -> None:
    global _from_store
    if not TOKEN_RE.fullmatch(token):
        raise ValueError("That is not a Claude Code token.")
    f = token_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(f.parent, 0o700)
    tmp = f.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(token)
    os.replace(tmp, f)
    if not os.environ.get(TOKEN_ENV) or _from_store:
        os.environ[TOKEN_ENV] = token
        _from_store = True


def load_stored_token() -> bool:
    """At start: the stored token goes into the environment when none is set there. True when it did."""
    global _from_store
    if os.environ.get(TOKEN_ENV):
        return False
    try:
        token = token_file().read_text(encoding="utf-8").strip()
    except OSError:
        return False
    if TOKEN_RE.fullmatch(token):
        os.environ[TOKEN_ENV] = token
        _from_store = True
        return True
    return False


def token_source() -> str | None:
    """"stored" (connected in the web UI), "environment" (.env or the desktop app) or None."""
    if not os.environ.get(TOKEN_ENV):
        return None
    return "stored" if _from_store else "environment"


def forget_token() -> bool:
    """Disconnect the web UI's login. A token from the environment is not ours to remove: False."""
    global _from_store
    if os.environ.get(TOKEN_ENV) and not _from_store:
        return False
    try:
        token_file().unlink()
    except FileNotFoundError:
        pass
    if _from_store:
        os.environ.pop(TOKEN_ENV, None)
        _from_store = False
    return True


# ---------- inside the container: run as the studio's owner, never as root ----------

RUN_AS = Path("/run/crewcut-user")


def drop_to_studio_owner() -> None:
    """`docker compose exec` runs as root; the CLI runs as the user Crewcut runs as (the entrypoint wrote it to
    /run/crewcut-user: the studio folder's owner, or root under rootless Docker, where root is you on the host)."""
    studio = Path(os.environ.get("CREWCUT_STUDIO", "/studio"))
    if os.geteuid() != 0 or not studio.is_dir():
        return
    uid = gid = None
    try:
        u, g = RUN_AS.read_text(encoding="utf-8").strip().split(":")
        uid, gid = int(u), int(g)
    except (OSError, ValueError):
        st = studio.stat()
        uid, gid = (st.st_uid, st.st_gid) if st.st_uid else (1000, 1000)
    os.environ["HOME"] = str(studio / ".crewcut" / "home")
    if uid == 0:
        os.environ["IS_SANDBOX"] = "1"  # as the entrypoint: root in a rootless container is the host's user
        return
    os.setgroups([])
    os.setgid(gid)
    os.setuid(uid)


# ---------- the Claude sign-in, driven in a pseudo-terminal ----------

def clean(text: str) -> str:
    return CTRL_RE.sub("", ANSI_RE.sub("", text).replace("\r", "\n"))


def cli_error(text: str) -> str | None:
    """The CLI's own error line in its output, if there is one; never a line with the masked echo of the code."""
    for line in reversed(clean(text).splitlines()):
        line = line.strip()
        if line and ERROR_RE.search(line) and "*" not in line and len(line) <= 240:
            return line
    return None


def sign_in_url(text: str) -> str | None:
    """The first https link to Anthropic's own sign-in in the CLI's output (any other link is ignored)."""
    for m in URL_RE.finditer(clean(text)):
        url = m.group(0).rstrip(".,)")
        host = re.sub(r"^https://([^/:?#]+).*$", r"\1", url).lower()
        if any(host == h or host.endswith("." + h) for h in SIGN_IN_HOSTS):
            return url
    return None


class ClaudeSignIn:
    """One `claude setup-token` run: start() gives the sign-in link, finish(code) gives the token."""

    def __init__(self, binary: str, env: dict[str, str] | None = None, columns: int = 1000):
        self.binary = binary
        self.env = {**os.environ, **(env or {}), "BROWSER": "true", "COLUMNS": str(columns), "TERM": "xterm"}
        self.env.pop(TOKEN_ENV, None)  # the CLI must not see an old token while it makes a new one
        self.columns = columns
        self.out = ""
        self.proc: subprocess.Popen | None = None
        self.master: int | None = None
        self.lock = threading.Lock()
        self.reader: threading.Thread | None = None

    def _read(self) -> None:
        assert self.master is not None
        while True:
            try:
                r, _, _ = select.select([self.master], [], [], 0.5)
                if not r:
                    if self.proc and self.proc.poll() is not None:
                        break
                    continue
                data = os.read(self.master, 65536)
            except OSError:
                break
            if not data:
                break
            with self.lock:
                self.out += data.decode("utf-8", "replace")

    def _wait_for(self, find, timeout: float):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            with self.lock:
                hit = find(self.out)
            if hit:
                return hit
            if self.proc and self.proc.poll() is not None:
                time.sleep(0.3)  # the last bytes
                with self.lock:
                    return find(self.out)
            time.sleep(0.2)
        return None

    def start(self, timeout: float = 45) -> str:
        import fcntl
        import pty
        import struct
        import termios
        master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 50, self.columns, 0, 0))
        self.master = master
        self.proc = subprocess.Popen([self.binary, "setup-token"], stdin=slave, stdout=slave, stderr=slave,
                                     env=self.env, start_new_session=True, close_fds=True)
        os.close(slave)
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()
        url = self._wait_for(sign_in_url, timeout)
        if not url:
            err = cli_error(self.out)
            self.close()
            raise RuntimeError("Claude Code did not show a sign-in link." + (f" It says: {err}" if err else ""))
        return url

    def finish(self, code: str, timeout: float = 90) -> str:
        """Types the code into the CLI and presses Enter, then waits for the token. The code is the whole text Claude's
        page shows (code#state); spaces and line breaks from copying are dropped."""
        code = re.sub(r"\s+", "", code)
        if not CODE_RE.fullmatch(code):
            raise ValueError("That does not look like the code from Claude's page. Copy it again.")
        if self.master is None or not self.proc or self.proc.poll() is not None:
            raise RuntimeError("The sign-in has ended. Start it again.")
        with self.lock:
            seen = len(self.out)
        # The terminal UI reads its input in raw mode: text and Enter in one write would count as pasted text, so the
        # Enter key (a carriage return) goes in its own write after a moment.
        os.write(self.master, code.encode())
        time.sleep(0.5)
        os.write(self.master, b"\r")

        def found(text: str) -> tuple[str, str] | None:
            new = text[seen:]
            m = TOKEN_RE.search(clean(new))
            if m:
                return ("token", m.group(0))
            err = cli_error(new)
            return ("error", err) if err else None

        hit = self._wait_for(found, timeout)
        exited = self.proc.poll() is not None
        self.close()
        if hit and hit[0] == "token":
            return hit[1]
        if hit:
            raise RuntimeError(f"Claude did not accept the code. Claude Code says: {hit[1]}")
        if exited:
            raise RuntimeError("Claude did not accept the code. Copy the whole code from Claude's page and start again.")
        raise RuntimeError("Claude did not answer after the code was sent. Start again.")

    def close(self) -> None:
        if self.proc and self.proc.poll() is None:
            try:
                os.killpg(self.proc.pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        if self.master is not None:
            try:
                os.close(self.master)
            except OSError:
                pass
            self.master = None


def claude_account(token: str, binary: str | None = None) -> dict:
    """Best effort: what `claude auth status --json` says about the account of a token (email, organization, plan)."""
    binary = binary or shutil.which("claude")
    if not binary:
        return {}
    try:
        r = subprocess.run([binary, "auth", "status", "--json"], capture_output=True, text=True, timeout=20,
                           env={**os.environ, TOKEN_ENV: token}, stdin=subprocess.DEVNULL)
        data = json.loads(r.stdout or "{}")
    except (OSError, subprocess.SubprocessError, ValueError):
        return {}
    keep = {}
    for key in ("email", "orgName", "subscriptionType", "authMethod"):
        v = data.get(key) if isinstance(data, dict) else None
        if isinstance(v, str) and v:
            keep[key] = v
    return keep


# ---------- `crewcut engine connect` and `disconnect` ----------

def _say(obj: dict) -> None:
    print(json.dumps(obj, ensure_ascii=False), flush=True)


def cli_connect(name: str, print_token: bool) -> int:
    """JSON lines on stdout: {"step": "url"|"device"|"done"|"error", ...}. Claude reads the code as one line on stdin."""
    from . import get
    drop_to_studio_owner()
    eng = get(name)
    if not eng.installed():
        _say({"step": "status", "text": f"Installing {eng.label} first..."})
        ok, out = eng.install()
        if not ok:
            _say({"step": "error", "text": f"{eng.label} could not be installed: {out}"})
            return 1
    if eng.name == "codex":
        def tell(url: str, code: str | None) -> None:
            _say({"step": "device", "url": url, "code": code})
        ok, why = eng.device_login(tell)
        _say({"step": "done", "ok": ok, "text": why} if ok else {"step": "error", "text": why})
        return 0 if ok else 1
    session = ClaudeSignIn(eng.binary() or "claude")
    try:
        url = session.start()
        _say({"step": "url", "url": url})
        line = sys.stdin.readline()
        if not line.strip():
            _say({"step": "error", "text": "No code was given."})
            return 3
        token = session.finish(line)
    except (RuntimeError, ValueError) as e:
        _say({"step": "error", "text": str(e)})
        if os.environ.get("CREWCUT_CONNECT_DEBUG") == "1":  # CI: what the CLI showed, cleaned (its echo is masked)
            print(clean(session.out)[-2000:], file=sys.stderr, flush=True)
        return 1
    finally:
        session.close()
    account = claude_account(token, eng.binary())
    if print_token:
        _say({"step": "done", "token": token, "account": account})
    else:
        store_token(token)
        _say({"step": "done", "stored": True, "account": account})
    return 0


def cli_disconnect(name: str) -> int:
    from . import get
    drop_to_studio_owner()
    eng = get(name)
    if eng.name == "codex":
        if eng.installed():
            subprocess.run([eng.binary() or "codex", "logout"], env={**os.environ, **eng.env()},
                           capture_output=True, timeout=30)
        _say({"step": "done", "text": "Codex is disconnected."})
        return 0
    if not forget_token():
        _say({"step": "error", "text": "This Claude login comes from the environment (.env or the desktop app); "
                                       "remove it there."})
        return 1
    _say({"step": "done", "text": "Claude is disconnected."})
    return 0
