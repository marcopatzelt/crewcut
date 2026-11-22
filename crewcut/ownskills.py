"""Bring your own skills: the user's private skills from the studio folder, per step and per crew member.

A studio keeps its own skills next to its brand, in `<studio>/skills/<name>/` (a `SKILL.md` with its scripts,
references and data), and names in `<studio>/config/crewcut.toml` where each one applies:

    [[skills.own]]
    name = "my-titles"            # the folder <studio>/skills/my-titles/
    steps = ["title"]             # Crewcut steps; "*" = every step and channel conversations
    roles = ["scout"]             # optional: only these crew members (default: whoever works on those steps)
    replaces = ["title"]          # optional: the Crewcut skills it overrides on content, voice and style
    path = "skills/my-titles"     # optional: another folder inside the studio

Precedence: the user's skill wins over Crewcut's generic skill on content, voice, language, style, structure, data and
checks. Crewcut keeps its tools, commands, cards, episode files and safety rules. A newer explicit user correction (chat
or a dated rule in `brand/rules/`) still wins over an older skill rule.

A skill that was written for another setup may name old paths or tools. Its adapter note `CREWCUT.md` next to
`SKILL.md` maps them to Crewcut; `SKILL.md` itself stays exactly as the user wrote it.

Claude Code loads the skills the proper way: Crewcut builds a small plugin (`studio`, skills `studio:<name>`) whose
skill folders link to the studio folders, so scripts and data are the user's own files. Codex gets the text of the
skills of its step in the prompt, the way it gets the crew member's identity.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path

from . import config, paths

PLUGIN = "studio"
ADAPTER = "CREWCUT.md"
TEXT_LIMIT = 120_000  # characters of skill text per Codex run; beyond that the agent reads the files itself


def _list(v) -> list[str]:
    if v is None:
        return []
    if isinstance(v, str):
        return [v]
    return [str(x) for x in v if str(x).strip()]


def _folder(spec: dict) -> Path | None:
    """The skill folder inside the studio, or None when the configured path leaves the studio."""
    root = paths.studio_root().resolve()
    p = root / str(spec.get("path") or f"skills/{spec['name']}")
    try:
        p.resolve().relative_to(root)  # a link is fine while it stays inside the studio
    except ValueError:
        return None
    return p


def skill_name(folder: Path) -> str | None:
    """The `name:` in the front matter of SKILL.md, or None when the folder is not a skill."""
    try:
        text = (folder / "SKILL.md").read_text(encoding="utf-8")
    except OSError:
        return None
    m = re.match(r"^---\s*\n(.*?)\n---", text, re.S)
    if not m:
        return None
    n = re.search(r"(?m)^name:\s*['\"]?([\w.-]+)", m.group(1))
    return n.group(1) if n else None


def configured() -> list[dict]:
    """Every own skill the studio names, with its folder and whether it is usable (`ok`) or why not (`problem`)."""
    out = []
    for item in config.get("crewcut", "skills.own", None) or []:
        if not isinstance(item, dict) or not re.fullmatch(r"[\w.-]+", str(item.get("name") or "")):
            continue
        spec = {"name": str(item["name"]), "steps": _list(item.get("steps")), "roles": _list(item.get("roles")),
                "replaces": _list(item.get("replaces")), "path": item.get("path")}
        problem, real, adapter = None, None, None
        try:  # a folder the app may not read is reported, never a crash of the job
            folder = _folder(spec)
            if folder is None:
                problem = "its path leaves the studio folder"
            elif not (folder / "SKILL.md").is_file():
                problem = f"no SKILL.md in {folder}"
            elif not skill_name(folder):
                problem = "SKILL.md has no name in its front matter, or it cannot be read"
            real = folder.resolve() if folder else None  # scripts that find files next to them see their real place
            adapter = str(real / ADAPTER) if real and (real / ADAPTER).is_file() else None
        except OSError as e:
            problem = f"cannot be read ({type(e).__name__}: {e.strerror or e})"
        spec.update(folder=str(real) if real else None, ok=problem is None, problem=problem, adapter=adapter)
        out.append(spec)
    return out


def _applies(spec: dict, identity: str | None, step: str | None) -> bool:
    steps = spec["steps"]
    if "*" not in steps and (not step or step not in steps):
        return False
    return not spec["roles"] or (identity or "") in spec["roles"]


def for_job(identity: str | None, step: str | None) -> list[dict]:
    """The usable own skills for one crew member on one step (step None: channel or onboarding work)."""
    return [s for s in configured() if s["ok"] and _applies(s, identity, step)]


def unusable_for_job(identity: str | None, step: str | None) -> list[dict]:
    """Own skills that belong to this job but cannot be used: the crew says so instead of silently going generic."""
    return [s for s in configured() if not s["ok"] and _applies(s, identity, step)]


def for_identity(ident: dict) -> list[dict]:
    """The usable own skills a crew member may need on any of its steps (for its agent file)."""
    steps = set(ident.get("steps") or [])
    return [s for s in configured() if s["ok"] and (not s["roles"] or ident.get("id") in s["roles"])
            and ("*" in s["steps"] or steps & set(s["steps"]))]


def prompt_block(skills: list[dict], unusable: list[dict] | None = None) -> str:
    """What every engine is told about the user's own skills of this job: which, where, and who wins."""
    missing = [f"- The user's own skill `{s['name']}` belongs to this work but cannot be used: {s['problem']}. Tell the "
               "user in one sentence; never guess its content." for s in unusable or []]
    if not skills:
        return "\n".join(missing) + "\n" if missing else ""
    lines = ["Your studio's own skills for this work (written by the user; they come first):"]
    for s in skills:
        extra = f"; adapter note {s['adapter']}" if s["adapter"] else ""
        over = (f"; overrides Crewcut's {', '.join(f'`{x}`' for x in s['replaces'])} on content, voice and style"
                if s["replaces"] else "")
        lines.append(f"- `{PLUGIN}:{s['name']}`: {s['folder']}/SKILL.md{extra}{over}")
    lines += [
        "Load each one first, before any Crewcut skill (Claude Code: the Skill tool with its `studio:` name; "
        "otherwise read its SKILL.md), then read its adapter note and follow the references the skill says to read "
        "for your task. Say in your first progress line which own skill you follow.",
        "Precedence: on content, voice, language, style, structure of deliverables, data and checks the user's skill "
        "wins over Crewcut's generic skills and over your own preferences. Crewcut keeps its tools, commands, cards, "
        "episode files and all safety rules. A newer explicit user correction (chat, a later dated rule in "
        "brand/rules/) still wins over an older skill rule.",
        "Where the skill names old paths, tools or manual steps, follow its adapter note; when none covers it, use the "
        "matching crewcut command and say in one line what you mapped. Run its scripts from its folder with absolute "
        "paths and treat their errors like the errors of a Crewcut check. Never edit the user's SKILL.md.",
    ] + missing
    return "\n".join(lines) + "\n"


def skill_texts(skills: list[dict], limit: int = TEXT_LIMIT) -> str:
    """The SKILL.md and adapter text of these skills, for engines without plugins (Codex)."""
    parts, used = [], 0
    for s in skills:
        folder = Path(s["folder"])
        try:
            text = (folder / "SKILL.md").read_text(encoding="utf-8")
        except OSError:
            continue
        adapter = ""
        if s["adapter"]:
            try:
                adapter = Path(s["adapter"]).read_text(encoding="utf-8")
            except OSError:
                adapter = ""
        piece = (f"\n\n---\nThe user's own skill `{s['name']}` ({folder}/SKILL.md). Scripts and references are in "
                 f"{folder}.\n\n{text}" + (f"\n\nAdapter note for Crewcut ({s['adapter']}):\n\n{adapter}" if adapter
                                            else ""))
        if used + len(piece) > limit:
            parts.append(f"\n\n---\nThe user's own skill `{s['name']}` is too long to include here: read "
                         f"{folder}/SKILL.md" + (f" and {s['adapter']}" if s["adapter"] else "") + " before you start.")
            continue
        parts.append(piece)
        used += len(piece)
    return "".join(parts)


def plugin_dir() -> Path:
    return paths.state_dir() / "plugin" / PLUGIN


def build_plugin(dest: Path | None = None) -> Path | None:
    """The `studio` plugin for Claude Code: one linked folder per usable own skill. None when there is none.

    Links, not copies: the agent runs the user's scripts and writes their data in the user's own folders. The folder is
    rebuilt only when the set of skills changed, so a run that starts at the same moment never sees it half built.
    """
    dest = Path(dest) if dest else plugin_dir()
    skills = [s for s in configured() if s["ok"]]
    if not skills:
        if dest.exists():
            shutil.rmtree(dest, ignore_errors=True)
        return None
    want = {s["name"]: os.path.relpath(s["folder"], dest / "skills") for s in skills}
    manifest = dest / ".crewcut-links.json"
    try:
        if json.loads(manifest.read_text(encoding="utf-8")) == want and all(
                (dest / "skills" / n / "SKILL.md").is_file() for n in want):
            return dest
    except (OSError, ValueError):
        pass
    tmp = dest.with_name(f"{dest.name}.building-{os.getpid()}")
    shutil.rmtree(tmp, ignore_errors=True)
    (tmp / ".claude-plugin").mkdir(parents=True)
    (tmp / ".claude-plugin" / "plugin.json").write_text(json.dumps({
        "name": PLUGIN, "displayName": "Studio skills",
        "description": "The user's own skills from the studio folder, loaded by Crewcut."}, indent=2) + "\n",
        encoding="utf-8")
    (tmp / "skills").mkdir()
    for name, target in want.items():
        (tmp / "skills" / name).symlink_to(target, target_is_directory=True)
    (tmp / ".crewcut-links.json").write_text(json.dumps(want, indent=1) + "\n", encoding="utf-8")
    old = dest.with_name(f"{dest.name}.old-{os.getpid()}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.rename(old)
    tmp.rename(dest)
    shutil.rmtree(old, ignore_errors=True)
    return dest


__all__ = ["configured", "for_job", "unusable_for_job", "for_identity", "prompt_block", "skill_texts", "build_plugin", "plugin_dir",
           "PLUGIN", "ADAPTER"]
