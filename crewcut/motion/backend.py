"""Backend: invokes the real EffectCraft engine through its native command line, ``effectcraft-cli``.

Nothing here re-implements EffectCraft. Every mutation is an engine command (``exec`` / ``run --commands``)
or an After Effects-style script (``script``) executed by EffectCraft itself, and every picture comes from
EffectCraft's renderer (``render-frame`` / ``render``). The project file (``.ecproj``, versioned JSON) is the
state between commands; the engine writes it with ``--save``.

Finding the binary, in order: the ``cli`` argument (``--cli``), ``$EFFECTCRAFT_CLI``, ``effectcraft-cli`` on ``PATH``.
The Crewcut image ships it as ``/usr/local/bin/effectcraft-cli`` (pin and patches in ``third_party/effectcraft``).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

INSTALL_HINT = (
    "effectcraft-cli not found. The Crewcut image ships it. Elsewhere build it from source (Rust >= 1.95 via rustup)\n"
    "at the commit in third_party/effectcraft/PIN with the patches in third_party/effectcraft/patches applied:\n"
    "  cargo build --release -p effectcraft-cli\n"
    "then put target/release on PATH or set EFFECTCRAFT_CLI=/path/to/effectcraft-cli"
)


class BackendError(RuntimeError):
    """EffectCraft refused a command or could not run. ``detail`` holds the engine's JSON reply if any."""

    def __init__(self, message: str, detail: Any = None, argv: list[str] | None = None):
        super().__init__(message)
        self.detail = detail
        self.argv = argv or []


def find_effectcraft(cli: str | None = None) -> str:
    """Return the path of a runnable ``effectcraft-cli`` or raise :class:`BackendError` with build instructions."""
    for cand in (cli, os.environ.get("EFFECTCRAFT_CLI"), shutil.which("effectcraft-cli")):
        if not cand:
            continue
        p = os.path.expanduser(cand)
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    raise BackendError(INSTALL_HINT)


def _parse_json_out(text: str) -> Any:
    """The CLI prints one JSON document with --json; tolerate log lines before it."""
    text = text.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # last line that parses, else the first '{' or '[' to the end
    for line in reversed(text.splitlines()):
        line = line.strip()
        if line.startswith(("{", "[")):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    for opener in ("{", "["):
        i = text.find(opener)
        if i >= 0:
            try:
                return json.loads(text[i:])
            except json.JSONDecodeError:
                continue
    return {"raw": text}


@dataclass
class Backend:
    """A thin, stateless wrapper around one ``effectcraft-cli`` binary."""

    cli: str | None = None
    gpu: bool = False
    timeout: float = 3600.0
    extra_env: dict[str, str] = field(default_factory=dict)
    last_argv: list[str] = field(default_factory=list)
    engine: Any = None          # optional persistent McpEngine (--persistent): same results, no reload per call

    def _eng(self, project: str | None, save_as: str | None = None) -> Any:
        """The persistent engine if it holds this project (and no save-as is asked), else None."""
        e = self.engine
        if e is None or not project or save_as or not e.alive():
            return None
        return e if os.path.abspath(project) == e.project else None

    @property
    def binary(self) -> str:
        if not getattr(self, "_bin", None):
            self._bin = find_effectcraft(self.cli)
        return self._bin

    # ── low level ────────────────────────────────────────────────────────
    def argv(self, sub: list[str], project: str | None = None, save: bool = False, save_as: str | None = None,
             empty: bool = False, json_out: bool = True) -> list[str]:
        a = [self.binary]
        if project:
            a += ["--project", str(project)]
        elif empty:
            a += ["--empty"]
        if self.gpu:
            a += ["--gpu"]
        a += sub
        if save_as:
            a += ["--save-as", str(save_as)]
        elif save and project:
            a += ["--save"]
        if json_out:
            a += ["--json"]
        return a

    def call(self, argv: list[str], timeout: float | None = None, check: bool = True) -> Any:
        """Run one CLI call, return its parsed JSON reply. Engine errors become :class:`BackendError`."""
        self.last_argv = argv
        env = dict(os.environ, **self.extra_env)
        try:
            r = subprocess.run(argv, capture_output=True, text=True, timeout=timeout or self.timeout, env=env)
        except subprocess.TimeoutExpired as e:
            raise BackendError(f"effectcraft-cli timed out after {e.timeout:.0f} s", argv=argv) from e
        out = _parse_json_out(r.stdout)
        if check and r.returncode != 0:
            msg = None
            if isinstance(out, dict):
                msg = out.get("error")
                if isinstance(msg, dict):
                    msg = msg.get("message") or json.dumps(msg)
            msg = msg or (r.stderr.strip().splitlines() or [f"exit {r.returncode}"])[-1]
            raise BackendError(f"effectcraft-cli: {msg}", detail=out if out is not None else r.stderr, argv=argv)
        if isinstance(out, dict) and out.get("error") and check:
            raise BackendError(f"effectcraft-cli: {out['error']}", detail=out, argv=argv)
        return out

    # ── engine commands ──────────────────────────────────────────────────
    def version(self) -> str:
        r = subprocess.run([self.binary, "--version"], capture_output=True, text=True, timeout=30)
        return r.stdout.strip() or r.stderr.strip()

    def info(self, project: str | None = None) -> Any:
        return self.call(self.argv(["info"], project=project, empty=project is None))

    def commands(self, filt: str | None = None) -> Any:
        sub = ["commands"] + (["--filter", filt] if filt else [])
        return self.call(self.argv(sub, empty=True))

    def exec(self, command: str, params: dict | None = None, project: str | None = None, save: bool = True,
             save_as: str | None = None) -> Any:
        """One engine command. With ``project`` and ``save`` the engine writes the project back."""
        e = self._eng(project, save_as)
        if e:
            return e.exec(command, params, save=save)
        sub = ["exec", command, "--params", json.dumps(params or {})]
        return self.call(self.argv(sub, project=project, save=save, save_as=save_as, empty=project is None))

    def run_steps(self, steps: list[dict], project: str | None = None, save: bool = True,
                  save_as: str | None = None) -> Any:
        """Several engine commands in one process: ``[{"command": id, "params": {...}}, ...]``."""
        e = self._eng(project, save_as)
        if e:
            return e.run_steps(steps, save=save)
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(steps, f)
            path = f.name
        try:
            sub = ["run", "--commands", path]
            return self.call(self.argv(sub, project=project, save=save, save_as=save_as, empty=project is None))
        finally:
            os.unlink(path)

    def script(self, code: str, project: str | None = None, save: bool = True, save_as: str | None = None,
               name: str = "crewcut-motion.jsx", keep: str | None = None) -> Any:
        """Run After Effects-style JavaScript inside EffectCraft (``script``). ``keep`` writes the code there."""
        e = self._eng(project, save_as)
        if e:
            if keep:
                Path(keep).parent.mkdir(parents=True, exist_ok=True)
                Path(keep).write_text(code, encoding="utf-8")
            return e.script(code, save=save, name=name)
        d = tempfile.mkdtemp(prefix="ecjsx-")
        path = os.path.join(d, name)
        Path(path).write_text(code, encoding="utf-8")
        if keep:
            Path(keep).parent.mkdir(parents=True, exist_ok=True)
            Path(keep).write_text(code, encoding="utf-8")
        try:
            out = self.call(self.argv(["script", path], project=project, save=save, save_as=save_as,
                                      empty=project is None), check=False)
            if isinstance(out, dict) and out.get("error"):
                e = out["error"]
                where = f":{e.get('line')}:{e.get('column')}" if isinstance(e, dict) and e.get("line") else ""
                msg = e.get("message") if isinstance(e, dict) else str(e)
                raise BackendError(f"script error{where}: {msg}", detail=out, argv=self.last_argv)
            return out
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def props(self, project: str, comp: str, layer: str, flat: bool = True, time: float | None = None) -> Any:
        sub = ["props", comp, layer] + (["--flat"] if flat else []) + (["--time", str(time)] if time is not None else [])
        return self.call(self.argv(sub, project=project))

    def get(self, project: str, comp: str, layer: str, path: str, time: float | None = None) -> Any:
        sub = ["get", comp, layer, path] + (["--time", str(time)] if time is not None else [])
        return self.call(self.argv(sub, project=project))

    # ── pictures ─────────────────────────────────────────────────────────
    def render_frame(self, project: str, out: str, comp: str | None = None, time: float | None = None,
                     frame: int | None = None, max_side: int | None = None, transparent: bool = False) -> Any:
        e = self._eng(project)
        if e:
            return e.render_frame(out, comp=comp, time=time, max_side=max_side, transparent=transparent)
        sub = ["render-frame"]
        if comp:
            sub += ["--comp", comp]
        if frame is not None:
            sub += ["--frame", str(frame)]
        elif time is not None:
            sub += ["--time", str(time)]
        if max_side:
            sub += ["--max-side", str(max_side)]
        if transparent:
            sub += ["--transparent"]
        sub += ["--out", str(out)]
        return self.call(self.argv(sub, project=project), timeout=900)

    def render(self, project: str, out: str, comp: str | None = None, start: float | None = None,
               end: float | None = None, fmt: str | None = None, extra: list[str] | None = None) -> Any:
        sub = ["render", "--out", str(out)]
        if comp:
            sub += ["--comp", comp]
        if start is not None:
            sub += ["--start", f"{start:.6f}"]
        if end is not None:
            sub += ["--end", f"{end:.6f}"]
        if fmt:
            sub += ["--format", fmt]
        sub += list(extra or [])
        return self.call(self.argv(sub, project=project))
