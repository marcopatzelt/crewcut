"""Claude Code, the primary engine: the user's own `claude` CLI, headless, on their Claude subscription.

Crewcut is a conductor, not a wrapper: whatever Claude Code can do, it can do in Crewcut. The command line has three
layers:
1. what Crewcut needs to read the run (fixed): `-p`, `--output-format stream-json`, `--verbose`, resume;
2. what Crewcut sets for the job: the crew member (`--agent crewcut:<id>`), the Crewcut plugin (`--plugin-dir`),
   `--model`, `--effort`, `--add-dir`, `--name`, the job context (`--append-system-prompt`);
3. what the user or the crew member adds (`extra_args`): passed through unchanged. A flag from layer 3 that layer 2 also
   sets wins over layer 2; layer 1 cannot be overridden, because without it Crewcut cannot read the run.
Login: CLAUDE_CODE_OAUTH_TOKEN from `claude setup-token`, made by "Connect Claude" (engines/connect.py) or by hand. It
stays in the environment: never an argument or a log. The web UI keeps it in the engine volume (mode 0600, never in the
studio folder); the desktop app keeps it in the system keychain.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from .base import Engine, Event, Task, scrub

FIXED = {"-p", "--print", "--output-format", "--verbose", "--resume", "-r", "--continue", "-c", "--input-format"}
WITH_VALUE = {"--agent", "--agents", "--model", "--effort", "--add-dir", "--name", "--append-system-prompt",
              "--plugin-dir", "--settings", "--mcp-config", "--permission-mode", "--fallback-model",
              "--max-budget-usd", "--setting-sources", "--output-format", "--resume", "-r", "--input-format",
              "--json-schema", "--allowedTools", "--disallowedTools", "--tools", "--system-prompt"}


def describe_tool(block: dict) -> str:
    """A one-line, readable description of a tool call for the log and the Crew column. Works for unknown tools too."""
    name = str(block.get("name", "tool"))
    inp = block.get("input") or {}
    if name == "Bash":
        return inp.get("description") or ("$ " + str(inp.get("command", ""))[:120])
    if name in ("Read", "Write", "Edit", "NotebookEdit"):
        return f"{name} {Path(str(inp.get('file_path') or inp.get('notebook_path') or '')).name}"
    if name in ("Glob", "Grep"):
        return f"{name} {inp.get('pattern', '')}"[:120]
    if name in ("WebFetch", "WebSearch"):
        return f"{name} {inp.get('url') or inp.get('query') or ''}"[:120]
    if name == "Skill":
        return f"Skill {inp.get('skill', '')}"
    if name in ("Task", "Agent"):
        who = str(inp.get("subagent_type") or "a helper").split(":")[-1]
        return f"Hands over to {who}: {inp.get('description') or ''}".strip().rstrip(":")[:140]
    if name == "TodoWrite":
        todos = inp.get("todos") or []
        cur = next((t.get("activeForm") or t.get("content") for t in todos if t.get("status") == "in_progress"), None)
        return cur or "Planning the steps"
    if name.startswith("mcp__"):
        parts = name.split("__")
        return f"{parts[1]}: {'__'.join(parts[2:])}" if len(parts) > 2 else name
    for key in ("description", "title", "prompt", "query", "path", "file_path", "command"):
        v = inp.get(key)
        if isinstance(v, str) and v.strip():
            return f"{name}: {v.strip()[:100]}"
    return name


def merge_args(layer2: list[str], extra: list[str]) -> tuple[list[str], list[str]]:
    """Layer 3 wins over layer 2 for the same flag; layer-1 flags in layer 3 are dropped (with a note)."""
    notes: list[str] = []
    user_flags = set()
    cleaned: list[str] = []
    i = 0
    while i < len(extra):
        a = extra[i]
        flag = a.split("=", 1)[0]
        takes = flag in WITH_VALUE and "=" not in a and i + 1 < len(extra)
        if flag in FIXED:
            notes.append(f"ignored {flag}: Crewcut needs its own value to read the run")
            i += 2 if takes else 1
            continue
        if flag.startswith("-"):
            user_flags.add(flag)
        cleaned.append(a)
        if takes:
            cleaned.append(extra[i + 1])
            i += 2
        else:
            i += 1
    kept: list[str] = []
    i = 0
    while i < len(layer2):
        a = layer2[i]
        takes = a in WITH_VALUE and i + 1 < len(layer2)
        repeatable = a in ("--add-dir", "--plugin-dir", "--mcp-config")
        if a in user_flags and not repeatable:
            i += 2 if takes else 1
            continue
        kept.append(a)
        if takes:
            kept.append(layer2[i + 1])
            i += 2
        else:
            i += 1
    return kept + cleaned, notes


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
            return False, ("Claude is not connected: press Connect Claude in Crewcut (or put a `claude setup-token` "
                           "token into .env)")
        return True, f"{kind} credential present (value never shown)"

    def command(self, task: Task) -> list[str]:
        layer1 = [self.binary() or "claude", "-p", task.prompt, "--output-format", "stream-json", "--verbose"]
        if task.resume:
            layer1 += ["--resume", task.resume]
        opts = task.engine_options or {}
        layer2: list[str] = []
        for d in opts.get("plugin_dirs") or []:
            layer2 += ["--plugin-dir", str(d)]
        if task.agent:
            layer2 += ["--agent", task.agent]
        if task.system:
            layer2 += ["--append-system-prompt", task.system]
        if task.model:
            layer2 += ["--model", task.model]
        if task.effort:
            layer2 += ["--effort", task.effort]
        for d in task.extra_dirs:
            layer2 += ["--add-dir", d]
        if task.name:
            layer2 += ["--name", task.name]
        if opts.get("settings"):
            layer2 += ["--settings", json.dumps(opts["settings"])]
        for flag in opts.get("flags") or []:          # switches without a value, e.g. --forward-subagent-text
            layer2.append(flag)
        if opts.get("skip_permissions", True):
            layer2.append("--dangerously-skip-permissions")
        merged, notes = merge_args(layer2, list(task.extra_args))
        task.engine_options.setdefault("notes", []).extend(notes)
        return layer1 + merged

    def parse(self, obj: dict, state: dict) -> list[Event]:
        out: list[Event] = []
        t = obj.get("type")
        if obj.get("session_id") and state.get("session") != obj["session_id"]:
            state["session"] = obj["session_id"]
            out.append(Event("session", data={"session": obj["session_id"]}))
        sub = obj.get("parent_tool_use_id")  # set when a subagent produced this message
        if t == "assistant":
            for block in (obj.get("message") or {}).get("content") or []:
                bt = block.get("type")
                if bt == "text" and block.get("text", "").strip():
                    if sub:
                        out.append(Event("subagent", block["text"][:300], {"parent": sub}))
                    else:
                        state["texts"].append(block["text"])
                        out.append(Event("text", block["text"]))
                elif bt == "tool_use":
                    kind = "step" if block.get("name") == "TodoWrite" else "tool"
                    out.append(Event(kind, describe_tool(block), {"name": block.get("name"), "subagent": bool(sub)}))
                elif bt == "thinking":
                    out.append(Event("thinking", "", {}))
        elif t == "user":
            pass  # tool results: the next assistant message says what came of them
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
        elif t == "system" and obj.get("subtype") == "init":
            out.append(Event("init", data={k: obj.get(k) for k in ("model", "claude_code_version", "agents",
                                                                    "plugins", "skills", "mcp_servers")
                                           if obj.get(k) is not None}))
        elif t == "system" and "hook" in str(obj.get("subtype", "")):
            out.append(Event("hook", str(obj.get("hook_event_name") or obj.get("subtype")), {"raw": obj}))
        else:
            # never swallow what Crewcut does not know yet: it goes to the job log with its type
            out.append(Event("raw", str(t or "unknown") + (f"/{obj.get('subtype')}" if obj.get("subtype") else ""),
                             {"raw": obj}))
        return out

    def probe(self, timeout_s: int = 120, model: str | None = None) -> tuple[bool, str]:
        if not self.installed():
            return False, "claude is not installed"
        ok, why = self.login_status()
        if not ok:
            return False, why
        from .. import config
        cmd = [self.binary(), "-p", "Reply with the single word: ok", "--output-format", "json"]
        probe_model = model or config.get("crewcut", "engine.claude.probe_model", "")
        if probe_model:
            cmd += ["--model", probe_model]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s, stdin=subprocess.DEVNULL)
        except subprocess.TimeoutExpired:
            return False, f"no answer within {timeout_s} s"
        try:
            d = json.loads(r.stdout)
        except ValueError:
            return False, scrub((r.stderr or r.stdout).strip()[-300:]) or f"exit {r.returncode}"
        if d.get("is_error"):
            return False, scrub(str(d.get("result"))[:300])
        return True, f"login works ({self.login_kind()})"
