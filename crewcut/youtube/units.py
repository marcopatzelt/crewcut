"""Audience retention per content unit of a published video (``crewcut retention units <episode>``).

A long video is a chain of content units (hook, retain, reward), each one standing alone like a Short. This command
asks the YouTube Analytics API (``reports.query``, read-only) for the retention curve of the published video
(``audienceWatchRatio`` and ``relativeRetentionPerformance`` by ``elapsedVideoTimeRatio``), cuts it at the unit
boundaries of the final edit's transcript and measures every unit: start and end, the share of viewers at both,
points lost per minute, the mean rank against similar YouTube videos, the hook sentence, and the sentence where the
steepest drop starts.

Unit boundaries, the first that applies:

1. **A Drehzettel** (``brief/DREHZETTEL-vNNN.md``, the newest): its units start with the count word ("Punkt eins.");
   the type comes from the ``Beleg:`` head of the unit, the redemption and the outro from the ``EINLÖSUNG:`` and
   ``URTEIL:`` lines, found in the transcript by their words.
2. **Counted signposts** in the transcript: "Punkt eins", "Rolle 3", "Schritt zwei", "1 ist der ...", "erstens"
   (and the English forms), as a chain 1, 2, 3 ... in this order.
3. **The parts of the newest script** (``brief/SCRIPT-vNNN.md``, parts separated by three empty lines), found in the
   transcript by their first words.

The intro is everything before the first unit. The outro starts at the first link or goodbye sentence after the last
unit's hook (or at the Drehzettel's ``URTEIL:`` line).

**Versions.** A video trimmed in YouTube Studio after publication has two lengths, and the API reports positions as a
share of the length the viewer saw. ``analytics/versions.json`` names each version with its words file, its length
(``duration_s`` or a local ``file``) and its days (``since``, ``until``, inclusive, YouTube's calendar days). Every
version is measured only with the days that belong to it. Without the file there is one version: the newest edit
plan's words, from the upload day until today.

Output: ``analytics/retention-units.json`` and ``.md`` in the episode, and one dated block per episode and data day in
``<studio>/library/learnings/retention-units.md`` (format at the top of that file, read by the script critic).
``--clips N`` cuts the N steepest drops from the local export into ``analytics/drops/`` for a person or a video model
to watch; their reasons, written to ``analytics/retention-units-why.json``, go into the report.

A hint, not proof: a curve of a few dozen viewers moves in steps of one person, and what a unit says matters more than
its form. A pattern becomes a lesson only when it repeats in ``REPEATS`` episodes. No data yet (the API is two to three
days behind): "no retention data yet", and nothing is written.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from .. import paths
from .analytics import NoData, at, upload

SCHEMA = 1
NO_DATA = "no retention data yet"
HOLDS = 5.0           # a unit that loses at most this many points of the audience per minute holds
LOSES = 15.0          # one that loses at least this many loses
INTRO_HOLDS = 0.5     # the intro is judged by its rank against similar videos (relativeRetentionPerformance)
INTRO_LOSES = 0.3
MIN_S = 15.0          # a unit shorter than this is "too short" to judge (a point of the curve is 1 % of the video)
SMALL = 100           # fewer views than this in the measured days: a small sample
REPEATS = 3           # a pattern counts as a lesson when it repeats in this many episodes
CONTEXT = (8.0, 4.0)  # seconds before and after a drop in a clip
LEARNINGS = ("library", "learnings", "retention-units.md")
OVERALL_START, OVERALL_END = "<!-- overall:start -->", "<!-- overall:end -->"
DATA_MARK = "<!-- retention-units "

# ---------------------------------------------------------------------------------------------------- the API


class YouTube:
    """The real calls, read-only: ``reports.query`` (YouTube Analytics v2) and ``videos.list`` (Data API v3)."""

    def __init__(self):
        self._yt = None

    def query(self, params: dict) -> dict:
        from .analytics import api_query
        return api_query(params)

    def duration(self, video_id: str) -> float | None:
        if self._yt is None:
            from googleapiclient.discovery import build

            from . import auth
            self._yt = build("youtube", "v3", credentials=auth.credentials(), cache_discovery=False)
        items = self._yt.videos().list(part="contentDetails", id=video_id).execute().get("items") or []
        return iso_seconds(items[0]["contentDetails"]["duration"]) if items else None


def iso_seconds(text: str) -> float | None:
    """``PT4M47S`` -> 287.0."""
    m = re.fullmatch(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?)?", str(text or ""))
    if not m or not any(m.groups()):
        return None
    d, h, mi, s = (float(x or 0) for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + s


def points(resp: dict) -> list[list[float | None]]:
    """``[[ratio, audienceWatchRatio, relativeRetentionPerformance or None]]`` from a ``reports.query`` answer."""
    heads = [str(h.get("name")) for h in (resp or {}).get("columnHeaders") or []]
    if "elapsedVideoTimeRatio" not in heads or "audienceWatchRatio" not in heads:
        return []
    i, j = heads.index("elapsedVideoTimeRatio"), heads.index("audienceWatchRatio")
    k = heads.index("relativeRetentionPerformance") if "relativeRetentionPerformance" in heads else None
    out = []
    for row in (resp or {}).get("rows") or []:
        try:
            rel = float(row[k]) if k is not None and row[k] is not None else None
            out.append([float(row[i]), float(row[j]), rel])
        except (IndexError, TypeError, ValueError):
            continue
    return sorted(out)


def fetch(api, video_id: str, since: str, until: str) -> dict:
    """The curve and the sample (views, mean view duration, last day with data) of one video for days since..until."""
    base = {"ids": "channel==MINE", "startDate": since, "endDate": until, "filters": f"video=={video_id}"}
    curve = points(api.query({**base, "metrics": "audienceWatchRatio,relativeRetentionPerformance",
                              "dimensions": "elapsedVideoTimeRatio", "sort": "elapsedVideoTimeRatio"}))
    days = api.query({**base, "metrics": "views,averageViewDuration,averageViewPercentage", "dimensions": "day",
                      "sort": "day"})
    views = dur = pct = 0.0
    last = None
    for row in days.get("rows") or []:
        try:
            v = float(row[1])
        except (IndexError, TypeError, ValueError):
            continue
        if v > 0:
            views += v
            dur += v * float(row[2] or 0)
            pct += v * float(row[3] or 0)
            last = str(row[0])
    sample = {"views": int(views), "average_view_s": round(dur / views, 1) if views else None,
              "average_view_percent": round(pct / views, 1) if views else None}
    return {"curve": curve, "sample": sample, "data_until": last}


# ---------------------------------------------------------------------------------------------------- words


def norm_words(raw) -> list[dict]:
    """Words as ``[{"w", "s", "e"}]``; also the ``[start, end, word]`` rows of older studios."""
    if isinstance(raw, dict):
        raw = raw.get("words") or raw.get("segments") or []
    if isinstance(raw, list) and raw and isinstance(raw[0], (list, tuple)):
        out = []
        for r in raw:
            try:
                out.append({"w": str(r[2]), "s": float(r[0]), "e": float(r[1])})
            except (IndexError, TypeError, ValueError):
                continue
        return sorted(out, key=lambda x: x["s"])
    from ..motion import density
    return density.norm_words(raw)


TOKEN = re.compile(r"[^\W_]+", re.U)


def toks(text: str) -> list[str]:
    return [t.lower() for t in TOKEN.findall(text)]


def sentences(words: list[dict]) -> list[dict]:
    """Sentences with times: ``{"s", "e", "text", "toks"}``. A sentence ends at a word ending in . ! ? or …"""
    out, cur = [], []
    for w in words:
        cur.append(w)
        if re.search(r"[.!?…][\"'“”»«)]*$", w["w"].strip()):
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    sents = []
    for ws in out:
        text = re.sub(r"\s+([.,!?;:])", r"\1", " ".join(w["w"].strip() for w in ws)).strip()
        if text:
            sents.append({"s": ws[0]["s"], "e": ws[-1]["e"], "text": text, "toks": toks(text)})
    return sents


def said(sents: list[dict], a: float, b: float) -> str:
    """The sentences spoken between a and b (a sentence counts when any part of it falls inside)."""
    return " ".join(s["text"] for s in sents if s["e"] > a and s["s"] < b)


def sentence_at(sents: list[dict], t: float) -> dict | None:
    """The sentence being spoken at t (or the last one that started before it)."""
    cur = None
    for s in sents:
        if s["s"] <= t + 1e-6:
            cur = s
        else:
            break
    return cur


# ---------------------------------------------------------------------------------------------------- boundaries

NUMS = {"de": ["eins", "zwei", "drei", "vier", "fünf", "sechs", "sieben", "acht", "neun", "zehn", "elf", "zwölf"],
        "en": ["one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve"]}
ORDS = {"de": ["erstens", "zweitens", "drittens", "viertens", "fünftens", "sechstens", "siebtens", "achtens"],
        "en": ["firstly", "secondly", "thirdly", "fourthly", "fifthly", "sixthly", "seventhly", "eighthly"]}
COUNTED = {"de": r"punkt|rolle|schritt|teil|stufe|nummer|regel|fehler|tipp|job|platz|test|aufgabe|grund|frage|lektion",
           "en": r"point|role|step|part|stage|number|rule|mistake|tip|job|level|test|task|reason|question|lesson"}
LEAD = {"de": r"(?:und|also|jetzt|dann|okay|so)?", "en": r"(?:and|so|now|okay|then)?"}
IS = {"de": r"(?:ist|sind|war|heißt)\s+(?:der|die|das|ein|eine|mein|meine)", "en": r"(?:is|are|was)\s+(?:the|a|my)"}
OUTRO = {"de": re.compile(r"\blink\b|\bbeschreibung\b|\bdanke\b|\bbis zum nächsten mal\b|\btschüss\b|\btrag dich\b|"
                          r"\bnächste[ns]? (?:video|folge)\b", re.I),
         "en": re.compile(r"\blink\b|\bdescription\b|\bthanks? (?:you )?for watching\b|\bsee you\b|\bsign up\b|"
                          r"\bnext video\b", re.I)}
OBJECTION = {"de": re.compile(r"\bjetzt denkst du\b|\bdu denkst (?:jetzt|dir|vielleicht)\b|\bvielleicht denkst du\b|"
                              r"\bdu fragst dich\b|\bdu wirst (?:jetzt )?sagen\b", re.I),
             "en": re.compile(r"\byou might (?:think|be thinking|say|wonder)\b|\byou(?:'re| are) (?:probably )?"
                              r"(?:thinking|wondering)\b|\bbut wait\b", re.I)}
FIRST_PERSON = {"de": {"ich", "mein", "meine", "meinen", "meinem", "meiner", "wir", "unser", "unsere", "unseren"},
                "en": {"i", "my", "we", "our", "i'm", "i've"}}
NUMWORD = re.compile(r"^(?:zwei|drei|vier|fünf|sechs|sieben|acht|neun|zehn|elf|zwölf|zwanzig|dreißig|vierzig|fünfzig|"
                     r"hundert|tausend|million|millionen|milliarde|milliarden|two|three|four|five|six|seven|eight|nine|"
                     r"ten|eleven|twelve|twenty|thirty|forty|fifty|hundred|thousand|million|billion)\w*$", re.I)


def language(sents: list[dict]) -> str:
    w = [t for s in sents for t in s["toks"]]
    de = sum(1 for x in w if x in {"ich", "und", "das", "ist", "nicht", "der", "die", "mit", "ein", "auf"})
    en = sum(1 for x in w if x in {"i", "and", "the", "is", "not", "with", "a", "on", "it", "of"})
    return "de" if de >= en else "en"


def _num(token: str, lang: str) -> int | None:
    if token.isdigit():
        n = int(token)
        return n if 1 <= n <= 12 else None
    if lang == "de" and token == "ein":
        return None
    words = NUMS[lang]
    return words.index(token) + 1 if token in words else None


def signpost(sent: dict, lang: str) -> int | None:
    """The count of a counted signpost at the start of a sentence ("Punkt eins.", "Rolle 3 ist ...", "1 ist der
    ...", "Erstens ..."), or None."""
    text = " ".join(sent["toks"][:8])
    num = r"(\d{1,2}|" + "|".join(NUMS[lang]) + r")"
    for rx in (rf"^{LEAD[lang]}\s*(?:{COUNTED[lang]})\s+{num}\b", rf"^{LEAD[lang]}\s*{num}\s+{IS[lang]}\b"):
        m = re.match(rx, text)
        if m:
            return _num(m.group(1), lang)
    m = re.match(rf"^{LEAD[lang]}\s*({'|'.join(ORDS[lang])})\b", text)
    return ORDS[lang].index(m.group(1)) + 1 if m else None


def chain(cands: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """The longest chain 1, 2, 3 ... of (sentence index, count) in time order (the earliest when two are as long)."""
    best: list[tuple[int, int]] = []
    for i, (idx, n) in enumerate(cands):
        if n != 1:
            continue
        cur = [(idx, n)]
        for idx2, n2 in cands[i + 1:]:
            if idx2 > cur[-1][0] and n2 == cur[-1][1] + 1:
                cur.append((idx2, n2))
        if len(cur) > len(best):
            best = cur
    return best if len(best) >= 2 else []


def _stems(text: str, lang: str) -> set[str]:
    from ..spoken import STOP
    stop = STOP.get(lang, STOP["en"])
    return {t[:5] for t in toks(text) if len(t) > 2 and t not in stop}


def _split(text: str) -> list[str]:
    return [x for x in re.split(r"(?<=[.!?…])\s+", " ".join(str(text or "").split())) if TOKEN.search(x)]


def find(text: str, sents: list[dict], start: int, lang: str, need: float = 0.45) -> int | None:
    """The sentence (from index ``start`` on) where ``text`` begins, or None. The first two sentences of ``text`` are
    laid over two sentences of the transcript (the first counts 0.7, the second 0.3), or both over one when the
    speaker joined them; the score is the share of their content words that were said."""
    parts = _split(text)[:2] or [text]
    q1 = _stems(" ".join(toks(parts[0])[:14]), lang)
    q2 = _stems(" ".join(toks(parts[1])[:14]), lang) - q1 if len(parts) > 1 else set()
    if not q1:
        return None
    best, where = 0.0, None
    for i in range(max(0, start), len(sents)):
        own = {t[:5] for t in sents[i]["toks"]}
        nxt = {t[:5] for t in sents[i + 1]["toks"]} if i + 1 < len(sents) else set()
        a1 = len(q1 & own) / len(q1)
        score = 0.7 * a1 + 0.3 * len(q2 & nxt) / len(q2) if q2 else a1
        if q2:
            score = max(score, min(len((q1 | q2) & own) / len(q1 | q2), a1))
        if score > best + 1e-9:
            best, where = score, i
    return where if best >= need else None


def drehzettel(ep_dir: Path) -> tuple[dict | None, str | None]:
    """The newest Drehzettel's units (``{"units": {n: {...}}, "redemption", "verdict"}``) and its name."""
    files = sorted((ep_dir / "brief").glob("DREHZETTEL-v*.md"), key=_version_key)
    files = [f for f in files if re.fullmatch(r"DREHZETTEL-v\d+\.md", f.name)] or files
    if not files:
        return None, None
    text = files[-1].read_text(encoding="utf-8")
    body = re.split(r"(?m)^---[ \t]*$", text)[0]
    out: dict = {"units": {}, "redemption": None, "verdict": None, "intro": None}
    block, cur = None, None
    for line in body.splitlines():
        s = line.strip()
        m = re.match(r"^##\s+(.*)$", s)
        if m:
            head = m.group(1)
            u = re.match(r"(?i)einheit\s+(\d+)\s*(.*)$", head) or re.match(r"(?i)unit\s+(\d+)\s*(.*)$", head)
            if u:
                n = int(u.group(1))
                kind = re.search(r"(?i)(?:beleg|proof):\s*([^|]+)", u.group(2))
                short = re.search(r"(?i)short:\s*(ja|nein|yes|no)", u.group(2))
                cur = {"type": kind.group(1).strip() if kind else None,
                       "short": short.group(1).lower() in ("ja", "yes") if short else None, "hook": None, "punch": None}
                out["units"][n] = cur
                block = "unit"
            else:
                block, cur = head.strip().lower(), None
            continue
        mark = re.match(r"^([A-ZÄÖÜ0-9]+):\s*(.*)$", s)
        if not mark:
            continue
        key, val = mark.group(1), mark.group(2).strip()
        if block == "unit" and cur is not None and key in ("HOOK", "PUNCH"):
            cur[key.lower()] = val
        elif key == "EINLÖSUNG":
            out["redemption"] = val
        elif key == "URTEIL":
            out["verdict"] = val
        elif key == "SATZ1":
            out["intro"] = val
    return (out if out["units"] else None), files[-1].name


def _version_key(p: Path) -> tuple[int, str]:
    m = re.search(r"-v(\d+)", p.name)
    return (int(m.group(1)) if m else -1, p.name)


def script_parts(ep_dir: Path) -> tuple[list[str], str | None]:
    """The parts of the newest script as text (parts separated by three empty lines)."""
    from .. import craft
    files = [f for f in (ep_dir / "brief").glob("SCRIPT-v*.md") if re.fullmatch(r"SCRIPT-v\d+[\w-]*\.md", f.name)]
    if not files:
        return [], None
    plain = [f for f in files if re.fullmatch(r"SCRIPT-v\d+\.md", f.name)]
    newest = sorted(plain or files, key=_version_key)[-1]
    parts = craft.parts(newest.read_text(encoding="utf-8"))
    return [" ".join(s for par in part for s in par) for part in parts], newest.name


CHAPTER = re.compile(r"^\s*(?:(\d{1,2}):)?(\d{1,2}):(\d{2})\s+[-–—:]?\s*(.+?)\s*$")


def chapters(text: str) -> list[tuple[float, str]]:
    """YouTube chapters (``0:00 Title`` lines) from a description or a chapters file; at least two, from 0:00."""
    out = []
    for line in str(text or "").splitlines():
        m = CHAPTER.match(line)
        if m:
            h, mi, se, title = m.groups()
            out.append((int(h or 0) * 3600 + int(mi) * 60 + int(se), title))
    return out if len(out) >= 2 and out[0][0] == 0 else []


def chapter_source(ep_dir: Path, version: dict | None) -> tuple[list[tuple[float, str]], str | None]:
    """Chapters of a version: its ``chapters`` file in versions.json, else the description of ``export/upload.json``."""
    rel = (version or {}).get("chapters")
    if rel:
        p = paths.inside(ep_dir, rel)
        if p.is_file():
            return chapters(p.read_text(encoding="utf-8")), rel
    try:
        desc = json.loads((ep_dir / "export" / "upload.json").read_text(encoding="utf-8")).get("description")
        return chapters(desc), "export/upload.json"
    except (OSError, ValueError, AttributeError):
        return [], None


def snap(t: float, sents: list[dict]) -> int | None:
    """The sentence a chapter starts with: the first that starts at most 1 s before its time (authors set a chapter
    at the start of a section or a moment before it)."""
    return next((k for k, s in enumerate(sents) if s["s"] >= t - 1.0), None)


def boundaries(ep_dir: Path, sents: list[dict], lang: str, version: dict | None = None) -> dict:
    """The units of the transcript: ``{"source", "file", "units": [{"kind", "n", "i", "type", "short", "planned",
    "title"}]}`` where ``i`` is the index of the unit's first sentence."""
    dz, dz_name = drehzettel(ep_dir)
    found = chain([(i, n) for i, s in enumerate(sents) if (n := signpost(s, lang))])
    source, name = ("drehzettel", dz_name) if dz else ("signposts", None)
    starts: list[tuple[int, int]] = list(found)
    titles: dict[int, str] = {}
    outro_at = None
    if dz and len(starts) < 2:                         # the count words were not heard: the hooks by their words
        starts, pos = [], 1
        for n in sorted(dz["units"]):
            hook = re.sub(r"(?i)^(?:punkt|point)\s+\w+\.\s*", "", dz["units"][n].get("hook") or "")
            i = find(hook, sents, pos, lang)
            if i is not None:
                starts.append((i, n))
                pos = i + 1
    if not dz and len(starts) < 2:
        chs, cname = chapter_source(ep_dir, version)
        starts = []
        for t, title in chs[1:]:
            i = snap(t, sents)
            if i is not None and i > 0 and (not starts or i > starts[-1][0]):
                starts.append((i, len(starts) + 1))
                titles[i] = title
        if starts:
            source, name = "chapters", cname
    if not dz and len(starts) < 2:
        texts, sname = script_parts(ep_dir)
        starts, pos = [], 1
        for k, text in enumerate(texts[1:], start=1):
            i = find(text, sents, pos, lang)
            if i is None:
                continue
            if k == len(texts) - 1 and OUTRO[lang].search(text):    # the last part asks for the link: the outro
                outro_at = i
                break
            starts.append((i, len(starts) + 1))
            pos = i + 1
        source, name = ("script", sname) if starts else ("whole video", None)
    units = [{"kind": "intro", "n": 0, "i": 0, "type": None, "short": None, "planned": None, "title": None}]
    for i, n in starts:
        meta = (dz or {}).get("units", {}).get(n) or {}
        if i == 0:
            units = []
        units.append({"kind": "unit", "n": n, "i": i, "type": meta.get("type"), "short": meta.get("short"),
                      "planned": meta.get("hook"), "title": titles.get(i)})
    last = starts[-1][0] if starts else 0
    red = find(dz["redemption"], sents, last + 1, lang, 0.6) if dz and dz.get("redemption") else None
    if red is not None:
        units.append({"kind": "redemption", "n": None, "i": red, "type": None, "short": None,
                      "planned": dz["redemption"], "title": None})
        last = red
    outro = outro_at
    if outro is None and dz and dz.get("verdict"):
        outro = find(dz["verdict"], sents, last + 1, lang, 0.6)
    if outro is None:
        outro = next((j for j in range(last + 1, len(sents)) if OUTRO[lang].search(sents[j]["text"])), None)
    if outro is not None:
        units.append({"kind": "outro", "n": None, "i": outro, "type": None, "short": None,
                      "planned": (dz or {}).get("verdict"), "title": None})
    return {"source": source, "file": name, "units": units}


# ---------------------------------------------------------------------------------------------------- measuring


def hook_of(sents: list[dict], i: int, j: int) -> tuple[str, str, bool]:
    """The hook of a unit that starts at sentence i (and ends before j), the sentence to judge it by, and whether that
    sentence holds the count word. A count sentence of up to 6 words takes the next sentence with it; one of up to 3
    words ("Punkt eins.") is judged by the next sentence."""
    first = sents[i]["text"]
    if len(sents[i]["toks"]) <= 6 and i + 1 < j:
        hook = f"{first} {sents[i + 1]['text']}"
        return (hook, sents[i + 1]["text"], False) if len(sents[i]["toks"]) <= 3 else (hook, first, True)
    return first, first, True


def hook_type(claim: str, lang: str, counted: bool) -> tuple[str, bool]:
    """``number``, ``question``, ``objection``, ``label`` (only names the topic, up to 4 words before the first comma
    after the count word: "Rolle 3 ist der Schnitt.", "Kurz zu dem Problem.") or ``claim``, and whether it starts in
    the first person after the count word."""
    ws = toks(claim)
    rest = ws
    if counted:                       # drop the count phrase and a copula: "Punkt eins", "Rolle 3 ist der", "1 ist der"
        m = re.match(rf"^{LEAD[lang]}\s*(?:(?:{COUNTED[lang]})\s+\S+|\d{{1,2}}|{'|'.join(NUMS[lang])}|"
                     rf"{'|'.join(ORDS[lang])})\s*(?:{IS[lang]}\s*)?", " ".join(ws))
        if m:
            rest = " ".join(ws)[m.end():].split()
    first_person = bool(rest) and rest[0] in FIRST_PERSON[lang]
    if claim.rstrip().endswith("?"):
        return "question", first_person
    if OBJECTION[lang].search(claim):
        return "objection", first_person
    if has_number(claim, rest[:12]):
        return "number", first_person
    clause = len(toks(re.split(r"[,;:–—]", claim)[0])) - (len(ws) - len(rest))
    if clause <= 4:
        return "label", first_person
    return "claim", first_person


def has_number(text: str, window: list[str]) -> bool:
    """A real number in the window: digits or a number word, not a model or version name ("Qwen 3.8", "RTX 5090",
    "3D", "4K")."""
    names = {d for m in re.finditer(r"(?<=[A-Za-z] )\d+[.,]\d+\b|(?<=[A-Z]{2} )\d{3,}\b", text)
             for d in re.findall(r"\d+", m.group(0))}
    for t in window:
        if t.isdigit() and t not in names:
            return True
        if NUMWORD.match(t):
            return True
    return False


def steepest(curve: list[tuple[float, float]], a: float, b: float, width: float = 6.0) -> dict | None:
    """The steepest drop inside a..b: the window of about ``width`` seconds (at least two points) that loses the
    most, widened while the neighbouring steps still fall at half its pace or more. ``{"start", "end", "points"}``."""
    pts = [(t, y) for t, y in curve if a - 1e-6 <= t <= b + 1e-6]
    if len(pts) < 2:
        return None
    step = sorted(pts[i + 1][0] - pts[i][0] for i in range(len(pts) - 1))[(len(pts) - 1) // 2]
    w = max(width, 2 * step - 1e-6)
    best = None
    for k in range(len(pts) - 1):
        j = k + 1
        while j + 1 < len(pts) and pts[j + 1][0] - pts[k][0] <= w + 1e-6:
            j += 1
        loss = pts[k][1] - pts[j][1]
        if loss > 1e-4 and (best is None or loss > best[0] + 1e-9):
            best = (loss, k, j)
    if not best:
        return None
    loss, k, j = best
    pace = loss / max(1e-6, pts[j][0] - pts[k][0])

    def falls(x: int, y: int) -> bool:
        return (pts[x][1] - pts[y][1]) / max(1e-6, pts[y][0] - pts[x][0]) >= pace / 2

    while k > 0 and falls(k - 1, k):
        k -= 1
    while j + 1 < len(pts) and falls(j, j + 1):
        j += 1
    while k < j - 1 and pts[k][1] - pts[k + 1][1] <= 1e-4:          # no flat step at the start or the end
        k += 1
    while j > k + 1 and pts[j - 1][1] - pts[j][1] <= 1e-4:
        j -= 1
    return {"start": round(pts[k][0], 2), "end": round(pts[j][0], 2), "points": round((pts[k][1] - pts[j][1]) * 100, 1)}


def verdict(kind: str, drop_per_min: float, rel_mean: float | None, seconds: float = MIN_S) -> str:
    if seconds < MIN_S:
        return "too short"
    if kind == "intro":
        if rel_mean is None:
            return "unknown"
        return "holds" if rel_mean >= INTRO_HOLDS else ("loses" if rel_mean < INTRO_LOSES else "neutral")
    return "holds" if drop_per_min <= HOLDS else ("loses" if drop_per_min >= LOSES else "neutral")


def measure(words: list[dict], curve: list[list], duration: float, ep_dir: Path, version: dict | None = None) -> dict:
    """The units of one version with their numbers."""
    sents = sentences(words)
    if not sents:
        raise ValueError("the words file has no words")
    lang = language(sents)
    bnd = boundaries(ep_dir, sents, lang, version)
    aw = [(r[0] * duration, r[1]) for r in curve]
    rel = [(r[0] * duration, r[2]) for r in curve if r[2] is not None]
    ratio = [(r[0], r[1]) for r in curve]

    def ret(t: float) -> float:
        return at(ratio, min(1.0, max(0.0, t / duration)))

    def rank(t: float) -> float | None:
        return at([(x / duration, y) for x, y in rel], min(1.0, max(0.0, t / duration))) if rel else None

    units = []
    spec = bnd["units"]
    for k, u in enumerate(spec):
        i = u["i"]
        j = spec[k + 1]["i"] if k + 1 < len(spec) else len(sents)
        start = 0.0 if k == 0 else sents[i]["s"]
        end = sents[j]["s"] if j < len(sents) else duration
        end = min(max(end, start + 0.01), duration)
        r0, r1 = ret(start), ret(end)
        minutes = (end - start) / 60
        drop = (r0 - r1) * 100
        inside = [y for t, y in rel if start <= t <= end]
        rel_mean = (sum(inside) / len(inside)) if inside else rank((start + end) / 2)
        rel0, rel1 = rank(start), rank(end)
        hook, claim, counted = hook_of(sents, i, j)
        htype, first_person = hook_type(claim, lang, counted and bnd["source"] in ("signposts", "drehzettel"))
        if u["kind"] == "intro" and htype == "label":
            htype = "claim"
        st = steepest(aw, start, end)
        if st:
            s_at = sentence_at(sents, st["start"])
            st["sentence"] = s_at["text"] if s_at else ""
            st["said"] = said(sents, st["start"] - 3, st["end"])
        body = " ".join(s["text"] for s in sents[i:j])
        numbers = len([t for t in toks(body) if t.isdigit() or NUMWORD.match(t)])
        label = {"intro": "Intro", "redemption": "Redemption", "outro": "Outro"}.get(u["kind"]) or f"Unit {u['n']}"
        if u.get("title"):
            label += f" ({short(u['title'], 40)})"
        units.append({
            "index": k, "kind": u["kind"], "n": u["n"], "label": label, "type": u["type"], "short": u["short"],
            "start": round(start, 2), "end": round(end, 2), "seconds": round(end - start, 1),
            "retention_start": round(r0 * 100, 1), "retention_end": round(r1 * 100, 1), "drop_points": round(drop, 1),
            "drop_per_min": round(drop / minutes, 1) if minutes > 0 else 0.0,
            "rel_mean": round(rel_mean, 3) if rel_mean is not None else None,
            "rel_change": round(rel1 - rel0, 3) if rel0 is not None and rel1 is not None else None,
            "title": u.get("title"), "hook": hook, "hook_type": htype, "hook_first_person": first_person, "planned_hook": u["planned"],
            "numbers_per_min": round(numbers / minutes, 1) if minutes > 0 else 0.0,
            "objection": bool(OBJECTION[lang].search(body)), "steepest": st, "why": []})
    for u in units:
        u["verdict"] = verdict(u["kind"], u["drop_per_min"], u["rel_mean"], u["seconds"])
    content = [u for u in units if u["kind"] == "unit"] or units
    worst = max(content, key=lambda u: u["drop_points"])
    return {"language": lang, "boundaries": bnd["source"], "boundaries_file": bnd["file"], "units": units,
            "worst_unit": worst["index"]}


# ---------------------------------------------------------------------------------------------------- versions


def _plan_words(ep_dir: Path) -> str | None:
    plans = sorted((ep_dir / "edit").glob("plan-v*.json"), key=_version_key)
    for p in reversed(plans):
        try:
            w = json.loads(p.read_text(encoding="utf-8")).get("words")
        except (OSError, ValueError, AttributeError):
            continue
        if w and (ep_dir / w).is_file():
            return w
    return None


def video_id(ep_dir: Path, given: str | None = None) -> str | None:
    """``--video``, ``analytics/versions.json`` ``video_id``, ``export/upload-result.json``, or a ``video-id.txt``
    of an earlier upload folder."""
    if given:
        return given
    vf = ep_dir / "analytics" / "versions.json"
    if vf.is_file():
        try:
            v = json.loads(vf.read_text(encoding="utf-8")).get("video_id")
            if v:
                return str(v)
        except (OSError, ValueError, AttributeError):
            pass
    if upload(ep_dir).get("video_id"):
        return str(upload(ep_dir)["video_id"])
    try:                                   # an imported publication (crewcut/import_history.py)
        ev = (json.loads((ep_dir / "project.json").read_text(encoding="utf-8")).get("import_history") or {}).get(
            "provider_evidence") or {}
        if ev.get("provider") == "youtube" and re.fullmatch(r"[A-Za-z0-9_-]{11}", str(ev.get("video_id") or "")):
            return str(ev["video_id"])
    except (OSError, ValueError, AttributeError):
        pass
    for p in sorted((ep_dir / "export").glob("*/video-id.txt")):
        v = p.read_text(encoding="utf-8").strip()
        if re.fullmatch(r"[A-Za-z0-9_-]{11}", v):
            return v
    return None


def versions(ep_dir: Path, a) -> list[dict]:
    """The versions to measure: from the command line, from ``analytics/versions.json``, or one default version."""
    up = upload(ep_dir)
    first_day = str(up.get("at") or "")[:10] or None
    if getattr(a, "words", None) or getattr(a, "duration", None) or getattr(a, "since", None) or \
            getattr(a, "until", None):
        words = a.words or _plan_words(ep_dir)
        return [{"label": Path(words).stem if words else "video", "words": words, "duration_s": a.duration,
                 "since": a.since or first_day, "until": a.until, "file": None}]
    vf = ep_dir / "analytics" / "versions.json"
    if vf.is_file():
        data = json.loads(vf.read_text(encoding="utf-8"))
        out = []
        for v in data.get("versions") or []:
            if isinstance(v, dict) and v.get("words"):
                out.append({"label": str(v.get("label") or Path(v["words"]).stem), "words": v["words"],
                            "duration_s": v.get("duration_s"), "since": v.get("since") or first_day,
                            "until": v.get("until"), "file": v.get("file"), "chapters": v.get("chapters"),
                            "note": v.get("note")})
        if out:
            return out
    words = _plan_words(ep_dir)
    if not words:
        found = sorted((ep_dir / "work").glob("words-v*.json"), key=_version_key)
        words = found[-1].relative_to(ep_dir).as_posix() if found else None
    return [{"label": Path(words).stem if words else "video", "words": words, "duration_s": None,
             "since": first_day, "until": None, "file": None}]


def probe(path: Path) -> float | None:
    if not shutil.which("ffprobe") or not path.is_file():
        return None
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                              str(path)], capture_output=True, text=True, timeout=60).stdout.strip()
        return float(out)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def local_file(ep_dir: Path, version: dict, duration: float) -> Path | None:
    """The local video of a version: its ``file``, else an export whose length matches within a second."""
    if version.get("file"):
        try:
            p = paths.inside(ep_dir, version["file"])
        except ValueError:
            return None
        return p if p.is_file() else None
    for p in sorted((ep_dir / "export").glob("*.mp4"), key=lambda x: x.stat().st_mtime, reverse=True):
        d = probe(p)
        if d is not None and abs(d - duration) <= 1.0:
            return p
    return None


# ---------------------------------------------------------------------------------------------------- the command


def run(episode: str, a, api=None, today: date | None = None) -> dict:
    """Fetch (or reuse the saved curve), measure every version with data, write the episode report, add the block to
    the learnings file. Raises NoData when no version has data yet (nothing is written then)."""
    ep_dir = paths.episode_dir(episode)
    if not ep_dir.is_dir():
        raise FileNotFoundError(f"There is no episode {episode}.")
    out_dir = ep_dir / "analytics"
    saved = {}
    if getattr(a, "saved", False):
        try:
            saved = json.loads((out_dir / "retention-units.json").read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise FileNotFoundError("There is no saved measurement (analytics/retention-units.json).") from e
    vid = video_id(ep_dir, getattr(a, "video", None)) or saved.get("video_id")
    if not vid:
        raise NoData("the episode has no published video id (export/upload-result.json, analytics/versions.json or "
                     "--video)")
    day = today or datetime.now(UTC).date()
    api = api if api is not None or saved else YouTube()
    vers = versions(ep_dir, a)
    api_duration = None
    results, skipped = [], []
    old = {m["label"]: m for m in saved.get("measurements") or []}
    for n, v in enumerate(vers):
        try:
            wf = paths.inside(ep_dir, v["words"]) if v["words"] else None
        except ValueError:
            wf = None
        if wf is None or not wf.is_file():
            skipped.append({"label": v["label"], "status": f"words file missing ({v['words']})"})
            continue
        words = norm_words(json.loads(wf.read_text(encoding="utf-8")))
        if saved:
            if v["label"] not in old:
                skipped.append({"label": v["label"], "status": "not in the saved measurement"})
                continue
            got = {"curve": old[v["label"]]["curve"], "sample": old[v["label"]]["sample"],
                   "data_until": old[v["label"]]["data_until"]}
            duration = float(old[v["label"]]["duration_s"])
        else:
            since = v["since"] or (day - timedelta(days=3650)).isoformat()
            until = v["until"] or day.isoformat()
            got = fetch(api, vid, since, until)
            duration = v["duration_s"]
            if not duration and v.get("file"):
                f = local_file(ep_dir, v, 0.0)
                duration = probe(f) if f else None
            if not duration and not v["until"] and n == len(vers) - 1:
                api_duration = api_duration or api.duration(vid)
                duration = api_duration
            duration = float(duration or (words[-1]["e"] + 1.0))
        if len(got["curve"]) < 2 or not got["sample"]["views"]:
            skipped.append({"label": v["label"], "status": NO_DATA, "since": v["since"], "until": v["until"]})
            continue
        m = measure(words, got["curve"], duration, ep_dir, v)
        warn = []
        if words[-1]["e"] > duration + 2 or words[-1]["e"] < duration - 30:
            warn.append(f"the words end at {words[-1]['e']:.0f} s, the video is {duration:.0f} s long: is this the "
                        "words file of the published version?")
        if got["sample"]["views"] < SMALL:
            warn.append(f"small sample: {got['sample']['views']} views, the curve moves in steps of a few viewers")
        results.append({"label": v["label"], "words": v["words"], "file": v.get("file"), "duration_s": round(duration, 2),
                        "since": v["since"], "until": v["until"], "note": v.get("note"), "data_until":
                        got["data_until"], "sample": got["sample"], "curve": got["curve"], "warnings": warn, **m})
    if not results:
        raise NoData(NO_DATA + "".join(f"; {s['label']}: {s['status']}" for s in skipped))
    why = read_why(out_dir)
    for r in results:
        for u in r["units"]:
            u["why"] = [w for w in why if w.get("version", r["label"]) == r["label"] and w.get("unit") == u["index"]]
    res = {"schema": SCHEMA, "episode": episode, "video_id": vid, "measured": day.isoformat(),
           "measurements": results, "skipped": skipped,
           "note": "a hint, not proof: single findings are 'watch' until they repeat in "
                   f"{REPEATS} episodes"}
    clips = int(getattr(a, "clips", 0) or 0)
    if clips:
        res["clips"] = cut_clips(ep_dir, results[-1], clips)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "retention-units.json").write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n",
                                                  encoding="utf-8")
    (out_dir / "retention-units.md").write_text(render_md(res), encoding="utf-8")
    if not getattr(a, "no_learnings", False):
        res["learnings"] = str(add_learnings(res))
    return res


def read_why(out_dir: Path) -> list[dict]:
    """``analytics/retention-units-why.json``: ``[{"version", "unit", "at", "by", "text"}]`` from whoever watched."""
    try:
        data = json.loads((out_dir / "retention-units-why.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [w for w in data if isinstance(w, dict) and w.get("text")] if isinstance(data, list) else []


def cut_clips(ep_dir: Path, m: dict, n: int) -> list[dict]:
    """The n steepest drops of a measurement's content units (the intro's first seconds lose cold viewers in every
    video) as short clips, 8 s before to 4 s after, in ``analytics/drops/``."""
    src = local_file(ep_dir, {"file": m.get("file")}, m["duration_s"])
    pool = [u for u in m["units"] if u.get("steepest") and u["kind"] in ("unit", "redemption")] or \
        [u for u in m["units"] if u.get("steepest")]
    drops = sorted(pool, key=lambda u: -u["steepest"]["points"])[:n]
    if src is None or not shutil.which("ffmpeg"):
        return [{"unit": u["index"], "status": "no local video of this length" if src is None else "no ffmpeg"}
                for u in drops]
    out = []
    folder = ep_dir / "analytics" / "drops"
    folder.mkdir(parents=True, exist_ok=True)
    for u in drops:
        a = max(0.0, u["steepest"]["start"] - CONTEXT[0])
        b = min(m["duration_s"], u["steepest"]["end"] + CONTEXT[1])
        name = f"{m['label']}-unit{u['index']}-{int(a) // 60}m{int(a) % 60:02d}s.mp4"
        cmd = ["ffmpeg", "-y", "-v", "error", "-ss", f"{a:.2f}", "-i", str(src), "-t", f"{b - a:.2f}",
               "-vf", "scale=-2:720", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-c:a", "aac",
               "-b:a", "128k", str(folder / name)]
        ok = subprocess.run(cmd, capture_output=True, timeout=600).returncode == 0
        out.append({"unit": u["index"], "file": f"analytics/drops/{name}" if ok else None, "from": round(a, 2),
                    "to": round(b, 2), "source": src.relative_to(ep_dir).as_posix(),
                    "status": "cut" if ok else "ffmpeg failed"})
    return out


# ---------------------------------------------------------------------------------------------------- reports


def tc(t: float | None) -> str:
    if t is None:
        return "-"
    m, s = divmod(int(round(float(t))), 60)
    return f"{m}:{s:02d}"


def short(text: str, n: int = 90) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def _type(u: dict) -> str:
    return u["type"] or u["kind"]


def _hook(u: dict) -> str:
    return u["hook_type"] + ("+I" if u["hook_first_person"] else "")


def render_md(res: dict) -> str:
    L = [f"# Retention per content unit: {res['episode']}", "",
         f"Video {res['video_id']}, measured {res['measured']}. A hint, not proof: one video is a small sample.", ""]
    for m in res["measurements"]:
        s = m["sample"]
        L += [f"## Version {m['label']} ({tc(m['duration_s'])}, words `{m['words']}`)", "",
              f"Days {m['since'] or 'upload'} to {m['until'] or 'today'}, data until {m['data_until']}: "
              f"{s['views']} views, mean view {s['average_view_s']} s ({s['average_view_percent']} %). "
              f"Units from {m['boundaries']}" + (f" (`{m['boundaries_file']}`)" if m["boundaries_file"] else "") + "."]
        if m.get("note"):
            L.append(f"Note: {m['note']}")
        L += [f"Warning: {w}" for w in m["warnings"]]
        L += ["", "Retention = share of viewers who see that moment (over 100 % = some watch it again). Rel. = rank "
              "against similar YouTube videos at the same place (0.5 = middle, under 0.3 weak), mean over the unit "
              "and its change from start to end.", "",
              "| # | Unit | Type | Hook type | Time | Retention | Lost | Lost/min | Rel. (change) | Verdict |",
              "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
        for u in m["units"]:
            rel = "-" if u["rel_mean"] is None else f"{u['rel_mean']:.2f} ({u['rel_change']:+.2f})" \
                if u["rel_change"] is not None else f"{u['rel_mean']:.2f}"
            L.append(f"| {u['index']} | {u['label']}: {short(u['hook'], 70)} | {_type(u)} | {_hook(u)} | "
                     f"{tc(u['start'])}–{tc(u['end'])} | {u['retention_start']:.0f} → {u['retention_end']:.0f} % | "
                     f"{u['drop_points']:.1f} | {u['drop_per_min']:.1f} | {rel} | {u['verdict']} |")
        worst = m["units"][m["worst_unit"]]
        L += ["", f"Lost the most: {worst['label']} ({tc(worst['start'])}–{tc(worst['end'])}), "
              f"{worst['drop_points']:.1f} points, {worst['drop_per_min']:.1f} per minute.", "",
              "### Where the steepest drop of each unit starts", ""]
        for u in m["units"]:
            st = u.get("steepest")
            if not st:
                L.append(f"- {u['label']}: no falling stretch.")
                continue
            L.append(f"- {u['label']}: {tc(st['start'])}–{tc(st['end'])}, −{st['points']:.1f} points, at "
                     f"\"{short(st['sentence'], 160)}\" (said: \"{short(st['said'], 220)}\")")
        whys = [(u, w) for u in m["units"] for w in u.get("why") or []]
        if whys:
            L += ["", "### Why viewers left (watched)", ""]
            for u, w in whys:
                L.append(f"- {u['label']}, {tc(w.get('at'))} ({w.get('by') or 'watcher'}): {w['text'].strip()}")
        L.append("")
    for s in res.get("skipped") or []:
        L.append(f"- Version {s['label']}: {s['status']}.")
    for c in res.get("clips") or []:
        L.append(f"- Clip of unit {c['unit']}: {c.get('file') or c['status']}")
    return "\n".join(L).rstrip() + "\n"


HEADER = """# Retention per content unit: what holds viewers and what loses them

Written by `crewcut retention units <episode>` after a video is published (YouTube Analytics, read-only). Read by the
script critic before it judges a new script or Drehzettel. Do not edit by hand: the overall section is rewritten on
every run, the episode blocks below it are appended (a run with the same episode and data day replaces its block).

Format (schema 1, stable):

- `## Overall`, between the two comment lines `overall:start` and `overall:end`: one row per group over the newest
  block of every episode. Groups: `kind` (intro, unit, redemption, outro: all parts), and for the content units only
  `type` (the Drehzettel `Beleg:` of the unit, else "unknown"), `hook` (hook type) and `first person` (the hook after
  the count word starts with I, my, we or our). Columns: units, episodes, holds, loses, mean drop per minute, mean
  change of the rank, and `Status`: "lesson: holds" (or "lesson: loses") when the group holds (loses) in at least 3
  episodes and the other way in at most one, else "watch".
- One block per episode and data day: heading `## <episode> · data until <YYYY-MM-DD>`, a line with the measuring day,
  video, version, views and where the unit boundaries came from, a table with one row per unit, then the lines
  `- Holds:`, `- Loses:`, `- Steepest drop:` (per losing unit, the sentence where the drop starts) and, when someone
  watched the drops, `- Why (watched by …):`. The last line `<!-- retention-units {...} -->` holds the same numbers as
  JSON for programs.
- Table columns: `#` (0 = intro), `Unit` (hook sentence, shortened), `Type`, `Hook type` (number = a real number in the
  first 12 words after the count word, question, objection, label = only names the topic, claim; `+I` = first person),
  `Time`, `Retention` (share of viewers at start and end), `Drop/min` (points of the audience lost per minute),
  `Rel.` (mean rank against similar YouTube videos at the same place: 0.5 = middle, under 0.3 weak; in brackets its
  change over the unit), `Verdict` (holds: at most 5 points per minute; loses: at least 15; the intro by its rank:
  holds from 0.5, loses under 0.3; "too short" under 15 s).
- A hint, not proof: a curve of a few dozen viewers moves in steps of one person. Trust a group only when its status
  is "lesson".

## Overall

""" + OVERALL_START + "\n" + OVERALL_END + "\n"


def block(res: dict) -> str:
    """The learnings block of one measurement (the newest version with data)."""
    m = res["measurements"][-1]
    s = m["sample"]
    L = [f"## {res['episode']} · data until {m['data_until']}", "",
         f"Measured {res['measured']} · video {res['video_id']} · version {m['label']} ({tc(m['duration_s'])}) · "
         f"{s['views']} views" + (" (small sample)" if s["views"] < SMALL else "") +
         f" · units from {m['boundaries']}", "",
         "| # | Unit | Type | Hook type | Time | Retention | Drop/min | Rel. | Verdict |",
         "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for u in m["units"]:
        rel = "-" if u["rel_mean"] is None else f"{u['rel_mean']:.2f}" + (
            f" ({u['rel_change']:+.2f})" if u["rel_change"] is not None else "")
        L.append(f"| {u['index']} | {short(u['hook'], 60)} | {_type(u)} | {_hook(u)} | {tc(u['start'])}–"
                 f"{tc(u['end'])} | {u['retention_start']:.0f} → {u['retention_end']:.0f} % | {u['drop_per_min']:.1f} | "
                 f"{rel} | {u['verdict']} |")
    held = [u for u in m["units"] if u["verdict"] == "holds"]
    lost = [u for u in m["units"] if u["verdict"] == "loses"]
    L.append("")
    L.append("- Holds: " + ("; ".join(f"{u['label']} ({_type(u)}, {_hook(u)} hook \"{short(u['hook'], 60)}\")"
                                      for u in held) or "none"))
    L.append("- Loses: " + ("; ".join(f"{u['label']} ({_type(u)}, {_hook(u)} hook \"{short(u['hook'], 60)}\", "
                                      f"{u['drop_per_min']:.0f} points per minute)" for u in lost) or "none"))
    for u in lost:
        st = u.get("steepest")
        if st:
            L.append(f"- Steepest drop: {u['label']} at {tc(st['start'])}, −{st['points']:.0f} points, "
                     f"\"{short(st['sentence'], 140)}\"")
    for u in m["units"]:
        for w in u.get("why") or []:
            L.append(f"- Why (watched by {w.get('by') or 'a watcher'}): {u['label']} at {tc(w.get('at'))}: "
                     f"{short(w['text'], 600)}")
    data = {"schema": SCHEMA, "episode": res["episode"], "video_id": res["video_id"], "measured": res["measured"],
            "data_until": m["data_until"], "views": s["views"], "version": m["label"],
            "units": [{"index": u["index"], "kind": u["kind"], "type": u["type"], "hook_type": u["hook_type"],
                       "first_person": u["hook_first_person"], "seconds": u["seconds"],
                       "drop_per_min": u["drop_per_min"], "rel_mean": u["rel_mean"], "rel_change": u["rel_change"],
                       "verdict": u["verdict"]} for u in m["units"]]}
    L += ["", DATA_MARK + json.dumps(data, ensure_ascii=False) + " -->", ""]
    return "\n".join(L)


def _blocks(text: str) -> list[tuple[str, str]]:
    """(heading, text) of every episode block below the overall section."""
    body = text.split(OVERALL_END, 1)[1] if OVERALL_END in text else ""
    parts = re.split(r"(?m)^(?=## )", body)
    return [(p.splitlines()[0], p) for p in parts if p.startswith("## ") and DATA_MARK in p]


def overall(blocks: list[tuple[str, str]]) -> str:
    """The overall table from the newest block of every episode."""
    newest: dict[str, dict] = {}
    for _, text in blocks:
        line = next((x for x in text.splitlines() if x.startswith(DATA_MARK)), None)
        if not line:
            continue
        try:
            d = json.loads(line[len(DATA_MARK):].rsplit("-->", 1)[0])
        except ValueError:
            continue
        if d.get("episode") not in newest or str(d.get("data_until")) >= str(newest[d["episode"]].get("data_until")):
            newest[d["episode"]] = d
    groups: dict[tuple[str, str], list[tuple[str, dict]]] = {}
    for ep, d in newest.items():
        for u in d.get("units") or []:
            keys = [("kind", u["kind"])]
            if u["kind"] == "unit":
                keys += [("type", u.get("type") or "unknown"), ("hook", u["hook_type"]),
                         ("first person", "yes" if u.get("first_person") else "no")]
            for k in keys:
                groups.setdefault(k, []).append((ep, u))
    if not groups:
        return "No measured episodes yet."
    L = [f"Episodes: {len(newest)} ({', '.join(sorted(newest))}).", "",
         "| Group | Value | Units | Episodes | Holds | Loses | Drop/min | Rel. change | Status |",
         "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for (g, v), rows in sorted(groups.items()):
        hold = {ep for ep, u in rows if u["verdict"] == "holds"}
        lose = {ep for ep, u in rows if u["verdict"] == "loses"}
        drops = [u["drop_per_min"] for _, u in rows if u["verdict"] != "too short"] or [0.0]
        rc = [u["rel_change"] for _, u in rows if u.get("rel_change") is not None]
        status = ("lesson: holds" if len(hold) >= REPEATS and len(lose) <= 1 else
                  "lesson: loses" if len(lose) >= REPEATS and len(hold) <= 1 else "watch")
        L.append(f"| {g} | {v} | {len(rows)} | {len({ep for ep, _ in rows})} | "
                 f"{sum(1 for _, u in rows if u['verdict'] == 'holds')} | "
                 f"{sum(1 for _, u in rows if u['verdict'] == 'loses')} | {sum(drops) / len(drops):.1f} | "
                 f"{(sum(rc) / len(rc)) if rc else 0:+.2f} | {status} |")
    return "\n".join(L)


def learnings_path() -> Path:
    return paths.studio_root().joinpath(*LEARNINGS)


def add_learnings(res: dict) -> Path:
    """Add (or replace) this episode's block for its data day and rewrite the overall section."""
    p = learnings_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    text = p.read_text(encoding="utf-8") if p.is_file() else HEADER
    if OVERALL_END not in text:
        text = HEADER + "\n" + text
    new = block(res)
    head = new.splitlines()[0]
    blocks = _blocks(text)
    kept = [b for h, b in blocks if h.strip() != head.strip()]
    kept.append(new)
    top = text.split(OVERALL_START, 1)[0]
    body = overall([(b.splitlines()[0], b) for b in kept])
    out = top + OVERALL_START + "\n" + body + "\n" + OVERALL_END + "\n\n" + "\n".join(b.rstrip() + "\n" for b in kept)
    tmp = p.with_suffix(".md.tmp")
    tmp.write_text(out, encoding="utf-8")
    tmp.replace(p)
    return p


def lines(res: dict) -> list[str]:
    out = []
    for m in res["measurements"]:
        out.append(f"retention per unit of {res['video_id']}, version {m['label']} (data until {m['data_until']}, "
                   f"{m['sample']['views']} views, units from {m['boundaries']}). A hint, not proof.")
        for w in m["warnings"]:
            out.append(f"  warning: {w}")
        for u in m["units"]:
            st = u.get("steepest")
            out.append(f"  {u['index']:>2} {u['label']:<11} {tc(u['start'])}-{tc(u['end'])}  "
                       f"{u['retention_start']:5.1f} -> {u['retention_end']:5.1f} %  {u['drop_per_min']:5.1f}/min  "
                       f"rel {u['rel_mean'] if u['rel_mean'] is not None else '-'}  {u['verdict']:<7} "
                       f"{_hook(u)}: {short(u['hook'], 60)}"
                       + (f"  | drop at {tc(st['start'])}: {short(st['sentence'], 60)}" if st else ""))
    for s in res.get("skipped") or []:
        out.append(f"  version {s['label']}: {s['status']}")
    for c in res.get("clips") or []:
        out.append(f"  clip unit {c['unit']}: {c.get('file') or c['status']}")
    if res.get("learnings"):
        out.append(f"  learnings: {res['learnings']}")
    return out


def main(a) -> int:
    if a.rtcmd != "units":
        return 2
    try:
        res = run(a.episode, a)
    except NoData as e:
        print(str(e))
        return 0
    except PermissionError as e:
        print(str(e))
        return 4
    except ImportError:
        print("The YouTube libraries are missing in this image (pip extra 'youtube').")
        return 1
    if a.json:
        print(json.dumps({k: v for k, v in res.items()}, ensure_ascii=False, indent=1))
    else:
        print("\n".join(lines(res)))
    return 0
