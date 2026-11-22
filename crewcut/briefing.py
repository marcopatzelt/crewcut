"""The channel brief: what every crew job knows about the channel before it starts, on both engines.

Three parts, all read from the studio, none invented:
- the channel facts of the style pack (`brand/channel.json`): name, niche, audience, language, tone, topics to avoid;
- the user's own brief, `brand/brief.md`: a short text about what the channel is for, the business behind it and
  what worked (cut at BRIEF_LIMIT characters; the agent is told where the whole file is);
- the real results of published videos that Crewcut measured (`episodes/*/review/results-*.json`, written by
  `crewcut youtube results`). Without measurements there is no results section, never a guess.
"""

from __future__ import annotations

import json
from pathlib import Path

from . import brand, paths

BRIEF_LIMIT = 6000
RESULT_ROWS = 12
FACTS = (("name", "Channel"), ("url", "Link"), ("niche", "Niche"), ("audience", "Audience"),
         ("language", "Language"), ("country", "Country"), ("tone", "Tone"), ("topics_to_avoid", "Avoid"),
         ("closing_line", "Closing line"))


def brief_path() -> Path:
    return paths.user_brand_dir() / "brief.md"


def channel_facts(pack=None) -> list[str]:
    pack = pack or brand.load()
    if pack.is_neutral:
        return []
    out = []
    for key, label in FACTS:
        v = pack.value(f"channel.{key}")
        if v in (None, "", [], {}):
            continue
        out.append(f"{label}: {', '.join(map(str, v)) if isinstance(v, list) else v}")
    return out


def results() -> list[dict]:
    """The newest measured result of every episode, newest first."""
    rows = []
    for ep in sorted(paths.studio_root().glob("episodes/*/review/results-*.json")):
        try:
            r = json.loads(ep.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(r, dict) or not isinstance(r.get("metrics"), dict):
            continue
        r["_file"] = ep
        rows.append(r)
    newest: dict[str, dict] = {}
    for r in rows:
        key = str(r.get("episode") or r["_file"].parents[1].name)
        if key not in newest or str(r.get("fetched_at", "")) > str(newest[key].get("fetched_at", "")):
            newest[key] = r
    return sorted(newest.values(), key=lambda r: str(r.get("fetched_at", "")), reverse=True)[:RESULT_ROWS]


def _title(episode_dir: Path) -> str:
    try:
        return str(json.loads((episode_dir / "project.json").read_text(encoding="utf-8")).get("title") or "")
    except (OSError, ValueError):
        return ""


def result_lines() -> list[str]:
    out = []
    for r in results():
        m, period = r["metrics"], r.get("period") or {}
        parts = [f"{m['views']:g} views" if isinstance(m.get("views"), (int, float)) else None,
                 f"{m['averageViewPercentage']:.0f} % watched" if isinstance(m.get("averageViewPercentage"),
                                                                             (int, float)) else None,
                 f"+{m['subscribersGained']:g} subscribers" if isinstance(m.get("subscribersGained"),
                                                                         (int, float)) else None]
        ep_dir = r["_file"].parents[1]
        title = _title(ep_dir)
        out.append(f"- {ep_dir.name}{f' “{title}”' if title else ''}, {period.get('start')} to {period.get('end')}: "
                   + ", ".join(p for p in parts if p))
    return out


def text() -> str:
    """The brief for the system prompt, or "" for a studio without a brand, a brief and results."""
    sections = []
    facts = channel_facts()
    if facts:
        sections.append("Channel facts (brand/channel.json):\n" + "\n".join(f"- {f}" for f in facts))
        lang = brand.load().value("channel.language")
        if lang:
            sections.append(f"Everything viewers will see (titles, scripts, image text, descriptions) is in the channel "
                            f"language ({lang}), unless the user asks for another language for one piece.")
    p = brief_path()
    try:
        own = p.read_text(encoding="utf-8").strip()
    except OSError:
        own = ""
    if own:
        if len(own) > BRIEF_LIMIT:
            own = own[:BRIEF_LIMIT].rsplit("\n", 1)[0] + f"\n(shortened; read the whole brief in {p})"
        sections.append(f"The user's channel brief ({p}):\n{own}")
    lines = result_lines()
    if lines:
        sections.append("Measured results of published videos (Crewcut's YouTube data, newest first):\n"
                        + "\n".join(lines))
    if not sections:
        return ""
    return "CHANNEL BRIEF (read before you plan; it is evidence and direction, not a new approval)\n" + \
        "\n\n".join(sections) + "\n"


__all__ = ["text", "brief_path", "channel_facts", "results", "result_lines"]
