"""Voice and structure checks for a script: does it sound like the reference speaker and follow the structure?

The style gate (crewcut/stylegate.py) adds these checks to the studio checker's result, in the checker's interface
(version 1), so they show, fail and go back to the Writer like any other check. They need a voice profile, written on
the host by `host/voice-profile.py` from the reference speaker's transcripts (docs/hormozi-voice.md):

    {"schema": 1, "script": {"lang": "de", "wpm": 178, "bullet_seconds": 12, "min_sentences": {"long": 12, "short": 5}},
     "targets": {"long": {"<metric>": {"min": …, "max": …, "severity": "error"|"hint"|"info", "why": "…"}},
                 "short": {…}},
     "reference": {"long_top": {"metrics": {"<metric>": {"median", "p25", "p75", "n"}}}, "short_top": {…}},
     "check_names": {"voice": "STIMME", "structure": "STRUKTUR"}, "lexicon": {…}}

Two families of checks:

- **Voice** (`<voice>:<metric>`, crewcut/voicemetrics.py): sentence length (median, 90th percentile, share of short
  sentences), numbers per minute and the time of the first number, "you" and "I" per 100 words, questions per minute,
  commands, filler words, transitions, unit length, each against its band. A band with severity "error" fails the
  check, "hint" only informs the Critic, "info" is not shown. Each failing check names the lines that break the band
  and a rewrite hint (`points`). Below `min_sentences` spoken sentences every voice check is a hint (too few to measure).
- **Structure** (`<structure>:<rule>`): long: the opening has proof, promise and plan and ends by about 0:35; a number
  or the promise starts before 0:20 (times estimated from the word position at the speaker's words per minute); every
  unit has a hook, a retain part and a reward; a reward at least every `reward_gap_s` seconds (default 45); no recap and
  no goodbye at the end; each new unit's hook opens a loop (a number, a question or a contrast). Short: sentence 1 is a
  case with a number and no question, proof by 0:15, a punch line of at most 8 words, no ask.

A cue sheet (crewcut/cuesheet.py) is read as it will be spoken: the fixed lines are sentences, every bullet takes
`bullet_seconds` of free speech and its numbers count. A full script is read above its line `---`.

Settings (`[style_gate]` in config/crewcut.toml or `script.style_gate` in the style pack): `voice` block (default when
a profile exists), hint (every finding is a hint) or off; `voice_profile`, the profile's path inside the studio.

Command: `crewcut voice check <file> [--format lang|short] [--json] [--profile FILE] [--mode block|hint]` (the Writer
runs it before the gate; it uses the studio's `voice` mode, so in hint mode every count is a hint and the exit is 0;
in block mode exit 1 when an error-severity check fails). `crewcut voice reading <file>` checks the reading version of
a script (crewcut/delivery.py).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from . import voicemetrics as vm

MODES = ("block", "hint", "off")
NAMES = {"voice": "VOICE", "structure": "STRUCTURE"}
SHORT_METRIC = {"sentence_words_median": "sentence length (median)", "sentence_words_p90": "long sentences (90 %)",
                "short_share": "short sentences (<= 8 words)", "numbers_per_minute": "numbers per minute",
                "first_number_s": "first number (s)", "you_per_100": "'you' per 100 words",
                "i_per_100": "'I' per 100 words", "questions_per_minute": "questions per minute",
                "imperative_share": "commands", "fillers_per_100": "filler words per 100 words",
                "transitions_per_minute": "counted transitions per minute",
                "unit_seconds_median": "unit length (s)", "words_per_minute": "words per minute",
                "sentence_words_p25": "sentence length (25 %)", "sentence_words_p75": "sentence length (75 %)"}
SPLITTERS = (", und ", ", denn ", ", weil ", ", aber ", ", dann ", ", also ", ", and ", ", because ", ", but ",
             ", so ", ", which ", " und ", " and ")


# ---- settings ------------------------------------------------------------------------------------------------------
def settings() -> dict:
    from . import stylegate
    cfg = stylegate.settings()
    mode = str(cfg.get("voice") or "block").lower()
    return {"voice": mode if mode in MODES else "block", "voice_profile": cfg.get("voice_profile")}


def profile_path(cfg: dict | None = None) -> Path | None:
    from . import paths
    cfg = cfg or settings()
    rel = cfg.get("voice_profile")
    if not rel:
        return None
    p = Path(str(rel)).expanduser()
    p = p if p.is_absolute() else paths.studio_root() / p
    return p if p.is_file() else None


def load_profile(p: Path) -> dict:
    data = json.loads(p.read_text(encoding="utf-8"))
    if data.get("schema") != 1 or not isinstance(data.get("targets"), dict):
        raise ValueError(f"{p.name}: not a voice profile (schema 1 with targets)")
    return data


# ---- reading a script ------------------------------------------------------------------------------------------------
@dataclass
class Spoken:
    """A script as it will be spoken: fixed sentences with estimated times, bullets as timed blocks."""
    sentences: list[vm.Sentence] = field(default_factory=list)
    bullets: list[dict] = field(default_factory=list)      # {"text", "line", "start", "end", "numbers", "unit"}
    units: list[dict] = field(default_factory=list)        # {"n", "start", "end", "hook", "punch", "bridge", ...}
    opening_end: float | None = None
    end: float = 0.0
    cue_sheet: bool = False
    excerpt: bool = False
    roles: dict[int, str] = field(default_factory=dict)    # id(sentence) -> fixed line role (cue sheets)


def _clean_line(s: str) -> str:
    s = re.sub(r"\[\[.*?\]\]", " ", s)
    s = re.sub(r"\[[^\]]*\]", " ", s)
    return " ".join(s.replace("**", "").replace("__", "").split())


def read_script(text: str, wpm: float) -> Spoken:
    top = re.split(r"(?m)^---\s*$", text, maxsplit=1)[0]
    lines = []
    for i, raw in enumerate(top.splitlines(), 1):
        s = raw.strip()
        if not s or s.startswith("#") or s.startswith("<!--"):
            continue
        letters = re.sub(r"[^A-Za-zÄÖÜäöüß]", "", s)
        if len(letters) > 3 and letters.upper() == letters:
            continue
        s = _clean_line(s)
        if s:
            lines.append((i, s))
    sents = vm.from_lines(lines, wpm)
    return Spoken(sentences=sents, end=sents[-1].end if sents else 0.0)


def read_cue_sheet(text: str, wpm: float, bullet_seconds: float, lex: dict) -> Spoken:
    from . import cuesheet
    sheet = cuesheet.parse(text)
    out = Spoken(cue_sheet=True)
    t = 0.0
    for part in sheet.parts:
        unit = None
        if part.kind == "unit":
            unit = {"n": part.number, "start": t, "end": t, "hook": None, "punch": None, "bridge": None,
                    "bullets": 0, "line": None}
            out.units.append(unit)
        for ln in part.lines:
            if ln.kind == "bullet":
                txt = " ".join(ln.groups) or ln.text
                b = {"text": ln.text, "line": ln.line, "start": t, "end": t + bullet_seconds,
                     "numbers": vm.numbers_in(txt, lex), "role": ln.role, "unit": part.number}
                out.bullets.append(b)
                t += bullet_seconds
                if unit:
                    unit["bullets"] += 1
                continue
            new = vm.from_text(ln.spoken, wpm, ln.line, t)
            for s in new:
                out.roles[id(s)] = ln.role
            out.sentences += new
            if new:
                t = new[-1].end
            if unit is not None and ln.role in ("hook", "punch", "bridge") and new:
                unit[ln.role] = {"text": ln.spoken, "line": ln.line, "start": new[0].start, "end": new[-1].end}
                if ln.role == "hook":
                    unit["line"] = ln.line
        if unit:
            unit["end"] = t
        if part.kind == "opening":
            out.opening_end = t
    out.end = t
    out.excerpt = sheet.part("close") is None
    return out


def read(path: Path, profile: dict) -> Spoken:
    from . import cuesheet
    sc = profile.get("script") or {}
    wpm = float(sc.get("wpm") or 160)
    text = path.read_text(encoding="utf-8")
    if cuesheet.is_cue_sheet(path, text):
        return read_cue_sheet(text, wpm, float(sc.get("bullet_seconds") or 12), _lex(profile))
    return read_script(text, wpm)


def _lex(profile: dict) -> dict:
    return vm.lexicon((profile.get("script") or {}).get("lang") or "en", profile.get("lexicon"))


# ---- helpers -------------------------------------------------------------------------------------------------------
def mmss(t: float) -> str:
    return f"{int(t // 60)}:{int(t % 60):02d}"


def where(s: vm.Sentence | None = None, line: int | None = None, t: float | None = None) -> str | None:
    if s is not None:
        line, t = s.line, s.start
    if line is None and t is None:
        return None
    return (f"Z{line} " if line else "") + (f"~{mmss(t)}" if t is not None else "")


def point(text: str, why: str, rewrite: str | None = None, s: vm.Sentence | None = None, line: int | None = None,
          t: float | None = None) -> dict:
    p = {"text": " ".join(str(text).split())[:300], "why": why, "wo": where(s, line, t)}
    if rewrite:
        p["rewrite"] = rewrite
    return p


def split_hint(text: str) -> str | None:
    """A long sentence split at its first joint (', und', ', denn', ', because' …) into two sentences."""
    low = text
    for j in SPLITTERS:
        k = low.find(j)
        if 12 < k < len(low) - 12:
            a, b = text[:k].rstrip(" ,"), text[k + len(j):].strip()
            word = j.strip(" ,")
            b = (word.capitalize() + " " + b) if word in ("denn", "weil", "aber", "because", "but") else \
                (b[:1].upper() + b[1:])
            return a.rstrip(".") + ". " + b
    return None


def without_fillers(text: str, lex: dict) -> str:
    out = text
    for f in sorted(lex["fillers"], key=len, reverse=True):
        out = re.sub(r"(?i)(?<![\w-])" + re.escape(f) + r"(?![\w-])\s*", "", out)
    return " ".join(out.replace(" ,", ",").split())


# ---- the checks ----------------------------------------------------------------------------------------------------
def _band(t: dict) -> str:
    lo, hi = t.get("min"), t.get("max")
    if lo is not None and hi is not None:
        return f"{lo} to {hi}"
    return f"at least {lo}" if lo is not None else f"at most {hi}" if hi is not None else "-"


def _metric_points(metric: str, value: float, t: dict, sp: Spoken, lex: dict, profile: dict) -> list[dict]:
    lo, hi = t.get("min"), t.get("max")
    low = lo is not None and value < lo
    S = sp.sentences
    wpm = float((profile.get("script") or {}).get("wpm") or 160)
    pts: list[dict] = []
    if metric in ("sentence_words_median", "sentence_words_p90", "sentence_words_p75") and not low:
        limit = hi if metric == "sentence_words_p90" else max(int(hi or 15) + 6, 18)
        for s in sorted([s for s in S if len(s.words) > limit], key=lambda s: -len(s.words))[:6]:
            pts.append(point(s.text, f"{len(s.words)} words; split it into two sentences (the reference speaker's "
                             f"long sentences end around {limit} words)", split_hint(s.text), s))
    elif metric == "sentence_words_median" and low:
        runs = [S[i] for i in range(len(S) - 2) if all(len(x.words) <= 5 for x in S[i:i + 3])]
        for s in runs[:4]:
            pts.append(point(s.text, "three very short sentences in a row; join two of them with a reason "
                             "('und', 'weil', 'denn' / 'and', 'because') so a chain builds before the punch", None, s))
    elif metric == "short_share" and low:
        for s in sorted(S, key=lambda s: -len(s.words))[:4]:
            pts.append(point(s.text, "too few short sentences: after a long chain put a punch of at most 8 words "
                             "(the result, the number, the verdict)", split_hint(s.text), s))
    elif metric == "short_share" and not low:
        runs = [S[i] for i in range(len(S) - 2) if all(len(x.words) <= 8 for x in S[i:i + 3])]
        for s in runs[:4]:
            pts.append(point(s.text, "a run of short sentences reads as staccato; build one longer chain with a "
                             "reason before the next punch", None, s))
    elif metric == "numbers_per_minute" and low:
        if sp.cue_sheet:
            for u in sp.units:
                h = u.get("hook")
                if h and not vm.numbers_in(h["text"], lex):
                    pts.append(point(h["text"], "the hook has no number; put the unit's measured number into it "
                                     "(numbers only from the test)", None, line=h["line"], t=h["start"]))
        if not pts:
            for s in [s for s in S if not vm.numbers_in(s.text, lex)][:4]:
                pts.append(point(s.text, "no number nearby; say the measured number here (only from the material)",
                                 None, s))
    elif metric == "numbers_per_minute":
        for s in [s for s in S if len(vm.numbers_in(s.text, lex)) >= 3][:4]:
            pts.append(point(s.text, "three or more numbers in one sentence; keep one, show the rest on screen",
                             None, s))
    elif metric == "first_number_s" and not low:
        n = int((hi or 20) * wpm / 60)
        for s in S[:3]:
            pts.append(point(s.text, f"the first number comes too late; a number belongs in the first {hi} s, that is "
                             f"within about the first {n} spoken words", None, s))
    elif metric == "you_per_100" and low:
        cand = [s for s in S if re.search(r"\b(man|one)\b", s.text, re.I)] or \
               [s for s in S if set(s.words) & lex["i"] and not set(s.words) & lex["you"]]
        for s in cand[:5]:
            pts.append(point(s.text, "speak to the viewer: say what this means for them ('du' / 'you'), not "
                             "'man' or only 'ich'", None, s))
    elif metric == "imperative_share" and not low:
        for s in [s for s in S if vm.imperative(s, lex)][:4]:
            pts.append(point(s.text, "a command; tell the result of the test instead and keep at most one advice "
                             "line", None, s))
    elif metric == "fillers_per_100" and not low:
        for s in [s for s in S if vm.fillers(s.text, lex)][:6]:
            pts.append(point(s.text, "filler words; the speaker adds them by himself, the script does not",
                             without_fillers(s.text, lex), s))
    elif metric == "questions_per_minute" and low:
        for u in sp.units[:-1]:
            if not u.get("bridge"):
                pts.append(point(f"unit {u['n']} has no bridge", "a real question the next hook answers keeps the "
                                 "loop open", None, line=u.get("line"), t=u["end"]))
    return pts[:6]


def voice_checks(sp: Spoken, fmt: str, profile: dict, prefix: str) -> list[dict]:
    targets = (profile.get("targets") or {}).get("short" if fmt == "short" else "long") or {}
    lex = _lex(profile)
    if not sp.sentences:
        return []
    m = vm.measure(sp.sentences, (profile.get("script") or {}).get("lang"), profile.get("lexicon"))
    minutes = max(sp.end / 60.0, 1e-6)
    if sp.cue_sheet:   # the bullets are spoken too: their numbers and their time count
        nums = sum(len(vm.numbers_in(s.text, lex)) for s in sp.sentences) + sum(len(b["numbers"]) for b in sp.bullets)
        m["numbers_per_minute"] = nums / minutes
        firsts = [b["start"] for b in sp.bullets if b["numbers"]]
        if m.get("first_number_s") is not None:
            firsts.append(m["first_number_s"])
        m["first_number_s"] = min(firsts) if firsts else None
        m["words_per_minute"] = None
        trans = vm.transitions(sp.sentences, lex)
        m["transitions_per_minute"] = len(trans) / minutes
        lens = [u["end"] - u["start"] for u in sp.units]
        m["unit_seconds_median"] = sorted(lens)[len(lens) // 2] if lens else None
    small = len(sp.sentences) < int(((profile.get("script") or {}).get("min_sentences") or {}).get(
        "short" if fmt == "short" else "long", 12 if fmt != "short" else 5))
    ref = (profile.get("reference") or {}).get("short_top" if fmt == "short" else "long_top", {}).get("metrics", {})
    out = []
    for metric, t in targets.items():
        if not isinstance(t, dict) or t.get("severity") == "info" or metric not in m:
            continue
        v = m.get(metric)
        if v is None:
            if metric == "first_number_s" and t.get("max") is not None:
                v = float("inf")
            else:
                continue
        lo, hi = t.get("min"), t.get("max")
        ok = (lo is None or v >= lo) and (hi is None or v <= hi)
        r = ref.get(metric) or {}
        refs = f"; reference median {r.get('median')} ({r.get('p25')} to {r.get('p75')})" if r else ""
        hint = t.get("severity") != "error" or small
        if hint and ok:
            continue   # a hint inside its band says nothing
        c = {"id": f"{prefix}:{metric}", "rule": prefix, "kind": "hinweis" if hint else "auto",
             "titel": SHORT_METRIC.get(metric, metric),
             "measured": ("none" if v == float("inf") else round(v, 2) if isinstance(v, float) else v),
             "target": _band(t) + refs, "pass": None if hint else ok, "line": None, "fix": None, "alt": "neu"}
        if hint:
            c["frage"] = (("Too few spoken sentences to measure; " if small else "")
                          + f"{'outside' if not ok else 'inside'} the band: {t.get('why') or ''}").strip()
        if not ok:
            pts = _metric_points(metric, v, t, sp, lex, profile)
            c["points"] = pts
            c["line"] = pts[0].get("wo") if pts else None
            if not hint:
                c["fix"] = (f"Bring {SHORT_METRIC.get(metric, metric)} into {_band(t)}: " + (t.get("why") or "")
                            + (" Lines: " + " | ".join(f"\"{p['text'][:80]}\"" + (f" -> {p['rewrite']}" if p.get(
                                "rewrite") else "") for p in pts[:4]) if pts else ""))[:900]
        out.append(c)
    return out


def _has(rx: str, text: str, lex: dict) -> bool:
    return bool(lex["_" + rx].search(" ".join(vm.words(text))))


def _check(prefix: str, rid: str, titel: str, ok: bool, measured, target: str, pts: list[dict], fix: str,
           hint: bool = False) -> dict:
    c = {"id": f"{prefix}:{rid}", "rule": prefix, "kind": "hinweis" if hint else "auto", "titel": titel,
         "measured": measured, "target": target, "pass": None if hint else ok, "line": None, "fix": None,
         "alt": "neu"}
    if not ok:
        c["points"] = pts
        c["line"] = pts[0].get("wo") if pts else None
        if not hint:
            c["fix"] = (fix + (" Lines: " + " | ".join(f"\"{p['text'][:80]}\"" for p in pts[:4]) if pts else ""))[:900]
        else:
            c["frage"] = fix
    return c


def structure_long(sp: Spoken, profile: dict, prefix: str) -> list[dict]:
    lex = _lex(profile)
    S = sp.sentences
    if not S:
        return []
    sc = profile.get("script") or {}
    wpm = float(sc.get("wpm") or 160)
    out = []
    # 1. the opening: proof, promise, plan, by about 0:35
    limit = float(sc.get("opening_s") or 35)
    if sp.cue_sheet:
        op = [s for s in S if s.end <= (sp.opening_end or 0) + 0.01]
    else:
        op = [s for s in S if s.start < limit]
    roles = {sp.roles.get(id(s)) for s in op}
    proof = any(vm.numbers_in(s.text, lex) or _has("proof", s.text, lex) for s in op) or "proof" in roles
    promise = any(_has("promise", s.text, lex) for s in op) or "promise" in roles
    plan = any(_has("plan", s.text, lex) for s in op) or (
        "plan" in roles and any(vm.numbers_in(s.text, lex) or _has("plan", s.text, lex)
                                for s in op if sp.roles.get(id(s)) == "plan"))
    end_op = sp.opening_end if sp.cue_sheet else max((s.end for s in op if _has("plan", s.text, lex)), default=None)
    missing = [w for w, ok in (("proof", proof), ("promise", promise), ("plan with a count", plan)) if not ok]
    late = end_op is not None and end_op > limit
    out.append(_check(prefix, "intro", "opening: proof, promise, plan by ~0:35",
                      not missing and not late,
                      ("missing: " + ", ".join(missing) if missing else "proof, promise, plan")
                      + (f"; the opening ends at ~{mmss(end_op)}" if end_op is not None else ""),
                      f"proof, promise and plan, opening done by 0:{int(limit):02d}",
                      [point(op[-1].text if op else S[0].text,
                             "the opening needs " + (", ".join(missing) if missing else "to be shorter")
                             + f": one sentence each, done by about {int(limit)} s ({int(limit * wpm / 60)} words)",
                             None, op[-1] if op else S[0])],
                      "Write the opening as proof (the test with a number), promise (what the viewer has at the end) "
                      "and plan (the count of points), in about 30 seconds."))
    # 2. a number or the promise starts before 0:20
    win = float(sc.get("number_window_s") or 20)
    first = next((s for s in S if vm.numbers_in(s.text, lex) or _has("promise", s.text, lex)), None)
    tfirst = first.start if first else None
    if sp.cue_sheet:
        tb = next((b["start"] for b in sp.bullets if b["numbers"]), None)
        if tb is not None and (tfirst is None or tb < tfirst):
            tfirst = tb
    bg = [s for s in S if s.start < win and _has("background", s.text, lex)]
    ok = tfirst is not None and tfirst <= win and not bg
    out.append(_check(prefix, "window", f"number or promise by 0:{int(win):02d}, no background",
                      ok, (f"first at ~{mmss(tfirst)}" if tfirst is not None else "none") + (
                          f", {len(bg)} background sentence(s)" if bg else ""),
                      f"by 0:{int(win):02d} (about word {int(win * wpm / 60)} at {wpm:g} words per minute)",
                      [point(s.text, "background before the first result; cut it or move it into the unit that needs "
                             "it", None, s) for s in bg[:2]] or [point(S[0].text, f"put a measured number or the "
                                                                     f"promise into the first {int(win)} s", None, S[0])],
                      "Put a measured number or the promise into the first 20 seconds; no background there."))
    # 3. units: hook, retain, reward; 4. reward cadence; 6. loops
    units = sp.units if sp.cue_sheet else _script_units(S, lex)
    bad, loops = [], []
    for _k, u in enumerate(units):
        hook, punch = u.get("hook"), u.get("punch")
        retain = u.get("bullets", 0) > 0 if sp.cue_sheet else u.get("sentences", 0) >= 3
        if not (hook and retain and punch):
            miss = [w for w, ok in (("hook", hook), ("retain", retain), ("reward", punch)) if not ok]
            bad.append(point(f"unit {u['n']}: " + ((hook or {}).get("text") or "")[:120],
                             "missing " + ", ".join(miss) + ": a hook that opens a question, what is shown (one "
                             "example), and a short punch line that answers the hook", None,
                             line=u.get("line"), t=u.get("start")))
        if hook:
            txt = re.sub(r"(?i)^\s*(punkt|nummer|number|point)\s+\w+[.:,]?\s*", "", hook["text"])
            opens = (vm.numbers_in(txt, lex) or txt.rstrip().endswith("?") or _has("contrast", txt, lex))
            if not opens:
                loops.append(point(hook["text"], "the hook only names the topic; give it a number, a contrast or a "
                                   "question the unit answers (label hooks lost viewers in the retention data)",
                                   None, line=hook.get("line"), t=hook.get("start")))
        b = u.get("bridge")
        if b and not b["text"].rstrip().endswith("?"):
            loops.append(point(b["text"], "a bridge is a real question the next hook answers, or nothing", None,
                               line=b.get("line"), t=b.get("start")))
    if units:
        out.append(_check(prefix, "units", "every unit: hook, retain, reward", not bad,
                          f"{len(units)} units, {len(bad)} incomplete", "hook, retain and reward in each unit", bad,
                          "Build every unit like a Short: hook, what is shown, punch line."))
        out.append(_check(prefix, "loops", "each hook opens a loop", not loops,
                          f"{len(loops)} hook(s) or bridge(s) without an open loop", "a number, a contrast or a "
                          "question in every hook; bridges are questions", loops,
                          "Give every hook a number, a contrast or a question; a bridge is a question or nothing."))
    else:
        out.append(_check(prefix, "units", "counted units", False, "no counted units",
                          "counted units ('Punkt eins' / 'number one')",
                          [point(S[min(len(S) - 1, 3)].text, "count the units out loud so the viewer knows where "
                                 "he is", None, S[min(len(S) - 1, 3)])],
                          "Count the units out loud and build each as hook, retain, reward."))
    gap_max = float(sc.get("reward_gap_s") or 45)
    events = sorted(_rewards(sp, units, lex))
    start = sp.opening_end if sp.cue_sheet and sp.opening_end else (S[0].start if S else 0.0)
    stop = (units[-1]["end"] if units else sp.end) if not sp.excerpt else sp.end
    gaps, prev = [], start
    for t in [e for e in events if start <= e <= stop] + [stop]:
        if t - prev > gap_max:
            gaps.append((prev, t))
        prev = max(prev, t)
    gpts = []
    for a, b in gaps[:4]:
        s = next((x for x in S if x.start >= a), S[-1])
        gpts.append(point(s.text, f"{b - a:.0f} s from ~{mmss(a)} to ~{mmss(b)} without a reward (a number, a proof "
                          "on screen or a punch line)", None, s))
    out.append(_check(prefix, "rewards", f"a reward at least every {int(gap_max)} s", not gaps,
                      f"{len(gaps)} gap(s) over {int(gap_max)} s" if gaps else "no long gap",
                      f"a reward about every 30 s, no gap over {int(gap_max)} s", gpts,
                      "Put a reward into the gap: a measured number, a proof on screen or a punch line."))
    # 5. no recap, no goodbye at the end
    if not sp.excerpt:
        tail = [s for s in S if s.end > sp.end - 60]
        bad_end = [s for s in tail if _has("recap", s.text, lex) or _has("goodbye", s.text, lex)]
        out.append(_check(prefix, "ending", "no recap, no goodbye", not bad_end, len(bad_end),
                          "0 recap or goodbye sentences in the last 60 s",
                          [point(s.text, "cut it: the video ends with the verdict, then at most one link sentence",
                                 None, s) for s in bad_end],
                          "End with the verdict that picks up sentence 1; no recap, no goodbye."))
    return out


def _script_units(S: list[vm.Sentence], lex: dict) -> list[dict]:
    tr = vm.transitions(S, lex)
    units = []
    for k, s in enumerate(tr):
        nxt = tr[k + 1].start if k + 1 < len(tr) else S[-1].end + 1
        body = [x for x in S if s.start <= x.start < nxt]
        hook = s
        if len(s.words) <= 3 and len(body) > 1:   # "Punkt eins." alone: the hook is the sentence after it
            hook = body[1]
        half = body[len(body) // 2:]
        punch = next((x for x in reversed(half) if len(x.words) <= 10 and x is not hook and x is not s), None)
        units.append({"n": k + 1, "start": s.start, "end": body[-1].end if body else s.end,
                      "hook": {"text": hook.text, "line": hook.line, "start": hook.start},
                      "punch": {"text": punch.text, "line": punch.line, "start": punch.start} if punch else None,
                      "bridge": None, "sentences": len(body), "line": s.line})
    return units


def _rewards(sp: Spoken, units: list[dict], lex: dict) -> list[float]:
    ev = [u["punch"]["start"] for u in units if u.get("punch")]
    ev += [b["start"] for b in sp.bullets if b["numbers"] or b["role"] in ("proof", "beleg", "zahl", "number",
                                                                          "rechnung", "calculation")]
    ev += [s.start for s in sp.sentences if vm.numbers_in(s.text, lex)]
    if not sp.cue_sheet:
        ev += [s.start for s in sp.sentences if len(s.words) <= 8]
    return ev


def structure_short(sp: Spoken, profile: dict, prefix: str) -> list[dict]:
    lex = _lex(profile)
    S = sp.sentences
    if not S:
        return []
    s1, last = S[0], S[-1]
    out = []
    ok = bool(vm.numbers_in(s1.text, lex)) and not s1.question
    out.append(_check(prefix, "case", "sentence 1: the own case with a number", ok,
                      ("question" if s1.question else "no number") if not ok else "case with a number",
                      "a number in sentence 1, no question",
                      [point(s1.text, "start with your own case and its number (who, number, problem); never a "
                             "question", None, s1)], "Sentence 1 is the own case with a number, in first person."))
    proof = next((s for s in S if s.start <= 15 and (vm.numbers_in(s.text, lex) or _has("proof", s.text, lex))
                  and s is not s1), None) or next((b for b in sp.bullets if b["start"] <= 15), None)
    out.append(_check(prefix, "proof", "proof by 0:15", proof is not None, "found" if proof else "none",
                      "a proof (number or what is on screen) by 0:15",
                      [point(S[min(1, len(S) - 1)].text, "show the proof right after sentence 1", None,
                             S[min(1, len(S) - 1)])], "Show the proof fast, by 0:15."))
    ok = len(last.words) <= 8 and not last.question
    out.append(_check(prefix, "punch", "a punch line at the end (<= 8 words, no question)", ok,
                      f"{len(last.words)} words" + (", a question" if last.question else ""), "at most 8 words",
                      [point(last.text, "end with a short punch line: the result in a few words", None, last)],
                      "End with a punch line of at most 8 words, no question."))
    asks = [s for s in S if _has("ask", s.text, lex)]
    out.append(_check(prefix, "no-ask", "no ask in a Short", not asks, len(asks), "0 asks",
                      [point(s.text, "cut the ask: a Short gives, it does not ask", None, s) for s in asks],
                      "No subscribe, no link, no comment request in a Short."))
    return out


def checks(path: Path, fmt: str, profile: dict, mode: str = "block") -> list[dict]:
    """The voice and structure checks of one file, in the checker interface (version 1)."""
    if mode == "off":
        return []
    names = {**NAMES, **(profile.get("check_names") or {})}
    sp = read(path, profile)
    out = voice_checks(sp, fmt, profile, names["voice"])
    out += structure_short(sp, profile, names["structure"]) if fmt == "short" else \
        structure_long(sp, profile, names["structure"])
    if mode == "hint":
        for c in out:
            if c["kind"] == "auto":
                c.update({"kind": "hinweis", "frage": c.get("fix") or c.get("titel"), "pass": None, "fix": None})
    return out


def for_gate(path: Path, fmt: str, cfg: dict | None = None) -> list[dict]:
    """What the style gate adds to a checker result. Never raises: a broken profile becomes one hint."""
    try:
        cfg = cfg or settings()
        if cfg.get("voice") == "off" or Path(path).suffix.lower() not in (".md", ".txt"):
            return []   # a words file of a recording is not a script
        p = profile_path(cfg)
        if p is None:
            return []
        return checks(path, fmt, load_profile(p), cfg.get("voice") or "block")
    except Exception as e:  # noqa: BLE001 - the voice check must never stop the studio's own gate
        return [{"id": "VOICE:profile", "rule": "VOICE", "kind": "hinweis", "titel": "voice profile",
                 "measured": f"not usable: {e}"[:300], "target": "a readable profile", "pass": None, "line": None,
                 "fix": None, "frage": "The voice check could not run; check the profile path in [style_gate]."}]


def prompt_lines() -> str:
    """For the Writer: where the profile is and how to run the check."""
    p = profile_path()
    if p is None:
        return ""
    if settings()["voice"] != "block":
        return (f"Voice profile: {p} (the reference speaker's measured voice). In this studio its counts are hints for "
                "the Critic, never a target and never a failure: do not add, cut or bend a sentence to hit a number "
                "(sentence length, short sentences, numbers per minute, 'you' per 100 words).")
    return (f"Voice profile: {p} (the reference speaker's measured voice and the target bands for this channel). "
            "Run `crewcut voice check <script>` before you end a draft: its voice and structure checks are part of "
            "the style gate and every failing line comes back to you.")


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="crewcut voice", description="Voice and structure checks against a profile.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="check a script or a cue sheet")
    c.add_argument("file")
    c.add_argument("--format", choices=["lang", "short"])
    c.add_argument("--profile", help="the profile file (default: [style_gate] voice_profile)")
    c.add_argument("--json", action="store_true")
    c.add_argument("--mode", choices=["block", "hint"], help="default: the studio's [style_gate] voice")
    from . import delivery
    delivery.add_parser(sub)
    return ap


def main(argv: list[str] | None = None) -> int:
    a = _parser().parse_args(argv)
    if a.cmd == "reading":
        from . import delivery
        return delivery.cli(a.file, a.script, a.json)
    p = Path(a.profile) if a.profile else profile_path()
    if p is None or not p.is_file():
        print("No voice profile: set [style_gate] voice_profile or pass --profile.", file=sys.stderr)
        return 2
    path = Path(a.file)
    if not path.is_file():
        print(f"{path} not found.", file=sys.stderr)
        return 2
    prof = load_profile(p)
    fmt = a.format or ("short" if re.match(r"(?i)^short", path.name) else "lang")
    mode = a.mode or ("hint" if settings()["voice"] == "hint" else "block")
    res = checks(path, fmt, prof, mode)
    failed = [x for x in res if x["pass"] is False]
    if a.json:
        print(json.dumps({"version": 1, "file": str(path), "format": fmt, "profile": str(p), "mode": mode,
                          "pass": not failed, "checks": res}, ensure_ascii=False, indent=1))
    else:
        for x in res:
            state = {True: "PASS", False: "FAIL", None: "HINT"}[x["pass"]]
            print(f"{state:5s} {x['id']}: {x['measured']} (target {x['target']})")
            for pt in (x.get("points") or [])[:6] if x["pass"] is not True else []:
                print(f"        {pt.get('wo') or ''} \"{pt['text'][:110]}\" : {pt['why']}"
                      + (f"\n          -> {pt['rewrite']}" if pt.get("rewrite") else ""))
        print(f"{len(failed)} failed." + (" Mode hint: every count is a hint for the Critic, never a target."
                                          if mode == "hint" else ""))
    return 1 if failed else 0


__all__ = ["checks", "for_gate", "load_profile", "main", "profile_path", "prompt_lines", "read", "settings"]


if __name__ == "__main__":
    sys.exit(main())
