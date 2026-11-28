"""Title and thumbnail pairs against the test (docs/formats.md): a pair whose claim the measured result reverses never
reaches the title card.

A show-format episode's plan writes brief/PACKAGING-v001.md before the test: title and thumbnail pairs, each a section
`## Pair A …` (German `## Paar A …`) with a line `- Title: …` (`- Titel: …`). After the test the title step checks every
pair against the test result and writes the next PACKAGING-vNNN.md with one line per pair:

    - Test: carries                  German: - Test: trägt
    - Test: reverses, <why>          German: - Test: dreht um, <warum>

A pair reverses when its title or image says the opposite of what was measured (the title says "not as current as you
think", the test found it more current) or when its formula's condition is not met. The title card (`crewcut card
propose --kind title`) is refused while the newest packaging is older than the test result or leaves a pair unchecked,
and when it has no pair in this shape (a table is not read), and an option that is the title of a reversed pair (in
any packaging version written after the result) is refused. A dropped pair stays in the file with its `- Test:
reverses` line. An episode without a show format, a test result or a packaging file is not checked.
"""

from __future__ import annotations

import re
from pathlib import Path

PACKAGING_FILE = re.compile(r"^PACKAGING-v(\d{3,})[^/]*\.md$", re.I)
# "## Paar A: …", "## Pair 2 …"; not "## Paar mit dem besten Wert"
PAIR = re.compile(r"^(#{2,4})\s*(?i:Paar|Pair)\s+([A-Z]|\d{1,2})\b.*$", re.M)
BOLD_LABEL = re.compile(r"^(\s*[-*•]?\s*)(?:\*\*|__)([^*_\n]{1,30}?)(?:\*\*|__)")   # "- **Titel:** …" -> "- Titel: …"
TITLE = re.compile(r"^\s*[-*•]?\s*(?:Titel|Title)\s*:\s*(.+?)\s*$", re.I)
VERDICT = re.compile(r"^\s*[-*•]?\s*Test\s*:\s*(.+?)\s*$", re.I)
# the verdict is the start of the `Test:` line; what follows is the reason ("carries (v001 contradicted the result)")
REVERSES = re.compile(r"^\W*(?:dreht\s+(?:es\s+)?um|umgedreht|widerlegt|widerspricht|gegenteil|revers\w*|contradict\w*|"
                      r"opposite|(?:trägt|hält|stimmt|passt)\s+nicht|nicht\s+(?:gedeckt|getragen)|"
                      r"not\s+(?:supported|carried|true)|does\s*n[o'’]?t\s+(?:carry|hold)|fails?)\b", re.I)
CARRIES = re.compile(r"^\W*(?:trägt|carries|carried|holds|hält|gedeckt|supported|stimmt|passt)\b", re.I)
MARKS = "`- Test: carries` or `- Test: reverses` (German: `- Test: trägt` or `- Test: dreht um`)"
SHAPE = ("each pair a section `## Pair A …` (German `## Paar A …`) with a line `- Title: …` (`- Titel: …`) and one "
         f"line {MARKS}")


class Unchecked(ValueError):
    """The title card may not go to the user: a pair is not checked against the test, or an option reverses it."""


def versions(episode: str) -> list[Path]:
    """Every brief/PACKAGING-vNNN.md of an episode, oldest first."""
    from . import paths
    d = paths.episode_dir(episode) / "brief"
    if not d.is_dir():
        return []
    found = []
    for p in d.iterdir():
        m = PACKAGING_FILE.match(p.name)
        if m:
            found.append((int(m.group(1)), p))
    return [p for _, p in sorted(found)]


def newest(episode: str) -> Path | None:
    """The newest brief/PACKAGING-vNNN.md of an episode, or None."""
    found = versions(episode)
    return found[-1] if found else None


def _clean(title: str) -> str:
    """The title itself: the bold or quoted span when there is one, else the text without a trailing note in
    parentheses ("(47 Zeichen, im Titel-Schritt kürzen)") or after " · " / " | "."""
    t = title.strip()
    m = re.search(r"\*\*(.+?)\*\*|__(.+?)__", t) or re.match(r"^[\"„“”«‚‘']\s*(.+?)\s*[\"“”»‘’']", t)
    if m:
        return next(g for g in m.groups() if g).strip()
    t = re.split(r"\s+[·|]\s+", t, maxsplit=1)[0]
    while re.search(r"\s*\([^()]*\)\s*$", t):
        t = re.sub(r"\s*\([^()]*\)\s*$", "", t)
    return t.strip().strip("\"'„“”‚‘’«»`").strip()


def _key(title: str) -> str:
    t = re.sub(r"^\s*(?:[A-Z]|\d{1,2})[).:]\s+", "", title or "")   # an option's own label: "A) …", "2. …"
    return re.sub(r"[\W_]+", " ", _clean(t)).strip().casefold()


def verdict(text: str) -> str | None:
    """"reverses", "carries" or None for the text of a `Test:` line."""
    if REVERSES.search(text):
        return "reverses"
    return "carries" if CARRIES.search(text) else None


def pairs(text: str) -> list[dict]:
    """The pairs of a packaging file in order: {"pair": "A", "title": … or None, "test": "carries"|"reverses"|None}."""
    out = []
    heads = list(PAIR.finditer(text or ""))
    for i, h in enumerate(heads):
        block = text[h.end():heads[i + 1].start() if i + 1 < len(heads) else len(text)]
        block = re.split(rf"(?m)^#{{1,{len(h.group(1))}}}\s", block, maxsplit=1)[0]   # the next section ends it
        title = test = None
        for ln in block.splitlines():
            ln = BOLD_LABEL.sub(r"\1\2", ln)
            if title is None and (m := TITLE.match(ln)):
                title = _clean(m.group(1)) or None
            if test is None and (m := VERDICT.match(ln)):
                test = verdict(m.group(1))
        out.append({"pair": h.group(2).upper(), "title": title, "test": test})
    return out


def _same(option: str, title: str) -> bool:
    t = _key(title)
    return bool(t) and _key(option) == t


def problems(episode: str | None, options: list[str] | None = None) -> list[str]:
    """Why a title card of this episode may not go to the user yet; empty when it may (or nothing is checked)."""
    from . import episodes, showformats
    if not episode or episode.startswith("_"):
        return []
    try:
        project = episodes.read(episode)
    except (FileNotFoundError, ValueError):
        return []
    if not project.get("show_format"):
        return []
    result = showformats.test_result(episode)
    pack = newest(episode)
    if result is None or pack is None:
        return []
    if pack.stat().st_mtime < result.stat().st_mtime:
        return [f"brief/{pack.name} is older than the test result brief/{result.name}. Check every title and thumbnail "
                f"pair against the result and write the next PACKAGING version, {SHAPE}; a pair whose claim the "
                "result reverses is dropped or rebuilt in the measured direction."]
    try:
        ps = [p for p in pairs(pack.read_text(encoding="utf-8")) if p["title"]]
    except (OSError, ValueError):
        return []
    if not ps:
        return [f"brief/{pack.name} has no title and thumbnail pair the check can read (a table is not read): "
                f"{SHAPE}."]
    out = []
    unchecked = [p["pair"] for p in ps if p["test"] is None]
    if unchecked:
        out.append(f"brief/{pack.name}: pair {', '.join(unchecked)} is not checked against brief/{result.name}; give "
                   f"every pair one line, {MARKS}.")
    # a reversed pair stays refused when a later version dropped it: every check written after the result counts
    reversed_ = []
    for v in versions(episode):
        if v.stat().st_mtime >= result.stat().st_mtime:
            try:
                reversed_ += [(v, p) for p in pairs(v.read_text(encoding="utf-8"))
                              if p["title"] and p["test"] == "reverses"]
            except (OSError, ValueError):
                continue
    for i, o in enumerate(options or [], 1):
        hit = next(((v, p) for v, p in reversed_ if _same(o, p["title"])), None)
        if hit:
            out.append(f"Option {i} ({o!r}) is pair {hit[1]['pair']}, and the test result reverses its claim "
                       f"(brief/{hit[0].name}): drop it or rebuild it in the measured direction.")
    return out


def require(episode: str | None, options: list[str] | None = None) -> None:
    """Raise Unchecked when the title card may not go to the user (see problems)."""
    found = problems(episode, options)
    if found:
        raise Unchecked("The title card may not go to the user: " + " ".join(found))


def critic_note(episode: str | None) -> str:
    """The hard question of the title step's Critic in a show-format episode with a test result; "" otherwise."""
    from . import episodes, showformats
    if not episode or episode.startswith("_"):
        return ""
    try:
        if not episodes.read(episode).get("show_format"):
            return ""
    except (FileNotFoundError, ValueError):
        return ""
    result = showformats.test_result(episode)
    if result is None:
        return ""
    pack = newest(episode)
    where = f"brief/{pack.name}" if pack else "the packaging file"
    return (f"TITLE AGAINST THE TEST (a hard check, never a hint): read brief/{result.name}. For every title and "
            f"thumbnail pair in {where} say whether the measured result carries its claim or reverses it (the title or "
            "the image says the opposite of what was measured, or the formula's condition is not met). A reversed pair "
            f"fails: it is dropped or rebuilt in the measured direction, and the title card refuses it. Marks: {MARKS}.")


__all__ = ["Unchecked", "critic_note", "newest", "pairs", "problems", "require", "verdict", "versions"]
