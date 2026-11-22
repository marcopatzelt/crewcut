"""Codex, the second engine (beta): the user's own `codex` CLI, headless, on their ChatGPT subscription.

Login without forms: `crewcut engine login codex` runs `codex login --device-auth` inside the container and posts the
link and the one-time code into the chat; the user opens the link and types the code on OpenAI's page. Device-code login
must be switched on once in the ChatGPT security settings. Credentials stay in CODEX_HOME (the engine volume,
`/opt/engine/codex-home`), never in the studio folder; Crewcut never reads that file.

Not yet run on a real episode: marked beta in the README.
"""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Callable

from .base import Engine, Event, Task, scrub

DEVICE_URL = re.compile(r"https://\S+")
DEVICE_CODE = re.compile(r"\b([A-Z0-9]{4}-[A-Z0-9]{4,5})\b")


def codex_home() -> str:
    return os.environ.get("CODEX_HOME") or os.path.join(os.environ.get("CREWCUT_ENGINE_PREFIX", "/opt/engine"),
                                                         "codex-home")


def describe_item(item: dict) -> tuple[str, str] | None:
    """(kind, text) for a Codex item, or None when it is not worth a line."""
    t = item.get("type") or item.get("item_type") or ""
    if t in ("agent_message", "assistant_message"):
        return "text", str(item.get("text") or "")
    if t == "command_execution":
        return "tool", "$ " + str(item.get("command") or "")[:120]
    if t == "file_change":
        files = [c.get("path", "") for c in item.get("changes") or []]
        return "tool", "Edit " + ", ".join(os.path.basename(f) for f in files[:3])
    if t == "mcp_tool_call":
        return "tool", f"{item.get('server', '')} {item.get('tool', '')}".strip()
    if t == "web_search":
        return "tool", "WebSearch " + str(item.get("query") or "")[:100]
    if t in ("todo_list", "plan_update"):
        todos = item.get("items") or item.get("plan") or []
        cur = next((x.get("text") or x.get("step") for x in todos if not x.get("completed")
                    and x.get("status") not in ("completed",)), None)
        return "step", cur or "Planning the steps"
    if t == "error":
        return "error", str(item.get("message") or "")
    return None


class Codex(Engine):
    name = "codex"
    label = "Codex"
    beta = True
    binary_name = "codex"
    npm_package = "@openai/codex"

    def env(self) -> dict[str, str]:
        return {"CODEX_HOME": codex_home()}

    def login_status(self) -> tuple[bool, str]:
        if not self.installed():
            return False, "codex is not installed"
        try:
            r = subprocess.run([self.binary(), "login", "status"], capture_output=True, text=True, timeout=30,
                               env={**os.environ, **self.env()}, stdin=subprocess.DEVNULL)
        except subprocess.TimeoutExpired:
            return False, "codex login status did not answer"
        msg = scrub((r.stdout or r.stderr).strip().splitlines()[0] if (r.stdout or r.stderr).strip() else "")
        if r.returncode == 0 and "not logged in" not in msg.lower():
            return True, msg or "logged in"
        return False, "not logged in: say \"use Codex\" in the chat, or run `crewcut engine login codex`"

    def command(self, task: Task) -> list[str]:
        # Codex has no separate system prompt flag in exec mode; the identity and the house rules go first in the
        # prompt. Layer 1 (fixed): exec --json and the resume subcommand. Layer 2: sandbox, approvals, model, effort.
        # Layer 3: extra_args and -c key=value pairs, passed through unchanged after layer 2 (later -c wins in Codex).
        opts = task.engine_options or {}
        soul = opts.get("soul") or ""
        prompt = (f"{soul}\n\n" if soul else "") + f"{task.system}\n\n---\n\nYOUR TASK\n\n{task.prompt}"
        cmd = [self.binary() or "codex", "exec", "--json", "--skip-git-repo-check", "--sandbox", "danger-full-access",
               "-c", 'approval_policy="never"']
        if task.model:
            cmd += ["-m", task.model]
        if task.effort:
            cmd += ["-c", f'model_reasoning_effort="{task.effort}"']
        for kv in opts.get("config") or []:
            cmd += ["-c", kv]
        cmd += [a for a in task.extra_args if a not in ("--json",)]
        if task.resume:
            cmd += ["resume", task.resume]  # untested: exec flags before the resume subcommand
        return cmd + [prompt]

    def parse(self, obj: dict, state: dict) -> list[Event]:
        out: list[Event] = []
        t = obj.get("type", "")
        if t == "thread.started" and obj.get("thread_id"):
            state["session"] = obj["thread_id"]
            out.append(Event("session", data={"session": obj["thread_id"]}))
        elif t in ("item.started", "item.completed"):
            item = obj.get("item") or {}
            d = describe_item(item)
            if d and (t == "item.completed" or d[0] != "text"):
                kind, text = d
                if kind == "text" and text.strip():
                    state["texts"].append(text)
                if text.strip():
                    out.append(Event(kind, text, {"type": item.get("type")}))
        elif t == "turn.completed":
            u = obj.get("usage") or {}
            tot = state.setdefault("usage", {})
            for k, v in u.items():
                if isinstance(v, (int, float)):
                    tot[k] = tot.get(k, 0) + v
            state["turns"] = int(state.get("turns") or 0) + 1
            out.append(Event("usage", data={"usage": dict(tot)}))
        elif t in ("turn.failed", "error"):
            err = obj.get("error") or {}
            state["error"] = str(err.get("message") if isinstance(err, dict) else err or obj.get("message") or t)[:400]
            out.append(Event("error", state["error"]))
        elif t not in ("turn.started", "item.updated"):
            out.append(Event("raw", str(t or "unknown"), {"raw": obj}))  # never swallow an event Crewcut does not know
        return out

    def probe(self, timeout_s: int = 180, model: str | None = None) -> tuple[bool, str]:
        ok, why = self.login_status()
        if not ok:
            return False, why
        cmd = [self.binary(), "exec", "--json", "--skip-git-repo-check", "--sandbox", "read-only"]
        if model:
            cmd += ["-m", model]
        try:
            r = subprocess.run([*cmd, "Reply with the single word: ok"], capture_output=True, text=True, timeout=timeout_s,
                               env={**os.environ, **self.env()}, stdin=subprocess.DEVNULL)
        except subprocess.TimeoutExpired:
            return False, f"no answer within {timeout_s} s"
        if r.returncode != 0:
            return False, scrub((r.stderr or r.stdout).strip()[-300:]) or f"exit {r.returncode}"
        return True, "login works (ChatGPT subscription)"

    def device_login(self, on_prompt: Callable[[str, str | None], None], timeout_s: int = 900) -> tuple[bool, str]:
        """Run `codex login --device-auth`; hand the link and code to on_prompt(url, code); wait for the user."""
        if not self.installed():
            return False, "codex is not installed"
        os.makedirs(codex_home(), mode=0o700, exist_ok=True)
        proc = subprocess.Popen([self.binary(), "login", "--device-auth"], stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, env={**os.environ, **self.env()},
                                stdin=subprocess.DEVNULL, start_new_session=True)
        url = code = None
        told = False
        assert proc.stdout is not None
        try:
            for line in proc.stdout:
                clean = re.sub(r"\x1b\[[0-9;]*m", "", line)
                url = url or (DEVICE_URL.search(clean).group(0) if DEVICE_URL.search(clean) else None)
                code = code or (DEVICE_CODE.search(clean).group(1) if DEVICE_CODE.search(clean) else None)
                if url and code and not told:
                    on_prompt(url, code)
                    told = True
            proc.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            proc.kill()
            return False, "the code expired; say \"use Codex\" again"
        if url and not told:
            on_prompt(url, code)
        return self.login_status()
