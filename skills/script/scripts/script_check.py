#!/usr/bin/env python3
"""Check a spoken script before it goes to the user (skill: skills/script).

Only the spoken part counts: everything above the first line that is just "---". Notes for the edit
(scenes, clips, where each number comes from) go below that line.

Limits come from the active style pack (crewcut.brand): channel.json "script", "closing_line",
edit-style.json "length_minutes", and voice.md ("## Words to avoid", "## Words to use").

  python3 skills/script/scripts/script_check.py brief/SCRIPT-v001.md --title "The title" --name ToolName
  python3 skills/script/scripts/script_check.py brief/SCRIPT-v001.md --facts work/material-v001.md --json
  python3 skills/script/scripts/script_check.py brief/SCRIPT-v001.md --interview brief/INTERVIEW-v001.md
  python3 skills/script/scripts/script_check.py brief/SCRIPT-v001.md --text-only     (the spoken part only)
  python3 skills/script/scripts/script_check.py brief/SCRIPT-v001.md --short [--language de] [--facts F]
  python3 skills/script/scripts/script_check.py brief/SCRIPT-v001.md --spoken    (speak and story checks only)
  python3 skills/script/scripts/script_check.py brief/SCRIPT-v001.md --craft     (the script craft only)
  python3 skills/script/scripts/script_check.py brief/SCRIPT-v001.md --minutes 11-14   (the brief's length wins)

Every mode checks that the spoken text reads aloud (crewcut.spoken): no colon, semicolon, bracket, slash, arrow, list
mark or notes section above the line; a script card is refused otherwise. The long mode and --spoken also read the
story: the plan below --- (premise, arc, 3 to 5 beats), list smell, staged run-ups, repeats, the subscribe line.

The long mode and --craft measure the script craft (crewcut.craft, references/craft.md): the hook in 30 seconds (a
number, a roadmap with a count, an open loop, why it matters, an honest limit by 0:45, no greeting), the depth pattern
(words and seconds per part, "try this" per depth part, examples, sums said aloud, contrast pairs), the spoken rhythm
(share of short sentences, questions per 1,000 words and their answers, objections, "you" against "I") and the ending
(at most 60 seconds, exactly one call to action, list, the human's part, a verdict with its limit, the open loop
resolved). Levels and limits: channel.json "script.craft". The longest sentence: "script.sentence_max_words".

--short checks a Short's script with the reel rules instead (see check_short): word range from edit-style.json
"shorts.words", more I-sentences than you-sentences, a turn (expectation, then the break), an uneven real number or a
visible proof, a time anchor or a number in a series, and the phrase list of the language
(references/phrases-<language>.txt: phrases that sound written or like filler, "not X but Y" patterns, dashes).

Motion marks: below the "---" line the Writer may mark up to five beats for motion graphics, as wishes for the
Editor's motion pass: [[motion: number | "30 cents per million tokens"]] (the kind of picture | the spoken words it
belongs to). Both modes count them (stats "motion_marks"); a mark above the line or a sixth mark is an error.

Interview marks: when the creator answered the interview (brief/INTERVIEW-vNNN.md), the Writer marks below the "---"
line which spoken lines come from it: [[interview: 3 | "the spoken words"]] (the question number | the words as they
stand in the script). With --interview FILE the check wants at least one mark, each mark's words in the spoken text,
and reports how many spoken sentences share a run of five words with the answers.

Levels: error (must go before the user sees the script), warn and hint (read and decide; a hint you keep gets one
sentence of reason below the "---" line).

Exit: 0 = no error, 1 = at least one error, 2 = wrong call.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

LEVELS = ("error", "warn", "hint")
WORD = re.compile(r"[^\W_]+(?:[.,'’-][^\W_]+)*")
NUMBER = re.compile(r"(?<![\w.,])\d+(?:[.,]\d+)*(?:\s?%)?")
TIMESTAMP = re.compile(r"(?<![\d.,])\d{1,2}:\d{2}(?!\d)")
DASH = re.compile(r"[–—]|\s-{1,2}\s")
FILE_NAME = re.compile(r"\b[\w-]+\.(?:py|js|ts|tsx|json|md|ya?ml|sh|toml|env|html|css|txt)\b", re.I)
FLAG = re.compile(r"(?<![\w-])--[a-z][\w-]*")
CAMEL = re.compile(r"\b[a-z]+[A-Z][A-Za-z]+\b")
MOTION_MARK = re.compile(r"\[\[\s*motion\s*:(?P<body>[^\]]*)\]\]", re.I)
MOTION_MARKS_MAX = 5
INTERVIEW_MARK = re.compile(r"\[\[\s*interview\s*:(?P<body>[^\]]*)\]\]", re.I)


def _brand():
    try:
        from crewcut import brand
    except ImportError:  # run from a checkout without the package installed
        sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
        from crewcut import brand
    return brand


def _spoken():
    _brand()
    from crewcut import spoken
    return spoken


def speak_check(text: str, add, passed: list[str]) -> None:
    """Hard: every mark in the teleprompter text reads aloud (crewcut.spoken). Headings, list marks and timestamps are
    reported by form_check already."""
    found = [f for f in _spoken().speakable(MOTION_MARK.sub(" ", text))     # marks: check_motion_marks
             if f["kind"] not in ("heading", "list", "timestamp")]
    for f in found:
        add("error", "speak", f["text"] + ". Say it in words; shot ideas and notes go below ---.")
    if not found:
        passed.append("speak: no colon, semicolon, bracket, slash or notes section in the spoken text")


def story_check(text: str, add, passed: list[str], lang: str | None = None) -> None:
    """The story plan below --- and the reading help for the Critic: list smell, staged run-ups, repeats, the place
    of the subscribe line (crewcut.spoken.story)."""
    found = _spoken().story(text, lang)
    for f in found:
        add(f["level"], f["area"], f["text"])
    if not any(f["level"] == "error" for f in found):
        passed.append("story: plan below --- and no strong list smell")


def _craft():
    _brand()
    from crewcut import craft
    return craft


def craft_check(text: str, pack, add, passed: list[str], stats: dict, lang: str | None = None) -> dict:
    """The four craft groups (crewcut.craft): hook in 30 seconds, depth pattern, spoken rhythm, ending. The word lists
    follow the script's language unless one is given."""
    wpm = float(pack.value("channel.script.words_per_minute", 150))
    r = _craft().check(text, lang, wpm, pack.value("channel.script.craft", {}) or {})
    for f in r["findings"]:
        add(f["level"], f["area"], f["text"])
    passed.extend(r["passed"])
    stats["craft"] = r["stats"]
    return r


def load_pack(pack_dir: str | None = None):
    return _brand().load(pack_dir)


# ---------- text helpers ----------
def spoken_part(text: str) -> str:
    out = []
    for line in text.splitlines():
        if line.strip() == "---":
            break
        out.append(line.rstrip())
    return "\n".join(out)


def motion_marks(text: str) -> list[dict]:
    """The Writer's motion marks, [[motion: kind | "spoken words"]], in file order: line, kind, words, and whether the
    mark stands below the first "---" line (where it belongs)."""
    out, below = [], False
    for nr, line in enumerate(text.splitlines(), 1):
        if not below and line.strip() == "---":
            below = True
            continue
        for m in MOTION_MARK.finditer(line):
            kind, _, said = m.group("body").partition("|")
            out.append({"line": nr, "kind": kind.strip(), "words": said.strip().strip('"“”\'').strip(),
                        "below": below, "mark": m.group(0)})
    return out


def check_motion_marks(text: str, spoken: str, add, passed: list[str], stats: dict) -> None:
    """At most MOTION_MARKS_MAX marks, all below the --- line, each with a kind and words that are spoken."""
    marks = motion_marks(text)
    below = [m for m in marks if m["below"]]
    stats["motion_marks"] = len(below)
    if not marks:
        return
    above = [m for m in marks if not m["below"]]
    if above:
        add("error", "motion", f"motion mark above the --- line (line {above[0]['line']}: {above[0]['mark'][:50]}). "
            "Marks are notes for the edit: put them below ---.")
    if len(below) > MOTION_MARKS_MAX:
        add("error", "motion", f"{len(below)} motion marks; at most {MOTION_MARKS_MAX}. Keep the beats where a "
            "picture says more than the face.")
    loose = [m for m in below if not m["kind"] or not m["words"]]
    if loose:
        add("warn", "motion", f"motion mark without a kind or without the spoken words (line {loose[0]['line']}). "
            'Form: [[motion: number | "30 cents per million tokens"]].')
    said = " " + " ".join(words(spoken.lower())) + " "
    unheard = [m for m in below if m["words"] and f" {' '.join(words(m['words'].lower()))} " not in said]
    if unheard:
        add("hint", "motion", f'the words of a motion mark are not in the spoken text: "{unheard[0]["words"][:50]}" '
            f"(line {unheard[0]['line']}). Quote the words as they are said.")
    if not above and len(below) <= MOTION_MARKS_MAX and not loose:
        passed.append(f"motion marks: {len(below)} below the --- line (at most {MOTION_MARKS_MAX})")


def blocks(text: str) -> list[dict]:
    """Paragraphs with their first line number and the number of empty lines before them."""
    out, buf, start, empty, empty_before = [], [], 0, 0, 0
    for i, line in enumerate(text.split("\n"), 1):
        if line.strip():
            if not buf:
                start, empty_before = i, empty
            buf.append(line.strip())
            empty = 0
        else:
            if buf:
                out.append({"line": start, "text": " ".join(buf), "empty_before": empty_before})
                buf = []
            empty += 1
    if buf:
        out.append({"line": start, "text": " ".join(buf), "empty_before": empty_before})
    return out


def sentences(text: str) -> list[str]:
    """Split on . ! ? and the ellipsis. A single letter before a period (e.g. 'e.g.') does not end a sentence."""
    parts, cur = [], ""
    for piece in re.split(r"(?<=[.!?…])\s+", text.strip()):
        cur = f"{cur} {piece}".strip() if cur else piece
        if re.search(r"(?:^|\s|\.)[^\W\d_]\.$", cur):
            continue
        parts.append(cur)
        cur = ""
    if cur:
        parts.append(cur)
    return [s for s in parts if WORD.search(s)]


def words(text: str) -> list[str]:
    return WORD.findall(text)


def norm_number(x: str) -> str:
    return re.sub(r"[^\d]", "", x)


def voice_items(text: str, heading: str) -> list[str]:
    """Phrases listed under '## heading' in voice.md. Commas separate phrases; 'label: a, b' drops the label."""
    out, inside = [], False
    for line in (text or "").splitlines():
        s = line.strip()
        if s.startswith("#"):
            inside = s.lstrip("#").strip().lower() == heading.lower()
            continue
        if inside and re.match(r"^[-*]\s+", s):
            item = re.sub(r"^[-*]\s+", "", s)
            item = re.sub(r"^[\w-]+\s*:\s*", "", item) if re.match(r"^[\w-]+\s*:\s*\S", item) else item
            out += [p.strip().strip('"“”\'') for p in item.split(",") if p.strip().strip('"“”\'')]
    return out


def phrase_regex(phrase: str) -> re.Pattern:
    if phrase.endswith("*"):
        return re.compile(r"(?<!\w)" + re.escape(phrase[:-1]) + r"\w*", re.I)
    return re.compile(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", re.I)


def level(pack, key: str, default: str = "off") -> str:
    v = pack.value(f"channel.script.checks.{key}", default)
    return v if v in LEVELS else "off"


def _plain(text: str) -> list[str]:
    return re.findall(r"[^\W_]+", text.lower())


def check_interview(text: str, spoken: str, interview: str, add, passed: list[str], stats: dict) -> None:
    """The creator's interview answers carry the script: marks below ---, their words spoken, sentences traced."""
    answers = interview.split("## Answers", 1)[-1].split("## Do not mention", 1)[0]
    parts = re.split(r"(?m)^---[ \t]*$", text, maxsplit=1)
    below = parts[1] if len(parts) > 1 else ""
    marks = [m.group("body").partition("|")[2].strip().strip('"“”„\'').strip() for m in INTERVIEW_MARK.finditer(below)]
    if INTERVIEW_MARK.search(spoken):
        add("error", "interview", "interview mark above the --- line: marks are notes, put them below ---.")
    said = " ".join(_plain(spoken))
    loose = [w for w in marks if w and " ".join(_plain(w)) not in said]
    a = _plain(answers)
    grams = {tuple(a[i:i + 5]) for i in range(len(a) - 4)}
    sents = [_plain(x) for x in sentences(spoken) if len(_plain(x)) >= 5]
    traced = sum(1 for w in sents if any(tuple(w[i:i + 5]) in grams for i in range(len(w) - 4)))
    stats["interview_marks"], stats["interview_sentences"] = len(marks), traced
    if not marks:
        add("error", "interview", 'no interview mark below the --- line. Mark the lines that come from the answers: '
            '[[interview: 3 | "the spoken words"]].')
    elif loose:
        add("warn", "interview", f"{len(loose)} interview mark(s) with words that are not spoken, e.g. \"{loose[0][:50]}\".")
    else:
        passed.append(f"interview: {len(marks)} marked lines")
    if sents and traced == 0:
        add("warn", "interview", "no spoken sentence shares five words in a row with the answers. Use the creator's "
            "own sentences.")
    elif sents:
        passed.append(f"interview: {traced} of {len(sents)} sentences use the creator's own words")


# ---------- the check ----------
def form_check(raw: str, dash_lv: str, add, passed: list[str]) -> list[str]:
    """Teleprompter form, line by line, collected per kind. Returns the lines without stage notes (headings empty)."""
    per_kind: dict[tuple[str, str], list[str]] = {}

    def hit(lv, kind, nr, s):
        per_kind.setdefault((lv, kind), []).append(f'line {nr}: "{s[:50]}"')

    clean = []
    for nr, line in enumerate(raw.split("\n"), 1):
        s = MOTION_MARK.sub(" ", line).strip()     # a motion mark here is reported by check_motion_marks
        if not s:
            clean.append("")
            continue
        heading = False      # brackets, colons and slashes: speak_check
        if s.startswith("#") or re.match(r"^={2,}", s):
            hit("error", "heading", nr, s)
            heading = True
        elif re.search(r"[^\W\d_]", s) and s == s.upper() and len([c for c in s if c.isalpha()]) > 5:
            hit("error", "line in capitals (looks like a heading)", nr, s)
            heading = True
        elif s.endswith(":") and len(s.split()) <= 6:
            hit("error", "short line ending with a colon (looks like a heading)", nr, s)
            heading = True
        if re.match(r"^(?:[-*•>]\s|\d+[.)]\s)", s):
            hit("error", "list or quote mark at the line start", nr, s)
        if TIMESTAMP.search(s):
            hit("error", "timestamp", nr, s)
        if dash_lv != "off" and DASH.search(s):
            hit(dash_lv, "dash", nr, s)
        rest = "" if heading else re.sub(r"\[[^\]]*\]|\([^)]*\)", " ", s).replace("**", "")
        clean.append(" ".join(rest.split()))
    for (lv, kind), where in per_kind.items():
        add(lv, "form", f"{kind}: {len(where)} times, e.g. " + "; ".join(where[:2]))
    if not any(lv == "error" for (lv, _k) in per_kind):
        passed.append("form: spoken text only")
    return clean


def check_script(text: str, pack, title: str | None = None, names: list[str] | tuple = (),
                 proof: str | None = None, interview: str | None = None,
                 minutes: tuple[float, float] | None = None) -> dict:
    raw = spoken_part(text)
    found: list[dict] = []
    passed: list[str] = []

    def add(lv: str, area: str, msg: str):
        if lv in LEVELS:
            found.append({"level": lv, "area": area, "text": msg})

    # 1. Teleprompter form: only words the user says, every mark readable aloud, told as one story.
    clean = form_check(raw, level(pack, "dash"), add, passed)
    speak_check(text, add, passed)
    story_check(text, add, passed)

    bl = blocks("\n".join(clean))
    if not bl:
        raise ValueError("no spoken text above the --- line")
    all_s = [s for b in bl for s in sentences(b["text"])]
    body = " ".join(b["text"] for b in bl)
    n_words = len(words(body))
    lens = [len(words(s)) for s in all_s]
    stats = {"words": n_words, "sentences": len(all_s), "words_per_sentence": round(n_words / max(1, len(all_s)), 1),
             "longest_sentence": max(lens) if lens else 0, "paragraphs": len(bl),
             "parts": 1 + sum(1 for b in bl[1:] if b["empty_before"] >= 3)}

    # 2. Paragraphs are breaths; parts are separated by three empty lines (cut points, prompter pages).
    max_s = int(pack.value("channel.script.paragraph_max_sentences", 3))
    long_p = [f"line {b['line']} ({len(sentences(b['text']))} sentences)" for b in bl
              if len(sentences(b["text"])) > max_s]
    if long_p:
        add(level(pack, "paragraph", "warn"), "form",
            f"paragraph with more than {max_s} sentences: " + ", ".join(long_p[:6]))
    for b in bl:
        if len(words(b["text"])) > 45 and len(sentences(b["text"])) <= max_s:
            add("hint", "form", f"paragraph at line {b['line']} has {len(words(b['text']))} words. Split it.")
    if len(bl) > 8 and stats["parts"] == 1:
        add("hint", "form", "no part break (three empty lines). Parts are where the edit cuts and the prompter pages.")

    # 3. Sentence length.
    max_w = int(pack.value("channel.script.sentence_max_words", 25))
    long_s = [(n, s) for n, s in zip(lens, all_s, strict=True) if n > max_w]
    if long_s:
        add("error", "sentences", f"{len(long_s)} sentence(s) over {max_w} words, e.g. ({long_s[0][0]}) "
            f'"{long_s[0][1][:70]}"')
    else:
        passed.append(f"sentences: longest has {stats['longest_sentence']} words")
    avg = float(pack.value("channel.script.sentence_avg_words", 14))
    if stats["words_per_sentence"] > avg:
        add("hint", "sentences", f"{stats['words_per_sentence']} words per sentence on average; target {avg:g} or less.")

    # 4. Technical tokens belong on screen, not in speech.
    for rx, what in ((FILE_NAME, "file name"), (FLAG, "command flag")):
        t = list(dict.fromkeys(rx.findall(body)))
        if t:
            add("error", "words", f"{what} in the spoken text ({', '.join(t[:3])}). Show it on screen instead.")
    camel = list(dict.fromkeys(w for w in CAMEL.findall(body) if w not in ("iPhone", "iPad", "eBay", "macOS", "iOS")))
    if camel:
        add("hint", "words", f"code names in the spoken text ({', '.join(camel[:3])}). Say what they do.")

    # 5. The user's voice (voice.md).
    voice = getattr(pack, "voice", "") or ""
    avoid = voice_items(voice, "Words to avoid")
    hits = [p for p in avoid if phrase_regex(p).search(body)]
    if hits:
        add("error", "voice", "words the user does not say (voice.md, Words to avoid): " + ", ".join(hits))
    elif avoid:
        passed.append(f"voice: none of the {len(avoid)} words to avoid")
    use = voice_items(voice, "Words to use")
    if use and not any(phrase_regex(p).search(body) for p in use):
        add("hint", "voice", "none of the user's own words from voice.md (Words to use) appear. Read it aloud once.")

    # 6. Opening: deliver the promise of title and thumbnail at once.
    if all_s:
        first = all_s[0]
        lv = level(pack, "question_opening", "hint")
        if first.rstrip().endswith("?"):
            add(lv, "opening", f'sentence 1 is a question ("{first[:60]}"). Open with the claim.')
        else:
            passed.append("opening: sentence 1 is a statement")
        within = int(pack.value("channel.script.name_within_sentences", 4))
        for name in [x for x in names if x]:
            if any(name.lower() in s.lower() for s in all_s[:within]):
                passed.append(f"opening: {name} named in the first {within} sentence(s)")
            else:
                add("error", "opening", f'"{name}" is not named in the first {within} sentence(s).')
        lv = level(pack, "hook_number")
        k = int(pack.value("channel.script.hook_sentences", 2))
        if lv != "off":
            if any(NUMBER.search(s) for s in all_s[:k]):
                passed.append(f"opening: a number in the first {k} sentences")
            else:
                add(lv, "opening", f"no number in the first {k} sentences (the hook carries promise and number).")
        lv = level(pack, "title_number", "warn")
        if title and lv != "off":
            k = int(pack.value("channel.script.title_number_within_sentences", 6))
            opening = {norm_number(x) for s in all_s[:k] for x in NUMBER.findall(s)}
            missing = [x for x in NUMBER.findall(title) if norm_number(x) not in opening]
            if missing:
                add(lv, "opening", f"number from the title missing in the first {k} sentences: {', '.join(missing)}.")
            else:
                passed.append("opening: the title's numbers are in the opening")

    # 7. Ending: the channel's closing line and what the end must mention.
    closing = pack.value("channel.closing_line")
    if closing and all_s:
        if " ".join(closing.lower().split()).rstrip(".!") in all_s[-1].lower():
            passed.append("ending: closing line")
        else:
            add("error", "ending", f'the last sentence is not the closing line from channel.json: "{closing}".')
    last = " ".join(all_s[-4:]).lower()
    for term in pack.value("channel.script.end_mentions", []) or []:
        if term.lower() not in last:
            add("error", "ending", f'"{term}" is not in the last 4 sentences (channel.json script.end_mentions).')

    # 8. Every statement once; no three blocks in a row with the same start.
    seen, dups = set(), []
    for s in all_s:
        k = " ".join(words(s.lower()))
        if len(k.split()) >= 5 and k in seen:
            dups.append(s)
        seen.add(k)
    if dups:
        add("hint", "structure", f'sentence said twice: "{dups[0][:60]}". Say each thing once.')
    starts = [" ".join(words(b["text"].lower())[:2]) for b in bl]
    for i in range(len(starts) - 2):
        if starts[i] and starts[i] == starts[i + 1] == starts[i + 2]:
            add("hint", "structure", f'three paragraphs in a row start with "{starts[i]}" (from line {bl[i]["line"]}). '
                "Change the form of the third.")
            break

    # 9. Length from the brief (--minutes) or edit-style.json length_minutes, and the speaking rate.
    wpm = float(pack.value("channel.script.words_per_minute", 150))
    lo_min, hi_min = minutes or (pack.value("edit_style.length_minutes", [3, 6]) or [3, 6])[:2]
    lo, hi = int(lo_min * wpm), int(hi_min * wpm)
    stats["minutes"] = round(n_words / wpm, 1)
    if n_words > hi * 1.25:
        add("error", "length", f"{n_words} words (about {stats['minutes']} min). Target {lo} to {hi}.")
    elif n_words < lo * 0.9 or n_words > hi * 1.06:
        add("hint", "length", f"{n_words} words (about {stats['minutes']} min). Target {lo} to {hi}.")
    else:
        passed.append(f"length: {n_words} words, about {stats['minutes']} min")

    # 10. The Writer's motion marks: at most five, below the --- line.
    check_motion_marks(text, body, add, passed, stats)

    # 11. No number without a source (the facts the Writer gathered, or a proof file when that step is on).
    if proof is not None:
        proof_nums = {norm_number(x) for x in NUMBER.findall(proof)}
        script_nums = [x for x in dict.fromkeys(NUMBER.findall(body)) if len(norm_number(x)) >= 2 or "%" in x
                       or "," in x or "." in x]
        missing = [x for x in script_nums if norm_number(x) not in proof_nums]
        if missing:
            add("warn", "proof", f"numbers not found in the facts file: {', '.join(missing[:8])}. Every number needs a "
                "source.")
        else:
            passed.append(f"proof: all {len(script_nums)} numbers appear in the facts file")

    # 12. The creator's interview: their sentences carry the script, marked below the --- line.
    if interview is not None:
        check_interview(text, raw, interview, add, passed, stats)

    # 13. The script craft: hook in 30 seconds, depth pattern, spoken rhythm, ending (references/craft.md).
    manual = craft_check(text, pack, add, passed, stats)["manual"]

    order = {"error": 0, "warn": 1, "hint": 2}
    found.sort(key=lambda f: order[f["level"]])
    errors = sum(1 for f in found if f["level"] == "error")
    return {"stats": stats, "findings": found, "passed": passed, "errors": errors,
            "warnings": sum(1 for f in found if f["level"] == "warn"),
            "hints": sum(1 for f in found if f["level"] == "hint"), "ready": errors == 0, "manual": manual}


# ---------- Shorts (reel rules) ----------
REFERENCES = Path(__file__).resolve().parents[1] / "references"
# Word lists per language. First person counts "we" too: the story is the speaker's own.
FIRST_PERSON = {
    "en": {"i", "i'm", "i've", "i'd", "i'll", "me", "my", "mine", "myself", "we", "we're", "we've", "us", "our"},
    "de": {"ich", "mich", "mir", "mein", "meine", "meinen", "meinem", "meiner", "meines", "hab", "wir", "uns",
           "unser", "unsere", "unseren", "unserem", "unserer"},
}
SECOND_PERSON = {
    "en": {"you", "you're", "you've", "you'd", "you'll", "your", "yours", "yourself", "yourselves", "ya"},
    "de": {"du", "dich", "dir", "dein", "deine", "deinen", "deinem", "deiner", "deines", "euch", "euer", "eure"},
}
EXPECT = {
    "en": [r"\bthought\b", r"\bexpected\b", r"\bassumed\b", r"\bwas (?:sure|convinced|certain)\b", r"\bbelieved\b",
           r"\bfigured\b", r"\bhoped\b", r"\bthe plan was\b", r"\bsupposed to\b", r"\bshould (?:have|be|work)\b",
           r"\bon paper\b", r"\bmy guess\b"],
    "de": [r"\bdachte\b", r"\bgedacht\b", r"\berwartet\b", r"\bwar (?:sicher|überzeugt)\b", r"\bgehofft\b",
           r"\bangenommen\b", r"\bder plan war\b", r"\bsollte\b", r"\beigentlich\b", r"\bauf dem papier\b"],
}
BREAK = {
    "en": [r"\bbut\b", r"\bturn(?:s|ed) out\b", r"\binstead\b", r"\buntil\b", r"\bexcept\b", r"\bactually\b",
           r"\bin fact\b", r"\bnope\b", r"\bwrong\b", r"\bthe opposite\b", r"\bdid(?:n't| not)\b", r"\bfailed\b",
           r"\bsuddenly\b"],
    "de": [r"\baber\b", r"\bdoch\b", r"stellte? sich (?:he)?raus", r"\btrotzdem\b", r"\bplötzlich\b", r"\bnur dass\b",
           r"\bwar'?s nicht\b", r"\bwar es nicht\b", r"\bpustekuchen\b", r"\bfalsch gedacht\b", r"\bstattdessen\b",
           r"\bin wahrheit\b", r"\bbis\b"],
}
_N = r"(?:\d+|a|an|one|a few|a couple of|two|three|four|five|six|seven|eight|nine|ten|several|some)"
_NDE = r"(?:\d+|ein paar|einigen|einer|einem|zwei|drei|vier|fünf|sechs|sieben|acht|neun|zehn)"
_MONTHS = {"en": "january|february|march|april|may|june|july|august|september|october|november|december",
           "de": "januar|februar|märz|april|mai|juni|juli|august|september|oktober|november|dezember"}
_DAYS = {"en": "monday|tuesday|wednesday|thursday|friday|saturday|sunday",
         "de": "montag|dienstag|mittwoch|donnerstag|freitag|samstag|sonntag"}
ANCHOR = {
    "en": [rf"\b{_N} (?:second|minute|hour|day|week|month|year)s? (?:ago|later)\b",
           r"\b(?:last|this|next) (?:night|morning|week|month|year|" + _DAYS["en"] + r")\b",
           r"\b(?:yesterday|today|tonight|recently)\b", rf"\b(?:on )?(?:{_DAYS['en']})\b", rf"\b(?:{_MONTHS['en']})\b",
           rf"\b(?:for|after|in) {_N} (?:second|minute|hour|day|week|month|year|tr(?:y|ie)|attempt)s?\b",
           r"\bsince\b", r"\b(?:day|week|part|episode|mistake|number|step|round|no\.?|#)\s?\d+",
           r"\b\d+ (?:of|out of) \d+\b", r"\b(?:first|second|third|fourth|fifth|tenth|last) (?:time|day|week|try)\b"],
    "de": [rf"\bvor {_NDE} (?:sekunden|minuten|stunden|tagen|wochen|monaten|jahren)\b",
           r"\bletzte[nrs]? (?:nacht|woche|monat|jahr)\b", r"\b(?:gestern|heute|neulich|vorhin)\b", r"\bseit\b",
           rf"\b(?:am )?(?:{_DAYS['de']})\b", rf"\b(?:{_MONTHS['de']})\b",
           rf"\bnach {_NDE} (?:sekunden|minuten|stunden|tagen|wochen|monaten|jahren|versuchen)\b",
           r"\b(?:folge|teil|tag|woche|fehler|nummer|schritt|runde|platz|nr\.?|#)\s?\d+", r"\b\d+ von \d+\b",
           r"\bzum (?:ersten|zweiten|dritten|\d+\.) mal\b"],
}
PROOF_NOTE = re.compile(r"\b(?:proof|beweis|beleg|demo|screen ?recording|bildschirm|screenshot)\b", re.I)


def load_phrases(lang: str, path: Path | None = None) -> list[tuple[str, re.Pattern]]:
    """(label, pattern) from references/phrases-<lang>.txt: one phrase per line, # comments, a trailing * matches
    any word ending, a line starting with re: is a regular expression (case-insensitive)."""
    p = path or REFERENCES / f"phrases-{lang}.txt"
    if not p.is_file():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        t = line.strip()
        if not t or t.startswith("#"):
            continue
        if t.startswith("re:"):
            out.append((t[3:].strip(), re.compile(t[3:].strip(), re.I)))
        else:
            out.append((t, phrase_regex(t)))
    return out


def crooked(token: str) -> bool:
    """A number that sounds measured, not made up: 37, 4.3, 1,247. Round (40, 1,000), single digits and years are
    not. A separator followed by exactly three digits groups thousands; any other separator is a decimal mark."""
    t = token.strip().rstrip("%").strip()
    m = re.fullmatch(r"(\d+(?:[.,]\d{3})*)(?:[.,](\d{1,2}|\d{4,}))?", t)
    if not m:
        return False
    whole, dec = re.sub(r"[.,]", "", m.group(1)), m.group(2)
    if dec and dec.strip("0"):
        return True
    if len(whole) == 4 and 1900 <= int(whole) <= 2099 and "," not in t and "." not in t:
        return False
    return len(whole) >= 2 and not whole.endswith("0")


def short_level(pack, key: str, default: str) -> str:
    v = pack.value(f"channel.script.short_checks.{key}", default)
    return v if v in LEVELS else "off"


def check_short(text: str, pack, lang: str | None = None, proof: str | None = None,
                phrases_file: Path | None = None) -> dict:
    """The reel rules for a Short's script (plan section "Script" for Shorts; built on 243 short videos of 7
    creators). Levels can be changed in channel.json script.short_checks.<rule> (error, warn, hint, off)."""
    raw = spoken_part(text)
    rule = re.search(r"^---[ \t]*$", text, re.M)
    notes = text[rule.end():] if rule else ""
    found: list[dict] = []
    passed: list[str] = []

    def add(lv: str, area: str, msg: str):
        if lv in LEVELS:
            found.append({"level": lv, "area": area, "text": msg})

    clean = form_check(raw, "off", add, passed)          # dashes are in the phrase list
    speak_check(text, add, passed)
    bl = blocks("\n".join(clean))
    if not bl:
        raise ValueError("no spoken text above the --- line")
    all_s = [x for b in bl for x in sentences(b["text"])]
    body = " ".join(b["text"] for b in bl)
    n_words = len(words(body))
    lens = [len(words(x)) for x in all_s]
    lang = (lang or str(pack.value("channel.language", "en") or "en")).lower()[:2]
    lists = lang if lang in FIRST_PERSON else "en"
    if lists != lang:
        add("hint", "language", f"no word lists for '{lang}': English lists are used. Add them to script_check.py.")
    wpm = float(pack.value("channel.script.words_per_minute", 150))
    stats = {"words": n_words, "sentences": len(all_s), "words_per_sentence": round(n_words / max(1, len(all_s)), 1),
             "longest_sentence": max(lens) if lens else 0, "paragraphs": len(bl), "parts": 1,
             "minutes": round(n_words / wpm, 1), "seconds": round(n_words / wpm * 60), "language": lang}

    # Length from the style pack.
    lo, hi = (pack.value("edit_style.shorts.words", [110, 170]) or [110, 170])[:2]
    msg = f"{n_words} words (about {stats['seconds']} s). Target {lo} to {hi}."
    if n_words > hi * 1.25 or n_words < lo * 0.75:
        add(short_level(pack, "length", "error"), "length", msg)
    elif not lo <= n_words <= hi:
        add("warn", "length", msg)
    else:
        passed.append(f"length: {n_words} words, about {stats['seconds']} s")
    max_w = int(pack.value("channel.script.sentence_max_words", 25))
    long_s = [x for n, x in zip(lens, all_s, strict=True) if n > max_w]
    if long_s:
        add("error", "sentences", f"{len(long_s)} sentence(s) over {max_w} words, e.g. \"{long_s[0][:70]}\"")

    # I-sentences against you-sentences.
    def has(sentence: str, group: set[str]) -> bool:
        return any(w.lower().replace("’", "'") in group for w in words(sentence))
    i_n = sum(1 for x in all_s if has(x, FIRST_PERSON[lists]))
    you_n = sum(1 for x in all_s if has(x, SECOND_PERSON[lists]))
    stats["i_sentences"], stats["you_sentences"] = i_n, you_n
    if i_n > you_n:
        passed.append(f"I-form: {i_n} I-sentences, {you_n} you-sentences")
    else:
        add(short_level(pack, "i_form", "error"), "i-form",
            f"{i_n} I-sentences, {you_n} you-sentences. Tell what you did, not what the viewer should do.")

    # The turn: an expectation, then the break (same or a later sentence).
    def first_hit(pats: list[str]) -> int | None:
        return next((k for k, x in enumerate(all_s) if any(re.search(p, x.lower()) for p in pats)), None)
    e_at = first_hit(EXPECT[lists])
    b_at = None if e_at is None else next((k for k in range(e_at, len(all_s))
                                           if any(re.search(p, all_s[k].lower()) for p in BREAK[lists])), None)
    if e_at is not None and b_at is not None:
        passed.append(f"turn: expectation in sentence {e_at + 1}, break in sentence {b_at + 1}")
    else:
        missing = "an expectation (what you thought)" if e_at is None else "the break after the expectation"
        add(short_level(pack, "turn", "warn"), "turn", f"no turn: {missing} is missing.")

    # An uneven real number, or a visible proof.
    nums = [x for x in dict.fromkeys(NUMBER.findall(body)) if crooked(x)]
    shown = bool(proof and proof.strip()) or bool(PROOF_NOTE.search(notes))
    if nums:
        passed.append(f"number: {', '.join(nums[:3])}")
    elif shown:
        passed.append("proof: a visible proof is noted")
    else:
        add(short_level(pack, "proof_number", "warn"), "proof",
            "no uneven real number (like 37 or 4.3) and no visible proof noted below ---. Round numbers sound made up.")

    # A time anchor or a number in a series.
    anchors = [m.group(0) for p_ in ANCHOR[lists] for m in re.finditer(p_, body.lower())]
    if anchors:
        passed.append(f"time anchor: {', '.join(list(dict.fromkeys(anchors))[:3])}")
    else:
        add(short_level(pack, "time_anchor", "warn"), "anchor",
            "no time anchor (\"three weeks ago\") and no number in a series (\"mistake 3 of 10\").")

    # The Writer's motion marks: at most five, below the --- line.
    check_motion_marks(text, body, add, passed, stats)

    # Phrases that sound written or like filler.
    hits = []
    for label, rx in load_phrases(lists, phrases_file):
        for m in rx.finditer(body):
            hits.append(m.group(0).strip()[:40] or label)
    hits = list(dict.fromkeys(hits))
    if hits:
        add(short_level(pack, "phrases", "error"), "phrases",
            f"phrases from the list (references/phrases-{lists}.txt): " + "; ".join(f"«{h}»" for h in hits[:8]))
    else:
        passed.append("phrases: none from the list")

    order = {"error": 0, "warn": 1, "hint": 2}
    found.sort(key=lambda f: order[f["level"]])
    errors = sum(1 for f in found if f["level"] == "error")
    return {"mode": "short", "stats": stats, "findings": found, "passed": passed, "errors": errors,
            "warnings": sum(1 for f in found if f["level"] == "warn"),
            "hints": sum(1 for f in found if f["level"] == "hint"), "ready": errors == 0,
            "manual": ["The user confirms the story really happened (\"This really happened\")."]}


def check_craft(text: str, pack, lang: str | None = None) -> dict:
    """Only the craft checks: for a studio whose own skill has its own script check."""
    found: list[dict] = []
    passed: list[str] = []
    stats: dict = {}

    def add(lv: str, area: str, msg: str):
        if lv in LEVELS:
            found.append({"level": lv, "area": area, "text": msg})

    manual = craft_check(text, pack, add, passed, stats, lang)["manual"]
    order = {"error": 0, "warn": 1, "hint": 2}
    found.sort(key=lambda f: order[f["level"]])
    errors = sum(1 for f in found if f["level"] == "error")
    return {"mode": "craft", "stats": stats, "findings": found, "passed": passed, "errors": errors,
            "warnings": sum(1 for f in found if f["level"] == "warn"),
            "hints": sum(1 for f in found if f["level"] == "hint"), "ready": errors == 0, "manual": manual}


def craft_line(c: dict) -> str:
    """One line of the craft numbers for the printed report."""
    if not c or "short_sentences_percent" not in c:
        return ""
    parts = ", ".join(f"{p['words']}" for p in c["parts"])
    return (f"craft: parts (words) {parts}; {c['short_sentences_percent']} % short sentences; {c['questions']} "
            f"questions ({c['questions_per_1000']} per 1,000); you {c['you']} / I {c['i']} (depth parts "
            f"{c['you_depth']} / {c['i_depth']}); {c['takeaways']} try-this for {c['depth_parts']} depth parts; "
            f"{c['objections']} objections; ending about {c['ending_seconds']} s, calls to action: "
            f"{', '.join(c['ending_calls_to_action']) or 'none'}")


def check_spoken(text: str, lang: str | None = None) -> dict:
    """Only the speak and story checks: for a studio whose own skill has its own script check."""
    found: list[dict] = []
    passed: list[str] = []

    def add(lv: str, area: str, msg: str):
        if lv in LEVELS:
            found.append({"level": lv, "area": area, "text": msg})

    for f in _spoken().speakable(text):
        add("error", "speak", f["text"] + ". Say it in words; shot ideas and notes go below ---.")
    if not found:
        passed.append("speak: every mark reads aloud")
    story_check(text, add, passed, lang)
    order = {"error": 0, "warn": 1, "hint": 2}
    found.sort(key=lambda f: order[f["level"]])
    errors = sum(1 for f in found if f["level"] == "error")
    return {"mode": "spoken", "findings": found, "passed": passed, "errors": errors, "ready": errors == 0}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Check a spoken script against the method and the style pack.")
    ap.add_argument("file", help="script file, e.g. brief/SCRIPT-v001.md")
    ap.add_argument("--title", help="the approved title; its numbers must be in the opening")
    ap.add_argument("--name", action="append", default=[], help="a name the opening must say (repeatable)")
    ap.add_argument("--facts", "--proof", dest="proof", metavar="FILE",
                    help="the gathered facts (work/material-vNNN.md, or brief/PROOF-vNNN.md when the proof step is on); "
                         "every number in the script must be in it")
    ap.add_argument("--interview", metavar="FILE", help="the creator's answers (brief/INTERVIEW-vNNN.md): the script "
                    "marks the lines that come from them")
    ap.add_argument("--pack", help="style pack folder (default: the active pack)")
    ap.add_argument("--text-only", action="store_true", help="print only the spoken part")
    ap.add_argument("--short", action="store_true", help="a Short's script: the reel rules instead of the long rules")
    ap.add_argument("--spoken", action="store_true",
                    help="only the speak and story checks (next to a studio's own script check, which stays as it is)")
    ap.add_argument("--craft", action="store_true",
                    help="only the craft checks (hook in 30 s, depth pattern, spoken rhythm, ending)")
    ap.add_argument("--minutes", metavar="MIN-MAX", help="target length from the brief, e.g. 11-14 (default: the "
                    "pack's edit-style.json length_minutes)")
    ap.add_argument("--language", help="with --short or --craft: language of the word lists (default: the pack's for "
                    "--short, the script's for --craft)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    p = Path(a.file)
    if not p.is_file():
        print(f"File not found: {p}", file=sys.stderr)
        return 2
    text = p.read_text(encoding="utf-8")
    if a.text_only:
        m = re.search(r"^---[ \t]*$", text, re.M)
        sys.stdout.write(text[:m.start()] if m else text)
        return 0
    if a.spoken:
        r = check_spoken(text, a.language)
        r["file"] = str(p)
        if a.json:
            print(json.dumps(r, ensure_ascii=False, indent=1))
        else:
            print(f"Speak and story check: {p}\n")
            for f in r["findings"]:
                print(f"  {f['level']:<5} [{f['area']}] {f['text']}")
            for x in r["passed"]:
                print(f"  ok    {x}")
            print(f"\nResult: {r['errors']} errors. Ready for the user: {'yes' if r['ready'] else 'no'}")
        return 0 if r["ready"] else 1
    pack = load_pack(a.pack)
    proof = Path(a.proof).read_text(encoding="utf-8") if a.proof else None
    minutes = None
    if a.minutes:
        m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*[-–]\s*(\d+(?:\.\d+)?)\s*", a.minutes)
        if not m:
            print(f"--minutes {a.minutes!r} is not a range like 11-14", file=sys.stderr)
            return 2
        minutes = (float(m.group(1)), float(m.group(2)))
    try:
        interview = Path(a.interview).read_text(encoding="utf-8") if a.interview else None
        r = (check_short(text, pack, a.language, proof) if a.short else
             check_craft(text, pack, a.language) if a.craft else
             check_script(text, pack, a.title, a.name, proof, interview, minutes))
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    r["file"] = str(p)
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=1))
    else:
        s = r["stats"]
        print(f"Script check: {p}")
        if a.short:
            print(f"{s['words']} words, {s['sentences']} sentences, about {s['seconds']} s, "
                  f"{s['i_sentences']} I-sentences, {s['you_sentences']} you-sentences ({s['language']})\n")
        elif a.craft:
            print(craft_line(s.get("craft", {})) + "\n")
        else:
            print(f"{s['words']} words, {s['sentences']} sentences, {s['words_per_sentence']} words per sentence, "
                  f"longest {s['longest_sentence']}, about {s['minutes']} min, {s['parts']} parts")
            print(craft_line(s.get("craft", {})) + "\n")
        for f in r["findings"]:
            print(f"  {f['level']:<5} [{f['area']}] {f['text']}")
        if r["passed"]:
            print("\nPassed:")
            for x in r["passed"]:
                print(f"  ok    {x}")
        if r.get("manual") and not a.short:
            print("\nBy hand (the Critic reads these):")
        for x in r.get("manual", []):
            print(f"  by hand {x}")
        print(f"\nResult: {r['errors']} errors, {r['warnings']} warnings, {r['hints']} hints. "
              f"Ready for the user: {'yes' if r['ready'] else 'no'}")
    return 0 if r["ready"] else 1


if __name__ == "__main__":
    sys.exit(main())
