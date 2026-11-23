"""Script craft: the measurable part of how a long explainer is written (skill: skills/script, references/craft.md).

Four groups, measured on 119 long videos of three successful English-language education channels (Nov 2026):

1. Hook in 30 seconds: a result or claim (no greeting before it), why it matters, one measured number, a roadmap with
   a count, an open loop that the end resolves, and one honest limit by 0:45.
2. Depth pattern: each idea 40 to 60 seconds (question, why, how on screen, failure or limit, number, "try this"),
   concrete examples, numbers worked out aloud, contrast pairs, parts counted aloud.
3. Spoken rhythm: connected sentences, then a short punch line; questions asked and answered at once; the viewer's
   objection said aloud; the key number repeated once; more "you" than "I" where it explains.
4. Ending in at most 60 seconds: the parts as one list, what the human still does, a verdict with its limit, exactly
   one call to action, and the hook's open loop resolved.

`check(text, lang, wpm, cfg)` measures a script (the spoken part above the first `---` line) and returns findings
(error, warn, hint), the passed checks and the numbers. A program can only see words, so every rule here is a signal for
the Writer and the Critic: what it cannot see (a demo by 1:30, one plain sentence per technical word, whether a question
is a real joint) is listed in `MANUAL` for the Critic's craft pass. Levels and limits come from the style pack
(`channel.json` `script.craft`, see docs/style-packs.md); German and English word lists are built in.
"""

from __future__ import annotations

import re

from . import spoken

LEVELS = ("error", "warn", "hint", "off")
DEFAULTS: dict = {
    "hook_seconds": 30,          # the hook: everything of group 1 except the limit
    "limit_seconds": 45,         # one honest limit by then
    "start_rate": 1.2,           # the first minute is dense: about this much faster than the base rate
    "idea_seconds": [40, 60],    # one idea, one concept
    "part_max_seconds": 180,     # a longer part holds several ideas
    "depth_min_words": 80,       # a shorter part between hook and ending is a bridge or a recap, not a depth part
    "end_seconds": 60,
    "end_min_words": 60,         # a very short last part (only the thanks) takes the parts before it
    "short_words": 6,            # a sentence of at most this many words is a punch line
    "short_share": [15, 40],     # percent of short sentences; about one in four
    "questions_per_1000": [2.5, 6],  # target 3 to 5: about 7 to 11 in a script of 2,000 words
    "min_words": 150,            # shorter texts get only the greeting check
    "checks": {
        "greeting": "error", "hook_number": "warn", "roadmap": "warn", "open_loop": "warn", "stakes": "hint",
        "limit": "warn", "part_length": "hint", "takeaways": "warn", "concrete": "hint", "signposts": "hint",
        "short_share": "hint", "questions": "warn", "answers": "hint", "objections": "hint", "repeat": "hint",
        "you_i": "hint", "ending_length": "warn", "cta": "warn", "subscribe_once": "warn", "ending_parts": "hint",
        "loop_resolved": "warn",
    },
}
MANUAL = [
    "Hook: are the five parts really there, or only their words? Is the number measured?",
    "The first demo of the real thing comes by 1:30 (see the shot ideas below ---).",
    "Every technical word gets one plain sentence the first time; at most one new word per 20 seconds.",
    "Each idea runs question, why, how on screen, failure or limit, number, try this; the task works without the product.",
    "Questions stand at joints, not as filler; objections sound like a real viewer's doubt.",
    "It reads as spoken, not written: natural word order, contractions where the speaker uses them.",
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
        "recap": _rx(r"\bto recap\b", r"\bin one sentence\b", r"\bonce more\b", r"\bquick recap\b", r"\bto sum up\b",
                     r"\bin short\b", r"\bone more time\b"),
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
        "recap": _rx(r"\bnoch einmal\b", r"\bin einem satz\b", r"\bzusammengefasst\b", r"\bkurz zusammen\b",
                     r"\balso nochmal\b"),
        "human": _rx(r"\bselbst\b", r"\bselber\b", r"\bbleibt (?:bei )?(?:dir|mir|dem menschen)\b",
                     r"\bdu entscheidest\b", r"\bentscheide ich\b"),
        "verdict": _rx(r"\burteil\b", r"\bfazit\b", r"\bunterm strich\b", r"\bfür mich\b", r"\bmeiner meinung nach\b",
                       r"\blohnt\b"),
        "caveat": _rx(r"\bnicht\b", r"\bnoch\b", r"\baber\b", r"\bnur\b", r"\bkein"),
        "cta": {
            "link": _rx(r"\blink\b", r"\bbeschreibung\b", r"\bformular\b", r"\bmeld(?:e)? dich\b", r"\bherunterladen\b",
                        r"\bhol dir\b"),
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
    """DEFAULTS with a style pack's `script.craft` block on top (unknown keys are kept, bad levels turn "off")."""
    cfg = {k: (dict(v) if isinstance(v, dict) else v) for k, v in DEFAULTS.items()}
    for k, v in (raw or {}).items():
        if k == "checks" and isinstance(v, dict):
            cfg["checks"].update({str(a): (b if b in LEVELS else "off") for a, b in v.items()})
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


def check(text: str, lang: str | None = None, wpm: float = 150, cfg: dict | None = None) -> dict:
    """Measure the four craft groups. Returns {"findings": [...], "passed": [...], "stats": {...}, "manual": [...]}."""
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

    # Group 1: hook in 30 seconds (no greeting first, at any length).
    greet = [s for s in alls[:2] if W["greeting"].search(s)]
    if greet:
        add("greeting", "hook", f'greeting before the hook ("{greet[0][:60]}"). Open with the result or the claim.')
    if n_words < c["min_words"]:
        stats["note"] = f"shorter than {c['min_words']} words: only the greeting is checked"
        return out
    start = wpm * float(c["start_rate"])
    hook_w, limit_w = round(start * c["hook_seconds"] / 60), round(start * c["limit_seconds"] / 60)
    hook, by_limit = _lead(alls, hook_w), _lead(alls, limit_w)
    stats.update(hook_words=hook_w, limit_words=limit_w)
    where = f"in the first {hook_w} words (about {c['hook_seconds']} s)"
    m = NUMBER.search(hook)
    if m:
        passed.append(f'hook: a number {where} ("{m.group(0)}")')
    else:
        add("hook_number", "hook", f"no number {where}. One measured number belongs in the hook.")
    roadmap = re.search(rf"\b{_COUNT[lists]}\s+(?:[^\W\d_][\w'-]*\s+){{0,2}}{_PARTS[lists]}\b", hook, re.I)
    if roadmap:
        passed.append(f'hook: a roadmap with a count ("{roadmap.group(0)}")')
    else:
        add("roadmap", "hook", f'no roadmap with a count {where} ("the six jobs", "three steps"). Tell the viewer how '
            "long the trip is.")
    loop = next((s for s in alls if W["open_loop"].search(s) and s in hook), None)
    if loop:
        passed.append(f'hook: an open loop ("{loop[:50]}")')
    else:
        add("open_loop", "hook", f'no open loop {where} ("at the end I\'ll show you what it cost"). Promise one thing '
            "that the end resolves.")
    if W["stakes"].search(hook):
        passed.append("hook: why it matters")
    else:
        add("stakes", "hook", f"nothing {where} says why it matters to the viewer.")
    lim = W["limit"].search(by_limit)
    if lim:
        passed.append(f'hook: an honest limit in the first {limit_w} words ("{lim.group(0)[:40]}")')
    else:
        add("limit", "hook", f"no honest limit in the first {limit_w} words (about {c['limit_seconds']} s), such as "
            '"Is it perfect? No." It makes everything after it credible.')

    # Group 2: the depth pattern.
    depth = [i for i in range(1, len(P) - 1) if part_words[i] >= c["depth_min_words"]]
    stats["depth_parts"] = len(depth)
    lo_s, hi_s = c["idea_seconds"]
    stats["idea_words"] = [round(wpm * lo_s / 60), round(wpm * hi_s / 60)]
    long_parts = [f"part {i + 1} ({part_words[i]} words, about {sec(part_words[i])} s)" for i in depth
                  if sec(part_words[i]) > c["part_max_seconds"]]
    if long_parts:
        add("part_length", "depth", "part longer than "
            f"{c['part_max_seconds']} s: {', '.join(long_parts[:3])}. One idea takes {lo_s} to {hi_s} s; split the "
            "ideas with three empty lines, each with question, why, how, limit, number, try this.")
    take = [pi for s, pi in S if W["takeaway"].search(s)]
    stats["takeaways"] = len(take)
    if depth:
        without = [i + 1 for i in depth if i not in take]
        msg = f"{len(take)} \"try this\" line(s) for {len(depth)} depth part(s)"
        if not take:
            add("takeaways", "depth", msg + ". After each idea, one small task the viewer can do without the product.")
        elif without:
            add("takeaways", "depth", msg + f"; none in part {', '.join(map(str, without[:6]))}.", "hint")
        else:
            passed.append("depth: " + msg)
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
        passed.append(f"depth: {ex} examples, {math} sums aloud, {con} contrast pairs")
    if roadmap and not sign:
        add("signposts", "depth", 'a roadmap with a count, but no part is counted aloud ("step three", "the fourth '
            'job").')

    # Group 3: the spoken rhythm.
    lens = [len(words(s)) for s in alls]
    short = round(100 * sum(1 for n in lens if n <= c["short_words"]) / len(lens))
    stats["short_sentences_percent"] = short
    lo, hi = c["short_share"]
    if lo <= short <= hi:
        passed.append(f"rhythm: {short} % short sentences")
    else:
        add("short_share", "rhythm", f"{short} % short sentences (up to {c['short_words']} words); about one in four: "
            "connected sentences, then a short punch line.")
    qs = [k for k, s in enumerate(alls) if s.rstrip().endswith("?")]
    per_k = round(1000 * len(qs) / max(1, n_words), 1)
    stats.update(questions=len(qs), questions_per_1000=per_k)
    qlo, qhi = c["questions_per_1000"]
    if not qs:
        add("questions", "rhythm", "no question. Ask at the joints and answer at once: about 3 to 5 per 1,000 words.")
    elif not qlo <= per_k <= qhi:
        add("questions", "rhythm", f"{len(qs)} questions, {per_k} per 1,000 words; target about 3 to 5, each at a "
            "joint.", "hint")
    else:
        passed.append(f"rhythm: {len(qs)} questions, {per_k} per 1,000 words")
    open_q = [alls[k] for k in qs if not any(S[j][1] == S[k][1] and not alls[j].rstrip().endswith("?")
                                             for j in range(k + 1, min(k + 3, len(S))))]
    if open_q:
        add("answers", "rhythm", f'{len(open_q)} question(s) without an answer in the next two sentences, e.g. '
            f'"{open_q[0][:60]}". Answer it at once.')
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
    if depth_s and you_d < i_d:
        add("you_i", "rhythm", f'{you_d} "you" against {i_d} "I" in the depth parts. Explain to the viewer; keep "I" '
            "for the story and the failures.")
    elif depth_s:
        passed.append(f'rhythm: {you_d} "you" against {i_d} "I" in the depth parts')

    # Group 4: the ending.
    if len(P) > 1:
        first = len(P) - 1
        while first > 1 and sum(part_words[first:]) < c["end_min_words"]:
            first -= 1
        end_s = [s for s, pi in S if pi >= first]
    else:
        end_s = alls[-8:]
    end_w = sum(len(words(s)) for s in end_s)
    end = " ".join(end_s)
    stats["ending_seconds"] = sec(end_w)
    if sec(end_w) > c["end_seconds"] * 1.1:
        add("ending_length", "ending", f"the ending (last part) has {end_w} words, about {sec(end_w)} s; at most "
            f"{c['end_seconds']} s: the parts as one list, what the human still does, a verdict with its limit, one "
            "call to action. Set it apart with three empty lines.")
    else:
        passed.append(f"ending: {end_w} words, about {sec(end_w)} s")
    kinds = [k for k, rx in W["cta"].items() if rx.search(end)]
    stats["ending_calls_to_action"] = kinds
    if len(kinds) == 1:
        passed.append(f"ending: exactly one call to action ({kinds[0]})")
    else:
        add("cta", "ending", (f"{len(kinds)} calls to action in the ending ({', '.join(kinds)}). Exactly one."
                              if kinds else "no call to action in the ending. Exactly one."))
    subs = sum(1 for s in alls if W["cta"]["subscribe"].search(s))
    if subs > 1:
        add("subscribe_once", "ending", f"{subs} subscribe lines. One, right after the first strong result.")
    noun = roadmap.group(0).split()[-1].lower() if roadmap else None
    gaps = []
    if not (W["recap"].search(end) or (noun and noun in end.lower())):
        gaps.append('the parts as one list ("the six jobs in one sentence")')
    if not W["human"].search(end):
        gaps.append("what the human still does")
    v = [k for k, s in enumerate(end_s) if W["verdict"].search(s)]
    if not v:
        gaps.append("a verdict")
    elif not any(W["caveat"].search(" ".join(end_s[k:k + 2])) for k in v):
        gaps.append("the limit of the verdict")
    if gaps:
        add("ending_parts", "ending", "the ending lacks " + ", ".join(gaps) + ".")
    else:
        passed.append("ending: list, the human's part and a verdict with its limit")
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


__all__ = ["DEFAULTS", "MANUAL", "check", "parts", "settings", "sentences", "words"]
