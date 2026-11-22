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


MODEL_PROBE = "engine_model_probe"   # db key: {"<engine>": {"<model>": true|false}} from the start-up probe


def model_ok(name: str, model: str) -> bool | None:
    """Whether the start-up probe could run this model on the user's plan: True, False, or None (not probed yet)."""
    import json
    try:
        seen = json.loads(db.kv_get(MODEL_PROBE) or "{}")
    except ValueError:
        return None
    v = (seen.get(normalize(name)) or {}).get(model)
    return v if isinstance(v, bool) else None


def configured_models(name: str | None = None) -> list[str]:
    """The step and role models of an engine (step_models, role_models): the ones the start-up probe tries."""
    key = normalize(name or current_name())
    sect = config.get("crewcut", f"engine.{key}", {}) or {}
    picks = [*(sect.get("step_models") or {}).values(), *(sect.get("role_models") or {}).values()]
    return list(dict.fromkeys(str(m) for m in picks if m))


def model_for(identity: dict | None, step: str | None, name: str | None = None) -> str | None:
    """The model of one run. role_models[<crew member>] wins, then step_models[<step>], then plan_model or work_model
    by the crew member's tier. A step or role model the start-up probe found unusable on the user's plan is skipped,
    so the run falls back to the tier model instead of failing."""
    key = normalize(name or current_name())
    sect = config.get("crewcut", f"engine.{key}", {}) or {}
    ident = identity or {}
    tier = sect.get("plan_model" if ident.get("model") == "plan" else "work_model") or None
    for pick in ((sect.get("role_models") or {}).get(ident.get("id") or ""),
                 (sect.get("step_models") or {}).get(step or "")):
        if pick and model_ok(key, str(pick)) is not False:
            return str(pick)
    return tier


__all__ = ["ENGINES", "Engine", "Event", "RunResult", "Task", "configured_models", "current", "current_name", "get",
           "model_for", "model_ok", "models", "normalize", "scrub", "use"]
