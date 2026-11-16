"""Stand-alone passages of a finished episode, for Clip-mode Shorts. The tool only lists; the Scout chooses.

  crewcut cut candidates <episode> [--words F] [--plan F] [--retention F] [--min 20] [--max 55] [--sentences 12]
                         [--limit 30] [--json]

Reads, all in the episode folder:
  words      the word record of the final cut (default: the edit plan's "words", else the newest work/words-vNNN.json)
  plan       the edit plan with the graphics (default: the newest edit/plan-vNNN.json; optional)
  decisions  the build record of the speaker cut (work/edit-decisions-<version of the plan's base>.json; optional):
             cut boundaries inside a passage, because a Short's piece may not cross one, and whether the originals
             and the clean voice are still there (a Clip Short is cut from them)
  retention  the audience retention curve, when the video is online (default: review/retention.json or .csv;
             optional). Rows of position and value: position as a share of the video (pos, ratio,
             elapsedVideoTimeRatio; 0..1 or 0..100 %) or in seconds (seconds, at, t); value as retention, value or
             audienceWatchRatio. Where the curve rises, viewers watched again.

Writes review/short-candidates-vNNN.json and prints it with --json:
  sentences  every sentence with times, words, numbers, result words, the graphics over it, rises of the curve and
             the cut boundaries inside it. A Short may combine sentences from different places: each one is a piece.
  passages   runs of whole sentences of min..max seconds (20 to 55), at most --sentences sentences, with simple
             signals and a score that only sorts the list: a number or result, graphics as proof, a rise of the
             curve, an opening that does not lean on what came before. Overlapping runs are thinned out.
Without a retention file the list rests on the text alone, and the output says so.
"""

from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path

from .common import CutError, channel_language, inside, read_json, rel, version_in, write_replace
from .short import load_words, newest, timeline

END = re.compile(r"[.!?…]+[\"'”»)]*$")
NUMBER = re.compile(r"\d")
LONG_PAUSE = 1.5      # a pause this long ends a sentence even without a full stop
# Words that tie a sentence to the one before; such an opening does not stand alone.
LINKS = {
    "en": {"and", "but", "so", "because", "then", "also", "or", "which", "plus", "anyway", "therefore", "however"},
    "de": {"und", "aber", "also", "denn", "weil", "dann", "auch", "oder", "sondern", "deshalb", "darum", "dabei",
           "trotzdem", "außerdem", "jedenfalls"},
}
NUMBER_WORDS = {
    "en": {"one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve",
           "twenty", "thirty", "forty", "fifty", "hundred", "thousand", "million", "billion", "percent", "half",
           "double", "twice", "third", "quarter"},
    "de": {"eins", "zwei", "drei", "vier", "fünf", "sechs", "sieben", "acht", "neun", "zehn", "elf", "zwölf",
           "zwanzig", "dreißig", "vierzig", "fünfzig", "hundert", "tausend", "million", "millionen", "milliarde",
           "milliarden", "prozent", "hälfte", "doppelt", "doppelte", "drittel", "viertel"},
}
RESULT_WORDS = {
    "en": {"result", "results", "won", "lost", "saved", "faster", "slower", "cheaper", "measured", "beat", "failed",
           "worked", "broke", "doubled", "halved", "score", "scored", "winner", "best", "worst", "ranking", "ranked"},
    "de": {"ergebnis", "ergebnisse", "gewonnen", "verloren", "gespart", "schneller", "langsamer", "billiger",
           "gemessen", "geschlagen", "gescheitert", "funktioniert", "kaputt", "verdoppelt", "halbiert", "gewinner",
           "beste", "schlechteste", "ranking", "platz"},
}


def toks(text: str) -> list[str]:
    return [t for t in (re.sub(r"^[\W_]+|[\W_]+$", "", w.lower()) for w in text.split()) if t]


def split_sentences(words: list[dict]) -> list[dict]:
    """Sentences from words: a full stop, question or exclamation mark ends one, so does a long pause."""
    out, cur = [], []
    for i, w in enumerate(words):
        cur.append(w)
        nxt = words[i + 1] if i + 1 < len(words) else None
        if END.search(w["w"]) or nxt is None or nxt["s"] - w["e"] >= LONG_PAUSE:
            text = " ".join(x["w"] for x in cur)
            out.append({"n": len(out) + 1, "from": round(cur[0]["s"], 2), "to": round(cur[-1]["e"], 2),
                        "words": len(cur), "text": text, "complete": bool(END.search(w["w"]))})
            cur = []
    return out


def numbers_in(text: str, lang: str) -> list[str]:
    nw = NUMBER_WORDS.get(lang, NUMBER_WORDS["en"])
    return [w for w in text.split() if NUMBER.search(w)] + [t for t in toks(text) if t in nw]


# ---- graphics and retention --------------------------------------------------------------------------------------
def graphics(plan: dict | None) -> list[dict]:
    """The inserts of an edit plan with a short label (the text the viewer sees, when the data has one)."""
    out = []
    for e in (plan or {}).get("inserts") or []:
        try:
            a, b = float(e["start"]), float(e["end"])
        except (KeyError, TypeError, ValueError):
            continue
        d = e.get("data") or {}
        label = " ".join(str(d[k]) for k in ("label", "value", "unit", "title", "text") if d.get(k))
        out.append({"id": e.get("id"), "kind": e.get("kind"), "scene": e.get("scene") or e.get("file"),
                    "from": a, "to": b, "label": label[:80]})
    return out


def covering(items: list[dict], a: float, b: float) -> list[dict]:
    return [g for g in items if g["from"] < b and g["to"] > a]


def _num(v) -> float | None:
    try:
        return float(str(v).strip().rstrip("%").replace(",", "."))
    except ValueError:
        return None


POS_SHARE = ("elapsedvideotimeratio", "pos", "position", "ratio", "share")
POS_SECONDS = ("seconds", "second", "at", "t", "time")
VALUE = ("audiencewatchratio", "retention", "value", "percent", "watch")


def _pick(keys: list[str], names: tuple[str, ...]) -> str | None:
    """The column whose name is one of names, else the first that contains one (names of 3 letters or more)."""
    low = {k: re.sub(r"[^a-z]", "", str(k).lower()) for k in keys}
    for n in names:
        for k, v in low.items():
            if v == n:
                return k
    for n in (x for x in names if len(x) >= 3):
        for k, v in low.items():
            if n in v:
                return k
    return None


def read_retention(path: Path, duration: float) -> list[tuple[float, float]]:
    """[(seconds, retention in percent)] from a JSON or CSV file (see the module text for the columns)."""
    text = path.read_text(encoding="utf-8-sig")
    if path.suffix.lower() == ".json":
        data = json.loads(text)
        rows = data.get("rows", data) if isinstance(data, dict) else data
        if rows and isinstance(rows[0], (list, tuple)):
            rows = [{"pos": r[0], "value": r[1]} for r in rows]
    else:
        rows = list(csv.DictReader(io.StringIO(text)))
    if not rows:
        return []
    keys = list(rows[0].keys())
    share, secs, val = _pick(keys, POS_SHARE), _pick(keys, POS_SECONDS), _pick(keys, VALUE)
    if val is None or (share is None and secs is None):
        raise CutError(f"{path.name}: needs a position column ({', '.join(POS_SHARE + POS_SECONDS)}) and a value "
                       f"column ({', '.join(VALUE)})")
    pts = []
    for r in rows:
        p, v = _num(r.get(share if share else secs)), _num(r.get(val))
        if p is None or v is None:
            continue
        pts.append((p, v))
    if share:
        top = max(p for p, _ in pts) if pts else 1
        scale = 100.0 if top > 1.0 else 1.0
        pts = [(p / scale * duration, v) for p, v in pts]
    if pts and max(v for _, v in pts) <= 1.5:      # ratios: as percent
        pts = [(p, v * 100) for p, v in pts]
    return sorted(pts)


def rises(curve: list[tuple[float, float]], min_gain: float = 1.0) -> list[dict]:
    """Stretches where the curve goes up by at least min_gain percentage points (viewers watched again)."""
    out, i = [], 1
    while i < len(curve):
        if curve[i][1] > curve[i - 1][1]:
            j = i
            while j + 1 < len(curve) and curve[j + 1][1] >= curve[j][1]:
                j += 1
            gain = curve[j][1] - curve[i - 1][1]
            if gain >= min_gain:
                out.append({"from": round(curve[i - 1][0], 1), "to": round(curve[j][0], 1), "gain": round(gain, 1)})
            i = j + 1
        else:
            i += 1
    return out


# ---- passages ----------------------------------------------------------------------------------------------------
def signals(p: dict, first: dict, length: list[float]) -> tuple[int, list[str]]:
    """A small, open score that only sorts the list. Every point has its reason."""
    score, why = 0, []
    if first["numbers"]:
        score, why = score + 2, why + ["the first sentence has a number"]
    elif p["numbers"]:
        score, why = score + 1, why + ["a number in the passage"]
    if p["result"]:
        score, why = score + 1, why + ["a result word"]
    if p["graphics"]:
        g = min(2, len(p["graphics"]))
        score, why = score + g, why + [f"{len(p['graphics'])} graphics as proof in the picture"]
    if p["retention_rises"]:
        score, why = score + 2, why + ["the retention curve rises here"]
    if first["starts_with_link"]:
        score, why = score - 2, why + ["the first sentence leans on the one before"]
    if first["text"].rstrip().endswith("?"):
        score, why = score - 1, why + ["opens with a question"]
    if length and length[0] <= p["seconds"] <= length[1]:
        score, why = score + 1, why + [f"length within {length[0]:g}-{length[1]:g} s"]
    return score, why


def passages(sents: list[dict], lo: float, hi: float, max_n: int, length: list[float], bounds: list[float],
             clips: list[dict] = (), missing: list[str] = ()) -> list[dict]:
    out = []
    for i in range(len(sents)):
        for j in range(i, min(len(sents), i + max_n)):
            seconds = sents[j]["to"] - sents[i]["from"]
            if seconds > hi:
                break
            if seconds < lo or not sents[j]["complete"]:
                continue
            run = sents[i:j + 1]
            p = {"sentences": [run[0]["n"], run[-1]["n"]], "from": run[0]["from"], "to": run[-1]["to"],
                 "seconds": round(seconds, 2), "words": sum(s["words"] for s in run),
                 "first_sentence": run[0]["text"], "last_sentence": run[-1]["text"],
                 "numbers": [x for s in run for x in s["numbers"]], "result": any(s["result"] for s in run),
                 "graphics": [g for g in {g["id"]: g for s in run for g in s["graphics_full"]}.values()],
                 "retention_rises": [r for r in {(r["from"], r["to"]): r for s in run
                                                 for r in s["rises"]}.values()],
                 "cut_boundaries": [round(b, 2) for b in bounds if run[0]["from"] < b < run[-1]["to"]]}
            p["pieces_needed"] = 1 + len(p["cut_boundaries"])
            p["originals_missing"] = sorted({c["source"] for c in clips if c.get("source") in missing
                                             and c["t0"] < p["to"] and c["t1"] > p["from"]})
            p["score"], p["signals"] = signals(p, run[0], length)
            out.append(p)
    return out


def thin(items: list[dict], limit: int, max_overlap: float = 0.5) -> list[dict]:
    """Best first; drop a passage that overlaps a kept one by more than max_overlap of the shorter one."""
    kept: list[dict] = []
    for p in sorted(items, key=lambda x: (-x["score"], x["from"])):
        if all(min(p["to"], k["to"]) - max(p["from"], k["from"]) <= max_overlap * min(p["seconds"], k["seconds"])
               for k in kept):
            kept.append(p)
        if len(kept) >= limit:
            break
    return kept


# ---- the command -------------------------------------------------------------------------------------------------
def default_retention(ep_dir: Path) -> Path | None:
    for name in ("retention.json", "retention.csv"):
        p = ep_dir / "review" / name
        if p.is_file():
            return p
    return None


def find(ep_dir: Path, words: Path | None = None, plan: Path | None = None, retention: Path | None = None,
         lo: float = 20.0, hi: float = 55.0, max_sentences: int = 12, limit: int = 30) -> dict:
    if not 0 < lo < hi:
        raise CutError("--min must be above 0 and below --max")
    plan_path = plan or newest(ep_dir / "edit", "plan")
    plan_data = read_json(plan_path) if plan_path else None
    if words is None:
        if plan_data and plan_data.get("words") and inside(ep_dir, plan_data["words"]).is_file():
            words = inside(ep_dir, plan_data["words"])
        else:
            words = newest(ep_dir / "work", "words")
    if not words or not Path(words).is_file():
        raise CutError("no word record of the final cut (work/words-vNNN.json): transcribe the finished voice first")
    word_list = load_words(Path(words))
    if not word_list:
        raise CutError(f"{Path(words).name} has no words")
    lang = channel_language()
    lang = lang if lang in LINKS else "en"
    version = version_in(Path(words).name) or version_in(plan_path.name if plan_path else "") or "v001"

    clips, duration, dec_rel, voice = [], word_list[-1]["e"], None, None
    base_v = version_in(str((plan_data or {}).get("base") or "")) or version_in(Path(words).name)
    dec = ep_dir / "work" / f"edit-decisions-{base_v}.json" if base_v else None
    if dec and dec.is_file():
        manifest = read_json(dec)
        clips = timeline(manifest)
        duration = max(duration, float(manifest.get("duration_seconds") or 0))
        dec_rel = rel(ep_dir, dec)
        voice = manifest.get("voice")
    bounds = [c["t1"] for c in clips[:-1]]
    missing = sorted({c["source"] for c in clips if c.get("source") and not inside(ep_dir, c["source"]).is_file()})
    material = {"originals_missing": missing,
                "clean_voice": voice if voice and inside(ep_dir, voice).is_file() else None}

    ret_path = retention or default_retention(ep_dir)
    curve = read_retention(ret_path, duration) if ret_path else []
    ups = rises(curve)
    gfx = graphics(plan_data)
    sents = split_sentences(word_list)
    links, results = LINKS[lang], RESULT_WORDS.get(lang, RESULT_WORDS["en"])
    for s in sents:
        t = toks(s["text"])
        s["numbers"] = numbers_in(s["text"], lang)
        s["result"] = any(x in results for x in t)
        s["starts_with_link"] = bool(t) and t[0] in links
        s["graphics_full"] = covering(gfx, s["from"], s["to"])
        s["graphics"] = [g["id"] for g in s["graphics_full"]]
        s["rises"] = [r for r in ups if r["from"] < s["to"] and r["to"] > s["from"]]
        s["cut_boundaries"] = [round(b, 2) for b in bounds if s["from"] < b < s["to"]]
    length = [float(x) for x in (_pack_length() or [])[:2]]
    found = passages(sents, lo, hi, max_sentences, length, bounds, clips, missing)
    chosen = thin(found, limit)
    notes = []
    if not curve:
        notes.append("no retention curve: the list rests on the text alone (put review/retention.csv or .json in "
                     "the episode once the video is online)")
    if not plan_data:
        notes.append("no edit plan: graphics are unknown, so proof in the picture is not counted")
    if not clips:
        notes.append("no build record of the speaker cut: cut boundaries are unknown; `crewcut cut short` still "
                     "refuses a piece that crosses one")
    if missing:
        notes.append(f"originals missing ({', '.join(missing[:3])}): passages over them cannot become a Clip Short")
    if clips and not material["clean_voice"]:
        notes.append("no clean voice of the cut: the Short takes the camera sound with the voice filter")
    notes.append("each sentence can be its own piece, so a Short may join sentences from different places; a "
                 "piece may not cross a cut boundary (pieces_needed counts them)")
    for s in sents:
        s.pop("graphics_full", None)
    return {"episode": ep_dir.name, "version": version, "language": lang, "words": rel(ep_dir, Path(words)),
            "plan": rel(ep_dir, plan_path) if plan_path else None, "decisions": dec_rel,
            "retention": rel(ep_dir, ret_path) if ret_path else None, "duration": round(duration, 2),
            "rules": {"min_s": lo, "max_s": hi, "max_sentences": max_sentences, "pack_length_s": length},
            "material": material, "retention_rises": ups, "passages_found": len(found), "passages": chosen,
            "sentences": sents,
            "notes": notes}


def _pack_length() -> list | None:
    from .. import brand
    try:
        return brand.load().value("edit_style.shorts.length_s")
    except Exception:  # a broken pack must not stop the listing
        return None


def write(ep_dir: Path, r: dict) -> Path:
    out = ep_dir / "review" / f"short-candidates-{r['version']}.json"
    write_replace(out, json.dumps(r, ensure_ascii=False, indent=1) + "\n")
    return out


def describe(r: dict) -> str:
    lines = [f"{len(r['sentences'])} sentences, {r['passages_found']} passages of {r['rules']['min_s']:g}-"
             f"{r['rules']['max_s']:g} s; the best {len(r['passages'])} without big overlaps:"]
    for p in r["passages"]:
        lines.append(f"  {p['from']:7.2f}-{p['to']:7.2f} ({p['seconds']:4.1f} s, sentences {p['sentences'][0]}-"
                     f"{p['sentences'][1]}, {p['pieces_needed']} piece(s), score {p['score']}) "
                     f"«{p['first_sentence'][:70]}»")
        lines.append(f"      {'; '.join(p['signals']) or 'no signal'}")
    lines += [f"note: {n}" for n in r["notes"]]
    return "\n".join(lines)
