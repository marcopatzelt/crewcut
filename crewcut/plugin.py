"""Crewcut as a Claude Code plugin: the skills, the crew as real agents, and a guard hook, in the form Claude Code loads.

`build()` writes the plugin from the sources of truth (`skills/`, `team/*.md`) into the studio state; every Claude Code
run loads it with `--plugin-dir`. The same folder can be loaded into a plain Claude Code session outside the container.
The crew members appear as `crewcut:<id>` agents. The guard hook stops publishing and spending by a crew member without
the right; publishing and money stay gated in Crewcut's own code as well (cards, checksums, caps), because a hook is a
setting that a user or another plugin can change.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import yaml

from . import __version__, config, paths, team

NAME = "crewcut"


def default_dir() -> Path:
    return paths.state_dir() / "plugin" / NAME


def agent_markdown(ident: dict, model: str | None = None) -> str:
    from .conductor.prompts import WORKSPACE_RULES
    rights = []
    if ident.get("may_spend"):
        rights.append("you may spend money, always through a spend card")
    if ident.get("may_publish"):
        rights.append("you may publish, only after the user's publish card")
    skills = ", ".join(f"`{NAME}:{s}`" for s in ident.get("skills") or []) or "none"
    steps = ", ".join(ident.get("steps") or []) or "any step the Showrunner gives you"
    front = {"name": ident["id"],
             "description": f"{ident.get('name')}: {ident.get('role')} Use for the Crewcut steps: {steps}."}
    if model:
        front["model"] = model
    if ident.get("effort"):
        front["effort"] = ident["effort"]
    from . import ownskills
    own = ownskills.for_identity(ident)
    own_line = ""
    if own:
        own_line = ("Your studio's own skills (the user's; on content, voice and style they win over Crewcut's): "
                    + ", ".join(f"`{ownskills.PLUGIN}:{s['name']}` ({', '.join(s['steps'])})" for s in own)
                    + ". Load the one for your step first, with its adapter note CREWCUT.md when it has one.\n")
    body = (f"You are {ident.get('name')}, a member of the Crewcut crew.\n\n{ident.get('soul', '').strip()}\n\n"
            f"Your skills: {skills}. Read the skill of your step before you start.\n{own_line}"
            f"Your rights: {'; '.join(rights) if rights else 'no spending, no publishing'}.\n\n{WORKSPACE_RULES}")
    return "---\n" + yaml.safe_dump(front, sort_keys=False, allow_unicode=True) + "---\n\n" + body


def hooks() -> dict:
    guard = [{"type": "command", "command": "crewcut hook pre-tool"}]
    return {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": guard},
                                     {"matcher": "SendMessage", "hooks": guard}]}}


def build(dest: Path | None = None) -> Path:
    dest = Path(dest) if dest else default_dir()
    tmp = dest.with_name(dest.name + ".building")
    shutil.rmtree(tmp, ignore_errors=True)
    (tmp / ".claude-plugin").mkdir(parents=True)
    (tmp / ".claude-plugin" / "plugin.json").write_text(json.dumps({
        "name": NAME, "displayName": "Crewcut", "version": __version__,
        "description": "A crew of agents that makes a whole YouTube video: skills, crew members and guard hooks.",
        "author": {"name": "Marco Patzelt"}, "repository": "https://github.com/marcopatzelt/crewcut",
        "license": "MIT", "keywords": ["youtube", "video", "crew"]}, indent=2) + "\n", encoding="utf-8")
    (tmp / "README.md").write_text(
        "# Crewcut plugin\n\nThe Crewcut crew for Claude Code: the video skills (idea, title, script, edit, 3D scenes, "
        "cut check, thumbnail, upload, onboarding), the crew members as agents (`crewcut:showrunner`, "
        "`crewcut:editor` and the others) and a guard hook that stops publishing and spending by a crew member without "
        "that right. Crewcut generates this folder from its `skills/` and `team/` at every start and loads it with "
        "`--plugin-dir`. Load it in your own Claude Code with `claude --plugin-dir <this folder>`. Source and licence "
        "(MIT): https://github.com/marcopatzelt/crewcut\n", encoding="utf-8")
    src = paths.skills_dir()
    for d in sorted(p for p in src.iterdir() if (p / "SKILL.md").is_file()):
        shutil.copytree(d, tmp / "skills" / d.name, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    (tmp / "agents").mkdir()
    models = config.get("crewcut", "engine.claude", {}) or {}
    from . import engines
    for ident in team.all_identities():
        # a crew member called as a subagent: its own role model, else its tier model, else the model of the run that
        # calls it ("inherit"), so the Critic's story pass in the Writer's run reads with the Writer's model
        role_model = (models.get("role_models") or {}).get(ident["id"])
        if role_model and engines.model_ok("claude", str(role_model)) is False:
            role_model = None
        role_model = role_model or models.get("plan_model" if ident.get("model") == "plan" else "work_model") or "inherit"
        (tmp / "agents" / f"{ident['id']}.md").write_text(agent_markdown(ident, role_model), encoding="utf-8")
    (tmp / "hooks").mkdir()
    (tmp / "hooks" / "hooks.json").write_text(json.dumps(hooks(), indent=2) + "\n", encoding="utf-8")
    shutil.rmtree(dest, ignore_errors=True)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp.rename(dest)
    return dest


# ---- the guard hook --------------------------------------------------------------------------------------------------
GUARDED = [
    ("publish", ("crewcut youtube upload",), "publishing"),
    ("spend", ("crewcut compute rent",), "renting machines"),
    ("spend", ("crewcut thumbnail make",), "paid image generation"),
]


def guard_decision(payload: dict, env_identity: str | None) -> tuple[bool, str]:
    """(allowed, reason) for one PreToolUse event. Which crew member runs comes from the hook's agent_type."""
    if payload.get("tool_name") == "SendMessage":
        from . import crewtalk
        episode = os.environ.get("CREWCUT_EPISODE") or None
        sender = str(payload.get("agent_type") or "").split(":")[-1] or env_identity
        return crewtalk.log_live(payload, episode, sender)
    if payload.get("tool_name") != "Bash":
        return True, ""
    cmd = " ".join(str((payload.get("tool_input") or {}).get("command", "")).split())
    agent = str(payload.get("agent_type") or "").split(":")[-1] or (env_identity or "")
    for right, needles, what in GUARDED:
        if not any(n in cmd for n in needles):
            continue
        if right == "spend" and "thumbnail make" in cmd and "--way api" not in cmd and "--way=api" not in cmd:
            continue  # the Codex way costs no extra money
        ident = team.get(agent) if agent else None
        if ident is None:
            return True, ""  # a person at the terminal, or an unknown agent: Crewcut's own code still checks the card
        if not ident.get(f"may_{right}"):
            return False, (f"{ident.get('name', agent)} may not do {what}. Hand it to the crew member who may "
                           "(team/README.md); the user's card is needed in any case.")
    return True, ""
