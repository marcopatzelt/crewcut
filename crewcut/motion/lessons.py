"""The channel's motion lessons: ``brand/rules/motion.md`` in the user's style pack (motion plan 3.8).

One lesson is one dated line with an id, the rule, the evidence and its source::

    - 2026-11-17: [2026-11-17-3] Every exit from a full-frame piece is caused by a motion. Evidence: 003-local-llms
      1:12, review/motion-v002/m3/sheet.jpg (source: review)

(on one line). The line also parses as an ordinary rule (``brand.parse_rules``). The director reads the lessons before
every motion pass and cites their ids in column (c); the Critic appends 1 to 5 after each video. Above
``MERGE_ABOVE`` lines the Critic proposes a merge. Lessons are rules with evidence, not a diary.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

from .. import paths

MERGE_ABOVE = 40
SOURCES = ("review", "user", "retention")
LINE = re.compile(r"^\s*-\s*(?P<date>\d{4}-\d{2}-\d{2})\s*:\s*(?:\[(?P<id>[^\]\s]+)\]\s*)?(?P<rest>.+?)\s*"
                  r"(?:\((?:source|Source):\s*(?P<source>[^)]*)\))?\s*$")
HEAD = "# Motion lessons\n\nRules with evidence. The director reads them before every motion pass and cites their ids.\n\n"


def read_path() -> Path:
    return paths.brand_dir() / "rules" / "motion.md"


def write_path() -> Path:
    from .. import approvals
    d = approvals.ensure_user_pack() / "rules"
    d.mkdir(parents=True, exist_ok=True)
    return d / "motion.md"


def parse(text: str) -> list[dict]:
    out = []
    for n, raw in enumerate(text.splitlines(), 1):
        m = LINE.match(raw)
        if not m:
            continue
        rule, _, evidence = m.group("rest").partition(" Evidence: ")
        out.append({"id": m.group("id"), "date": m.group("date"), "rule": rule.strip(),
                    "evidence": evidence.strip(), "source": (m.group("source") or "").strip(), "line": n})
    return out


def read() -> list[dict]:
    p = read_path()
    return parse(p.read_text(encoding="utf-8")) if p.is_file() else []


def ids() -> set[str]:
    return {x["id"] for x in read() if x["id"]}


def _today() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


def _clean(s: str) -> str:
    return " ".join(str(s).replace("(", "[").replace(")", "]").split())


def evidence_text(ev: dict) -> str:
    parts = [str(ev.get("episode") or "").strip()]
    if ev.get("time") not in (None, ""):
        t = ev["time"]
        parts[0] += f" {_tc(t) if isinstance(t, (int, float)) else str(t).strip()}"
    if ev.get("card"):
        parts.append(f"card #{ev['card']}")
    if ev.get("frame"):
        parts.append(str(ev["frame"]).strip())
    return _clean(", ".join(p for p in parts if p))


def _tc(t: float) -> str:
    m, s = divmod(max(0.0, float(t)), 60)
    return f"{int(m)}:{int(s):02d}"


def check(rule: str, evidence: dict, source: str) -> list[str]:
    """Why a lesson cannot be written. A lesson needs a rule, a source and evidence: the episode, the time and the
    frame (a lesson from the user's words may name the card instead of time and frame)."""
    out = []
    if not str(rule or "").strip():
        out.append("the lesson has no rule")
    if source not in SOURCES:
        out.append(f"source must be one of {', '.join(SOURCES)}")
    ev = evidence or {}
    if not ev.get("episode"):
        out.append("evidence needs the episode")
    if source == "user" and ev.get("card"):
        return out
    if ev.get("time") in (None, ""):
        out.append("evidence needs the time in the video")
    if not ev.get("frame"):
        out.append("evidence needs a frame (a file of the episode that shows it)")
    return out


def append(rule: str, evidence: dict, source: str, date: str | None = None) -> dict:
    """Append one lesson to ``brand/rules/motion.md`` and return it (with its new id)."""
    problems = check(rule, evidence, source)
    if problems:
        raise ValueError("No lesson without evidence: " + "; ".join(problems))
    date = date or _today()
    p = write_path()
    text = p.read_text(encoding="utf-8") if p.is_file() else HEAD
    if not text.endswith("\n"):
        text += "\n"
    same_day = [x for x in parse(text) if x["id"] and x["id"].startswith(date + "-")]
    n = max([int(x["id"].rsplit("-", 1)[1]) for x in same_day if x["id"].rsplit("-", 1)[1].isdigit()], default=0) + 1
    lid = f"{date}-{n}"
    rule_txt = _clean(rule).rstrip(".") + "."
    line = f"- {date}: [{lid}] {rule_txt} Evidence: {evidence_text(evidence)} (source: {source})"
    p.write_text(text + line + "\n", encoding="utf-8")
    return {"id": lid, "date": date, "rule": rule_txt, "evidence": evidence_text(evidence), "source": source}


def needs_merge() -> bool:
    return len(read()) > MERGE_ABOVE
