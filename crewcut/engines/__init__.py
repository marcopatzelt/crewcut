"""The two engines: Claude Code (primary) and Codex (beta). Both run on the user's own subscription.

The user picks one once by saying it ("use Codex"); the choice is stored in the studio. Default: Claude Code.
"""

from __future__ import annotations

from .. import config, db
from .base import Engine, Event, RunResult, Task, scrub
from .claude_code import ClaudeCode
from .codex import Codex

ENGINES: dict[str, type[Engine]] = {"claude": ClaudeCode, "codex": Codex}
ALIASES = {"claude": "claude", "claude-code": "claude", "claude_code": "claude", "codex": "codex"}


def normalize(name: str) -> str:
    key = ALIASES.get(name.strip().lower())
    if not key:
        raise ValueError(f"Crewcut supports two engines: Claude Code and Codex (got {name!r}).")
    return key


def get(name: str | None = None) -> Engine:
    return ENGINES[normalize(name or current_name())]()


def current_name() -> str:
    chosen = db.kv_get("engine")
    return normalize(chosen or config.get("crewcut", "engine.name", "claude"))


def current() -> Engine:
    return get(current_name())


def use(name: str) -> Engine:
    key = normalize(name)
    db.kv_set("engine", key)
    return ENGINES[key]()


def models(name: str | None = None) -> dict[str, str | None]:
    """plan_model and work_model for an engine, from [engine.<name>] in config/crewcut.toml (empty = engine default)."""
    key = normalize(name or current_name())
    sect = config.get("crewcut", f"engine.{key}", {}) or {}
    return {"plan": sect.get("plan_model") or None, "work": sect.get("work_model") or None}


__all__ = ["ENGINES", "Engine", "Event", "RunResult", "Task", "current", "current_name", "get", "models", "normalize",
           "scrub", "use"]
