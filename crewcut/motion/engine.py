"""Persistent engine connection: one `effectcraft-cli mcp` process holding the project in memory.

Measured on the render machine (17.11.2026, new comp + 20 layers with eased keys and Glow + 5 frames at 1080p):
one-shot CLI calls 13.9-15.6 s (66 processes), one JSX batch 2.0-5.7 s (7 processes), this connection 1.4-1.7 s
(1 process, 129 requests), no errors in any run. The harness stays CLI-first: one-shot commands still call the
native CLI; `crewcut motion --persistent` uses this connection so each command does not reload the project.

The protocol is MCP (JSON-RPC 2.0 over stdio), used here only as the engine's wire format. Every mutation is saved
to the project file right away, so the file on disk, snapshot undo and later one-shot calls always agree.
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
from typing import Any

from .backend import BackendError, find_effectcraft


class McpEngine:
    """One long-lived `effectcraft-cli mcp --project P` process."""

    def __init__(self, project: str | None = None, cli: str | None = None, gpu: bool = False, timeout: float = 900.0):
        self.project = os.path.abspath(project) if project else None
        self.binary = find_effectcraft(cli)
        self.gpu = gpu
        self.timeout = timeout
        self._id = 0
        self._lock = threading.Lock()
        self.proc: subprocess.Popen | None = None
        self.requests = 0
        self.start()

    # ── process ──────────────────────────────────────────────────────────
    def start(self) -> None:
        argv = [self.binary, "mcp"]
        if self.project:
            argv += ["--project", self.project]
        else:
            argv += ["--empty"]
        if self.gpu:
            argv += ["--gpu"]
        self.proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                     text=True, bufsize=1)
        r = self._rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                     "clientInfo": {"name": "crewcut-motion", "version": "1"}})
        if "error" in r:
            raise BackendError(f"mcp initialize failed: {r['error']}")
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def close(self) -> None:
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.stdin.close()
                self.proc.wait(timeout=30)
            except Exception:
                self.proc.kill()
        self.proc = None

    def alive(self) -> bool:
        return bool(self.proc and self.proc.poll() is None)

    def reopen(self, project: str) -> None:
        """Load another project (or the same file after undo/redo replaced it on disk)."""
        self.project = os.path.abspath(project)
        self.tool("open_project", {"path": self.project})

    # ── wire ─────────────────────────────────────────────────────────────
    def _send(self, msg: dict) -> None:
        if not self.alive():
            raise BackendError("effectcraft engine process is not running")
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()

    def _rpc(self, method: str, params: dict) -> dict:
        with self._lock:
            self._id += 1
            mid = self._id
            self._send({"jsonrpc": "2.0", "id": mid, "method": method, "params": params})
            while True:
                line = self.proc.stdout.readline()
                if not line:
                    raise BackendError("effectcraft engine process closed the connection")
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if msg.get("id") == mid:
                    self.requests += 1
                    return msg

    def tool(self, name: str, args: dict) -> Any:
        """Call one engine tool; returns its JSON result, raises BackendError on isError."""
        m = self._rpc("tools/call", {"name": name, "arguments": args})
        if "error" in m:
            raise BackendError(f"{name}: {m['error'].get('message', m['error'])}", detail=m)
        res = m.get("result") or {}
        text = "".join(c.get("text", "") for c in res.get("content", []) if c.get("type") == "text")
        try:
            data = json.loads(text) if text else None
        except json.JSONDecodeError:
            data = text
        if res.get("isError"):
            msg = data.get("error") if isinstance(data, dict) and data.get("error") else text
            raise BackendError(f"{name}: {msg}", detail=data)
        return data

    # ── the Backend interface used by the harness ────────────────────────
    def _save(self, save: bool) -> None:
        if save and self.project:
            self.tool("save_project", {"path": self.project})

    def exec(self, command: str, params: dict | None = None, save: bool = True) -> Any:
        r = self.tool("execute_command", {"command": command, "params": params or {}})
        self._save(save)
        return r

    def run_steps(self, steps: list[dict], save: bool = True) -> Any:
        r = self.tool("batch", {"steps": [{"command": s.get("command") or s.get("id"), "params": s.get("params", {})} for s in steps]})
        self._save(save)
        return r

    def script(self, code: str, save: bool = True, name: str = "crewcut-motion.jsx") -> Any:
        r = self.tool("run_script", {"code": code, "name": name})
        if isinstance(r, dict) and r.get("error"):
            e = r["error"]
            where = f":{e.get('line')}:{e.get('column')}" if isinstance(e, dict) and e.get("line") else ""
            raise BackendError(f"script error{where}: {e.get('message') if isinstance(e, dict) else e}", detail=r)
        self._save(save)
        return r

    def render_frame(self, out: str, comp: str | None = None, time: float | None = None, max_side: int | None = None,
                     transparent: bool = False) -> Any:
        args: dict = {"path": os.path.abspath(out), "inline": False, "max_side": max_side or 7680}
        if comp:
            args["comp"] = comp
        if time is not None:
            args["time"] = time
        if transparent:
            args["transparent"] = True
        return self.tool("render_frame", args)
