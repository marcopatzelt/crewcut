"""Script craft: the measurable part of how a long explainer is written (skill: skills/script, references/craft.md).

Four groups. Since 27 Nov 2026 they follow a study of Alex Hormozi's long videos (54 best against 33 typical ones,
443 openings, 542 endings) and the curves of one channel that applied it; the older rules from 119 videos of three
English-language education channels that the study contradicted are gone (a recap list and a goodbye at the end, an
honest limit by 0:45, "try this" in every part, a number in the first sentences):

1. Opening: a result or claim first (no greeting), a plan with a count by 0:30, at most one open loop, and no limit,
   caveat or background before the first content (the `[[first content | ...]]` mark below ---).
2. Counted units: each 45 to 75 seconds, a test step with its own evidence; examples, sums said aloud, contrast pairs,
   parts counted aloud; at most one "try this" line in the whole video, the advice belongs in the sentence.
3. Spoken rhythm: connected sentences, then a short punch line; questions at the joints (1.5 to 4 a minute), each
   answered in the next sentence and never with "because"; the viewer's objection said aloud; "you" at least as often
   as "I".
4. Ending: a verdict, then at most one link sentence, in at most 25 seconds; no goodbye, no recap and no list of the
   parts in the last 60 seconds; the one fixed ask (subscribe) stands between 15 and 60 % of the script, never in the
   ending; the hook's open loop is resolved.

`check(text, lang, wpm, cfg)` measures a script (the spoken part above the first `---` line) and returns findings
(error, warn, hint), the passed checks and the numbers. A program can only see words, so every rule here is a signal for
the Writer and the Critic: what it cannot see is listed in `MANUAL` for the Critic's pass. Levels and limits come from
the style pack (`channel.json` `script.craft`, see docs/style-packs.md); German and English word lists are built in.
A studio with its own style checker (the style gate, crewcut/stylegate.py) gets its hard gate there; these checks stay
the Writer's quick signal.
"""

from __future__ import annotations

import re

from . import spoken

LEVELS = ("error", "warn", "hint", "off")
DEFAULTS: dict = {
    "hook_seconds": 30,          # the plan with a count comes by then
    "limit_seconds": 45,         # only for a pack that switches the old "limit" check back on
    "start_rate": 1.2,           # the first minute is dense: about this much faster than the base rate
    "idea_seconds": [45, 75],    # one counted unit
    "part_max_seconds": 180,     # a longer part holds several units
    "depth_min_words": 80,       # a shorter part between opening and ending is a bridge, not a unit
    "end_seconds": 25,           # the verdict plus the link sentence
    "end_min_words": 30,         # a very short last part takes the part before it
    "end_window_seconds": 60,    # no goodbye and no recap in this last stretch
    "short_words": 5,            # a sentence of at most this many words is a punch line
    "short_share": [15, 40],     # percent of short sentences
    "questions_per_1000": [7.5, 20],  # 1.5 to 4 questions a minute at 200 words a minute
    "takeaways_max": 1,          # "try this" lines in the whole script
    "ask_share": [0.15, 0.6],    # the one fixed ask (subscribe) stands between these shares of the words
    "min_words": 150,            # shorter texts get only the greeting check
    "checks": {
        "greeting": "error", "roadmap": "warn", "open_loop": "hint", "stakes": "hint", "limit": "off",
        "limit_before_content": "warn", "part_length": "warn", "takeaways": "warn", "concrete": "hint",
        "signposts": "hint", "short_share": "hint", "questions": "warn", "answers": "warn", "objections": "hint",
        "repeat": "hint", "you_i": "warn", "ending_length": "warn", "cta": "warn", "subscribe_once": "warn",
        "recap": "error", "greeting_end": "error", "loop_resolved": "warn",
    },
}
# Checks that existed before 27 Nov 2026 and contradict the rule set; a pack that still names them changes nothing.
RETIRED = ("hook_number", "ending_parts")
MANUAL = [
    "Sentence 1 is a claim or a result of the own test that proves the title's promise, not a run-up.",
    "By 0:15 the viewer sees the real result with its exact number; 0:10 to 0:20 carry a number or the announcement.",
    "The title's topic comes before any other; before point one only proof, number, announcement, the viewer's "
    "situation, the plan or the one open loop.",
    "Each counted unit is an action or a test step with its own evidence, and two units in a row never use the same "
    "kind of evidence.",
    "Before every lesson stands a test, a picture or a story from this video; every claim gets its evidence at once.",
    "The end of each unit opens the question the next one answers.",
    "A viewer who never saw the creator understands every name and every reference the first time.",
    "Every open loop is resolved with exactly the promised thing (same number, same picture).",
    "The end is a verdict that picks up sentence 1, not a summary of the parts; no goodbye.",
    "It sounds spoken, in the creator's words, without translated phrases or nested clauses; every number is in the "
    "episode's material.",
]

_NUM = r"\d+(?:[.,]\d+)*"
NUMBER = re.compile(r"(?<![\w.,])\d+(?:[.,]\d+)*")
WORD = re.compile(r"[^\W_]+(?:['’.,-][^\W_]+)*")

_COUNT = {"en": r"(?:two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|[2-9]|1[0-2])",
          "de": r"(?:zwei|drei|vier|fünf|sechs|sieben|acht|neun|zehn|elf|zwölf|[2-9]|1[0-2])"}
_PARTS = {
    "en": r"(?:steps|parts|jobs|roles|mistakes|rules|tricks|stages|levels|points|things|ways|reasons|questions|tips|"
          r"lessons|tools|ideas|levers|phases|tasks|tests|layers|agents|models|workflows|principles|habits|hacks|"
          r"problems|decisions|checks|moves|specialists)",
    "de": r"(?:jobs|schritte|teile|rollen|fehler|regeln|tricks|stufen|punkte|dinge|wege|gründe|fragen|tipps|lektionen|"
          r"agents|agenten|werkzeuge|tools|ideen|hebel|bausteine|phasen|aufgaben|bereiche|ebenen|prüfungen|tests|"
          r"stationen|beispiele|spezialisten|helfer|module|versuche|modelle|abläufe|prinzipien|probleme|entscheidungen)",
}
_NUMWORDS = {
    "en": r"(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|twenty|thirty|forty|fifty|hundred|"
          r"thousand|million|billion)",
    "de": r"(?:null|eins?|zwei|drei|vier|fünf|sechs|sieben|acht|neun|zehn|elf|zwölf|zwanzig|dreißig|vierzig|fünfzig|"
          r"hundert|tausend|millionen?|milliarden?)",
}


def _rx(*parts: str) -> re.Pattern:
    return re.compile("|".join(parts), re.I)


WORDS: dict[str, dict] = {
    "en": {
        "greeting": _rx(r"^(?:hi|hey|hello|welcome|what'?s up|good (?:morning|afternoon|evening)|yo)\b"),
        "stakes": _rx(r"\bif you\b", r"\bfor you\b", r"\bcosts?\b", r"\blos(?:e|ing)\b", r"\bwast(?:e|es|ing)\b",
                      r"\bsaves?\b", r"\bmatters?\b", r"\bproblem\b", r"\brisk\b", r"\bat stake\b"),
        "open_loop": _rx(r"\bat the (?:very )?end\b", r"\bby the end\b", r"\blater (?:in this video|on)\b",
                         r"\bstick around\b", r"\bbefore (?:we|I) (?:finish|wrap up)\b", r"\bI'?ll get to (?:that|it)\b"),
        "resolved": _rx(r"\bpromised\b", r"\bat the (?:start|beginning)\b", r"\bremember (?:the|when|at)\b",
                        r"\bas I said\b", r"\bback to (?:the|that)\b"),
        "limit": _rx(r"\bperfect\b[^.!?]{0,30}\?\s*no\b", r"\bnot perfect\b", r"\bnot yet\b", r"\bcan(?:'t|not)\b",
                     r"\b(?:doesn't|does not|didn't|did not) (?:work|handle|do|get|see|hear|know)\b", r"\blimits?\b",
                     r"\bweak(?:ness|er|est)?\b", r"\bfail(?:s|ed)?\b", r"\bstill (?:looks|sounds|feels)\b",
                     r"\bisn'?t (?:perfect|great|good|there)\b", r"\bstruggles?\b"),
        "takeaway": _rx(r"\btry this\b", r"\bhere'?s (?:your|a small) task\b", r"\byour (?:homework|task)\b",
                        r"\bwhat you can take (?:away|from this)\b", r"\btake this with you\b",
                        r"\byou can do this (?:today|now|yourself)\b", r"\bdo this (?:today|yourself)\b"),
        "example": _rx(r"\blet'?s say\b", r"\bfor example\b", r"\bfor instance\b", r"\bimagine\b", r"\bsay you\b",
                       r"\bsuppose\b", r"\bpicture this\b"),
        "math": _rx(r"\btimes\b", r"\bdivided by\b", r"\bmultipl", r"\bplus\b", r"\bminus\b", r"\bequals\b",
                    r"\bcomes to\b", r"\badds up to\b", r"\bthat'?s\b", r"\bmakes\b"),
        "contrast": _rx(r"\bversus\b", r"\bvs\b", r"\bagainst\b", r"\binstead of\b", r"\bcompared (?:to|with)\b",
                        r"\brather than\b"),
        "signpost": _rx(r"\b(?:step|part|job|role|rule|point|stage|mistake|tip|number|level)\s+(?:one|two|three|four|"
                        r"five|six|seven|eight|nine|ten|[1-9])\b",
                        r"\bthe (?:first|second|third|fourth|fifth|sixth|seventh|eighth) (?:step|thing|job|part|role|"
                        r"rule|mistake|tip|one|stage|level)\b", r"\b(?:first|second|third|fourth)ly\b"),
        "objection": _rx(r"\byou might (?:think|be thinking|say|wonder|ask)\b",
                         r"\byou(?:'re| are) (?:probably )?(?:thinking|wondering)\b", r"\bnow you'?re like\b",
                         r"\bbut wait\b", r"\byou may (?:think|ask)\b", r"\bsounds too good\b"),
        "repeat": _rx(r"\bI'?ll say (?:that|it) again\b", r"\bsaid differently\b", r"\bin other words\b",
                      r"\bonce more\b", r"\blet me repeat\b", r"\bagain\s*[,:]?\s*\d"),
        "joint": _rx(r"\band so\b", r"\bthe reason\b", r"\bwhich means\b", r"\bthat means\b", r"\bbecause\b",
                     r"\bthat'?s why\b", r"\bso\b"),
        "recap": _rx(r"\bto recap\b", r"\bin one sentence\b", r"\bquick recap\b", r"\bto sum up\b",
                     r"\bin summary\b", r"\blet'?s recap\b", r"\bone more time,? the\b", r"\bonce more,? the\b"),
        "greeting_end": _rx(r"\bthanks?(?: you)? (?:so much )?for watching\b", r"\bthank you\b", r"\bsee you\b",
                            r"\bbye\b", r"\buntil next time\b", r"\btake care\b", r"\bcatch you\b"),
        "because": _rx(r"^(?:because|'cause|cause)\b"),
        "human": _rx(r"\byourself\b", r"\bmyself\b", r"\bstill (?:do|does|decide|film|record|check|choose)\b",
                     r"\byou decide\b", r"\bI decide\b", r"\bstays with (?:you|me)\b", r"\bhumans?\b",
                     r"\byour (?:job|part)\b", r"\bmy (?:job|part)\b"),
        "verdict": _rx(r"\bverdict\b", r"\bbottom line\b", r"\bfor me\b", r"\bin my opinion\b", r"\bworth it\b",
                       r"\bmy take\b"),
        "caveat": _rx(r"\bnot\b", r"n't\b", r"\bbut\b", r"\bstill\b", r"\bonly\b", r"\byet\b"),
        "cta": {
            "link": _rx(r"\blink\b", r"\bdescription\b", r"\bsign up\b", r"\bdownload\b", r"\bthe form\b",
                        r"\bget it (?:for )?free\b"),
            "subscribe": _rx(r"\bsubscrib", r"\bhit the bell\b"),
            "comment": _rx(r"\bcomment", r"\blet me know (?:in|below)\b"),
            "next video": _rx(r"\b(?:watch|check out) (?:this|my|the next) video\b", r"\bnext video\b",
                              r"\bvideo (?:right )?here\b"),
            "like": _rx(r"\blike (?:this|the) video\b", r"\bthumbs up\b", r"\bhit (?:the )?like\b"),
            "follow": _rx(r"\bfollow me\b"),
        },
        "you": {"you", "you're", "you've", "you'd", "you'll", "your", "yours", "yourself", "yourselves"},
        "i": {"i", "i'm", "i've", "i'd", "i'll", "me", "my", "mine", "myself"},
    },
    "de": {
        "greeting": _rx(r"^(?:hallo|hey|hi|servus|moin|na\b|willkommen|herzlich willkommen|"
                        r"guten (?:morgen|tag|abend)|schön, dass)\b"),
        "stakes": _rx(r"\bwenn du\b", r"\bfür dich\b", r"\bkoste[nt]?\b", r"\bverlier", r"\bfress", r"\bfrisst\b",
                      r"\bsparst?\b", r"\bwichtig\b", r"\bproblem\b", r"\brisiko\b", r"\bauf dem spiel\b",
                      r"\bzählt\b"),
        "open_loop": _rx(r"\bam ende\b", r"\bzum schluss\b", r"\bam schluss\b", r"\bzum ende\b", r"\bbis zum ende\b",
                         r"\bspäter\b", r"\bdazu komme ich\b", r"\bverrate ich\b", r"\bnoch eine sache\b"),
        "resolved": _rx(r"versprochen", r"\bam anfang\b", r"\bzu beginn\b", r"\beingangs\b", r"\bwie angekündigt\b",
                        r"\bvom anfang\b"),
        "limit": _rx(r"\bperfekt\b[^.!?]{0,30}\?\s*nein\b", r"\bnicht perfekt\b", r"\bnoch nicht\b",
                     r"\bkann\b[^.!?]{0,40}\bnicht\b", r"\bkann kein", r"\bgrenzen?\b", r"\bschwäche",
                     r"\bklappt (?:noch )?nicht\b", r"\bfunktioniert (?:noch )?nicht\b",
                     r"\bnoch\b[^.!?]{0,40}\b(?:künstlich|schwach|schlecht|holprig|langsam|fehlerhaft)",
                     r"\bnicht alles\b", r"\bscheitert\b", r"\bgescheitert\b", r"\bnicht gut\b"),
        "takeaway": _rx(r"\bprobier (?:das|es|mal|doch)\b", r"\bwas du (?:daraus |hier )?mitnimmst\b",
                        r"\bnimm (?:dir )?(?:das )?mit\b", r"\bmach das (?:mal )?selbst\b", r"\bteste das\b",
                        r"\bdeine aufgabe\b", r"\bdas gilt auch (?:für dich|bei dir|in deinem|im eigenen)\b"),
        "example": _rx(r"\bnehmen wir (?:an|mal)\b", r"\bzum beispiel\b", r"\bein beispiel\b", r"\bstell dir vor\b",
                       r"\bangenommen\b", r"\bsagen wir\b"),
        "math": _rx(r"\bmal\b", r"\bgeteilt\b", r"\bergibt\b", r"\bergeben\b", r"\bsind das\b", r"\bdas sind\b",
                    r"\bmacht\b", r"\bplus\b", r"\bminus\b"),
        "contrast": _rx(r"\bgegen\b", r"\bstatt\b", r"\banstatt\b", r"\bim vergleich\b", r"\bversus\b"),
        "signpost": _rx(r"\b(?:job|schritt|teil|rolle|regel|punkt|stufe|fehler|tipp|nummer)\s+(?:eins|zwei|drei|vier|"
                        r"fünf|sechs|sieben|acht|neun|zehn|[1-9])\b",
                        r"\b(?:der|die|das) (?:erste|zweite|dritte|vierte|fünfte|sechste|siebte|achte)\b",
                        r"\b(?:erstens|zweitens|drittens|viertens)\b"),
        "objection": _rx(r"\bjetzt denkst du\b", r"\bdu denkst (?:jetzt|dir|vielleicht)\b", r"\bvielleicht denkst du\b",
                         r"\bdu fragst dich\b", r"\bjetzt fragst du\b", r"\bdu wirst (?:jetzt )?sagen\b",
                         r"\baber (?:warte|moment)\b", r"\bklingt (?:zu schön|teuer|kompliziert)\b"),
        "repeat": _rx(r"\bich sag'?s (?:nochmal|noch einmal)\b", r"\banders gesagt\b", r"\bnoch einmal\b[^.!?]*\d"),
        "joint": _rx(r"\bdeshalb\b", r"\bdeswegen\b", r"\bdarum\b", r"\bdaher\b", r"\bdas heißt\b", r"\bder grund\b",
                     r"\bweil\b", r"\balso\b", r"\bdadurch\b", r"\bund dann\b"),
        "recap": _rx(r"\bnoch einmal (?:die|alle|kurz)\b", r"\bin einem satz\b", r"\bzusammengefasst\b",
                     r"\bzusammenfassend\b", r"\bkurz zusammen\b", r"\balso nochmal\b", r"\bnoch mal kurz\b",
                     r"\bfassen wir\b[^.!?]{0,20}\bzusammen\b"),
        "greeting_end": _rx(r"\bdanke\b", r"\btschüss\b", r"\bbis zum nächsten mal\b", r"\bbis bald\b",
                            r"\bmacht'?s gut\b", r"\bciao\b", r"\bwir sehen uns\b", r"\bbis dann\b"),
        "because": _rx(r"^(?:weil)\b"),
        "human": _rx(r"\bselbst\b", r"\bselber\b", r"\bbleibt (?:bei )?(?:dir|mir|dem menschen)\b",
                     r"\bdu entscheidest\b", r"\bentscheide ich\b"),
        "verdict": _rx(r"\burteil\b", r"\bfazit\b", r"\bunterm strich\b", r"\bfür mich\b", r"\bmeiner meinung nach\b",
                       r"\blohnt\b"),
        "caveat": _rx(r"\bnicht\b", r"\bnoch\b", r"\baber\b", r"\bnur\b", r"\bkein"),
        "cta": {
            "link": _rx(r"\blink\b", r"\bbeschreibung\b", r"\bformular\b", r"\bmeld(?:e)? dich\b", r"\bherunterladen\b",
                        r"\bhol dir\b", r"\btrag dich\b", r"\beintragen\b"),
            "subscribe": _rx(r"\babonnier", r"\bglocke\b"),
            "comment": _rx(r"\bkommentar", r"\bschreib (?:mir|es|das) (?:in|unten)\b"),
            "next video": _rx(r"\bnächste[ns]? (?:video|folge)\b", r"\bschau dir (?:[\wäöüß]+ ){0,3}(?:video|folge)\b"),
            "like": _rx(r"\bdaumen\b", r"\blike\b"),
            "follow": _rx(r"\bfolg mir\b"),
        },
        "you": {"du", "dich", "dir", "dein", "deine", "deinen", "deinem", "deiner", "deines"},
        "i": {"ich", "mich", "mir", "mein", "meine", "meinen", "meinem", "meiner", "meines"},
    },
}
_NOUN_STOP = {"ende", "schluss", "anfang", "video", "folge", "sache", "teil", "heute", "today", "thing", "things", "part",
              "show", "tell", "this", "that", "what", "when", "then", "will", "with", "zeige", "dann", "aber", "warum",
              "wenn", "your", "you'll", "i'll", "later", "here", "there", "they", "them", "from", "into", "just", "also",
              "auch", "eine", "einen", "dass", "noch", "ganz", "mehr", "have", "does", "much", "whole", "very", "back"}


def settings(raw: dict | None = None) -> dict:
    """DEFAULTS with a style pack's `script.craft` block on top (unknown keys are kept, bad levels turn "off", retired
    checks stay off)."""
    cfg = {k: (dict(v) if isinstance(v, dict) else v) for k, v in DEFAULTS.items()}
    for k, v in (raw or {}).items():
        if k == "checks" and isinstance(v, dict):
            cfg["checks"].update({str(a): (b if b in LEVELS else "off") for a, b in v.items() if a not in RETIRED})
        elif v is not None:
            cfg[k] = v
    return cfg


def words(text: str) -> list[str]:
    return WORD.findall(text.replace("**", ""))


def sentences(par: str) -> list[str]:
    """Split on . ! ? and the ellipsis. A single letter before a period ("e.g.", "z. B.") does not end a sentence."""
    out, cur = [], ""
    for piece in re.split(r"(?<=[.!?…])\s+", par.strip()):
        cur = f"{cur} {piece}".strip() if cur else piece
        if re.search(r"(?:^|\s|\.)[^\W\d_]\.$", cur):
            continue
        out.append(cur)
        cur = ""
    if cur:
        out.append(cur)
    return [s for s in out if WORD.search(s)]


def parts(text: str) -> list[list[list[str]]]:
    """The spoken part as parts (separated by three empty lines) of paragraphs (one empty line) of sentences."""
    body = spoken.prompter_text(text).replace("**", "")
    out: list[list[list[str]]] = []
    buf: list[str] = []
    empty = 3

    def flush():
        if buf:
            out[-1].append(sentences(" ".join(buf)))
            buf.clear()

    for line in body.split("\n"):
        if line.strip():
            if not buf:
                if not out or empty >= 3:
                    out.append([])
            buf.append(line.strip())
            empty = 0
        else:
            flush()
            empty += 1
    flush()
    return [p for p in out if any(p)]


def _lead(sents: list[str], n_words: int) -> str:
    out, c = [], 0
    for s in sents:
        if c >= n_words:
            break
        out.append(s)
        c += len(words(s))
    return " ".join(out)


MARK = re.compile(r"\[\[\s*(?P<kind>first content|urteil|verdict)\s*\|(?P<words>[^\]]*)\]\]", re.I)


def _mark(text: str, kinds: tuple[str, ...]) -> list[str] | None:
    """The words of a mark below the --- line ([[first content | "..."]], [[urteil | "..."]]), lower case."""
    _, notes = spoken.split(text)
    for m in MARK.finditer(notes):
        if m.group("kind").lower() in kinds:
            ws = [w.lower() for w in words(m.group("words").strip().strip('"“”„\'').strip())]
            return ws or None
    return None


def _find(alls: list[str], ws: list[str] | None) -> int | None:
    """The index of the sentence where the marked words start, or None."""
    if not ws:
        return None
    probe = " ".join(ws[:6])
    for k, s in enumerate(alls):
        if probe in " ".join(w.lower() for w in words(s)):
            return k
    return None


def check(text: str, lang: str | None = None, wpm: float = 150, cfg: dict | None = None) -> dict:
    """Measure the four craft groups. Returns {"findings": [...], "passed": [...], "stats": {...}, "manual": [...]}.
    `cfg` may also carry `closing_line`: the channel's own last sentence, which the goodbye check leaves alone."""
    c = settings(cfg)
    lang = (lang or spoken.language(text)).lower()[:2]
    lists = lang if lang in WORDS else "en"
    W = WORDS[lists]
    found: list[dict] = []
    passed: list[str] = []

    def add(rule: str, area: str, msg: str, level: str | None = None):
        lv = c["checks"].get(rule, "hint")
        lv = level if level and lv != "off" else lv      # a softer level for a partial miss, unless switched off
        if lv in ("error", "warn", "hint"):
            found.append({"level": lv, "area": area, "rule": rule, "text": msg})

    def on(rule: str) -> bool:
        return c["checks"].get(rule, "hint") in ("error", "warn", "hint")

    P = parts(text)
    S = [(s, pi) for pi, p in enumerate(P) for par in p for s in par]   # (sentence, part index)
    alls = [s for s, _ in S]
    n_words = sum(len(words(s)) for s in alls)
    part_words = [sum(len(words(s)) for par in p for s in par) for p in P]
    sec = lambda w: round(w / max(wpm, 1) * 60)  # noqa: E731
    stats: dict = {"language": lists, "words": n_words, "parts": [{"words": w, "seconds": sec(w)} for w in part_words]}
    out = {"findings": found, "passed": passed, "stats": stats, "manual": MANUAL}
    if not alls:
        return out
    starts, acc = [], 0                 # word position of each sentence
    for s in alls:
        starts.append(acc)
        acc += len(words(s))

    # Group 1: the opening (no greeting first, at any length).
    greet = [s for s in alls[:2] if W["greeting"].search(s)]
    if greet:
        add("greeting", "hook", f'greeting before the hook ("{greet[0][:60]}"). Open with the result or the claim.')
    if n_words < c["min_words"]:
        stats["note"] = f"shorter than {c['min_words']} words: only the greeting is checked"
        return out
    start = wpm * float(c["start_rate"])
    hook_w, limit_w = round(start * c["hook_seconds"] / 60), round(start * c["limit_seconds"] / 60)
    hook, by_limit = _lead(alls, hook_w), _lead(alls, limit_w)
    stats.update(hook_words=hook_w)
    where = f"in the first {hook_w} words (about {c['hook_seconds']} s)"
    roadmap = re.search(rf"\b{_COUNT[lists]}\s+(?:[^\W\d_][\w'-]*\s+){{0,2}}{_PARTS[lists]}\b", hook, re.I)
    if roadmap:
        passed.append(f'opening: a plan with a count ("{roadmap.group(0)}")')
    else:
        add("roadmap", "hook", f'no plan with a count {where} ("the four jobs", "three steps"). Tell the viewer how '
            "long the trip is.")
    loop = next((s for s in alls if W["open_loop"].search(s) and s in hook), None)
    if loop:
        passed.append(f'opening: an open loop ("{loop[:50]}")')
    else:
        add("open_loop", "hook", f'no open loop {where} ("at the end I\'ll show you what it cost"). At most one, '
            "resolved with exactly the promised thing.")
    if W["stakes"].search(hook):
        passed.append("opening: why it matters")
    else:
        add("stakes", "hook", f"nothing {where} says why it matters to the viewer.")
    if on("limit"):                     # the old rule (an honest limit by 0:45), only when a pack asks for it
        lim = W["limit"].search(by_limit)
        if lim:
            passed.append(f'opening: an honest limit in the first {limit_w} words ("{lim.group(0)[:40]}")')
        else:
            add("limit", "hook", f"no honest limit in the first {limit_w} words (about {c['limit_seconds']} s).")
    first = _find(alls, _mark(text, ("first content",)))
    if first is None:                   # no mark: the first sentence that counts a part, else the second part
        first = next((k for k, s in enumerate(alls) if W["signpost"].search(s)), None)
        if first is None and len(P) > 1:
            first = next(k for k, (_s, pi) in enumerate(S) if pi == 1)
    stats["first_content_sentence"] = None if first is None else first + 1
    if first is not None:
        before = [s for s in alls[:first] if W["limit"].search(s)]
        if before:
            add("limit_before_content", "hook", f'a limit or caveat before the first content ("{before[0][:60]}"). '
                "Before point one stand only proof, number, announcement, the viewer's situation, the plan or the "
                "one open loop; a limit goes into the unit where it matters.")
        else:
            passed.append(f"opening: no limit or caveat before the first content (sentence {first + 1})")

    # Group 2: the counted units.
    depth = [i for i in range(1, len(P) - 1) if part_words[i] >= c["depth_min_words"]]
    stats["depth_parts"] = len(depth)
    lo_s, hi_s = c["idea_seconds"]
    stats["idea_words"] = [round(wpm * lo_s / 60), round(wpm * hi_s / 60)]
    off = [f"part {i + 1} ({part_words[i]} words, about {sec(part_words[i])} s)" for i in depth
           if not lo_s <= sec(part_words[i]) <= min(hi_s, c["part_max_seconds"])
           or sec(part_words[i]) > c["part_max_seconds"]]
    if off:
        add("part_length", "depth", f"unit outside {lo_s} to {hi_s} s: {', '.join(off[:3])}. One counted unit, one "
            "test step with its evidence; split a longer one with three empty lines, join a shorter one.")
    elif depth:
        passed.append(f"units: {len(depth)} parts of {lo_s} to {hi_s} s")
    take = [pi for s, pi in S if W["takeaway"].search(s)]
    stats["takeaways"] = len(take)
    most = int(c.get("takeaways_max", 1))
    if len(take) > most:
        add("takeaways", "depth", f'{len(take)} "try this" lines; at most {most}. The advice belongs in the sentence '
            '("if you ..., do ..."), not in an added line.')
    else:
        passed.append(f'units: {len(take)} "try this" line(s), at most {most}')
    nums = re.compile(rf"(?<![\w.,]){_NUM}|\b{_NUMWORDS[lists]}\b", re.I)
    ex = sum(1 for s in alls if W["example"].search(s))
    math = sum(1 for s in alls if W["math"].search(s) and len(nums.findall(s)) >= 2)
    con = sum(1 for s in alls if W["contrast"].search(s))
    sign = sum(len(W["signpost"].findall(s)) for s in alls)
    stats.update(examples=ex, live_math=math, contrasts=con, signposts=sign)
    missing = [n for n, k in (("no example (\"let's say\")", ex), ("no number worked out aloud", math),
                              ("no contrast pair (\"A against B\")", con)) if not k]
    if missing:
        add("concrete", "depth", "; ".join(missing) + ". Abstract turns concrete through an example, a sum said aloud "
            "and a comparison.")
    else:
        passed.append(f"units: {ex} examples, {math} sums aloud, {con} contrast pairs")
    if roadmap and not sign:
        add("signposts", "depth", 'a plan with a count, but no part is counted aloud ("step three", "the fourth '
            'job").')

    # Group 3: the spoken rhythm.
    lens = [len(words(s)) for s in alls]
    short = round(100 * sum(1 for n in lens if n <= c["short_words"]) / len(lens))
    stats["short_sentences_percent"] = short
    lo, hi = c["short_share"]
    if lo <= short <= hi:
        passed.append(f"rhythm: {short} % short sentences")
    else:
        add("short_share", "rhythm", f"{short} % short sentences (up to {c['short_words']} words); target {lo} to "
            f"{hi} %: connected sentences, then a short punch line.")
    qs = [k for k, s in enumerate(alls) if s.rstrip().endswith("?")]
    per_k = round(1000 * len(qs) / max(1, n_words), 1)
    stats.update(questions=len(qs), questions_per_1000=per_k)
    qlo, qhi = c["questions_per_1000"]
    if not qlo <= per_k <= qhi:
        add("questions", "rhythm", (f"{len(qs)} questions, {per_k} per 1,000 words" if qs else "no question") +
            f"; target {qlo:g} to {qhi:g} per 1,000 words, each at a joint (a transition or an objection).")
    else:
        passed.append(f"rhythm: {len(qs)} questions, {per_k} per 1,000 words")
    open_q = [alls[k] for k in qs if not any(S[j][1] == S[k][1] and not alls[j].rstrip().endswith("?")
                                             for j in range(k + 1, min(k + 2, len(S))))]
    weil = [alls[k + 1] for k in qs if k + 1 < len(alls) and W["because"].search(alls[k + 1].strip())]
    if open_q:
        add("answers", "rhythm", f'{len(open_q)} question(s) without an answer in the next sentence, e.g. '
            f'"{open_q[0][:60]}". Answer it at once.')
    if weil:
        add("answers", "rhythm", f'{len(weil)} answer(s) that start with "because", e.g. "{weil[0][:60]}". Answer '
            "with the point itself.")
    if qs and not open_q and not weil:
        passed.append("rhythm: every question answered in the next sentence")
    obj = sum(1 for s in alls if W["objection"].search(s))
    stats["objections"] = obj
    if not obj:
        add("objections", "rhythm", "no objection said aloud (\"now you might think ...\"). Voice the viewer's doubt, "
            "then answer it.")
    digits = [re.sub(r"[.,]", "", x) for x in NUMBER.findall(" ".join(alls))]
    if not (any(digits.count(d) >= 2 for d in set(digits)) or any(W["repeat"].search(s) for s in alls)):
        add("repeat", "rhythm", "the key number is said only once. Repeat it once on purpose.")
    count = lambda group, ss: sum(1 for s in ss for w in words(s) if w.lower().replace("’", "'") in group)  # noqa: E731
    depth_s = [s for s, pi in S if pi in depth]
    you_n, i_n = count(W["you"], alls), count(W["i"], alls)
    you_d, i_d = count(W["you"], depth_s), count(W["i"], depth_s)
    stats.update(you=you_n, i=i_n, you_per_1000=round(1000 * you_n / max(1, n_words)),
                 i_per_1000=round(1000 * i_n / max(1, n_words)), you_depth=you_d, i_depth=i_d,
                 joints_per_1000=round(1000 * sum(len(W["joint"].findall(s)) for s in alls) / max(1, n_words), 1))
    if you_n < i_n:
        add("you_i", "rhythm", f'{you_n} "you" against {i_n} "I". Say "you" at least as often as "I": "if you ..., '
            'then ...", "you see ..."; keep "I" for the test, the finding and the verdict.')
    else:
        passed.append(f'rhythm: {you_n} "you" against {i_n} "I"')

    # Group 4: the ending: a verdict, then at most one link sentence.
    v_at = _find(alls, _mark(text, ("urteil", "verdict")))
    if v_at is not None:
        end_s = alls[v_at:]
    elif len(P) > 1:
        last = len(P) - 1
        while last > 1 and sum(part_words[last:]) < c["end_min_words"]:
            last -= 1
        end_s = [s for s, pi in S if pi >= last]
    else:
        end_s = alls[-3:]
    end_w = sum(len(words(s)) for s in end_s)
    end = " ".join(end_s)
    stats["ending_seconds"] = sec(end_w)
    if sec(end_w) > c["end_seconds"] * 1.1:
        add("ending_length", "ending", f"the ending has {end_w} words, about {sec(end_w)} s; at most "
            f"{c['end_seconds']} s: the verdict that picks up sentence 1, then one link sentence, then the cut. "
            "Mark the verdict below --- ([[urteil | \"...\"]]) or set the ending apart with three empty lines.")
    else:
        passed.append(f"ending: {end_w} words, about {sec(end_w)} s")
    kinds = [k for k, rx in W["cta"].items() if rx.search(end)]
    links = sum(1 for s in end_s if W["cta"]["link"].search(s))
    stats["ending_calls_to_action"] = kinds
    other = [k for k in kinds if k != "link"]
    if other or links > 1:
        add("cta", "ending", (f"a request in the ending ({', '.join(other)})" if other else
                              f"{links} link sentences in the ending") +
            ". After the verdict comes at most one link sentence; the fixed ask stands in the middle.")
    else:
        passed.append("ending: " + ("one link sentence" if links else "no request after the verdict"))
    subs = [k for k, s in enumerate(alls) if W["cta"]["subscribe"].search(s)]
    if len(subs) > 1:
        add("subscribe_once", "ending", f"{len(subs)} subscribe lines. One, as the fixed ask in the middle.")
    a_lo, a_hi = c["ask_share"]
    stats["ask_at"] = [round(starts[k] / max(1, n_words), 2) for k in subs]
    if not subs:
        add("cta", "ending", f"no fixed ask (subscribe) between {round(a_lo * 100)} and {round(a_hi * 100)} % of the "
            "script. One sentence, word for word the same in every video, after the first strong result.")
    elif not a_lo <= starts[subs[0]] / max(1, n_words) <= a_hi:
        add("cta", "ending", f"the fixed ask stands at {round(100 * starts[subs[0]] / max(1, n_words))} % of the script; "
            f"it belongs between {round(a_lo * 100)} and {round(a_hi * 100)} %.")
    else:
        passed.append(f"ask: the fixed ask at {round(100 * starts[subs[0]] / max(1, n_words))} % of the script")
    window = round(wpm * float(c["end_window_seconds"]) / 60)
    tail = [s for k, s in enumerate(alls) if starts[k] + len(words(s)) > n_words - window]
    closing = " ".join(str(c.get("closing_line") or "").lower().split()).rstrip(".!")
    bye = [s for s in tail if W["greeting_end"].search(s) and not (closing and closing in s.lower())]
    noun = roadmap.group(0).lower() if roadmap else None
    recap = [s for s in tail if W["recap"].search(s) or (noun and noun in s.lower())]
    if bye:
        add("greeting_end", "ending", f'goodbye or thanks in the last {c["end_window_seconds"]} s ("{bye[0][:60]}"). '
            "The video ends after the verdict and the link sentence.")
    if recap:
        add("recap", "ending", f'a recap or the list of the parts in the last {c["end_window_seconds"]} s '
            f'("{recap[0][:60]}"). End on the verdict, not on a summary.')
    if not bye and not recap:
        passed.append(f"ending: no goodbye and no recap in the last {c['end_window_seconds']} s")
    if loop:
        late = " ".join(alls[int(len(alls) * 0.6):])
        keys = [w for w in words(loop) if len(w) >= 4 and w.lower() not in _NOUN_STOP
                and w.lower() not in W["you"] | W["i"] and not W["open_loop"].search(w)]
        if W["resolved"].search(late) or any(re.search(rf"\b{re.escape(k)}\b", late, re.I) for k in keys):
            passed.append("ending: the hook's open loop is resolved")
        else:
            add("loop_resolved", "ending", f'the open loop of the hook ("{loop[:50]}") is not resolved in the last '
                "third.")
    return out


__all__ = ["DEFAULTS", "MANUAL", "RETIRED", "check", "parts", "settings", "sentences", "words"]
