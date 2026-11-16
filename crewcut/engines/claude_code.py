"""Claude Code, the primary engine: the user's own `claude` CLI, headless, on their Claude subscription.

Login: CLAUDE_CODE_OAUTH_TOKEN from `claude setup-token` (once, on any computer with a browser). An API key in
ANTHROPIC_API_KEY also works. The token stays in the environment: never an argument, never a file, never a log line.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from .base import Engine, Event, Task, scrub


def describe_tool(block: dict) -> str:
    """A one-line, readable description of a tool call for the log and the Crew column."""
    name = block.get("name", "tool")
    inp = block.get("input") or {}
    if name == "Bash":
        return inp.get("description") or ("$ " + str(inp.get("command", ""))[:120])
    if name in ("Read", "Write", "Edit"):
        return f"{name} {Path(str(inp.get('file_path', ''))).name}"
    if name in ("Glob", "Grep"):
        return f"{name} {inp.get('pattern', '')}"[:120]
    if name in ("WebFetch", "WebSearch"):
        return f"{name} {inp.get('url') or inp.get('query') or ''}"[:120]
    if name == "Skill":
        return f"Skill {inp.get('skill', '')}"
    if name == "TodoWrite":
        todos = inp.get("todos") or []
        cur = next((t.get("activeForm") or t.get("content") for t in todos if t.get("status") == "in_progress"), None)
        return cur or "Planning the steps"
    return name


class ClaudeCode(Engine):
    name = "claude"
    label = "Claude Code"
    beta = False
    binary_name = "claude"
    npm_package = "@anthropic-ai/claude-code"

    def login_kind(self) -> str | None:
        if os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"):
            return "subscription"
        if os.environ.get("ANTHROPIC_API_KEY"):
            return "api-key"
        return None

    def login_status(self) -> tuple[bool, str]:
        kind = self.login_kind()
        if not kind:
            return False, "no CLAUDE_CODE_OAUTH_TOKEN in the environment (run `claude setup-token` once, put it into .env)"
        return True, f"{kind} credential present (value never shown)"

    def command(self, task: Task) -> list[str]:
        cmd = [self.binary() or "claude", "-p", task.prompt, "--output-format", "stream-json", "--verbose",
               "--append-system-prompt", task.system, "--dangerously-skip-permissions"]
        if task.resume:
            cmd += ["--resume", task.resume]
        if task.model:
            cmd += ["--model", task.model]
        for d in task.extra_dirs:
            cmd += ["--add-dir", d]
        return cmd

    def parse(self, obj: dict, state: dict) -> list[Event]:
        out: list[Event] = []
        t = obj.get("type")
        if obj.get("session_id") and state.get("session") != obj["session_id"]:
            state["session"] = obj["session_id"]
            out.append(Event("session", data={"session": obj["session_id"]}))
        if t == "assistant":
            for block in (obj.get("message") or {}).get("content") or []:
                if block.get("type") == "text" and block.get("text", "").strip():
                    state["texts"].append(block["text"])
                    out.append(Event("text", block["text"]))
                elif block.get("type") == "tool_use":
                    kind = "step" if block.get("name") == "TodoWrite" else "tool"
                    out.append(Event(kind, describe_tool(block), {"name": block.get("name")}))
        elif t == "result":
            state["result"] = obj.get("result")
            state["cost"] = obj.get("total_cost_usd") or 0.0
            state["turns"] = obj.get("num_turns") or 0
            if obj.get("usage"):
                state["usage"] = {k: v for k, v in obj["usage"].items() if isinstance(v, (int, float))}
                out.append(Event("usage", data={"usage": state["usage"], "equiv_usd": state["cost"]}))
            if obj.get("is_error"):
                state["error"] = str(obj.get("result") or obj.get("subtype") or "error")[:400]
            out.append(Event("result", obj.get("subtype") or "", {"turns": state["turns"]}))
        return out

    def probe(self, timeout_s: int = 120) -> tuple[bool, str]:
        if not self.installed():
            return False, "claude is not installed"
        ok, why = self.login_status()
        if not ok:
            return False, why
        try:
            r = subprocess.run([self.binary(), "-p", "Reply with the single word: ok", "--output-format", "json",
                                "--model", "haiku"], capture_output=True, text=True, timeout=timeout_s,
                               stdin=subprocess.DEVNULL)
        except subprocess.TimeoutExpired:
            return False, f"no answer within {timeout_s} s"
        try:
            d = json.loads(r.stdout)
        except ValueError:
            return False, scrub((r.stderr or r.stdout).strip()[-300:]) or f"exit {r.returncode}"
        if d.get("is_error"):
            return False, scrub(str(d.get("result"))[:300])
        return True, f"login works ({self.login_kind()})"
