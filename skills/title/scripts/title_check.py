#!/usr/bin/env python3
"""Check YouTube title candidates before they go to the user (skill: skills/title).

Every limit comes from the active style pack (crewcut.brand): channel.json "title", thumbnail.json "max_words",
and the optional word lists in voice.md ("## Title hooks", "## Title words to avoid", "## Words to avoid").
The neutral pack has no word lists, so the hook check is then a hint to judge by hand.

  python3 skills/title/scripts/title_check.py "Title one" "Title two" --name ToolName
  python3 skills/title/scripts/title_check.py "Title" --thumbnail "TWO WORDS" --json
  python3 skills/title/scripts/title_check.py --file candidates.txt        (one title per line, # for comments)

Levels:
  error   breaks a hard limit (YouTube or the style pack). The title does not go to the user.
  warn    allowed, but against the pack's target.
  hint    weak signal. Use only with a reason.
  plus    a pattern the pack counts as a hook.

Points (0 to 100) rank candidates against each other; they are not a forecast.
Start 50, +6 per hook (at most +30), -25 per error, -8 per warning, -3 per hint.

Exit: 0 = no title with an error, 1 = at least one title with an error, 2 = wrong call.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

YOUTUBE_MAX_CHARS = 100  # YouTube's hard limit for a title
LEVELS = ("error", "warn", "hint")
ORDER = {"error": 0, "warn": 1, "hint": 2, "plus": 3}


def _brand():
    try:
        from crewcut import brand
    except ImportError:  # run from a checkout without the package installed
        sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
        from crewcut import brand
    return brand


def load_pack(pack_dir: str | None = None):
    return _brand().load(pack_dir)


# ---------- voice.md word lists ----------
def voice_section(text: str, heading: str) -> list[tuple[str | None, list[str]]]:
    """Items of one '## heading' section in voice.md as (label, terms).

    '- free: free, no cost' gives ('free', ['free', 'no cost']); '- game changer' gives (None, ['game changer']).
    """
    out: list[tuple[str | None, list[str]]] = []
    inside = False
    for line in (text or "").splitlines():
        s = line.strip()
        if s.startswith("#"):
            inside = s.lstrip("#").strip().lower() == heading.lower()
            continue
        if not inside or not re.match(r"^[-*]\s+", s):
            continue
        item = re.sub(r"^[-*]\s+", "", s).strip()
        label = None
        m = re.match(r"^([\w-]+)\s*:\s*(.+)$", item)
        if m:
            label, item = m.group(1), m.group(2)
        terms = [t.strip().strip('"“”\'') for t in item.split(",")]
        terms = [t for t in terms if t]
        if terms:
            out.append((label, terms))
    return out


def term_regex(term: str) -> re.Pattern:
    """Whole-word match, case-insensitive. A trailing * matches any ending. Symbols ($, %) match anywhere."""
    if not re.search(r"\w", term):
        return re.compile(re.escape(term))
    if term.endswith("*"):
        return re.compile(r"(?<!\w)" + re.escape(term[:-1]) + r"\w*", re.I)
    return re.compile(r"(?<!\w)" + re.escape(term) + r"(?!\w)", re.I)


def find_terms(text: str, terms: list[str]) -> list[str]:
    hits = []
    for t in terms:
        m = term_regex(t).search(text)
        if m:
            hits.append(m.group(0))
    return hits


# ---------- patterns that need no word list ----------
COLON = re.compile(r"(?<!\d):|:(?!\d)")  # 8:00 is a time, not a colon
DASH = re.compile(r"[–—]|\s-\s")
FACTOR = re.compile(r"(?<![\w.,])\d+(?:[.,]\d+)?\s?[x×](?![^\W\d_])", re.I)
AMOUNT = re.compile(r"[$€£¥]\s?\d|\d\s?(?:[$€£¥%])")
WORD = re.compile(r"[^\W_]+(?:['’-][^\W_]+)*")


def caps_words(title: str, acronyms: set[str]) -> list[str]:
    """Words of 4 or more letters in capitals that are not known acronyms (shouting)."""
    out = []
    for w in WORD.findall(title):
        for part in re.split(r"['’-]", w):
            letters = [c for c in part if c.isalpha()]
            if len(letters) >= 4 and part.isupper() and part.upper() not in acronyms:
                out.append(part)
    return out


def name_position(title: str, names: list[str]) -> tuple[str | None, int | None]:
    best: tuple[str | None, int | None] = (None, None)
    for name in names:
        m = re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", title, re.I)
        if m and (best[1] is None or m.start() < best[1]):
            best = (name, m.start())
    return best


def content_words(text: str) -> set[str]:
    """Words of 3 or more characters and all numbers, lower case. A rough, language-neutral overlap measure."""
    return {w.lower() for w in WORD.findall(text or "") if len(w) >= 3 or w.isdigit()}


def level_of(pack, key: str, default: str = "off") -> str:
    v = pack.value(f"channel.title.checks.{key}", default)
    return v if v in LEVELS else "off"


# ---------- the check ----------
def check_title(title: str, pack, names: list[str] | tuple = (), thumbnail: str | None = None) -> dict:
    t = " ".join((title or "").split())
    n = len(t)
    findings: list[dict] = []
    plus = 0

    def add(level: str, rule: str, text: str, points: int = 0):
        nonlocal plus
        findings.append({"level": level, "rule": rule, "text": text})
        if level == "plus":
            plus += points

    max_chars = int(pack.value("channel.title.max_chars", 70))
    target = int(pack.value("channel.title.target_chars", 55))
    within = int(pack.value("channel.title.name_within", 40))

    # Length: YouTube's limit, then the pack's limit and target. Phones cut long titles.
    if not t:
        add("error", "length", "Empty title.")
    elif n > YOUTUBE_MAX_CHARS:
        add("error", "length", f"{n} characters: YouTube allows at most {YOUTUBE_MAX_CHARS}.")
    elif n > max_chars:
        add("error", "length", f"{n} characters: more than {max_chars} (channel.json title.max_chars).")
    elif n > target:
        add("warn", "length", f"{n} characters: allowed, but over the target of {target} (title.target_chars).")
    if "<" in t or ">" in t:
        add("error", "characters", 'Contains "<" or ">". YouTube rejects these characters.')

    # The best-known name early: before the phone cuts the line.
    all_names = [x for x in list(pack.value("channel.title.names", []) or []) + list(names) if x]
    if not all_names:
        add("hint", "name", "No name to check. Pass --name with the best-known name the title is about.")
    else:
        name, pos = name_position(t, all_names)
        if name is None:
            add("error", "name", f"None of these names is in the title: {', '.join(all_names)}.")
        elif pos >= within:
            add("error", "name", f'"{name}" starts at character {pos + 1}. It must start within the first {within}.')
        else:
            add("plus", "name", f'"{name}" starts within the first {within} characters.', 6)

    # Words the pack forbids in titles, and words the user never says.
    voice = getattr(pack, "voice", "") or ""
    for label, terms in voice_section(voice, "Title words to avoid"):
        for hit in find_terms(t, terms):
            add("error", "avoid", f'"{hit}" is on the list "Title words to avoid" in voice.md'
                + (f" ({label})." if label else "."))
    for _, terms in voice_section(voice, "Words to avoid"):
        for hit in find_terms(t, terms):
            add("warn", "voice", f'"{hit}" is on the list "Words to avoid" in voice.md.')

    # Style checks whose level the pack sets (error, warn, hint or off).
    lv = level_of(pack, "colon")
    if lv != "off" and COLON.search(t):
        add(lv, "colon", "Colon in the title (channel.json title.checks.colon).")
    lv = level_of(pack, "dash")
    if lv != "off" and DASH.search(t):
        add(lv, "dash", "Dash in the title (title.checks.dash). A bracket or a comma reads calmer.")
    lv = level_of(pack, "factor")
    m = FACTOR.search(t)
    if lv != "off" and m:
        add(lv, "factor", f'"{m.group(0).strip()}": the pack wants a percentage instead of an "x times" factor.')
    lv = level_of(pack, "caps_words", "hint")
    if lv != "off":
        acr = {a.upper() for a in (pack.value("channel.title.acronyms", []) or [])}
        for w in caps_words(t, acr):
            add(lv, "caps", f'"{w}" is written in capitals. Add it to title.acronyms if it is an acronym.')
    lv = level_of(pack, "question", "hint")
    if lv != "off" and "?" in t:
        add(lv, "question", "Question mark. A statement usually promises more than a question.")
    max_ex = int(pack.value("channel.title.exclamations_max", 1))
    ex = t.count("!")
    if ex > max_ex:
        add("warn", "exclamation", f"{ex} exclamation marks; the pack allows {max_ex}.")
    if t.count("(") > 1:
        add("hint", "brackets", "More than one bracket. One bracket with a second promise is enough.")

    # Hooks: the pack's click words, plus an amount (money or percentage), which needs no word list.
    hooks = voice_section(voice, "Title hooks")
    found = False
    for label, terms in hooks:
        hits = find_terms(t, terms)
        if hits:
            add("plus", "hook", f'Hook "{label or hits[0]}": {", ".join(hits)}.', 6)
            found = True
    if AMOUNT.search(t):
        add("plus", "hook", "Hook: an amount (money or percentage).", 6)
        found = True
    if not found:
        if hooks:
            add("hint", "hook", "No hook found from voice.md (## Title hooks). Sharpen the reason to click.")
        else:
            add("hint", "hook", "No hook list in voice.md. Judge the reason to click by hand.")

    # Thumbnail text: repeat one key word of the title, never the whole title.
    if thumbnail:
        tw, bw = content_words(t), content_words(thumbnail)
        max_words = int(pack.value("thumbnail.max_words", 4))
        n_words = len(WORD.findall(thumbnail))
        if n_words > max_words:
            add("warn", "thumbnail", f"Thumbnail text has {n_words} words; thumbnail.json max_words is {max_words}.")
        if bw and bw == tw:
            add("warn", "thumbnail", "Thumbnail text repeats the whole title. Use one key word and the verdict.")
        elif tw & bw:
            add("plus", "thumbnail", f"Thumbnail text repeats a title word ({', '.join(sorted(tw & bw))}).", 0)
        else:
            add("hint", "thumbnail", "Thumbnail text shares no word with the title. Take one key word into the image.")

    plus = min(plus, 30)
    errors = sum(1 for f in findings if f["level"] == "error")
    warns = sum(1 for f in findings if f["level"] == "warn")
    hints = sum(1 for f in findings if f["level"] == "hint")
    points = max(0, min(100, 50 + plus - 25 * errors - 8 * warns - 3 * hints))
    findings.sort(key=lambda f: ORDER[f["level"]])
    return {"title": t, "chars": n, "words": len(WORD.findall(t)), "points": points,
            "status": "fail" if errors else "ok", "errors": errors, "warnings": warns, "hints": hints,
            "findings": findings}


def print_result(i: int, r: dict) -> None:
    print(f'[{i}] {r["title"]}')
    print(f'    {r["chars"]} characters, {r["words"]} words, points {r["points"]}, {r["status"].upper()}')
    for f in r["findings"]:
        print(f'    {f["level"]:<6} {f["text"]}')


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Check YouTube title candidates against the style pack.")
    ap.add_argument("titles", nargs="*", help="one or more titles")
    ap.add_argument("--name", action="append", default=[], help="a name that must start early (repeatable)")
    ap.add_argument("--thumbnail", help="planned thumbnail text; checks that it takes one word from the title")
    ap.add_argument("--file", help="text file with one title per line")
    ap.add_argument("--pack", help="style pack folder (default: the active pack)")
    ap.add_argument("--json", action="store_true", help="print JSON")
    a = ap.parse_args(argv)
    titles = list(a.titles)
    if a.file:
        for line in Path(a.file).read_text(encoding="utf-8").splitlines():
            if line.strip() and not line.lstrip().startswith("#"):
                titles.append(line.strip())
    if not titles:
        ap.print_usage(sys.stderr)
        return 2
    pack = load_pack(a.pack)
    results = [check_title(t, pack, a.name, a.thumbnail) for t in titles]
    if a.json:
        print(json.dumps(results, ensure_ascii=False, indent=1))
    else:
        for i, r in enumerate(results, 1):
            print_result(i, r)
        ok = sum(1 for r in results if r["status"] == "ok")
        print(f"\n{len(results)} titles checked: {ok} ok, {len(results) - ok} failed. Pack: {pack.dir.name}")
    return 1 if any(r["errors"] for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
