"""Motion density of an edit plan: the counts of the motion plan's density rules (not overloaded) and the length
limits of motion inserts. Pure Python (json and re only), so the check scripts in ``skills/cut-check`` can import it.

Limits come from the style pack's ``edit-style.json`` ``motion`` block when it has one, else the neutral numbers
below. ``speaker_min_seconds``, ``speaker_open_close_seconds``, ``keywords_max`` and ``shorts.end_face_s`` are the
pack's existing values.

A motion insert in the plan: ``{"id", "kind": "motion", "scene": "<template>" | "source": "motion/<id>/comp.jsx",
"start", "end", "transparent", "data", "cues", ...}``. ``start`` and ``end`` are seconds or a word anchor
``{"word": "costs", "offset": -0.6, "after": 10.0}`` resolved through the plan's words file.

Findings are dicts ``{"level", "id", "text", "time", "fix"}`` with the levels of the check scripts
(ERROR, CHECK, NOTE, OK).
"""

from __future__ import annotations

import copy
import re
from typing import Any

HEROES = ("big_claim", "card_gallery", "ranking")
KEYWORD_SCENES = ("keyword", "keyword_pop")

NEUTRAL: dict[str, Any] = {
    "insert_s": [3.0, 6.0],            # full-frame motion insert length
    "insert_long_s": 8.0,              # ranking and explainers ("explainer": true in data) may run this long
    "overlay_min_s": 1.5,              # nothing enters and leaves within 1 s
    "template_min_s": {"keyword_pop": 1.5, "lower_third": 3.0, "number_roll": 3.0, "prompt_bar": 3.0,
                       "word_reel": 3.0, "quote": 4.0},
    "template_max_s": {"prompt_bar": 6.0, "ranking": 8.0},
    "per_sentence_max": 1,             # motion per sentence (overlay or insert, never both)
    "big_moments": [3, 5],             # full-frame motion inserts per video
    "big_per_minute_max": 1.0,         # long videos: at most 1 big moment per minute
    "per_minute_max": 2.0,             # all motion, overlays included, on average
    "min_gap_s": 6.0,                  # never 2 motion starts inside 6 s
    "heroes": list(HEROES),
    "heroes_max": 2,                   # each hero once per video, at most 2 in total
    "sounds_per_motion_max": 1,
    "shorts": {"big_max": 2, "total": [3, 5], "heroes_max": 1},
}


def _merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        elif v is not None:
            out[k] = v
    return out


def limits(edit_style: dict | None) -> dict:
    """The motion limits: the pack's ``motion`` block over the neutral numbers, plus the pack values the rules use."""
    es = edit_style or {}
    block = es.get("motion") if isinstance(es.get("motion"), dict) else {}
    L = _merge(NEUTRAL, block)
    L["source"] = "edit-style.json motion" if block else "neutral numbers (no motion block in edit-style.json)"
    shorts = es.get("shorts") or {}
    L["speaker_min_s"] = float(es.get("speaker_min_seconds") or 2.0)
    L["open_close_s"] = float(es.get("speaker_open_close_seconds") or 3.0)
    L["end_face_s"] = float(shorts.get("end_face_s") or 2.0)
    L["keywords_max"] = es.get("keywords_max")
    mix = es.get("graphics_mix") or {}
    L["mix_motion"] = mix.get("motion")
    return L


# ---------------------------------------------------------------- words and times


def normalize(word: Any) -> str:
    """Lower case, punctuation at both ends removed: 'Thirty,' -> 'thirty' (as in crewcut.render.plan)."""
    return re.sub(r"^[\W_]+|[\W_]+$", "", str(word).strip().lower())


def norm_words(raw: Any) -> list[dict]:
    """Words as ``[{"w", "s", "e"}]`` from the usual shapes (w/s/e, word/start/end, text/start, caption groups)."""
    if isinstance(raw, dict):
        raw = raw.get("words") or raw.get("segments") or []
    out: list[dict] = []
    for w in raw or []:
        if not isinstance(w, dict):
            continue
        if isinstance(w.get("words"), list):
            out += norm_words(w["words"])
            continue
        text = w.get("w", w.get("word", w.get("text")))
        start = w.get("s", w.get("start"))
        if text is None or start is None:
            continue
        end = w.get("e", w.get("end", start))
        out.append({"w": str(text), "s": float(start), "e": float(end if end is not None else start)})
    return sorted(out, key=lambda x: x["s"])


def word_time(words: list[dict], word: str, after: float = 0.0) -> float | None:
    """Start of the first occurrence of a word or phrase at or after ``after`` seconds (None when not found)."""
    want = [t for t in (normalize(x) for x in str(word).split()) if t]
    if not want:
        return None
    for i, w in enumerate(words):
        if w["s"] < after - 0.05:
            continue
        if all(i + k < len(words) and normalize(words[i + k]["w"]) == t for k, t in enumerate(want)):
            return w["s"]
    return None


def seconds(v: Any, words: list[dict], after: float = 0.0) -> float | None:
    """A plan time as seconds: a number, ``{"word", "offset", "after"}`` or ``{"time", "offset"}``; None if unknown."""
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, dict):
        off = float(v.get("offset") or 0.0)
        if "word" in v:
            t = word_time(words, v["word"], float(v["after"]) if v.get("after") is not None else after)
            return None if t is None else t + off
        if "time" in v:
            return float(v["time"]) + off
    return None


def span(e: dict, words: list[dict]) -> tuple[float | None, float | None]:
    """Start and end of an insert in seconds (None where a word anchor cannot be resolved)."""
    s = seconds(e.get("start"), words, 0.0)
    t = seconds(e.get("end"), words, s or 0.0)
    return s, t


def cue_seconds(e: dict, words: list[dict], start: float) -> dict[str, float]:
    """Cues of a motion insert as seconds local to the insert (the way templates get them)."""
    out: dict[str, float] = {}
    for name, c in (e.get("cues") or {}).items():
        if isinstance(c, dict) and ("word" in c or "time" in c):
            t = seconds(c, words, start)
            if t is not None:
                out[str(name)] = round(t - start, 4)
        elif isinstance(c, (int, float)) and not isinstance(c, bool):
            out[str(name)] = float(c)       # already local seconds
    return out


def sentences(words: list[dict]) -> list[tuple[float, float]]:
    """Sentence spans (start of the first word, start of the next sentence) from the words file."""
    out: list[tuple[float, float]] = []
    start = None
    for i, w in enumerate(words):
        if start is None:
            start = w["s"]
        if re.search(r"[.?!]['\")\]]*$", w["w"].strip()) or i == len(words) - 1:
            nxt = words[i + 1]["s"] if i + 1 < len(words) else w["e"] + 0.01
            out.append((start, nxt))
            start = None
    return out


def tc(t: float | None) -> str:
    if t is None:
        return "-"
    m, s = divmod(max(0.0, float(t)), 60)
    return f"{int(m)}:{s:04.1f}"


# ---------------------------------------------------------------- the counts


def _sound_refs(plan: dict) -> dict[str, int]:
    """Sound events in the plan per insert id (``sound.hits/typing/whooshes`` hold "id" or "id@cue")."""
    out: dict[str, int] = {}
    snd = plan.get("sound") or {}
    for key in ("hits", "typing", "whooshes"):
        for ref in snd.get(key) or []:
            if isinstance(ref, str):
                iid = ref.partition("@")[0]
                out[iid] = out.get(iid, 0) + 1
    return out


def _keyword_count(e: dict) -> int:
    d = e.get("data") or {}
    if e.get("kind") == "motion":
        return 1 if e.get("scene") == "keyword_pop" else 0
    if e.get("scene") == "keyword" or (e.get("transparent") and e.get("kind") == "2d"):
        n = 1 if isinstance(d.get("text"), str) else 0
        return n + len(d.get("words") or [])
    return 0


def count(plan: dict, words: list[dict], L: dict, template_sounds: dict[str, int] | None = None,
          total_s: float | None = None) -> dict:
    """The density report of a plan: counts, lengths, gaps, sentences, findings. ``template_sounds`` maps a
    scene to the number of ``@sounds`` of its template (they become sound events when the insert says
    ``"sound": true``)."""
    fmt = plan.get("format") or "landscape"
    short = fmt == "portrait"
    found: list[dict] = []
    skipped: list[str] = []

    def add(level: str, cid: str, text: str, t: float | None = None, fix: str | None = None) -> None:
        found.append({"level": level, "id": cid, "text": text, "time": t, "fix": fix})

    every = []
    for e in plan.get("inserts") or []:
        if not isinstance(e, dict):
            continue
        s, t = span(e, words)
        if s is None or t is None:
            if e.get("kind") == "motion":
                skipped.append(f"{e.get('id')}: start or end is a word that is not in the words file")
                add("CHECK", f"motion-time:{e.get('id')}",
                    f"{e.get('id')}: start or end cannot be resolved (word anchor without a words file or word "
                    "missing); left out of the counts", fix="Give seconds or fix the word anchor")
            continue
        every.append({"id": str(e.get("id")), "kind": e.get("kind"), "scene": e.get("scene"),
                      "source": e.get("source"), "start": s, "end": t, "full": not e.get("transparent"),
                      "raw": e})
    every.sort(key=lambda x: x["start"])
    motion = [x for x in every if x["kind"] == "motion"]
    big = [x for x in motion if x["full"]]
    overlays = [x for x in motion if not x["full"]]
    ends = [x["end"] for x in every] + [w["e"] for w in words[-1:]]
    if total_s is None:
        total_s = max(ends or [0.0]) + float(plan.get("tail") or 0.0)
    minutes = total_s / 60.0 if total_s else 0.0

    # lengths (motion plan 2.2)
    lengths = []
    for x in motion:
        n = x["end"] - x["start"]
        tmin = L["template_min_s"].get(x["scene"] or "", None)
        if x["full"]:
            lo = max(L["insert_s"][0], tmin or 0.0)
            explainer = bool((x["raw"].get("data") or {}).get("explainer"))
            hi = L["template_max_s"].get(x["scene"] or "") or (L["insert_long_s"] if explainer else L["insert_s"][1])
        else:
            lo, hi = max(L["overlay_min_s"], tmin or 0.0), None
        ok = n >= lo - 1e-6 and (hi is None or n <= hi + 1e-6)
        lengths.append({"id": x["id"], "kind": "full" if x["full"] else "overlay", "length": round(n, 3),
                        "min": lo, "max": hi, "ok": ok})
        if not ok:
            add("ERROR", f"motion-length:{x['id']}",
                f"{x['id']} ({x['scene'] or 'custom'}) runs {n:.1f} s; "
                + (f"{'full frame' if x['full'] else 'overlay'} needs {lo:g} to {hi:g} s" if hi
                   else f"an overlay needs at least {lo:g} s"),
                x["start"], fix="Lengthen, shorten or split the moment")

    # big moments
    if short:
        big_max = int(L["shorts"]["big_max"])
    else:
        big_max = int(L["big_moments"][1])
        if minutes > big_max:                       # long videos: at most 1 per minute
            big_max = int(minutes * L["big_per_minute_max"])
    if len(big) > big_max:
        add("ERROR", "motion-big", f"{len(big)} full-frame motion inserts (at most {big_max}"
            + (" in a Short)" if short else f" in {minutes:.1f} min)"), fix="Drop the weakest big moment")
    elif not short and motion and len(big) < L["big_moments"][0]:
        add("NOTE", "motion-big", f"{len(big)} full-frame motion inserts (usual {L['big_moments'][0]} to "
            f"{L['big_moments'][1]}); fine when the speaker carries the video")
    else:
        add("OK", "motion-big", f"{len(big)} full-frame motion inserts (at most {big_max})")

    # all motion
    if short:
        lo, hi = L["shorts"]["total"]
        motion_max = int(hi)
        lvl = "ERROR" if len(motion) > hi else ("NOTE" if len(motion) < lo else "OK")
        add(lvl, "motion-total", f"{len(motion)} motion moments in this Short (pack: {lo} to {hi})")
    else:
        limit = L["per_minute_max"] * minutes
        motion_max = int(limit + 1e-9)
        rate = len(motion) / minutes if minutes else 0.0
        add("ERROR" if len(motion) > limit + 1e-9 else "OK", "motion-rate",
            f"{len(motion)} motion moments in {minutes:.1f} min = {rate:.1f} per minute "
            f"(at most {L['per_minute_max']:g} on average)", fix="Cut motion where the speaker already carries it")
    gaps = []
    if not short:
        for a, b in zip(motion, motion[1:], strict=False):
            g = b["start"] - a["start"]
            if g < L["min_gap_s"] - 1e-9:
                gaps.append({"a": a["id"], "b": b["id"], "gap": round(g, 3)})
                add("ERROR", f"motion-gap:{a['id']}-{b['id']}",
                    f"{a['id']} and {b['id']} start {g:.1f} s apart (never 2 inside {L['min_gap_s']:g} s)",
                    b["start"], fix="Drop one, or move it to another sentence")

    # per sentence
    per_sentence = []
    if words:
        spans = sentences(words)
        for a, b in spans:
            inside = [x["id"] for x in motion if a - 0.05 <= x["start"] < b]
            if len(inside) > L["per_sentence_max"]:
                per_sentence.append({"start": a, "motions": inside})
                add("ERROR", f"motion-sentence:{tc(a)}",
                    f"{len(inside)} motion moments in the sentence at {tc(a)}: {', '.join(inside)} "
                    f"(at most {L['per_sentence_max']}, overlay or insert, never both)", a,
                    fix="Keep the one that carries the sentence")
    elif motion:
        skipped.append("motion per sentence: the plan has no words file")
        add("NOTE", "motion-sentence", "Motion per sentence not counted: the plan has no words file")

    # heroes
    heroes: dict[str, int] = {}
    for x in motion:
        if x["scene"] in L["heroes"]:
            heroes[x["scene"]] = heroes.get(x["scene"], 0) + 1
    hmax = int(L["shorts"]["heroes_max"] if short else L["heroes_max"])
    twice = [k for k, n in heroes.items() if n > 1]
    if twice or sum(heroes.values()) > hmax:
        add("ERROR", "motion-heroes",
            f"Hero templates {heroes} (each once per video, at most {hmax} in total)",
            fix="Keep the strongest hero; reuse the long video's hero in a Short")
    elif heroes:
        add("OK", "motion-heroes", f"Hero templates {heroes} (at most {hmax})")

    # speaker between full-frame parts (all kinds)
    full = sorted((x for x in every if x["full"]), key=lambda x: x["start"])
    between = []
    for a, b in zip(full, full[1:], strict=False):
        gap = b["start"] - a["end"]
        if 0 < gap < L["speaker_min_s"] - 1e-9 and (a["kind"] == "motion" or b["kind"] == "motion"):
            between.append({"after": a["id"], "before": b["id"], "seconds": round(gap, 3)})
            add("ERROR", f"motion-speaker:{a['id']}-{b['id']}",
                f"Speaker only {gap:.1f} s between {a['id']} and {b['id']} (at least {L['speaker_min_s']:g} s)",
                a["end"], fix="Join the two parts, or move the second one later")

    # sounds
    refs = _sound_refs(plan)
    sounds = {}
    for x in motion:
        n = refs.get(x["id"], 0)
        if x["raw"].get("sound") and template_sounds:
            n += int(template_sounds.get(x["scene"] or "", 0))
        sounds[x["id"]] = n
        if n > L["sounds_per_motion_max"]:
            add("ERROR", f"motion-sounds:{x['id']}",
                f"{x['id']} has {n} sounds (at most {L['sounds_per_motion_max']} per motion)", x["start"],
                fix="Keep the sound on the landing")
    pops = [x for x in motion if x["scene"] == "keyword_pop"]
    for a, b in zip(pops, pops[1:], strict=False):
        nothing_between = not any(a["start"] < y["start"] < b["start"] for y in motion)
        if nothing_between and sounds.get(a["id"]) and sounds.get(b["id"]):
            add("ERROR", f"motion-pop-sound:{b['id']}",
                f"{a['id']} and {b['id']}: two keyword_pop in a row with a sound", b["start"],
                fix="Take the sound off the second keyword_pop")

    # first and last seconds: the speaker alone
    oc = L["open_close_s"]
    tail = L["end_face_s"] if short else oc
    for x in motion:
        if x["start"] < oc - 1e-9:
            add("ERROR", f"motion-open:{x['id']}",
                f"{x['id']} starts at {x['start']:.1f} s; the first {oc:g} s show the speaker alone", x["start"])
        if total_s and x["end"] > total_s - tail + 1e-9:
            add("ERROR", f"motion-close:{x['id']}",
                f"{x['id']} ends at {x['end']:.1f} s; the last {tail:g} s show the speaker alone", x["start"])

    # keywords (keyword + keyword_pop together)
    kw = sum(_keyword_count(x["raw"]) for x in every)
    if L.get("keywords_max") is not None:
        add("CHECK" if kw > L["keywords_max"] else "OK", "motion-keywords",
            f"{kw} keywords (keyword + keyword_pop) over the speaker (at most {L['keywords_max']})")

    # mix (note only)
    full_time = sum(x["end"] - x["start"] for x in every if x["full"])
    motion_time = sum(x["end"] - x["start"] for x in big)
    share = motion_time / full_time if full_time else 0.0
    if L.get("mix_motion") is not None and full_time:
        add("NOTE", "motion-mix", f"Motion is {share:.0%} of the full-screen insert time "
            f"(pack graphics_mix motion: {L['mix_motion']:.0%})")

    return {
        "format": fmt, "short": short, "duration_s": round(total_s, 3), "minutes": round(minutes, 2),
        "limits": {k: v for k, v in L.items() if k != "source"}, "limits_from": L["source"],
        "counts": {"motion": len(motion), "big": len(big), "overlays": len(overlays), "heroes": heroes,
                   "per_minute": round(len(motion) / minutes, 2) if minutes else None, "keywords": kw,
                   "sounds": sounds, "motion_share_of_full": round(share, 3)},
        "max": {"big": big_max, "motion": motion_max, "heroes": hmax},
        "moments": [{"id": x["id"], "scene": x["scene"], "source": x["source"], "start": round(x["start"], 3),
                     "end": round(x["end"], 3), "full": x["full"]} for x in motion],
        "lengths": lengths, "gaps": gaps, "sentences": per_sentence, "speaker_between": between,
        "skipped": skipped, "findings": found,
    }


def neighbours(report: dict, iid: str, window: float) -> list[str]:
    """Motion moments that start within ``window`` seconds of moment ``iid``."""
    ms = {m["id"]: m for m in report.get("moments") or []}
    me = ms.get(iid)
    if not me:
        return []
    return [m["id"] for m in ms.values() if m["id"] != iid and abs(m["start"] - me["start"]) < window]
