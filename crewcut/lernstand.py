"""The learning loop: what the critics found, which units held viewers, which scripts passed, written into one file the
Writer reads before every script (docs/hormozi-voice.md).

`refresh()` reads the whole studio and writes the learning file (default `library/learnings/script-learning.md`,
`[style_gate] learning_file`):

1. **Most frequent findings** across all episodes, from the Critic's answers next to each script (`*.kritik.json`:
   sentences marked without value with their question id, unit questions answered no, yes-no questions answered no),
   the second opinion (`*.zweitmeinung.json`) and, for scripts without such a file, the review reports
   `review/critic-*.md` (rule ids in their lines). Grouped by question or rule id, counted, with one example and the
   best fix that worked (a later review marked the finding done, and how).
2. **Best and worst units** from `analytics/retention-units.json` of every episode (the newest measurement): units
   ranked by their drop per minute against the median unit of the same video, with the hook sentence. A unit is a
   model to copy only when its hook group has the status "lesson" (it holds in at least 3 episodes and loses in at
   most one, the rule of crewcut/youtube/units.py); every other unit is listed as "watch", never as a model.

Findings on a script that still had placeholders (`[ZAHL nach Test]`, showformats.placeholders) are not counted: they
come from gaps, not from mistakes.
3. **Gold candidates**: when the gate says ready, every passing script is copied into the gold folder
   (`[style_gate] gold_dir`) as `CANDIDATE-NNN-<episode>-<file>` (German studios: `KANDIDAT-…`) with a score file.
4. **Rule cards**: a finding group that reaches `rule_after` (default 3) findings gets one rule card through the
   approvals rule mechanism (`crewcut rule propose`), once; the state is kept next to the learning file (`.json`).

`prompt_top()` is the head of the file for the Writer's and the Critic's system prompt. Hooks: the style gate after
every round and when it passes (crewcut/stylegate.py), the retention units after every run (crewcut/youtube/units.py).

Command: `crewcut lernstand [--no-cards] [--print]` writes the file now.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import statistics as st
import sys
from datetime import UTC, datetime
from pathlib import Path

from . import paths

DEFAULT_FILE = "library/learnings/script-learning.md"
CODE = re.compile(r"\b(?:[A-Z]{1,3}-[A-Z]{0,3}\d+[a-z]?|K-[A-Z][A-Z0-9-]*|HB\d+[a-z]?|HR\d+[a-z]?|DH-[LVS]\d+)\b")
SCRIPT_NAME = re.compile(r"^(?P<kind>SCRIPT|SHORT|CUES|DREHZETTEL)-v(?P<n>\d+)(?P<rest>[^/]*?)$", re.I)
MARK = "<!-- lernstand -->"
NEGATIVE = re.compile(r"\b(nein|no|raus|streichen|gestrichen|ändern|fehlt|missing|cut|change|without value|ohne wert)\b",
                      re.I)
WRONG = re.compile(r"mislead|wrong|false|contradict|irreführ|falsch|widerspr|nahelegt|stimmt nicht|in die irre", re.I)


# ---- settings ------------------------------------------------------------------------------------------------------
def settings() -> dict:
    from . import config
    out = {"learning_file": DEFAULT_FILE, "gold_dir": None, "rule_after": 3, "rules_per_run": 2, "learning_labels": [],
           "learning_ignore": [], "companion_prefix": "LEARN-", "reference_moves": None, "voice_profile": None}
    try:
        from . import stylegate
        cfg = stylegate.settings()
    except Exception:  # noqa: BLE001 - settings must not fail the caller
        cfg = config.get("crewcut", "style_gate", {}) or {}
    for k in out:
        if cfg.get(k) is not None:
            out[k] = cfg[k]
    if isinstance(out["learning_labels"], str):
        out["learning_labels"] = [out["learning_labels"]]
    return out


def _studio_path(rel: str | None) -> Path | None:
    if not rel:
        return None
    p = Path(str(rel)).expanduser()
    return p if p.is_absolute() else paths.studio_root() / p


def learning_path(cfg: dict | None = None) -> Path:
    cfg = cfg or settings()
    return _studio_path(cfg.get("learning_file") or DEFAULT_FILE)


def german() -> bool:
    try:
        from . import brand
        return str(brand.load().value("channel.language", "") or "").lower().startswith("de")
    except Exception:  # noqa: BLE001
        return False


# ---- reading the findings ------------------------------------------------------------------------------------------
def _norm(text: str) -> str:
    return " ".join(re.sub(r"[^\w]+", " ", str(text or "").lower()).split())


def _version(name: str) -> tuple[str, int]:
    m = SCRIPT_NAME.match(name)
    return (m.group("kind").upper(), int(m.group("n"))) if m else (name, 0)


def _category(item: dict, fallback: str) -> str:
    q = item.get("pruefrage") or item.get("question") or item.get("rule")
    if q:
        m = CODE.search(str(q))
        return m.group(0) if m else str(q).split(";")[0].split(",")[0].strip()
    m = CODE.search(" ".join(str(item.get(k) or "") for k in ("grund", "why", "was", "text")))
    return m.group(0) if m else fallback


def _read_json(p: Path) -> dict:
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def findings(root: Path | None = None, ignore: list[str] | None = None) -> tuple[list[dict], list[dict]]:
    """All findings and all 'done' notes (a later review says how a finding was fixed)."""
    root = root or paths.studio_root()
    ignore = set(ignore or [])
    out, done = [], []
    eps = root / "episodes"
    for ep in sorted(eps.iterdir()) if eps.is_dir() else []:
        brief = ep / "brief"
        if not brief.is_dir():
            continue
        with_json = set()
        gaps = _placeholder_scripts(brief)
        for p in sorted(brief.glob("*.kritik.json")):
            stem = p.name[: -len(".kritik.json")]
            with_json.add(_version(stem))
            if stem in gaps:
                continue   # a review of a script with placeholders learns from gaps, not from mistakes
            d = _read_json(p)
            base = {"episode": ep.name, "file": f"brief/{stem}.md", "mtime": p.stat().st_mtime}
            for key, src in (("hormozi_kritik", "critic"), ("hormozi_kritik_frisch", "fresh critic"),
                             ("critic", "critic"), ("review", "critic")):
                hk = d.get(key)
                if not isinstance(hk, dict):
                    continue
                for s in hk.get("saetze") or hk.get("sentences") or []:
                    if isinstance(s, dict) and (s.get("wert") is False or s.get("value") is False):
                        cat = _category(s, "sentence without value")
                        if cat in ignore:
                            continue
                        out.append({**base, "source": src, "category": cat, "text": s.get("text") or "",
                                    "why": s.get("grund") or s.get("why") or "", "fix": s.get("neu") or s.get("rewrite")})
                for u in hk.get("einheiten") or hk.get("units") or []:
                    if not isinstance(u, dict):
                        continue
                    for flag, v in u.items():
                        if v is False and flag not in ignore:
                            out.append({**base, "source": src, "category": f"unit: {flag}",
                                        "text": f"unit {u.get('einheit') or u.get('unit')}: "
                                                + str(u.get("grund") or "")[:160],
                                        "why": "", "fix": None})
                video = hk.get("video") if isinstance(hk.get("video"), dict) else {}
                for flag, v in video.items():
                    if v is False and flag not in ignore:
                        out.append({**base, "source": src, "category": f"video: {flag}", "text": "the video",
                                    "why": video.get("grund") or "", "fix": None})
                for f in hk.get("vorherige_funde") or hk.get("earlier_findings") or []:
                    if isinstance(f, dict) and str(f.get("status", "")).lower() in ("erledigt", "done", "fixed"):
                        done.append({**base, "text": f.get("text") or "", "how": f.get("wie") or f.get("how") or ""})
            for k, v in d.items():
                if not re.match(r"^K-", k) or k in ignore:
                    continue
                a = v.get("antwort", v.get("answer")) if isinstance(v, dict) else v
                if a is False:
                    out.append({**base, "source": "critic question", "category": k, "text": k,
                                "why": (v.get("grund") or v.get("why") or "") if isinstance(v, dict) else "",
                                "fix": None})
        for p in sorted(brief.glob("*.zweitmeinung.json")) + sorted(brief.glob("*.second-opinion.json")):
            stem = p.name.split(".")[0]
            if stem in gaps:
                continue
            d = _read_json(p)
            for pt in d.get("points") or []:
                if isinstance(pt, dict) and pt.get("text"):
                    kind = ("second opinion: wrong or misleading" if WRONG.search(str(pt.get("why") or ""))
                            else "second opinion: unclear or not needed")
                    out.append({"episode": ep.name, "file": f"brief/{stem}.md", "mtime": p.stat().st_mtime,
                                "source": "second opinion", "category": _category(pt, kind),
                                "text": pt["text"], "why": pt.get("why") or "", "fix": pt.get("rewrite")})
        review = ep / "review"
        for p in sorted(review.glob("critic-*.md")) if review.is_dir() else []:
            m = re.search(r"(SCRIPT|SHORT|CUES|DREHZETTEL)-v(\d+)", p.name, re.I)
            if not m or (m.group(1).upper(), int(m.group(2))) in with_json:
                continue
            if any(_version(g) == (m.group(1).upper(), int(m.group(2))) for g in gaps):
                continue
            try:
                lines = p.read_text(encoding="utf-8").splitlines()
            except OSError:
                continue
            for ln in lines:
                # a marked line quotes the sentence it is about; a line that only lists rule ids is not a finding
                if (not re.match(r"^\s*(?:[-*]|\d+\.)\s", ln) or not re.search(r"[\"„“»]", ln)
                        or not NEGATIVE.search(ln)):
                    continue
                for code in dict.fromkeys(CODE.findall(ln)):
                    if code not in ignore:
                        out.append({"episode": ep.name, "file": f"review/{p.name}", "mtime": p.stat().st_mtime,
                                    "source": "critic report", "category": code, "text": ln.strip(" -*")[:240],
                                    "why": "", "fix": None})
    out = [f for f in out if not _has_placeholder(f.get("text")) and not _has_placeholder(f.get("fix"))]
    return out, done


def _has_placeholder(text) -> bool:
    from . import showformats
    return bool(text) and bool(showformats.placeholders(str(text)))


def _placeholder_scripts(brief: Path) -> set[str]:
    """Stems of the scripts and cue sheets in brief/ that still have placeholders in their spoken part."""
    from . import showformats
    out = set()
    for p in brief.iterdir():
        if p.suffix == ".md" and SCRIPT_NAME.match(p.stem):
            try:
                if showformats.placeholders(p.read_text(encoding="utf-8")):
                    out.add(p.stem)
            except OSError:
                continue
    return out


def labels(files: list[str]) -> dict[str, str]:
    """Question and rule names: markdown lines '- P-S1 [G03] Question?' and JSON {"checks": {id: {"titel"|"frage"}}}."""
    out: dict[str, str] = {}
    for rel in files or []:
        p = _studio_path(rel)
        if p is None or not p.is_file():
            continue
        if p.suffix == ".json":
            j = _read_json(p)
            for k, v in (j.get("labels") or {}).items():
                out.setdefault(k, str(v))
            for k, v in (j.get("checks") or {}).items():
                if isinstance(v, dict):
                    out.setdefault(k, str(v.get("frage") or v.get("titel") or ""))
            continue
        for ln in p.read_text(encoding="utf-8").splitlines():
            m = re.match(r"^\s*[-*]\s+(?P<id>[A-Z][\w-]*\d[\w]*)\s+(?:\[[^\]]*\]\s*)?(?P<t>.+?)(?:\s*\{.*\})?$", ln)
            if m:
                out.setdefault(m.group("id"), m.group("t").strip())
    return out


def aliases(files: list[str]) -> dict[str, str]:
    """{"aliases": {"punch_belohnt": "P-U3"}} in a JSON label file: a unit flag and a question id are one group."""
    out: dict[str, str] = {}
    for rel in files or []:
        p = _studio_path(rel)
        if p is not None and p.suffix == ".json" and p.is_file():
            out.update({str(k): str(v) for k, v in (_read_json(p).get("aliases") or {}).items()})
    return out


def merge(items: list[dict], alias: dict[str, str]) -> list[dict]:
    for f in items:
        bare = f["category"].split(": ", 1)[-1]
        f["category"] = alias.get(f["category"]) or alias.get(bare) or f["category"]
    return items


def top_findings(items: list[dict], done: list[dict], n: int = 10) -> list[dict]:
    groups: dict[str, list[dict]] = {}
    for f in items:
        groups.setdefault(f["category"], []).append(f)
    fixed: dict[str, list[dict]] = {}
    for d in done:
        key = _norm(re.sub(r"\((?:runde|round|zweiter critic|second critic)[^)]*\)\s*$", "", d["text"], flags=re.I))[:60]
        for cat, fs in groups.items():
            if any(_norm(f["text"])[:60] and (_norm(f["text"])[:60] in key or key[:40] in _norm(f["text"]))
                   for f in fs if f["episode"] == d["episode"]):
                fixed.setdefault(cat, []).append(d)
                break
    out = []
    for cat, fs in sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0]))[:n]:
        fs = sorted(fs, key=lambda f: f["mtime"], reverse=True)
        worked = sorted(fixed.get(cat, []), key=lambda d: d["mtime"], reverse=True)
        best = worked[0]["how"] if worked else next((f["fix"] for f in fs if f.get("fix")), None)
        out.append({"category": cat, "count": len(fs), "episodes": sorted({f["episode"] for f in fs}),
                    "example": fs[0]["text"], "why": fs[0]["why"], "best_fix": best, "fix_worked": bool(worked),
                    "sources": sorted({f["source"] for f in fs})})
    return out


# ---- units ---------------------------------------------------------------------------------------------------------
def units(root: Path | None = None) -> list[dict]:
    root = root or paths.studio_root()
    out = []
    for p in sorted((root / "episodes").glob("*/analytics/retention-units.json")):
        d = _read_json(p)
        ms = d.get("measurements") or []
        if not ms:
            continue
        m = ms[-1]
        us = [u for u in m.get("units") or [] if u.get("kind") == "unit" and u.get("drop_per_min") is not None
              and (u.get("seconds") or 0) >= 15]
        if len(us) < 2:
            continue
        med = st.median(u["drop_per_min"] for u in us)
        for u in us:
            out.append({"episode": d.get("episode") or p.parent.parent.name, "index": u.get("index"),
                        "hook": u.get("hook") or u.get("label") or "", "hook_type": u.get("hook_type"),
                        "drop_per_min": u["drop_per_min"], "relative": round(u["drop_per_min"] - med, 1),
                        "seconds": u.get("seconds"), "verdict": u.get("verdict"),
                        "views": (m.get("sample") or {}).get("views")})
    status = hook_status(out)
    for u in out:
        u["status"] = status.get(u.get("hook_type") or "", "watch")
    return sorted(out, key=lambda u: u["relative"])


REPEATS = 3   # the same rule as crewcut/youtube/units.py: a pattern is a lesson when it repeats in 3 episodes


def hook_status(us: list[dict]) -> dict[str, str]:
    """Per hook type: "lesson: holds", "lesson: loses" or "watch" (holds in at least REPEATS episodes and loses in at
    most one, or the other way round)."""
    hold: dict[str, set] = {}
    lose: dict[str, set] = {}
    for u in us:
        t = u.get("hook_type") or ""
        if u.get("verdict") == "holds":
            hold.setdefault(t, set()).add(u["episode"])
        elif u.get("verdict") == "loses":
            lose.setdefault(t, set()).add(u["episode"])
    out = {}
    for t in {u.get("hook_type") or "" for u in us}:
        h, ls = len(hold.get(t, ())), len(lose.get(t, ()))
        out[t] = ("lesson: holds" if h >= REPEATS and ls <= 1 else "lesson: loses" if ls >= REPEATS and h <= 1
                  else "watch")
    return out


# ---- gold candidates -----------------------------------------------------------------------------------------------
def gold_dir(cfg: dict | None = None) -> Path | None:
    cfg = cfg or settings()
    return _studio_path(cfg.get("gold_dir"))


def candidates(cfg: dict | None = None) -> list[dict]:
    d = gold_dir(cfg)
    if d is None or not d.is_dir():
        return []
    out = []
    for p in sorted(d.glob("*-[0-9][0-9][0-9]-*.json")):
        j = _read_json(p)
        if j.get("candidate"):
            out.append(j)
    return out


def add_candidate(episode: str, rel: str, verdict_result: dict, cfg: dict | None = None) -> dict | None:
    """Copy a script that passed the gate into the gold folder, numbered, with a score file. Once per content."""
    cfg = cfg or settings()
    d = gold_dir(cfg)
    if d is None:
        return None
    src = paths.inside(paths.episode_dir(episode), rel)
    if not src.is_file():
        return None
    data = src.read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    have = candidates(cfg)
    if any(c.get("sha256") == sha for c in have):
        return None
    d.mkdir(parents=True, exist_ok=True)
    word = "KANDIDAT" if german() else "CANDIDATE"
    n = max([int(c.get("number") or 0) for c in have] + [0]) + 1
    name = f"{word}-{n:03d}-{episode}-{src.name}"
    shutil.copy2(src, d / name)
    for extra in (".kritik.json", ".zweitmeinung.json"):
        side = src.with_suffix(extra)
        if side.is_file():
            shutil.copy2(side, d / (Path(name).stem + extra))
    hints = verdict_result.get("hints") or 0
    score = {"candidate": True, "number": n, "file": name, "episode": episode, "source": rel, "sha256": sha,
             "date": datetime.now(UTC).strftime("%Y-%m-%d"), "format": verdict_result.get("format"),
             "words": verdict_result.get("words"), "seconds": verdict_result.get("seconds"),
             "hints": hints, "score": round(100.0 / (1 + hints), 1),
             "note": "passed the style gate (checker, Critic, fresh review, second opinion as configured); score = "
                     "100 / (1 + hints left for the Critic)"}
    (d / (Path(name).stem + ".json")).write_text(json.dumps(score, ensure_ascii=False, indent=1) + "\n",
                                                 encoding="utf-8")
    return score


# ---- the file ------------------------------------------------------------------------------------------------------
def _state_path(p: Path) -> Path:
    return p.with_suffix(".json")


def _state(p: Path) -> dict:
    s = _read_json(_state_path(p))
    s.setdefault("proposed", [])
    return s


def render(top: list[dict], us: list[dict], gold: list[dict], names: dict[str, str], proposals: list[dict],
           de: bool) -> str:
    def T(de_text, en_text):
        return (de_text if de else en_text)
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"# {T('Lernstand: was die nächsten Skripte besser macht', 'Learning file: what makes the next script better')}",
             "", MARK, "",
             T(f"Stand {now}. Automatisch geschrieben von Crewcut (crewcut/lernstand.py) nach jeder Runde des "
               "Stil-Gates und jeder Retention-Messung; nicht von Hand ändern. Der Writer liest den Kopf vor jedem "
               "Skript: vermeide die häufigsten Funde. Als Vorbild zum Kopieren gelten nur Einheiten mit Status "
               "„lesson“; alles mit „watch“ wird beobachtet, nie kopiert. Funde an Skripten mit Platzhaltern zählen "
               "nicht.",
               f"As of {now}. Written by Crewcut (crewcut/lernstand.py) after every style gate round and every "
               "retention run; do not edit by hand. The Writer reads the top before every script: avoid the most "
               "frequent findings. Only units with status \"lesson\" are models to copy; \"watch\" units are "
               "watched, never copied. Findings on scripts with placeholders do not count."), "",
             f"## 1. {T('Die häufigsten Funde (Critic, frischer Critic, Zweitmeinung)', 'Most frequent findings (Critic, fresh Critic, second opinion)')}",
             ""]
    if not top:
        lines.append(T("Noch keine Funde.", "No findings yet."))
    for i, f in enumerate(top, 1):
        name = label_of(f["category"], names)
        lines.append(f"{i}. **{f['category']}**" + (f" ({name})" if name else "") + f": {f['count']}x "
                     + T(f"in {len(f['episodes'])} Folge(n)", f"in {len(f['episodes'])} episode(s)")
                     + f" ({', '.join(f['sources'])})")
        lines.append(f"   - {T('Beispiel', 'Example')}: \u201e{f['example'][:200]}\u201c"
                     + (f" ({T('Grund', 'why')}: {f['why'][:220]})" if f.get("why") else ""))
        if f.get("best_fix"):
            lines.append(f"   - {T('Fix, der gewirkt hat' if f['fix_worked'] else 'Vorschlag des Critic', 'Fix that worked' if f['fix_worked'] else 'Critic rewrite')}: "
                         f"{str(f['best_fix'])[:260]}")
    lines += ["", f"## 2. {T('Beste und schwächste Einheiten (Retention)', 'Best and worst units (retention)')}", "",
              T("Verlust pro Minute gegen die mittlere Einheit desselben Videos (negativ = hält besser). Ein Hinweis, "
                "kein Beweis: kleine Zuschauerzahlen bewegen die Kurve in Stufen.",
                "Drop per minute against the median unit of the same video (negative = holds better). A hint, not "
                "proof: small audiences move the curve in steps."), ""]
    if not us:
        lines.append(T("Noch keine gemessenen Einheiten.", "No measured units yet."))
    else:
        hdr = T("| | Folge | Einheit | Hook | Typ | Verlust/min | relativ | Status |",
                "| | Episode | Unit | Hook | Type | Drop/min | relative | Status |")
        sep = "| --- | --- | --- | --- | --- | --- | --- | --- |"

        def rows(xs):
            return [f"| {i} | {u['episode']} | {u['index']} | {u['hook'][:90]} | {u['hook_type']} | "
                    f"{u['drop_per_min']} | {u['relative']:+} | {u.get('status', 'watch')} |" for i, u in enumerate(xs, 1)]
        models = [u for u in us if u.get("status") == "lesson: holds"][:5]
        watch_best = [u for u in us if u.get("status") != "lesson: holds" and u["relative"] < 0][:5]
        avoid = [u for u in reversed(us) if u.get("status") == "lesson: loses"][:5]
        watch_worst = [u for u in reversed(us) if u.get("status") != "lesson: loses" and u["relative"] > 0][:5]
        lines += [f"**{T('Vorbilder (Status lesson: hält in mindestens 3 Folgen)', 'Models (status lesson: holds in at least 3 episodes)')}**", ""]
        lines += ([hdr, sep] + rows(models)) if models else [T(
            "Noch keine. Keine Hook-Art hält in mindestens 3 Folgen. Kopiere keine Einheit aus den Listen unten.",
            "None yet. No hook type holds in at least 3 episodes. Copy no unit from the lists below.")]
        lines += ["", f"**{T('Gut gehalten, aber nur watch (beobachten, nicht kopieren)', 'Held well, but only watch (watch, do not copy)')}**", ""]
        lines += ([hdr, sep] + rows(watch_best)) if watch_best else [T("Keine.", "None.")]
        lines += ["", f"**{T('Meiden (Status lesson: verliert in mindestens 3 Folgen)', 'Avoid (status lesson: loses in at least 3 episodes)')}**", ""]
        lines += ([hdr, sep] + rows(avoid)) if avoid else [T("Noch keine.", "None yet.")]
        lines += ["", f"**{T('Schwach, aber nur watch', 'Weak, but only watch')}**", ""]
        lines += ([hdr, sep] + rows(watch_worst)) if watch_worst else [T("Keine.", "None.")]
    lines += ["", f"## 3. {T('Gold-Kandidaten (Skripte, die das Gate bestanden haben)', 'Gold candidates (scripts that passed the gate)')}", ""]
    if not gold:
        lines.append(T("Noch keiner. Jedes Skript, das das Gate besteht, kommt nummeriert in den Gold-Ordner.",
                       "None yet. Every script that passes the gate is copied, numbered, into the gold folder."))
    for g in gold[-10:]:
        lines.append(f"- {g['file']} ({g['episode']}, {g['date']}, {T('Punkte', 'score')} {g['score']}, "
                     f"{g.get('hints', 0)} {T('Hinweise', 'hints')})")
    lines += ["", f"## 4. {T('Regelvorschläge', 'Rule proposals')}", ""]
    if not proposals:
        lines.append(T("Keiner offen.", "None open."))
    for p in proposals:
        lines.append(f"- {p['category']}: {p['rule']} ({p['status']})")
    return "\n".join(lines) + "\n"


def label_of(cat: str, names: dict[str, str]) -> str:
    return names.get(cat) or names.get(cat.split(": ", 1)[-1]) or ""


def rule_text(f: dict, names: dict[str, str], de: bool) -> str:
    name = (label_of(f["category"], names) or f["category"]).rstrip(" .")
    name += "" if name.endswith(("?", "!")) else "."
    if de:
        return (f"Vor jeder Fassung prüfen: {name} Der Critic fand das {f['count']}-mal in {len(f['episodes'])} "
                f"Folge(n), zuletzt: \u201e{f['example'][:120]}\u201c."
                + (f" Was gewirkt hat: {str(f['best_fix'])[:160]}" if f.get("best_fix") else ""))
    return (f"Check before every draft: {name} The Critic found it {f['count']} times in {len(f['episodes'])} "
            f"episode(s), last: \"{f['example'][:120]}\"." + (f" What worked: {str(f['best_fix'])[:160]}"
                                                              if f.get("best_fix") else ""))


def refresh(cards: bool = True, root: Path | None = None) -> Path:
    """Write the learning file now (and propose rule cards for findings that repeat)."""
    cfg = settings()
    p = learning_path(cfg)
    items, done = findings(root, cfg.get("learning_ignore"))
    items = merge(items, aliases(cfg.get("learning_labels") or []))
    names = labels(cfg.get("learning_labels") or [])
    top = top_findings(items, done)
    de = german()
    state = _state(p)
    proposals = []
    limit = int(cfg.get("rule_after") or 0)
    budget = int(cfg.get("rules_per_run") or 2)   # never a flood of cards: the rest follow at the next runs
    for f in top:
        if limit and f["count"] >= limit and label_of(f["category"], names):   # a rule needs a named question
            prev = next((x for x in state["proposed"] if x["category"] == f["category"]), None)
            if prev:   # proposed once; the file shows today's counts, the card keeps its own text
                proposals.append({**prev, "rule": rule_text(f, names, de)})
                continue
            entry = {"category": f["category"], "rule": rule_text(f, names, de), "status": "",
                     "date": datetime.now(UTC).strftime("%Y-%m-%d")}
            if cards and budget > 0:
                budget -= 1
                try:
                    from . import approvals
                    card = approvals.propose_rule("script", entry["rule"],
                                                  f"learning loop, {f['count']} findings in {len(f['episodes'])} "
                                                  "episode(s)")
                    entry["status"] = f"card #{card.get('id')}"
                    entry["card"] = card.get("id")
                except Exception as e:  # noqa: BLE001 - a card that cannot be made is noted, not fatal
                    entry["status"] = f"no card yet ({str(e)[:80]})"
                    entry["retry"] = True
            else:
                entry["status"] = ("vorgeschlagen, Karte bei einem der nächsten Gate-Läufe" if de else
                                   "proposed, card at one of the next gate runs")
                entry["retry"] = True
            if not entry.get("retry"):
                state["proposed"].append(entry)
            proposals.append(entry)
    state["proposed"] = [x for x in state["proposed"] if not x.get("retry")]
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(render(top, units(root), candidates(cfg), names, proposals, de), encoding="utf-8")
    state["updated"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    state["top"] = [{k: f[k] for k in ("category", "count", "episodes")} for f in top]
    _state_path(p).write_text(json.dumps(state, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return p


def safe_refresh(**kw) -> Path | None:
    """For hooks: never raise."""
    try:
        return refresh(**kw)
    except Exception:  # noqa: BLE001 - learning must never break the gate or a measurement
        return None


def after_ready(episode: str, verdict: dict) -> None:
    """The gate passed: passing scripts become gold candidates, then the file is written again."""
    try:
        for r in verdict.get("results") or []:
            if r.get("pass") and r.get("file"):
                add_candidate(episode, r["file"], r)
    except Exception:  # noqa: BLE001
        pass
    safe_refresh()


def prompt_top(max_lines: int = 40) -> str:
    """The head of the learning file (findings and units) for a system prompt; "" when there is none."""
    try:
        p = learning_path()
        text = p.read_text(encoding="utf-8")
    except (OSError, ValueError):
        return ""
    body = text.split(MARK, 1)[-1].strip().splitlines()
    keep, sect = [], 0
    for ln in body:
        if ln.startswith("## "):
            sect += 1
            if sect > 2:
                break
        keep.append(ln)
    keep = keep[:max_lines]
    return (f"LEARNING FILE ({p}, written by the learning loop; avoid these findings; copy only units marked "
            "\"lesson\", never units marked \"watch\"):\n"
            + "\n".join(keep) + "\n")


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="crewcut lernstand", description="Write the learning file now.")
    ap.add_argument("--no-cards", action="store_true", help="list rule proposals without making cards")
    ap.add_argument("--print", action="store_true")
    return ap


def main(argv: list[str] | None = None) -> int:
    a = _parser().parse_args(argv)
    p = refresh(cards=not a.no_cards)
    print(p.read_text(encoding="utf-8") if a.print else str(p))
    return 0


if __name__ == "__main__":
    sys.exit(main())
