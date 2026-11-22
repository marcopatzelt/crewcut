"""Is a script speakable, and does it tell one story? (skill: skills/script, references/story.md)

The user reads the script from a teleprompter, so only the spoken part counts: everything above the first line that is
only `---`. Shot ideas, the story plan and other notes go below that line; the teleprompter never shows them.

Two kinds of checks:

- `speakable(text)` is hard. It finds marks that do not read aloud: colons, semicolons, brackets, slashes, arrows,
  pipes, headings, list marks, timestamps, and a notes section ("Bildideen:", "Shots:") above the line. A script card
  is refused while one is left (`approvals.propose`), whichever skill wrote the script.
- `story(text)` is reading help for the Writer and the Critic: paragraphs that change topic without a bridge (list
  smell), staged run-ups ("Jetzt kommt der Teil, der alles ändert"), an idea said twice, a subscribe line in an odd
  place, and whether the notes hold the story plan (premise, arc, beats). Only a missing plan and a strong list smell
  are errors; the rest are warnings the Critic decides on.
"""

from __future__ import annotations

import re

RULE = re.compile(r"(?m)^---[ \t]*$")
WORD = re.compile(r"[^\W\d_]+(?:['’-][^\W\d_]+)*")
TIMESTAMP = re.compile(r"(?<![\d.,])\d{1,2}:\d{2}(?!\d)")
# A line that opens a notes section: "Bildideen:", "## Shots", "Notizen (nicht sprechen)". Never a spoken sentence:
# the section word stands at the line start and the line ends with a colon or after at most a short bracket.
NOTES_HEAD = re.compile(
    r"^\s*(?:#+\s*)?(?:bildideen|bildwünsche|shots?|shot\s?list|notizen|notes|visuals|b-roll|regie|"
    r"schnittnotizen|story(?:plan)?|stage notes)\b[^.!?]{0,60}?(?::|\)\s*$|$)", re.I)
MARKS = (
    ("colon", re.compile(r":"), "a colon"),
    ("semicolon", re.compile(r";"), "a semicolon"),
    ("bracket", re.compile(r"[()\[\]{}]"), "a bracket"),
    ("slash", re.compile(r"/"), "a slash"),
    ("arrow", re.compile(r"[→←⇒]|->|=>|<-"), "an arrow"),
    ("pipe", re.compile(r"\|"), "a pipe"),
)

STAGED = {
    "de": [r"\bjetzt kommt\b", r"\bund jetzt (?:wird|kommt)\b", r"\bhier wird(?:'s| es) (?:spannend|interessant)\b",
           r"\bund hier kommt\b", r"\bjetzt wird(?:'s| es)\b", r"\bder teil, der alles\b", r"\bpass (?:jetzt )?auf\b",
           r"\b(?:aber|und) (?:jetzt |hier )?(?:kommt )?das beste\b", r"\bes kommt noch besser\b",
           r"\bder clou\b", r"\bund dann kam der moment\b", r"\bdas ändert alles\b", r"\bwartet ab\b",
           r"\bwart(?:e)? ab\b", r"\bjetzt kommt die frage\b"],
    "en": [r"\bhere'?s the thing\b", r"\bhere'?s where it gets\b", r"\bthis is where it gets\b", r"\bnow comes\b",
           r"\bhere comes the\b", r"\bbut here'?s the (?:kicker|catch|twist)\b", r"\bwait for it\b",
           r"\bthe part that changes everything\b", r"\bit gets better\b", r"\bthis changes everything\b",
           r"\band then came the moment\b"],
}
SUBSCRIBE = re.compile(r"\babonnier|\bsubscribe|\bhit the bell|\bglocke\b", re.I)
# Connectors that tie a paragraph to the one before wherever they stand in its first sentence.
STRONG = {
    "de": {"aber", "doch", "deshalb", "deswegen", "darum", "daher", "trotzdem", "stattdessen", "seitdem", "dadurch",
           "weil", "denn", "also", "dann", "danach", "damals", "erst", "sondern", "allerdings", "nämlich"},
    "en": {"but", "so", "because", "instead", "since", "then", "until", "that's", "which", "though", "yet", "still"},
}
# Words that tie a paragraph to the one before: cause, contrast, time, or a pointer back.
CONNECT = {
    "de": {"aber", "doch", "deshalb", "deswegen", "darum", "daher", "also", "dann", "danach", "seitdem", "seither",
           "weil", "denn", "trotzdem", "stattdessen", "dabei", "damit", "dafür", "dadurch", "dazu", "davor", "darauf",
           "so", "sonst", "nur", "erst", "bis", "jetzt", "heute", "damals", "früher", "vorher", "nachher",
           "irgendwann", "inzwischen", "mittlerweile", "plötzlich", "genau", "eigentlich", "nämlich", "übrigens",
           "das", "dies", "diese", "dieser", "dieses", "diesen", "da", "dort", "hier", "er", "sie", "es", "ihn", "ihm",
           "und", "oder", "auch", "sogar", "noch", "zuerst", "anfangs", "endlich", "schließlich", "wenigstens",
           "immerhin", "allerdings", "jedenfalls", "wieder", "einmal", "selbst", "solche", "solcher", "solches",
           "derselbe", "dieselbe", "dasselbe", "gleich", "ebenso", "genauso", "statt", "anstatt", "sobald",
           "als", "wenn", "nachdem", "bevor", "seit", "obwohl"},
    "en": {"but", "so", "because", "then", "that", "this", "these", "those", "it", "they", "he", "she", "here",
           "there", "also", "even", "only", "still", "yet", "instead", "since", "after", "before", "until", "now",
           "today", "back", "and", "or", "which", "same", "such", "once", "again", "finally", "first", "later",
           "meanwhile", "anyway", "though", "although", "when", "while", "that's", "it's", "there's", "here's",
           "turns", "except", "unless"},
}
STOP = {
    "de": {"ich", "du", "wir", "ihr", "mein", "meine", "meinen", "meinem", "meiner", "dein", "deine", "dich", "dir",
           "mich", "mir", "uns", "eine", "einer", "einen", "einem", "eines", "ein", "der", "die", "das", "den", "dem",
           "des", "und", "oder", "aber", "nicht", "kein", "keine", "keinen", "noch", "schon", "auch", "nur", "mehr",
           "sehr", "ganz", "immer", "wieder", "dann", "wenn", "weil", "dass", "damit", "habe", "hab", "hat", "haben",
           "hatte", "hätte", "sind", "ist", "war", "waren", "wird", "werden", "wurde", "kann", "können", "konnte",
           "muss", "will", "soll", "einfach", "eigentlich", "gerade", "jetzt", "heute", "hier", "dort", "also",
           "etwas", "was", "wer", "wie", "wo", "alles", "nichts", "viel", "viele", "dieses", "diese", "dieser",
           "mit", "von", "für", "auf", "aus", "bei", "nach", "über", "unter", "vor", "zum", "zur", "ins", "im", "am",
           "um", "bis", "so", "es", "sie", "er", "man", "sich", "selbst", "richtig", "halt", "mal", "gibt", "macht",
           "machen", "mache", "gemacht", "sagt", "sage", "sagen", "geht", "gehen", "ging", "kommt", "kam", "kamen",
           "zwei", "drei", "vier", "fünf", "erst", "ersten", "erste", "letzte", "letzten", "andere", "anderen",
           "dafür", "dabei", "danach", "deshalb", "darum", "doch", "denn", "seitdem", "wirklich", "genau", "zeit"},
    "en": {"the", "and", "but", "that", "this", "with", "from", "have", "has", "had", "was", "were", "are", "is",
           "for", "you", "your", "they", "them", "their", "what", "when", "then", "than", "just", "only", "also",
           "into", "about", "there", "here", "which", "would", "could", "should", "will", "can", "did", "does",
           "doing", "done", "make", "made", "makes", "like", "really", "very", "much", "more", "most", "some",
           "every", "each", "even", "still", "because", "after", "before", "while", "where", "who", "how", "why",
           "its", "it's", "i'm", "i've", "don't", "didn't", "one", "two", "three", "first", "last", "time", "now",
           "today", "thing", "things", "said", "says", "say", "got", "get", "gets", "goes", "went", "came", "come"},
}
# Words that point back to what was just said: after a subscribe line they show the beat is not over.
BACK = {"de": {"dabei", "damit", "dadurch", "davon", "darauf", "dafür", "dazu", "daran", "darin", "dies", "diese",
               "dieser", "dieses"},
        "en": {"it", "this", "that", "these", "those", "there"}}
PLAN_KEYS = {
    "premise": re.compile(r"^\s*(?:[-*]\s*)?(?:#+\s*)?(?:premise|prämisse|kernsatz|roter faden|through-?line)\b"
                          r"\s*[:\-–]?\s*(?P<rest>.*)$", re.I),
    "arc": re.compile(r"^\s*(?:[-*]\s*)?(?:#+\s*)?(?:arc|bogen|spannungsbogen|dramaturgie)\b\s*[:\-–]?\s*"
                      r"(?P<rest>.*)$", re.I),
    "beats": re.compile(r"^\s*(?:[-*]\s*)?(?:#+\s*)?(?:beats?|takte|stationen)\b\s*[:\-–]?\s*(?P<rest>.*)$", re.I),
}
ARC_PARTS = {"hook": ("hook", "einstieg", "aufhänger"),
             "tension": ("tension", "problem", "spannung", "konflikt", "hindernis"),
             "turn": ("turn", "wende", "wendepunkt", "klick", "umschwung"),
             "payoff": ("payoff", "auflösung", "ergebnis", "lohn", "einlösung"),
             "close": ("close", "schluss", "ende", "abschluss")}


def split(text: str) -> tuple[str, str]:
    """(spoken part, notes): the text above and below the first line that is only `---`."""
    m = RULE.search(text)
    return (text[:m.start()], text[m.end():]) if m else (text, "")


def prompter_text(text: str) -> str:
    """What a teleprompter shows: the spoken part, cut again at a notes section that was put above the line."""
    spoken, _ = split(text)
    out, said = [], False
    for line in spoken.splitlines():
        if said and NOTES_HEAD.match(line) and not line.lstrip().startswith("**"):
            break
        said = said or bool(line.strip())
        out.append(line)
    return "\n".join(out)


def speakable(text: str) -> list[dict]:
    """Every mark in the spoken part that does not read aloud, one finding per kind with up to three lines."""
    spoken, _ = split(text)
    hits: dict[str, list[str]] = {}
    labels: dict[str, str] = {}

    def hit(kind: str, label: str, nr: int, line: str) -> None:
        labels[kind] = label
        hits.setdefault(kind, []).append(f'line {nr}: "{line.strip()[:60]}"')

    said = False
    for nr, line in enumerate(spoken.splitlines(), 1):
        s = line.strip()
        if not s:
            continue
        if said and NOTES_HEAD.match(s) and not s.startswith("**"):
            hit("notes", "a notes section above the --- line (shots and notes go below it)", nr, s)
        said = True
        if s.startswith("#") or re.match(r"^={2,}\s*$", s):
            hit("heading", "a heading", nr, s)
        if re.match(r"^(?:[-*•>]\s|\d+[.)]\s)", s):
            hit("list", "a list or quote mark at the line start", nr, s)
        if TIMESTAMP.search(s):
            hit("timestamp", "a timestamp", nr, s)
        for kind, rx, label in MARKS:
            if kind == "colon" and TIMESTAMP.search(s) and not rx.search(TIMESTAMP.sub(" ", s)):
                continue
            if rx.search(s):
                hit(kind, label, nr, s)
    return [{"kind": k, "text": f"{labels[k]}: {len(v)} time(s), " + "; ".join(v[:3]), "lines": v}
            for k, v in hits.items()]


class Unspeakable(Exception):
    """A script card whose spoken part has marks the user cannot read aloud. The text says what to fix."""


def require_speakable(text: str, name: str = "the script") -> None:
    found = speakable(text)
    if found:
        raise Unspeakable(
            f"{name} cannot go to the user yet: the teleprompter text has marks that do not read aloud. "
            + " ".join(f["text"] + "." for f in found)
            + " Say it in words (no colon, semicolon, bracket, slash or list mark) and put shot ideas and notes below "
              "the --- line.")


# ---------- story ----------
def _paragraphs(spoken: str) -> list[str]:
    return [" ".join(p.split()) for p in re.split(r"\n\s*\n", spoken) if p.strip()]


def _sentences(par: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?…])\s+", par.strip()) if WORD.search(s)]


def _words(text: str) -> list[str]:
    return [w.lower() for w in WORD.findall(text.replace("**", ""))]


def language(text: str) -> str:
    w = _words(split(text)[0])
    de = sum(1 for x in w if x in {"ich", "und", "das", "ist", "nicht", "der", "die", "mit", "ein", "auf"})
    en = sum(1 for x in w if x in {"i", "and", "the", "is", "not", "with", "a", "on", "it", "of"})
    return "de" if de >= en else "en"


def _stems(par: str, lang: str, common: set[str] | frozenset = frozenset()) -> set[str]:
    stop = STOP.get(lang, STOP["en"])
    return {w[:5] for w in _words(par) if len(w) >= 4 and w not in stop} - set(common)


def topic_words(pars: list[str], lang: str) -> set[str]:
    """Stems in more than a quarter of the paragraphs (the video's own topic, e.g. "Claude", "Video"): sharing them
    ties nothing together."""
    if len(pars) < 6:
        return set()
    counts: dict[str, int] = {}
    for p in pars:
        for w in _stems(p, lang):
            counts[w] = counts.get(w, 0) + 1
    return {w for w, n in counts.items() if n > len(pars) / 4}


def bridged(prev: str, par: str, lang: str, common: set[str] | frozenset = frozenset()) -> bool:
    """A paragraph is tied to the one before when its first sentence carries a connector (cause, contrast, time; a
    pointer back in its first words) or when it shares a content word with it that is not the video's topic word."""
    first = _words(" ".join(_sentences(par)[:1]))
    if any(w in CONNECT.get(lang, CONNECT["en"]) for w in first[:3]):
        return True
    if any(w in STRONG.get(lang, STRONG["en"]) for w in first):
        return True
    return bool(_stems(prev, lang, common) & _stems(par, lang, common))


def list_smell(text: str, lang: str | None = None) -> dict:
    """Transitions between paragraphs without a bridge. `jumps` lists the paragraphs that start a new topic out of
    nowhere; `share` is their part of all transitions."""
    spoken = prompter_text(text)
    lang = lang or language(text)
    pars = _paragraphs(spoken)
    common = topic_words(pars, lang)
    # The opening (paragraphs 1 to 3) may cut hard, and a short goodbye needs no bridge.
    last = len(pars) - 1 if pars and len(_words(pars[-1])) <= 6 else len(pars)
    checked = range(3, last)
    jumps = [{"paragraph": i + 1, "start": " ".join(pars[i].split()[:8])}
             for i in checked if not SUBSCRIBE.search(pars[i]) and not SUBSCRIBE.search(pars[i - 1])
             and not bridged(pars[i - 1], pars[i], lang, common)]
    n = max(1, len(checked))
    run, longest = 0, 0
    jumped = {j["paragraph"] for j in jumps}
    for i in range(4, last + 1):
        run = run + 1 if i in jumped else 0
        longest = max(longest, run)
    return {"paragraphs": len(pars), "transitions": len(checked), "jumps": jumps, "share": round(len(jumps) / n, 2),
            "longest_run": longest}


def staged(text: str, lang: str | None = None) -> list[str]:
    spoken = prompter_text(text).lower()
    lang = lang or language(text)
    return list(dict.fromkeys(m.group(0) for p in STAGED.get(lang, []) + (STAGED["en"] if lang != "en" else [])
                              for m in re.finditer(p, spoken)))


def repeats(text: str, lang: str | None = None, threshold: float = 0.6) -> list[tuple[str, str]]:
    """Pairs of sentences in different paragraphs that say much the same: at least three shared content words
    (topic words aside), and most of the shorter sentence's."""
    lang = lang or language(text)
    pars = _paragraphs(prompter_text(text))
    common = topic_words(pars, lang)
    items = [(i, s, _stems(s, lang, common)) for i, p in enumerate(pars) for s in _sentences(p)]
    out = []
    for a in range(len(items)):
        for b in range(a + 1, len(items)):
            (pa, sa, xa), (pb, sb, xb) = items[a], items[b]
            shared = len(xa & xb)
            if pa != pb and shared >= 3 and shared / min(len(xa), len(xb)) >= threshold:
                out.append((sa, sb))
    return out


def subscribe_place(text: str, lang: str | None = None) -> list[str]:
    """Where the subscribe line sits: once, after the first strong result, not at the very start or the very end, and
    not inside a beat (the paragraph after it continues the paragraph before it)."""
    pars = _paragraphs(prompter_text(text))
    lang = lang or language(text)
    at = [i for i, p in enumerate(pars) if SUBSCRIBE.search(p)]
    out = []
    if len(at) > 1:
        out.append(f"{len(at)} subscribe lines; one is enough")
    for i in at[:1]:
        if i <= 1:
            out.append("the subscribe line comes before anything was shown")
        elif i >= len(pars) - 2:
            out.append("the subscribe line sits at the end, where it sounds like a plea")
        else:
            first = _words(" ".join(_sentences(pars[i + 1])[:1]))[:3]
            if any(w in BACK.get(lang, BACK["en"]) for w in first):
                out.append("the subscribe line cuts a beat in two: the next paragraph points back past it")
    return out


def plan(text: str) -> dict:
    """The story plan below the --- line: premise (one sentence), arc (hook, tension, turn, payoff, close) and 3 to 5
    beats. Labels in English or German, e.g. "Prämisse:", "Bogen:", "Beats:"."""
    _, notes = split(text)
    lines = notes.splitlines()
    found: dict = {"premise": "", "arc": "", "beats": []}
    for i, line in enumerate(lines):
        for key, rx in PLAN_KEYS.items():
            m = rx.match(line)
            if not m or (key in ("premise", "arc") and found[key]) or (key == "beats" and found["beats"]):
                continue
            rest = m.group("rest").strip()
            follow = []
            for nxt in lines[i + 1:]:
                if not nxt.strip() or any(r.match(nxt) for r in PLAN_KEYS.values()):
                    break
                follow.append(nxt.strip())
            if key == "beats":
                items = [re.sub(r"^(?:[-*•]|\d+[.)])\s*", "", x) for x in follow if re.match(r"^(?:[-*•]|\d+[.)])", x)]
                if not items and rest:
                    items = [x.strip() for x in re.split(r"\s*[;·]\s*|\s+\d+[.)]\s+", rest) if x.strip()]
                found["beats"] = items
            else:
                found[key] = " ".join([rest, *follow]).strip()
    arc = found["arc"].lower()
    found["arc_parts"] = [k for k, names in ARC_PARTS.items() if any(n in arc for n in names)]
    problems = []
    if not found["premise"]:
        problems.append("no premise (one sentence: what the whole video is about, the through-line)")
    if not found["arc"]:
        problems.append("no arc (hook, tension or problem, turning point, payoff, close)")
    elif len(found["arc_parts"]) < 4:
        problems.append("the arc names only " + (", ".join(found["arc_parts"]) or "none") + " of hook, tension, turn, "
                        "payoff, close")
    if not 3 <= len(found["beats"]) <= 5:
        problems.append(f"{len(found['beats'])} beats; plan 3 to 5 that serve the arc")
    found["problems"] = problems
    return found


# Share of jumps. Measured on 7 drafts of one episode: told as one story 0.17, told as a list 0.26 to 0.38.
SMELL_ERROR, SMELL_WARN = 0.25, 0.2
PLAN_MIN_WORDS = 150   # a text this long tells a story and needs its plan; a few lines do not


def story(text: str, lang: str | None = None) -> list[dict]:
    """Findings for the Writer and the Critic: error for a missing story plan and a strong list smell (from 6
    transitions on: SMELL_ERROR of them jump, or three paragraphs in a row start a new topic), warn or hint for the
    rest."""
    lang = lang or language(text)
    out = []
    p = plan(text)
    if p["problems"]:
        long = len(_words(prompter_text(text))) >= PLAN_MIN_WORDS
        out.append({"level": "error" if long else "hint", "area": "story",
                    "text": "story plan below --- incomplete: " + "; ".join(p["problems"]) + ". Write premise, arc and "
                            "beats before the draft (skills/script/references/story.md)."})
    smell = list_smell(text, lang)
    if smell["jumps"]:
        where = "; ".join(f'paragraph {j["paragraph"]} "{j["start"]}"' for j in smell["jumps"][:4])
        strong = smell["transitions"] >= 6 and (smell["share"] >= SMELL_ERROR or smell["longest_run"] >= 3)
        lv = "error" if strong else "warn" if smell["share"] >= SMELL_WARN else "hint"
        out.append({"level": lv, "area": "story",
                    "text": f"list smell: {len(smell['jumps'])} of {smell['transitions']} paragraphs start a new topic "
                            f"without a bridge ({where}). Tie each beat to the one before with cause or contrast "
                            "(deshalb, aber, und dann; so, but, and then), or cut the beat."})
    st = staged(text, lang)
    if st:
        out.append({"level": "warn", "area": "story",
                    "text": "staged run-up: " + ", ".join(f"«{x}»" for x in st[:4]) + ". Say the point itself."})
    rep = repeats(text, lang)
    if rep:
        out.append({"level": "warn", "area": "story",
                    "text": f'idea said twice: "{rep[0][0][:50]}" and "{rep[0][1][:50]}". Keep the stronger one.'})
    for msg in subscribe_place(text, lang):
        out.append({"level": "warn", "area": "story", "text": msg + "."})
    return out


__all__ = ["split", "prompter_text", "speakable", "require_speakable", "Unspeakable", "list_smell", "staged",
           "repeats", "subscribe_place", "plan", "story", "bridged", "language"]
