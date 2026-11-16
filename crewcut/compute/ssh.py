"""SSH and rsync to rented machines, through a replaceable runner (tests pass a fake).

The studio has its own ed25519 key in studio/.crewcut/compute/ssh/ (made on first use, never printed). Its public half
is registered with the provider account. Each machine gets its own known_hosts file, because hosts reuse IPs and ports.
"""

from __future__ import annotations

import os
import shlex
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path

from . import state
from .errors import ComputeError

Runner = Callable[..., tuple[int, str, str]]


def subprocess_runner(argv: Sequence[str], timeout: float = 60, input: str | None = None) -> tuple[int, str, str]:
    """Run a program. Error texts never contain the input."""
    try:
        r = subprocess.run([str(a) for a in argv], capture_output=True, text=True, timeout=timeout, input=input,
                           errors="replace")
        return r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        return 124, "", "time limit reached"
    except OSError as e:
        return 127, "", f"{type(e).__name__}: {e.strerror or ''}"


_runner: Runner = subprocess_runner


def use_runner(runner: Runner | None) -> None:
    global _runner
    _runner = runner or subprocess_runner


def run(argv: Sequence[str], timeout: float = 60, input: str | None = None) -> tuple[int, str, str]:
    return _runner(list(argv), timeout=timeout, input=input)


# ---- the studio key ------------------------------------------------------------------------------------------------
def key_dir() -> Path:
    d = state.compute_dir() / "ssh"
    d.mkdir(parents=True, exist_ok=True)
    os.chmod(d, 0o700)
    return d


def key_path() -> Path:
    return key_dir() / "id_ed25519"


def ensure_key() -> str:
    """Create the studio key on first use and return the public key text. The private key is never read or printed."""
    priv = key_path()
    pub = priv.with_name(priv.name + ".pub")
    if not (priv.is_file() and pub.is_file()):
        for p in (priv, pub):
            if p.exists():
                p.unlink()
        rc, _, err = run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "crewcut-compute", "-f", str(priv)], 30)
        if rc != 0 or not pub.is_file():
            raise ComputeError(f"could not create the SSH key (ssh-keygen: {err.strip()[-120:]})")
    os.chmod(priv, 0o600)
    return pub.read_text(encoding="utf-8").strip()


def known_hosts(instance: int | str) -> Path:
    return key_dir() / f"known_hosts_{instance}"


def base(port: int, instance: int | str) -> list[str]:
    return ["ssh", "-i", str(key_path()), "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
            "-o", "StrictHostKeyChecking=accept-new", "-o", f"UserKnownHostsFile={known_hosts(instance)}",
            "-o", "ConnectTimeout=12", "-o", "ServerAliveInterval=10", "-o", "ServerAliveCountMax=6",
            "-o", "LogLevel=ERROR", "-p", str(int(port))]


def ssh_argv(host: str, port: int, instance: int | str, command: str) -> list[str]:
    return base(port, instance) + [f"root@{host}", command]


def rsync_up_argv(sources: Sequence[Path | str], host: str, port: int, instance: int | str, dest: str) -> list[str]:
    return (["rsync", "-a", "--timeout=120", "--exclude", "__pycache__", "-e", shlex.join(base(port, instance))]
            + [str(s) for s in sources] + [f"root@{host}:{dest}"])


def rsync_down_argv(host: str, port: int, instance: int | str, source: str, dest: Path | str) -> list[str]:
    return ["rsync", "-a", "--timeout=120", "-e", shlex.join(base(port, instance)), f"root@{host}:{source}", str(dest)]
