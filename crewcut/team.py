"""The crew: identities in team/*.md (YAML front matter + a short soul that rides the system prompt)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from . import paths

SOUL_LIMIT = 4000  # characters; long knowledge belongs in skills, not in the soul


def parse(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text.strip()
    _, front, body = text.split("---", 2)
    return yaml.safe_load(front) or {}, body.strip()


@lru_cache(maxsize=1)
def _load_all(team_dir: str) -> tuple[dict, ...]:
    out = []
    for p in sorted(Path(team_dir).glob("*.md")):
        if p.name.lower() == "readme.md":
            continue
        meta, soul = parse(p.read_text(encoding="utf-8"))
        if not meta.get("id"):
            continue
        meta = {"skills": [], "steps": [], "may_spend": False, "may_publish": False, "model": "work", "sources": [],
                **meta, "soul": soul[:SOUL_LIMIT]}
        out.append(meta)
    return tuple(out)


def all_identities() -> list[dict]:
    return [dict(x) for x in _load_all(str(paths.team_dir()))]


def get(identity: str) -> dict | None:
    for x in all_identities():
        if x["id"] == identity:
            return x
    return None


def for_step(step: str) -> dict | None:
    """The crew member who owns a step (first match in team order)."""
    order = ["showrunner", "scout", "writer", "editor", "critic", "designer", "publisher", "brand"]
    ids = sorted(all_identities(), key=lambda x: order.index(x["id"]) if x["id"] in order else 99)
    for x in ids:
        if x["id"] != "showrunner" and step in (x.get("steps") or []):
            return x
    return get("showrunner")


def public(x: dict, with_soul: bool = False) -> dict:
    keys = ["id", "name", "role", "mark", "skills", "steps", "may_spend", "may_publish", "model", "sources"]
    d = {k: x.get(k) for k in keys}
    if with_soul:
        d["soul"] = x.get("soul", "")
    return d
