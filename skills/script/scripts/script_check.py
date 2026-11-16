#!/usr/bin/env python3
"""Check a spoken script before it goes to the user (skill: skills/script).

Only the spoken part counts: everything above the first line that is just "---". Notes for the edit
(scenes, clips, where each number comes from) go below that line.

Limits come from the active style pack (crewcut.brand): channel.json "script", "closing_line",
edit-style.json "length_minutes", and voice.md ("## Words to avoid", "## Words to use").

  python3 skills/script/scripts/script_check.py brief/SCRIPT-v001.md --title "The title" --name ToolName
  python3 skills/script/scripts/script_check.py brief/SCRIPT-v001.md --proof brief/PROOF-v001.md --json
  python3 skills/script/scripts/script_check.py brief/SCRIPT-v001.md --text-only     (the spoken part only)

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


def _brand():
    try:
        from crewcut import brand
    except ImportError:  # run from a checkout without the package installed
        sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
        from crewcut import brand
    return brand


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


# ---------- the check ----------
def check_script(text: str, pack, title: str | None = None, names: list[str] | tuple = (),
                 proof: str | None = None) -> dict:
    raw = spoken_part(text)
    found: list[dict] = []
    passed: list[str] = []

    def add(lv: str, area: str, msg: str):
        if lv in LEVELS:
            found.append({"level": lv, "area": area, "text": msg})

    # 1. Teleprompter form: only words the user says. Line by line, collected per kind.
    per_kind: dict[tuple[str, str], list[str]] = {}

    def hit(lv, kind, nr, s):
        per_kind.setdefault((lv, kind), []).append(f'line {nr}: "{s[:50]}"')

    clean = []
    dash_lv = level(pack, "dash")
    for nr, line in enumerate(raw.split("\n"), 1):
        s = line.strip()
        if not s:
            clean.append("")
            continue
        heading = False
        if re.search(r"[\[\]{}]", s):
            hit("error", "square or curly bracket (stage notes go below ---)", nr, s)
        if re.search(r"[()]", s):
            hit("warn", "round bracket (hard to say aloud)", nr, s)
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

    # 9. Length from edit-style.json length_minutes and the speaking rate.
    wpm = float(pack.value("channel.script.words_per_minute", 150))
    lo_min, hi_min = (pack.value("edit_style.length_minutes", [3, 6]) or [3, 6])[:2]
    lo, hi = int(lo_min * wpm), int(hi_min * wpm)
    stats["minutes"] = round(n_words / wpm, 1)
    if n_words > hi * 1.25:
        add("error", "length", f"{n_words} words (about {stats['minutes']} min). Target {lo} to {hi}.")
    elif n_words < lo * 0.9 or n_words > hi * 1.06:
        add("hint", "length", f"{n_words} words (about {stats['minutes']} min). Target {lo} to {hi}.")
    else:
        passed.append(f"length: {n_words} words, about {stats['minutes']} min")

    # 10. No number without proof.
    if proof is not None:
        proof_nums = {norm_number(x) for x in NUMBER.findall(proof)}
        script_nums = [x for x in dict.fromkeys(NUMBER.findall(body)) if len(norm_number(x)) >= 2 or "%" in x
                       or "," in x or "." in x]
        missing = [x for x in script_nums if norm_number(x) not in proof_nums]
        if missing:
            add("warn", "proof", f"numbers not found in the proof file: {', '.join(missing[:8])}. Every number needs proof.")
        else:
            passed.append(f"proof: all {len(script_nums)} numbers appear in the proof file")

    order = {"error": 0, "warn": 1, "hint": 2}
    found.sort(key=lambda f: order[f["level"]])
    errors = sum(1 for f in found if f["level"] == "error")
    return {"stats": stats, "findings": found, "passed": passed, "errors": errors,
            "warnings": sum(1 for f in found if f["level"] == "warn"),
            "hints": sum(1 for f in found if f["level"] == "hint"), "ready": errors == 0}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Check a spoken script against the method and the style pack.")
    ap.add_argument("file", help="script file, e.g. brief/SCRIPT-v001.md")
    ap.add_argument("--title", help="the approved title; its numbers must be in the opening")
    ap.add_argument("--name", action="append", default=[], help="a name the opening must say (repeatable)")
    ap.add_argument("--proof", help="proof file (brief/PROOF-vNNN.md); every number in the script must be in it")
    ap.add_argument("--pack", help="style pack folder (default: the active pack)")
    ap.add_argument("--text-only", action="store_true", help="print only the spoken part")
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
    pack = load_pack(a.pack)
    proof = Path(a.proof).read_text(encoding="utf-8") if a.proof else None
    try:
        r = check_script(text, pack, a.title, a.name, proof)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    r["file"] = str(p)
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=1))
    else:
        s = r["stats"]
        print(f"Script check: {p}")
        print(f"{s['words']} words, {s['sentences']} sentences, {s['words_per_sentence']} words per sentence, "
              f"longest {s['longest_sentence']}, about {s['minutes']} min, {s['parts']} parts\n")
        for f in r["findings"]:
            print(f"  {f['level']:<5} [{f['area']}] {f['text']}")
        if r["passed"]:
            print("\nPassed:")
            for x in r["passed"]:
                print(f"  ok    {x}")
        print(f"\nResult: {r['errors']} errors, {r['warnings']} warnings, {r['hints']} hints. "
              f"Ready for the user: {'yes' if r['ready'] else 'no'}")
    return 0 if r["ready"] else 1


if __name__ == "__main__":
    sys.exit(main())
