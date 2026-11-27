"""Measure how a text is spoken: sentence lengths, numbers, "you" against "I", questions, imperatives, fillers, pace,
transitions and unit length. Standard library only, no model, the same code for a reference speaker's transcripts
(host/voice-profile.py) and for a script draft (crewcut/voicecheck.py), so both sides count the same way.

Word lists exist for English and German (`LEXICON`); a profile may add its own words (`lexicon` in the profile, the
same keys). Every list is a heuristic: a word list finds most imperatives, numbers and fillers, not all.

Input is a list of `Sentence` (text, words, start and end in seconds, the line in the file when known):

- `from_text(text, wpm)` for a script: times are estimated from the word count at `wpm` words per minute.
- `from_timed(words)` for a transcript with word times (`[{"w", "s", "e"}]`).
- `from_chunks([(start_s, text), ...])` for a transcript in timed chunks: the time of a word is spread evenly between
  the start of its chunk and the start of the next one.

`measure(sentences, lang)` returns the metrics below; a metric that cannot be measured is None.
"""

from __future__ import annotations

import re
import statistics as st
from dataclasses import dataclass, field

METRICS = {
    "words_per_minute": "spoken words per minute",
    "sentence_words_median": "median words per sentence",
    "sentence_words_p25": "25th percentile of words per sentence",
    "sentence_words_p75": "75th percentile of words per sentence",
    "sentence_words_p90": "90th percentile of words per sentence",
    "short_share": "share of sentences with at most 8 words",
    "numbers_per_minute": "numbers (digits and number words) per minute",
    "first_number_s": "seconds until the first number",
    "first_number_word": "words until the first number",
    "you_per_100": "'you' words per 100 words",
    "i_per_100": "'I' words per 100 words",
    "questions_per_minute": "questions per minute",
    "imperative_share": "share of sentences that are commands",
    "fillers_per_100": "filler words per 100 words",
    "transitions_per_minute": "counted transitions ('number two', 'the next one') per minute",
    "first_transition_s": "seconds until the first counted transition",
    "unit_seconds_median": "median seconds between counted transitions (unit length)",
}

LEXICON: dict[str, dict] = {
    "en": {
        "you": ["you", "your", "yours", "yourself", "yourselves", "you're", "you've", "you'll", "you'd"],
        "i": ["i", "me", "my", "mine", "myself", "i'm", "i've", "i'll", "i'd"],
        "number_words": ["two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve",
                         "fifteen", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety",
                         "hundred", "thousand", "million", "millions", "billion", "billions", "half", "double",
                         "twice", "triple", "percent", "dozen"],
        "imperatives": ["think", "look", "imagine", "stop", "start", "pick", "go", "do", "don't", "make", "take", "get",
                        "write", "ask", "try", "remember", "focus", "figure", "put", "give", "keep", "find", "use",
                        "build", "sell", "charge", "raise", "cut", "test", "track", "show", "tell", "say", "let",
                        "let's", "watch", "listen", "consider", "picture", "choose", "decide", "spend", "save", "learn",
                        "read", "call", "send", "hire", "fire", "stay", "check", "count", "measure", "never", "always"],
        "lead_ins": ["so", "and", "now", "okay", "alright", "but", "then", "just", "well"],
        "after_imperative": ["you", "i", "we", "they", "he", "she", "it"],
        "fillers": ["um", "uh", "umm", "uhh", "basically", "literally", "actually", "you know", "kind of", "sort of",
                    "i mean"],
        "transitions": r"\bnumber (?:one|two|three|four|five|six|seven|eight|nine|ten|\d+)\b"
                       r"|\b(?:the )?(?:first|second|third|fourth|fifth|sixth|next|last|final) (?:one|thing|way|step|"
                       r"reason|mistake|lesson|piece|point|part|rule|lever|tip|thing is)\b"
                       r"|\bwhich brings (?:us|me) to\b|\bstep (?:one|two|three|four|five|\d+)\b"
                       r"|\b(?:firstly|secondly|thirdly)\b|\bmoving on\b",
        "promise": r"\bi'?ll show you\b|\bi'?m going to show you\b|\bby the end\b|\byou'?ll (?:know|see|have)\b"
                   r"|\bhere'?s (?:how|why|what)\b|\bi'?ll tell you\b|\bat the end\b|\bi keep\b|\bi pick\b|\bi use\b",
        "plan": r"\b(?:two|three|four|five|six|seven|\d+) (?:points|steps|things|ways|reasons|mistakes|lessons|rules|"
                r"tests|levers|parts|rounds|questions)\b|\bin (?:two|three|four|five|\d+)\b",
        "recap": r"\bto recap\b|\bin summary\b|\bto sum up\b|\bwe covered\b|\bwe(?:'ve)? (?:learned|seen) today\b"
                 r"|\bquick recap\b|\blet'?s recap\b",
        "goodbye": r"\bthanks? (?:you )?for watching\b|\bsee you (?:next time|in the next)\b|\bbye\b|\bcatch you\b"
                   r"|\buntil next time\b",
        "ask": r"\bsubscribe\b|\blink in the description\b|\bcomment below\b|\bleave a comment\b|\bfollow me\b"
               r"|\bhit the bell\b",
        "contrast": r"\bbut\b|\binstead\b|\bonly\b|\bvs\.?\b|\bversus\b|\bworse\b|\bbetter\b|\bmore\b|\bless\b|\bnot\b"
                    r"|\bnever\b|\bcheaper\b|\bfaster\b|\bslower\b",
        "proof": r"\bi (?:tested|built|measured|ran|tried|compared|paid)\b|\bhere(?:'s| is| are)\b|\byou see\b"
                 r"|\bon screen\b",
        "background": r"\blet me explain\b|\ba little (?:bit of )?background\b|\bbefore we dive\b|\bquick context\b",
    },
    "de": {
        "you": ["du", "dich", "dir", "dein", "deine", "deinen", "deinem", "deiner", "deines"],
        "i": ["ich", "mich", "mir", "mein", "meine", "meinen", "meinem", "meiner", "meines"],
        "number_words": ["zwei", "drei", "vier", "fünf", "sechs", "sieben", "acht", "neun", "zehn", "elf", "zwölf",
                         "fünfzehn", "zwanzig", "dreißig", "vierzig", "fünfzig", "sechzig", "siebzig", "achtzig",
                         "neunzig", "hundert", "tausend", "million", "millionen", "milliarde", "milliarden", "halb",
                         "halbe", "hälfte", "doppelt", "doppelte", "doppelten", "prozent", "dutzend", "viertel",
                         "drittel"],
        "imperatives": ["nimm", "guck", "schau", "stell", "schreib", "lass", "mach", "probier", "benutz", "nutz", "denk",
                        "frag", "gib", "hol", "such", "teste", "test", "prüf", "prüfe", "zähl", "rechne", "fang", "hör",
                        "achte", "merk", "vergiss", "wähl", "spar", "setz", "leg", "klick", "trag", "lies", "sieh",
                        "geh", "bau", "schick", "vergleich", "behalt", "streich", "bleib", "wart", "sag", "starte",
                        "start", "kauf", "zahl", "dreh", "zieh", "lad", "öffne", "schalt", "stopp", "versuch",
                        "überleg", "miss", "teil", "zeig", "vertrau", "verlang", "kopier", "wechsel", "lösch"],
        "lead_ins": ["also", "und", "dann", "jetzt", "aber", "einfach", "bitte", "deshalb", "darum"],
        "after_imperative": ["du", "ich", "wir", "ihr", "sie", "er", "es"],
        "fillers": ["äh", "ähm", "öhm", "halt", "quasi", "sozusagen", "irgendwie", "eigentlich", "grundsätzlich",
                    "letztendlich", "im prinzip", "an sich", "ein bisschen", "auf jeden fall"],
        "transitions": r"\bpunkt (?:eins|zwei|drei|vier|fünf|sechs|\d+)\b|\bnummer (?:eins|zwei|drei|vier|fünf|\d+)\b"
                       r"|\b(?:erstens|zweitens|drittens|viertens|fünftens)\b"
                       r"|\b(?:der|die|das|den|dem) (?:erste|zweite|dritte|vierte|fünfte|nächste|letzte)n? "
                       r"(?:paar|punkt|schritt|fehler|grund|regel|lektion|test|duell|teil|stufe|runde|hebel|frage)\b"
                       r"|\b(?:schritt|lektion|test|duell|runde|regel|fehler|hebel|rolle) (?:eins|zwei|drei|vier|fünf|\d+)\b",
        "promise": r"\bzeige? ich dir\b|\bich zeige? dir\b|\bam ende\b|\bsiehst du gleich\b|\bsag(?:e)? ich dir\b"
                   r"|\bdanach weißt du\b|\bam schluss\b|\bdu erfährst\b|\bich nehme\b|\bich bleibe bei\b"
                   r"|\bweißt du(?:,| am| danach| genau)\b",
        "plan": r"\b(?:zwei|drei|vier|fünf|sechs|sieben|acht|\d+) (?:punkten?|schritten?|duellen?|tests|stufen|fehlern?|"
                r"regeln|lektionen|teilen?|runden|gründen?|fragen|wegen?|dingen?|hebeln?|läufen?|vergleichen?)\b",
        "recap": r"\bzusammengefasst\b|\bzusammenfassend\b|\bkurz zusammen\b|\bfassen wir\b"
                 r"|\bwir haben (?:heute )?(?:gesehen|gelernt)\b|\bim überblick\b|\bheute hast du\b|\bnochmal kurz\b",
        "goodbye": r"\bdanke fürs (?:zuschauen|zugucken)\b|\bbis zum nächsten mal\b|\bbis bald\b|\btschüss\b|\bciao\b"
                   r"|\bwir sehen uns\b|\bmach'?s gut\b|\bbis dann\b",
        "ask": r"\babonnier\w*\b|\btrag dich\b|\beintragen\b|\bin die kommentare\b|\bschreib mir\b|\bkommentier\w*\b"
               r"|\blink\b|\b(?:video)?beschreibung\b",
        "contrast": r"\baber\b|\bstatt\b|\bnur\b|\bgegen\b|\bschlechter\w*\b|\bbesser\w*\b|\bmehr\b|\bweniger\b"
                    r"|\bnicht\b|\bkein\w*\b|\bnie\b|\bteurer\w*\b|\bbilliger\w*\b|\bschneller\b|\blangsamer\b"
                    r"|\bausgerechnet\b|\btrotzdem\b",
        "proof": r"\bich habe\b[^.?!]{0,80}\b(?:getestet|gebaut|gemessen|probiert|laufen lassen|verglichen|bezahlt)\b"
                 r"|\bhier (?:ist|sind|siehst)\b|\bsiehst du\b|\bim bild\b",
        "background": r"\bkurz zu (?:dem|der|den)\b|\bkurz zum\b|\bhintergrund\b|\bvorgeschichte\b|\bbevor (?:wir|ich)\b"
                      r"|\berst ?mal kurz\b",
    },
}

TOKEN = re.compile(r"[A-Za-zÄÖÜäöüß0-9$€%][A-Za-zÄÖÜäöüß0-9$€%'’.,\-]*")
SPLIT = re.compile(r"(?<=[.?!])[\"“”»«']?\s+(?=[\"„“»«'(]?[A-ZÄÖÜ0-9$€])")
VERSION_NAME = re.compile(r"\b(?:opus|fable|sonnet|haiku|glm|gemini|gpt|qwen|rtx|version|v)\s*\d+(?:[.,]\d+)*\b", re.I)
SPEAKER = re.compile(r">>\s*")
NOISE = re.compile(r"\[[^\]]*\]")


@dataclass
class Sentence:
    text: str
    start: float = 0.0
    end: float = 0.0
    line: int | None = None
    words: list[str] = field(default_factory=list)

    @property
    def question(self) -> bool:
        return self.text.rstrip().rstrip("\"“”»«')").endswith("?")


def words(text: str) -> list[str]:
    out = []
    for t in TOKEN.findall(text.replace("’", "'")):
        t = t.strip(".,'-")
        if t:
            out.append(t.lower())
    return out


def lexicon(lang: str | None, extra: dict | None = None) -> dict:
    """The word lists of a language (English when unknown), with a profile's own lists added."""
    base = LEXICON.get(str(lang or "en")[:2].lower(), LEXICON["en"])
    out = {k: (set(v) if isinstance(v, list) else v) for k, v in base.items()}
    for k, v in (extra or {}).items():
        if isinstance(v, list) and isinstance(out.get(k), set):
            out[k] = out[k] | {str(x).lower() for x in v}
        elif isinstance(v, str) and isinstance(out.get(k), str):
            out[k] = v
    for k, v in list(out.items()):
        if isinstance(v, str):
            out["_" + k] = re.compile(v, re.I)
    return out


def is_number(w: str, lex: dict) -> bool:
    return any(c.isdigit() for c in w) or w in lex["number_words"]


def numbers_in(text: str, lex: dict) -> list[str]:
    """Numbers in a sentence; version names like 'Opus 4' or 'RTX 5090' do not count as a number."""
    return [w for w in words(VERSION_NAME.sub(" ", text)) if is_number(w, lex)]


def split(text: str) -> list[str]:
    return [p.strip() for p in SPLIT.split(" ".join(text.split())) if p.strip()]


def clean(text: str) -> str:
    return " ".join(SPEAKER.sub(" ", NOISE.sub(" ", text)).split())


def from_text(text: str, wpm: float, line: int | None = None, start: float = 0.0) -> list[Sentence]:
    out, t = [], start
    for part in split(clean(text)):
        w = words(part)
        if not w:
            continue
        d = len(w) / max(wpm, 1.0) * 60.0
        out.append(Sentence(part, t, t + d, line, w))
        t += d
    return out


def from_lines(lines: list[tuple[int | None, str]], wpm: float) -> list[Sentence]:
    """Sentences of a script, line by line, with estimated times running on from line to line."""
    out: list[Sentence] = []
    for nr, txt in lines:
        out += from_text(txt, wpm, nr, out[-1].end if out else 0.0)
    return out


def from_timed(items: list) -> list[Sentence]:
    out, cur = [], []
    for d in items:
        if isinstance(d, list | tuple):
            d = {"s": d[0], "e": d[1], "w": d[2]}
        cur.append(d)
        if re.search(r"[.?!][\"“”»«')]?$", str(d.get("w", ""))):
            txt = " ".join(str(x["w"]) for x in cur)
            out.append(Sentence(txt, float(cur[0]["s"]), float(cur[-1]["e"]), None, words(txt)))
            cur = []
    if cur:
        txt = " ".join(str(x["w"]) for x in cur)
        out.append(Sentence(txt, float(cur[0]["s"]), float(cur[-1]["e"]), None, words(txt)))
    return [s for s in out if s.words]


def from_chunks(chunks: list[tuple[float, str]], end: float | None = None) -> list[Sentence]:
    """Timed chunks -> sentences; a word's time is spread evenly inside its chunk."""
    timed = []
    for i, (s0, text) in enumerate(chunks):
        s1 = chunks[i + 1][0] if i + 1 < len(chunks) else (end if end else s0 + max(len(text.split()) / 3.7, 1.0))
        toks = clean(text).split()
        if not toks:
            continue
        step = max(float(s1) - float(s0), 0.1) / len(toks)
        timed += [{"w": t, "s": float(s0) + k * step, "e": float(s0) + (k + 1) * step} for k, t in enumerate(toks)]
    return from_timed(timed)


def punctuated(sents: list[Sentence]) -> bool:
    """Has the transcript real sentence marks? (auto captions without them make one giant 'sentence')."""
    n = sum(len(s.words) for s in sents)
    return n > 0 and len(sents) * 100.0 / n >= 3.0


def imperative(s: Sentence, lex: dict) -> bool:
    w = list(s.words)
    while w and w[0] in lex["lead_ins"]:
        w = w[1:]
    if not w or s.question or w[0] not in lex["imperatives"]:
        return False
    return not (len(w) > 1 and w[1] in lex["after_imperative"])


def fillers(text: str, lex: dict) -> int:
    low = " " + " ".join(words(text)) + " "
    return sum(low.count(f" {f} ") for f in lex["fillers"])


def _q(xs: list[float], q: float) -> float:
    xs = sorted(xs)
    if len(xs) == 1:
        return float(xs[0])
    k = (len(xs) - 1) * q
    a = int(k)
    b = min(a + 1, len(xs) - 1)
    return xs[a] + (xs[b] - xs[a]) * (k - a)


def transitions(sents: list[Sentence], lex: dict, gap: float = 20.0) -> list[Sentence]:
    """Sentences with a counted transition; two within `gap` seconds count once."""
    out: list[Sentence] = []
    for s in sents:
        if lex["_transitions"].search(" ".join(s.words)) and (not out or s.start - out[-1].start > gap):
            out.append(s)
    return out


def measure(sents: list[Sentence], lang: str | None = "en", extra: dict | None = None,
            sentence_metrics: bool = True) -> dict:
    """The metrics of one text. `sentence_metrics=False` leaves out what needs real sentence marks."""
    lex = lexicon(lang, extra)
    if not sents:
        return {k: None for k in METRICS}
    allw = [w for s in sents for w in s.words]
    n = len(allw)
    minutes = max((sents[-1].end - sents[0].start) / 60.0, 1e-6)
    r: dict = {"words": n, "sentences": len(sents), "minutes": round(minutes, 3)}
    r["words_per_minute"] = n / minutes
    lens = [len(s.words) for s in sents]
    if sentence_metrics:
        r["sentence_words_median"] = float(st.median(lens))
        r["sentence_words_p25"] = _q(lens, 0.25)
        r["sentence_words_p75"] = _q(lens, 0.75)
        r["sentence_words_p90"] = _q(lens, 0.90)
        r["short_share"] = sum(1 for x in lens if x <= 8) / len(lens)
        r["questions_per_minute"] = sum(1 for s in sents if s.question) / minutes
        r["imperative_share"] = sum(1 for s in sents if imperative(s, lex)) / len(sents)
    else:
        for k in ("sentence_words_median", "sentence_words_p25", "sentence_words_p75", "sentence_words_p90",
                  "short_share", "questions_per_minute", "imperative_share"):
            r[k] = None
    nums = [(s, numbers_in(s.text, lex)) for s in sents]
    r["numbers_per_minute"] = sum(len(x) for _, x in nums) / minutes
    first = next(((s, x) for s, x in nums if x), None)
    r["first_number_s"] = None
    r["first_number_word"] = None
    if first:
        s, x = first
        before = sum(len(t.words) for t in sents[:sents.index(s)])
        idx = next((i for i, w in enumerate(s.words) if w in {y.lower() for y in x}), 0)
        r["first_number_word"] = before + idx
        r["first_number_s"] = s.start + (s.end - s.start) * (idx / max(len(s.words), 1))
    r["you_per_100"] = sum(1 for w in allw if w in lex["you"]) * 100.0 / max(n, 1)
    r["i_per_100"] = sum(1 for w in allw if w in lex["i"]) * 100.0 / max(n, 1)
    r["fillers_per_100"] = sum(fillers(s.text, lex) for s in sents) * 100.0 / max(n, 1)
    tr = transitions(sents, lex)
    r["transitions_per_minute"] = len(tr) / minutes
    r["first_transition_s"] = tr[0].start if tr else None
    gaps = [b.start - a.start for a, b in zip(tr, tr[1:], strict=False)]
    r["unit_seconds_median"] = float(st.median(gaps)) if gaps else None
    return r


def summary(values: list[float]) -> dict | None:
    """Median and quartiles of one metric over many texts."""
    xs = [float(v) for v in values if v is not None]
    if not xs:
        return None
    return {"median": round(st.median(xs), 3), "p25": round(_q(xs, 0.25), 3), "p75": round(_q(xs, 0.75), 3),
            "n": len(xs)}


__all__ = ["LEXICON", "METRICS", "Sentence", "fillers", "from_chunks", "from_lines", "from_text", "from_timed",
           "imperative", "is_number", "lexicon", "measure", "numbers_in", "punctuated", "split", "summary",
           "transitions", "words"]
