"""The Humanizer pass: every script draft goes through Humanizer (blader/humanizer) before the user sees it.

The Writer writes the draft, runs the Humanizer skill in its "Embedded" mode with the user's own spoken words as the
voice sample (`brand/voice/`), writes the result as the script version, and records the pass:

    crewcut humanize record --draft work/script-draft-v003.md --final brief/SCRIPT-v003.md --why "§1, §6"

The record (`review/humanizer-SCRIPT-v003.json`) holds what changed, sentence by sentence, computed here from the two
files (not reported by the model), plus the Humanizer version and the voice samples used. A script card needs that
record for the exact file (checksum) unless the user switched the pass off (`[humanizer] enabled = false`) or Humanizer
could not be installed; the card then says so. The card shows "Humanized" with the changes, collapsed.
"""

from __future__ import annotations

import difflib
import json
import re
from pathlib import Path

from . import extskills, paths

MAX_CHANGES = 60
SENTENCE = re.compile(r"(?<=[.!?…])\s+|\n+")


class Missing(Exception):
    """A script card without its Humanizer record. The text says what to run."""


def body(text: str) -> str:
    """The spoken part of a script: everything above the first line that is only `---`."""
    return re.split(r"(?m)^---\s*$", text, maxsplit=1)[0]


def sentences(text: str) -> list[str]:
    out = []
    for part in SENTENCE.split(body(text)):
        s = " ".join(part.split()).strip()
        if s and not s.startswith("#"):
            out.append(s)
    return out


def changes(draft: str, final: str) -> list[dict]:
    a, b = sentences(draft), sentences(final)
    out: list[dict] = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes():
        if op == "equal":
            continue
        out.append({"before": " ".join(a[i1:i2]), "after": " ".join(b[j1:j2])})
    return out[:MAX_CHANGES]


def voice_samples() -> list[str]:
    d = paths.user_brand_dir() / "voice"
    return sorted(str(p.relative_to(paths.studio_root())) for p in d.glob("*.md")) if d.is_dir() else []


def record_path(final: Path) -> Path:
    ep = final.parent.parent
    return ep / "review" / f"humanizer-{final.stem}.json"


def record(episode_dir: Path, draft: str, final: str, why: str = "") -> dict:
    from .approvals import sha256
    d = paths.inside(episode_dir, draft)
    f = paths.inside(episode_dir, final)
    if not d.is_file() or not f.is_file():
        raise FileNotFoundError(f"need both files: {draft} and {final}")
    hz = extskills.current("humanizer")
    rec = {
        "file": final,
        "sha256": sha256(f),
        "draft": draft,
        "skill": {k: hz.get(k) for k in ("name", "version", "repo", "license")} if hz else None,
        "mode": "embedded" if voice_samples() else "plain",
        "voice": voice_samples(),
        "why": why.strip(),
        "changes": changes(d.read_text(encoding="utf-8"), f.read_text(encoding="utf-8")),
    }
    rec["count"] = len(rec["changes"])
    out = record_path(f)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return rec


def for_card(episode_dir: Path, kind: str, file: str | None) -> dict | None:
    """What a card shows about the Humanizer pass; raises Missing for a script card without the pass."""
    if kind not in ("script", "title") or not file:
        return None
    if not extskills.humanizer_enabled():
        return {"skipped": "switched off in this studio"} if kind == "script" else None
    from .approvals import sha256
    f = paths.inside(episode_dir, file)
    rp = record_path(f)
    rec = None
    if rp.is_file():
        try:
            rec = json.loads(rp.read_text(encoding="utf-8"))
        except ValueError:
            rec = None
    if rec and f.is_file() and rec.get("sha256") == sha256(f):
        skill = rec.get("skill") or {}
        return {"version": skill.get("version"), "repo": skill.get("repo"), "mode": rec.get("mode"),
                "voice": rec.get("voice") or [], "why": rec.get("why") or "", "count": rec.get("count", 0),
                "changes": rec.get("changes") or []}
    if kind != "script":
        return None
    if extskills.current("humanizer") is None:
        return {"skipped": "Humanizer could not be installed (offline at start)"}
    raise Missing(f"The script goes through the Humanizer before its card. Run the skill on the draft, write the result "
                  f"to {file}, then: crewcut humanize record --draft <draft> --final {file}")


__all__ = ["record", "for_card", "changes", "sentences", "voice_samples", "Missing"]
