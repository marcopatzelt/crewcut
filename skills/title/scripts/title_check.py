#!/usr/bin/env python3
"""Check YouTube title candidates before they go to the user (skill: skills/title).

The check is a gate: a title passes or fails. It is not a score to raise. Every limit comes from the active style pack
(crewcut.brand): channel.json "title" (levels in "title.checks": colon, dash, factor, caps_words, question,
quotes_long, series; the word list "title.banned" is always an error), thumbnail.json "max_words", and the optional
word lists in voice.md ("## Title hooks", "## Title words to avoid", "## Words to avoid"). The neutral pack has no word
lists, so the hook check is then a hint to judge by hand. --short checks Shorts titles, where a quote is a good form.

  python3 skills/title/scripts/title_check.py "Title one" "Title two" --name ToolName
  python3 skills/title/scripts/title_check.py "Title" --thumbnail "TWO WORDS" --json
  python3 skills/title/scripts/title_check.py --file candidates.txt        (one title per line, # for comments)
  python3 skills/title/scripts/title_check.py --set work/title-candidates-v001.tsv --name ToolName

--set is the candidate gate of the title step: one candidate per line, `<formula><TAB><title>` (or
`<formula> | <title>`). It passes when there are at least channel.json title.candidates (10) different titles from at
least title.formulas_min (4) different formulas of FORMULAS below, and every title passes on its own.

Levels:
  error   breaks a hard limit (YouTube or the style pack). The title fails and does not go to the user.
  warn    allowed, but against the pack's target.
  hint    weak signal. Use only with a reason.
  plus    a pattern the pack counts as a hook (information, not points).

Exit: 0 = every title passes (and the set gate passes), 1 = a title or the set gate fails, 2 = wrong call.
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

# Title formulas for the candidate set (`--set`). The channel's rules say which come first; the gate only counts how
# many different ones the candidates use. Measured on Alex Hormozi's channel (outlier views against the 30 uploads
# around each video, 3,424 long videos, 26 Nov 2026): "How I'd ..." 2.7, "If I ..., I'd ..." 2.2, the viewer's time to
# a result 2.1, "If you ..." 2.0, a year 1.8, knowledge condensed 1.8, "How to ..." 1.35; open questions 0.74.
FORMULAS = {
    "situation": 'the viewer\'s situation: "If you ...", "Wenn du ..."',
    "howto": 'how-to: "How to ...", "So ..."',
    "contrast": "a cost or risk contrast: cheap against expensive, safe against risky",
    "flip": "the expectation flips: what the viewer believes turns out wrong",
    "plan": 'my plan: "How I\'d ...", "So würde ich ..."',
    "condition-plan": 'condition plus my plan: "If I ..., I\'d ...", "Wenn ich ..., würde ich ..."',
    "condensed": 'knowledge condensed: "N years in M minutes", "everything I learned in ..."',
    "year": "a year that frames a plan",
    "time": "the viewer's time to the result: \"in one evening\", \"in 15 minutes\"",
    "case": "a case: who, a number, the problem (Shorts), a quote or an I-sentence",
}
ALIASES = {"how-to": "howto", "how_to": "howto", "condition_plan": "condition-plan", "conditionplan": "condition-plan",
           "if-you": "situation", "if-i": "condition-plan", "how-id": "plan"}


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
QUOTES = re.compile(r"[\"„“”«»]|(?<![\w])['‘’‚][^'‘’‚]+['‘’](?![\w])")
SERIES = re.compile(r"\b(?:teil|part|folge|episode|ep\.?|staffel|season)\s*\d+\b|#\s?\d+\b|\(\s*\d+\s*/\s*\d+\s*\)", re.I)
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
def check_title(title: str, pack, names: list[str] | tuple = (), thumbnail: str | None = None,
                short: bool = False) -> dict:
    """One title. `short`: a Shorts title, where a quote is a good form (the long-title quote check is left out)."""
    t = " ".join((title or "").split())
    n = len(t)
    findings: list[dict] = []

    def add(level: str, rule: str, text: str):
        findings.append({"level": level, "rule": rule, "text": text})

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
            add("plus", "name", f'"{name}" starts within the first {within} characters.')

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
        add(lv, "question", "Question mark. A statement usually promises more than a question; a question has to flip "
            "an expectation, and the image shows the evidence.")
    lv = level_of(pack, "quotes_long")
    if lv != "off" and not short and QUOTES.search(t):
        add(lv, "quotes", "Quotation marks in a long title (title.checks.quotes_long). A quote is a Shorts form.")
    lv = level_of(pack, "series")
    m = SERIES.search(t)
    if lv != "off" and m:
        add(lv, "series", f'"{m.group(0).strip()}": a part number or series name (title.checks.series). Each title stands '
            "on its own.")
    for hit in find_terms(t, [str(x) for x in pack.value("channel.title.banned", []) or [] if str(x).strip()]):
        add("error", "banned", f'"{hit}" is on the list title.banned in channel.json.')
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
            add("plus", "hook", f'Hook "{label or hits[0]}": {", ".join(hits)}.')
            found = True
    if AMOUNT.search(t):
        add("plus", "hook", "Hook: an amount (money or percentage).")
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
            add("plus", "thumbnail", f"Thumbnail text repeats a title word ({', '.join(sorted(tw & bw))}).")
        else:
            add("hint", "thumbnail", "Thumbnail text shares no word with the title. Take one key word into the image.")

    errors = sum(1 for f in findings if f["level"] == "error")
    warns = sum(1 for f in findings if f["level"] == "warn")
    hints = sum(1 for f in findings if f["level"] == "hint")
    findings.sort(key=lambda f: ORDER[f["level"]])
    return {"title": t, "chars": n, "words": len(WORD.findall(t)), "status": "fail" if errors else "ok",
            "passed": not errors, "errors": errors, "warnings": warns, "hints": hints, "findings": findings}


def print_result(i: int, r: dict) -> None:
    head = f'[{i}] {r["title"]}' + (f'   (formula: {r["formula"]})' if r.get("formula") else "")
    print(head)
    print(f'    {r["chars"]} characters, {r["words"]} words, {"PASS" if r["passed"] else "FAIL"}')
    for f in r["findings"]:
        print(f'    {f["level"]:<6} {f["text"]}')


# ---------- the candidate set (gate of the title step) ----------
def formula_id(label: str) -> str | None:
    key = re.sub(r"[\s_]+", "-", (label or "").strip().lower())
    key = ALIASES.get(key, key)
    return key if key in FORMULAS else None


def parse_set(text: str) -> list[tuple[str, str]]:
    """Lines `<formula><TAB><title>` or `<formula> | <title>`; # starts a comment. A line without a formula keeps an
    empty label (the gate reports it)."""
    rows = []
    for line in (text or "").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if "\t" in s:
            label, title = s.split("\t", 1)
        elif " | " in s:
            label, title = s.split(" | ", 1)
        else:
            label, title = "", s
        rows.append((label.strip(), title.strip()))
    return rows


def check_set(rows: list[tuple[str, str]], pack, names: list[str] | tuple = (), thumbnail: str | None = None,
              short: bool = False) -> dict:
    """The title step's gate: enough different candidates, from enough different formulas, each one passing."""
    need = int(pack.value("channel.title.candidates", 10))
    need_f = int(pack.value("channel.title.formulas_min", 4))
    results, problems, seen = [], [], {}
    for label, title in rows:
        r = check_title(title, pack, names, thumbnail, short)
        r["formula"] = formula_id(label)
        r["label"] = label
        if r["formula"] is None:
            r["findings"].insert(0, {"level": "error", "rule": "formula", "text": (
                f'No known formula ("{label}"). Use one of: {", ".join(FORMULAS)}.' if label else
                f'No formula named. Write "<formula><TAB><title>"; formulas: {", ".join(FORMULAS)}.')})
            r["errors"] += 1
            r["status"], r["passed"] = "fail", False
        key = r["title"].lower()
        if key in seen:
            problems.append(f'"{r["title"]}" is in the set twice (lines {seen[key]} and {len(results) + 1}).')
        seen.setdefault(key, len(results) + 1)
        results.append(r)
    distinct = len(seen)
    used = sorted({r["formula"] for r in results if r["formula"]})
    if distinct < need:
        problems.append(f"{distinct} different candidates; the title step writes at least {need} "
                        "(channel.json title.candidates).")
    if len(used) < need_f:
        problems.append(f"{len(used)} different formulas ({', '.join(used) or 'none'}); at least {need_f} are needed "
                        "(title.formulas_min). Write candidates from other formulas instead of variants of one.")
    failed = [r["title"] for r in results if not r["passed"]]
    if failed:
        problems.append(f"{len(failed)} candidate(s) fail their own check; rewrite or drop them.")
    return {"passed": not problems, "candidates": distinct, "formulas": used, "need_candidates": need,
            "need_formulas": need_f, "problems": problems, "results": results}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Check YouTube title candidates against the style pack.")
    ap.add_argument("titles", nargs="*", help="one or more titles")
    ap.add_argument("--name", action="append", default=[], help="a name that must start early (repeatable)")
    ap.add_argument("--thumbnail", help="planned thumbnail text; checks that it takes one word from the title")
    ap.add_argument("--file", help="text file with one title per line")
    ap.add_argument("--set", dest="set_file", help="the candidate set: one `<formula><TAB><title>` per line (the gate)")
    ap.add_argument("--pack", help="style pack folder (default: the active pack)")
    ap.add_argument("--short", action="store_true", help="Shorts titles: quotes are allowed")
    ap.add_argument("--json", action="store_true", help="print JSON")
    a = ap.parse_args(argv)
    if a.set_file:
        pack = load_pack(a.pack)
        rep = check_set(parse_set(Path(a.set_file).read_text(encoding="utf-8")), pack, a.name, a.thumbnail, a.short)
        if a.json:
            print(json.dumps(rep, ensure_ascii=False, indent=1))
        else:
            for i, r in enumerate(rep["results"], 1):
                print_result(i, r)
            print(f'\nSet: {rep["candidates"]} candidates, {len(rep["formulas"])} formulas '
                  f'({", ".join(rep["formulas"]) or "none"}). Pack: {pack.dir.name}')
            for p in rep["problems"]:
                print("  - " + p)
            print("GATE PASSED" if rep["passed"] else "GATE FAILED")
        return 0 if rep["passed"] else 1
    titles = list(a.titles)
    if a.file:
        for line in Path(a.file).read_text(encoding="utf-8").splitlines():
            if line.strip() and not line.lstrip().startswith("#"):
                titles.append(line.strip())
    if not titles:
        ap.print_usage(sys.stderr)
        return 2
    pack = load_pack(a.pack)
    results = [check_title(t, pack, a.name, a.thumbnail, a.short) for t in titles]
    if a.json:
        print(json.dumps(results, ensure_ascii=False, indent=1))
    else:
        for i, r in enumerate(results, 1):
            print_result(i, r)
        ok = sum(1 for r in results if r["passed"])
        print(f"\n{len(results)} titles checked: {ok} pass, {len(results) - ok} fail. Pack: {pack.dir.name}")
    return 1 if any(r["errors"] for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
