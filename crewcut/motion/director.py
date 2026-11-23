"""The motion pass: start from the video, not from the library (motion plan 3.1).

The Editor (with the Designer for look) runs it once per video after the speaker cut and its words exist, and again in
short form for each Short. ``crewcut motion plan <episode>`` writes a skeleton; the director fills it; ``--check``
validates it, computes the density and budget lines (never typed by hand) and writes the Markdown for people; ``--card``
opens the ``motion-plan`` card. Files, in the episode::

    edit/motion-plan-vNNN.json   what tools read (the director edits this one)
    edit/motion-plan-vNNN.md     what people read; written from the JSON

The JSON (``schema`` 1)::

    {"episode", "version", "format", "short", "title", "words", "script", "duration_s",
     "bar": {"episode", "strengths"} | null, "last_video": {"episode", "motion_moments", "custom"} | null,
     "lessons": [{"id", "rule"}], "references": [{"id", "reason"}], "marks": [{"n", "what", "quote", "beat", "time"}],
     "shelf": [{"name", "origin", "kind", "formats", "version", "loop"}],
     "beats": [{"n", "start", "end", "says", "purpose", "picture", "column", "piece", "params", "at", "length_s",
                "overlay", "cost_usd", "wish", "struck"}],
     "new": [{"id", "beat", "brief", "why_new", "kind", "plates", "effort", "cost_usd", "cap_usd", "struck"}],
     "upgrades": [{"id", "upgrade", "source": {"kind", "ref"}, "effort", "cost_usd", "chosen", "struck"}],
     "cap_usd", "density", "budget", "based_on", "struck_rows"}

``column`` is ``a`` (on the shelf: ``piece`` is a template name, ``params`` its values), ``b`` (built new: ``piece`` is
the id of a ``new`` entry), ``c`` (a chosen upgrade: ``piece`` is its id) or ``-`` (no motion: the speaker carries
it, or a recording plays). Most beats get ``-``.

Every full-frame picture of the video has its own row, whatever renders it: a motion template, a comp built for this
video, a 2D scene (``piece`` names a 2D scene of the pack or the app) or a 3D scene. The density line counts them
all, the render path refuses a full-frame insert without its row (``motion_gate``) and without the yes on its style
frame (``custom.style_frame_gate``). A beat may be split into several rows (``"n": "12a"``, ``"12b"``); every full-frame
insert names its own row.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .. import brand, config, paths
from . import density as dens
from . import lessons as lessons_mod
from . import library, marks
from . import references as refs_mod

COLUMNS = ("a", "b", "c", "-")
MOTION = ("a", "b", "c")
RENDERS = ("motion", "2d", "3d")
FLAT_2D = ("Beat {n}: the 2D scene {piece} as the whole full-frame picture reads as a slide. Prefer a motion piece "
           "from the shelf (crewcut motion library) or a comp built for this video in the launch film's craft (a "
           "camera that never stops, layers in depth, symbol and label close together); a 2D window belongs inside "
           "such a shot as one element. The style frame card and the slide check decide.")
EFFORTS = ("S", "M", "L")
SOURCE_KINDS = ("lesson", "reference", "baseline", "retention")
UPGRADES = (2, 4)
CAP_USD = {"long": 2.0, "short": 0.5}
BEAT_MIN_S = 6.0
BEAT_MAX_SENTENCES = 3
DEFAULT_LEN = {"full": 4.0, "overlay": 2.0}
NO_UPGRADE = ("No upgrade is chosen: every video picks at least one in column (c), the thing that makes it clearly "
              "better than the last one.")
FILE = re.compile(r"motion-plan-v(\d{3,})\.json")


class PlanError(ValueError):
    """The motion plan cannot be made or used. The message says what to change."""


# ---------------------------------------------------------------- files


def plans(ep_dir: Path) -> list[Path]:
    """The episode's motion plan JSON files, oldest first."""
    found = [(int(m.group(1)), p) for p in (ep_dir / "edit").glob("motion-plan-v*.json") if (m := FILE.fullmatch(p.name))]
    return [p for _n, p in sorted(found)]


def newest(ep_dir: Path) -> Path | None:
    ps = plans(ep_dir)
    return ps[-1] if ps else None


def version_of(p: Path) -> int:
    m = FILE.fullmatch(p.name)
    return int(m.group(1)) if m else 0


def md_of(p: Path) -> Path:
    return p.with_suffix(".md")


def load(p: Path) -> dict:
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise PlanError(f"{p.name} is not readable JSON ({e})") from e
    if not isinstance(data, dict):
        raise PlanError(f"{p.name}: the motion plan must be a JSON object")
    return data


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _newest(folder: Path, pattern: str) -> Path | None:
    files = sorted(folder.glob(pattern), key=lambda f: (len(f.stem), f.stem))
    return files[-1] if files else None


def tc(t: float | None) -> str:
    if t is None:
        return "-"
    m, s = divmod(max(0.0, float(t)), 60)
    return f"{int(m)}:{int(s):02d}"


# ---------------------------------------------------------------- inputs


def bar() -> dict | None:
    """The motion bar: the ``motion`` block of ``brand/baseline.json`` (None before the first approved video)."""
    m = brand.load().value("baseline.motion")
    return m if isinstance(m, dict) and m.get("episode") else None


def last_video(episode: str) -> dict | None:
    """The newest motion report of an earlier episode: its moments and custom pieces (for the plan's header)."""
    for eid in sorted((p.name for p in paths.episodes_dir().iterdir() if p.is_dir()), reverse=True):
        if eid >= episode:
            continue
        rep = _newest(paths.episode_dir(eid) / "review", "motion-report-v*.json")
        if rep:
            try:
                d = json.loads(rep.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            m = d.get("measured") or {}
            return {"episode": eid, "report": f"review/{rep.name}", "motion_moments": m.get("motion_moments"),
                    "custom": m.get("custom")}
    return None


def beats_from_words(words: list[dict]) -> list[dict]:
    """Beats from the words file: sentences joined until a beat lasts ``BEAT_MIN_S`` or holds
    ``BEAT_MAX_SENTENCES`` sentences."""
    out: list[dict] = []
    cur: list[tuple[float, float]] = []
    for s in dens.sentences(words):
        cur.append(s)
        if cur[-1][1] - cur[0][0] >= BEAT_MIN_S or len(cur) >= BEAT_MAX_SENTENCES:
            out.append((cur[0][0], cur[-1][1]))
            cur = []
    if cur:
        if out and cur[-1][1] - cur[0][0] < BEAT_MIN_S / 2:
            out[-1] = (out[-1][0], cur[-1][1])
        else:
            out.append((cur[0][0], cur[-1][1]))
    beats = []
    for i, (a, b) in enumerate(out, 1):
        said = " ".join(w["w"] for w in words if a - 1e-6 <= w["s"] < b - 1e-6)
        beats.append({"n": i, "start": round(a, 2), "end": round(b, 2), "says": said, "purpose": "", "picture": "",
                      "column": "", "piece": "", "params": {}, "at": None, "length_s": None, "overlay": None,
                      "cost_usd": 0.0, "wish": None, "struck": False})
    return beats


def _place_marks(found: list[dict], words: list[dict], beats: list[dict]) -> list[dict]:
    out = []
    for m in found:
        t = dens.word_time(words, " ".join(m["quote"].split()[:4])) if m["quote"] else None
        beat = next((b["n"] for b in beats if t is not None and b["start"] - 1e-6 <= t < b["end"]), None)
        out.append({**m, "time": t, "beat": beat})
        if beat:
            b = beats[beat - 1]
            b["wish"] = (b["wish"] + "; " if b["wish"] else "") + f"{m['what']}: \"{m['quote']}\""
    return out


def _cap(short: bool) -> float:
    key = "motion.cap_usd_short" if short else "motion.cap_usd"
    return float(config.get("crewcut", key, CAP_USD["short" if short else "long"]))


def shelf_rows() -> list[dict]:
    rows = []
    for r in library.entries(include_episodes=True):
        loop = next((v for k, v in (r.get("samples") or {}).items() if k != "poster"), None)
        rows.append({"name": r["name"], "origin": r["origin"], "kind": r["kind"], "formats": r["formats"],
                     "version": r["version"], "title": r.get("title"), "loop": loop,
                     "poster": (r.get("samples") or {}).get("poster")})
    return rows


def scenes() -> dict[str, dict]:
    """2D and 3D scenes a row may name in column (a): ``name -> {"render": "2d"|"3d", "kind": "full"|"overlay"}``.
    The pack's own scenes (``brand/templates/2d``, ``brand/templates/3d``) come first, then the app's."""
    from ..render import plan as rplan
    out: dict[str, dict] = {}
    dirs = []
    pack = paths.brand_dir()
    if pack.resolve() != paths.neutral_pack_dir().resolve():
        dirs.append(pack / "templates")
    dirs.append(paths.templates_dir())
    for root in dirs:
        for render in ("2d", "3d"):
            d = root / render
            if not d.is_dir():
                continue
            shared = set(rplan.SHARED[render])
            for f in sorted(d.glob(f"*{rplan.EXT[render]}")):
                if f.name in shared or f.name.endswith(".scene.json"):
                    continue
                out.setdefault(f.stem, {"render": render, "kind": "overlay" if f.stem == "keyword" else "full"})
    return out


def render_of(plan: dict, b: dict, shelf: dict[str, dict] | None = None,
              found: dict[str, dict] | None = None) -> str:
    """What renders a row: ``motion`` (a shelf template or a comp), ``2d`` or ``3d`` (a scene). A row may say it with
    ``"render"``; else column (a) looks the piece up on the motion shelf first, then among the scenes."""
    if b.get("render") in RENDERS:
        return str(b["render"])
    piece = str(b.get("piece") or "").partition("@")[0]
    if b.get("column") == "a":
        shelf = _shelf(plan) if shelf is None else shelf
        if piece in shelf:
            return "motion"
        found = scenes() if found is None else found
        return found.get(piece, {}).get("render", "motion")
    if b.get("column") == "b":
        x = _new_by_id(plan).get(piece) or {}
        return str(x.get("render")) if x.get("render") in RENDERS else "motion"
    return "motion"


def skeleton(episode: str, short: bool | None = None) -> Path:
    """Write ``edit/motion-plan-vNNN.json`` (and ``.md``) with the beats from the words file, the Writer's marks, the
    shelf and the inputs the director reads. Returns the JSON path."""
    from .. import episodes
    ep_dir = paths.episode_dir(episode)
    project = episodes.read(episode)
    words_file = _newest(ep_dir / "work", "words-v*.json")
    if words_file is None:
        raise PlanError("no words file yet (work/words-vNNN.json): the motion pass runs after the speaker cut and its "
                        "words exist")
    words = dens.norm_words(json.loads(words_file.read_text(encoding="utf-8")))
    if not words:
        raise PlanError(f"{words_file.name} holds no words")
    short = bool(short) or project.get("kind") == "short" or project.get("format") == "portrait"
    script = _newest(ep_dir / "brief", "SCRIPT-v*.md")
    found = marks.parse(script.read_text(encoding="utf-8")) if script else []
    beats = beats_from_words(words)
    placed = _place_marks(found[:marks.MAX_MARKS], words, beats)
    b = bar()
    plan: dict[str, Any] = {
        "schema": 1, "kind": "motion-plan", "episode": episode, "version": 0,
        "format": "portrait" if short else (project.get("format") or "landscape"), "short": short,
        "title": project.get("title", episode), "words": words_file.relative_to(ep_dir).as_posix(),
        "script": script.relative_to(ep_dir).as_posix() if script else None,
        "duration_s": round(words[-1]["e"] + 0.5, 2),
        "bar": {"episode": b["episode"], "strengths": b.get("strengths") or []} if b else None,
        "last_video": last_video(episode),
        "lessons": [{"id": x["id"], "rule": x["rule"]} for x in lessons_mod.read() if x["id"]],
        "references": [{"id": x["id"], "reason": x.get("reason")} for x in refs_mod.read()],
        "marks": placed, "shelf": shelf_rows(), "beats": beats, "new": [],
        "upgrades": [{"id": f"u{i}", "upgrade": "", "source": {"kind": "", "ref": ""}, "effort": "", "cost_usd": 0.0,
                      "chosen": False, "struck": False} for i in (1, 2)],
        "cap_usd": _cap(short), "density": None, "budget": None, "based_on": None, "struck_rows": [],
    }
    return write(ep_dir, plan)


# ---------------------------------------------------------------- computing and checking


def _shelf(plan: dict) -> dict[str, dict]:
    live = library.shelf_names()
    return live or {r["name"]: r for r in plan.get("shelf") or [] if r.get("origin") != "episode"}


def _new_by_id(plan: dict) -> dict[str, dict]:
    return {str(n.get("id")): n for n in plan.get("new") or [] if isinstance(n, dict)}


def _up_by_id(plan: dict) -> dict[str, dict]:
    return {str(u.get("id")): u for u in plan.get("upgrades") or [] if isinstance(u, dict)}


def _is_overlay(plan: dict, b: dict, shelf: dict[str, dict], found: dict[str, dict] | None = None) -> bool:
    if b.get("overlay") is not None:
        return bool(b["overlay"])
    if b.get("column") == "a":
        name = str(b.get("piece") or "").partition("@")[0]
        row = shelf.get(name) or (found or {}).get(name) or {}
        return row.get("kind") == "overlay"
    if b.get("column") == "b":
        return (_new_by_id(plan).get(str(b.get("piece"))) or {}).get("kind") == "overlay"
    return False


def moving(plan: dict) -> list[dict]:
    """Beats with motion that are not struck."""
    return [b for b in plan.get("beats") or [] if b.get("column") in MOTION and not b.get("struck")]


def compute(plan: dict, ep_dir: Path) -> dict:
    """The plan with ``density`` and ``budget`` computed from its rows (the density counts of ``density.py``)."""
    pack = brand.load()
    words: list[dict] = []
    if plan.get("words") and (ep_dir / plan["words"]).is_file():
        words = dens.norm_words(json.loads((ep_dir / plan["words"]).read_text(encoding="utf-8")))
    shelf = _shelf(plan)
    found = scenes()
    inserts = []
    for b in moving(plan):
        overlay = _is_overlay(plan, b, shelf, found)
        start = float(b["at"] if b.get("at") is not None else b.get("start") or 0.0)
        length = float(b.get("length_s") or DEFAULT_LEN["overlay" if overlay else "full"])
        scene = str(b.get("piece") or "").partition("@")[0] if b.get("column") == "a" else None
        render = render_of(plan, b, shelf, found)
        inserts.append({"id": f"beat{b['n']}", "kind": render, "scene": scene,
                        "source": None if scene or render != "motion" else f"motion/{b.get('piece')}/comp.jsx",
                        "start": round(start, 3), "end": round(start + length, 3), "transparent": overlay})
    pseudo = {"format": "portrait" if plan.get("short") else plan.get("format") or "landscape", "inserts": inserts}
    rep = dens.count(pseudo, words, dens.limits(pack.value("edit_style", {}) or {}),
                     total_s=float(plan.get("duration_s") or 0) or None)
    c, mx = rep["counts"], rep["max"]
    heroes = sum(c["heroes"].values())
    line = (f"full-frame {c['big']} of max {mx['big']}{dens.kinds_text(c.get('big_by_kind') or {})} · all motion "
            f"{c['motion']} in {tc(rep['duration_s'])} (max {mx['motion']}) · heroes {heroes}")
    plan["density"] = {"line": line, "counts": {k: c[k] for k in ("motion", "big", "overlays", "heroes", "big_by_kind")},
                       "max": mx, "findings": [f for f in rep["findings"] if f["level"] in ("ERROR", "CHECK")]}
    new = [n for n in plan.get("new") or [] if not n.get("struck")]
    ups = [u for u in plan.get("upgrades") or [] if u.get("chosen") and not u.get("struck")]
    est = sum(float(x.get("cost_usd") or 0) for x in new + ups)
    est += sum(float(b.get("cost_usd") or 0) for b in moving(plan) if b.get("column") == "a")
    cap = float(plan.get("cap_usd") or _cap(bool(plan.get("short"))))
    money = f"GPU about ${est:.2f}" if est > 0 else "GPU none"
    plan["budget"] = {"line": f"{money}, cap ${cap:g}", "estimate_usd": round(est, 2), "cap_usd": cap}
    plan["cap_usd"] = cap
    return plan


def _plain(s: Any) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", str(s or "").lower()).split())


def check(plan: dict, ep_dir: Path) -> tuple[list[str], list[str]]:
    """(errors, warnings) of a finished plan. Errors stop the card; warnings are read and answered."""
    errors: list[str] = []
    warns: list[str] = []
    compute(plan, ep_dir)
    shelf = _shelf(plan)
    found = scenes()
    names = {_plain(n) for n in shelf} | {_plain(n) for n in found}
    new, ups = _new_by_id(plan), _up_by_id(plan)
    beats = [b for b in plan.get("beats") or [] if isinstance(b, dict)]
    if not beats:
        errors.append("the plan has no beats")
    seen: set[str] = set()
    for b in beats:
        if str(b.get("n")) in seen:
            errors.append(f"beat {b.get('n')} appears twice: give a split beat its own number (12a, 12b)")
        seen.add(str(b.get("n")))
    for b in beats:
        n = b.get("n")
        col = str(b.get("column") or "")
        if not str(b.get("purpose") or "").strip():
            errors.append(f"beat {n}: say what the viewer must understand or feel (purpose)")
        if not str(b.get("picture") or "").strip():
            errors.append(f"beat {n}: describe the picture (what happens on screen, or the speaker)")
        if col not in COLUMNS:
            errors.append(f"beat {n}: column must be a, b, c or - (no motion), not {col or 'empty'}")
            continue
        if col == "-" and not b.get("struck"):
            words = set(re.findall(r"[a-z0-9_]+", str(b.get("picture") or "").lower()))
            named = sorted(w for w in words if "_" in w and (w in found or w in shelf))
            if named:
                errors.append(f"beat {n}: column - leaves the beat to the speaker, but the picture names graphics "
                              f"({', '.join(named)}): give every full-frame picture its own row (column a, b or c), "
                              "so the card counts it and it gets its style frame")
        if col == "-" or b.get("struck"):
            continue
        pic = _plain(b.get("picture"))
        if pic and (pic in names or pic == _plain(b.get("piece"))):
            errors.append(f"beat {n}: the picture only names a template; say what happens on screen first")
        piece = str(b.get("piece") or "")
        if col == "a":
            name = piece.partition("@")[0]
            if name not in shelf and name not in found:
                errors.append(f"beat {n}: {piece or 'no piece'} is not on the shelf (crewcut motion library) and is "
                              "not a 2D or 3D scene")
            elif name not in shelf and found[name]["render"] == "2d" and not _is_overlay(plan, b, shelf, found):
                warns.append(FLAT_2D.format(n=n, piece=name))
        elif col == "b":
            if piece not in new:
                errors.append(f"beat {n}: column b names the new piece in 'new' (id {piece or 'missing'})")
            elif new[piece].get("struck"):
                errors.append(f"beat {n}: new piece {piece} was struck")
        elif col == "c":
            u = ups.get(piece)
            if not u or not u.get("chosen") or u.get("struck"):
                errors.append(f"beat {n}: column c names a chosen upgrade (id {piece or 'missing'})")
        if b.get("length_s") is not None and float(b["length_s"]) <= 0:
            errors.append(f"beat {n}: length must be above 0 s")
        elif col == "a" and not b.get("length_s"):
            errors.append(f"beat {n}: give the length in seconds")
    if len(beats) >= 3 and beats and all(b.get("column") in MOTION and not b.get("struck") for b in beats):
        errors.append("every beat has motion: leave the beats the speaker carries without it")
    for nid, x in new.items():
        if x.get("struck"):
            continue
        if not str(x.get("brief") or "").strip():
            errors.append(f"new piece {nid}: write the brief (what must be understood in 2 s)")
        if not str(x.get("why_new") or "").strip():
            errors.append(f"new piece {nid}: say why no shelf piece does it")
        if x.get("effort") not in EFFORTS:
            errors.append(f"new piece {nid}: effort is S, M or L")
        if not any(b.get("piece") == nid and b.get("column") == "b" for b in beats):
            warns.append(f"new piece {nid} is not used by any beat")
    live = [u for u in ups.values() if not u.get("struck")]
    lesson_ids = lessons_mod.ids()
    ref_ids = refs_mod.ids()
    if not UPGRADES[0] <= len(live) <= UPGRADES[1]:
        errors.append(f"column (c) holds {UPGRADES[0]} to {UPGRADES[1]} candidates; it has {len(live)}")
    for u in live:
        uid = u.get("id")
        if not str(u.get("upgrade") or "").strip():
            errors.append(f"upgrade {uid}: say what changes")
        src = u.get("source") if isinstance(u.get("source"), dict) else {}
        if src.get("kind") not in SOURCE_KINDS or not str(src.get("ref") or "").strip():
            errors.append(f"upgrade {uid}: name its source (a lesson id, a reference, a gap to the baseline or a "
                          "retention finding)")
        elif src["kind"] == "lesson" and src["ref"] not in lesson_ids:
            warns.append(f"upgrade {uid}: lesson {src['ref']} is not in brand/rules/motion.md")
        elif src["kind"] == "reference" and src["ref"] not in ref_ids:
            warns.append(f"upgrade {uid}: reference {src['ref']} is not in brand/references/motion/index.json")
        if u.get("chosen") and u.get("effort") not in EFFORTS:
            errors.append(f"upgrade {uid}: effort is S, M or L")
    if live and not any(u.get("chosen") for u in live):
        errors.append(NO_UPGRADE)
    if lesson_ids and not any((u.get("source") or {}).get("kind") == "lesson" for u in live if
                              isinstance(u.get("source"), dict)):
        warns.append(f"{len(lesson_ids)} lessons exist (brand/rules/motion.md) and no upgrade cites one: read them "
                     "and cite the id that applies")
    bud = plan["budget"]
    if bud["estimate_usd"] > bud["cap_usd"] + 1e-9:
        errors.append(f"the plan costs about ${bud['estimate_usd']:.2f}, over the cap ${bud['cap_usd']:g}: drop a "
                      "piece, or ask for a higher cap")
    for f in plan["density"]["findings"]:
        warns.append(f"density: {f['text']}")
    missing = uncovered(plan, ep_dir)
    if missing:
        warns.append(f"{missing['plan']} shows {len(missing['ids'])} full-frame picture(s) without a row in this plan: "
                     f"{', '.join(missing['ids'][:12])}{' …' if len(missing['ids']) > 12 else ''}. Every full-frame "
                     "insert names its own row (\"beat\", \"column\"); the render refuses it otherwise")
    return errors, warns


def uncovered(plan: dict, ep_dir: Path) -> dict | None:
    """Full-frame graphic inserts of the newest edit plan without a motion row of ``plan`` (None when all have one)."""
    p = _newest(ep_dir / "edit", "plan-v*.json")
    if p is None:
        return None
    try:
        edit = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    rows = {str(b.get("n")) for b in moving(plan)}
    ids = [str(e.get("id")) for e in gated(edit) if not e.get("transparent") and str(e.get("beat")) not in rows]
    return {"plan": p.name, "ids": ids} if ids else None


# ---------------------------------------------------------------- the Markdown for people


def _piece_txt(plan: dict, b: dict) -> str:
    col, piece = b.get("column"), str(b.get("piece") or "")
    if col == "a":
        params = ", ".join(f"{k}: {v}" for k, v in (b.get("params") or {}).items())
        render = render_of(plan, b)
        tag = f" ({render.upper()})" if render != "motion" else ""
        return f"{piece}{tag} {{{params}}}" if params else f"{piece}{tag}"
    if col == "b":
        x = _new_by_id(plan).get(piece) or {}
        return f'custom "{piece}"' + (f", {x['plates']} plate{'s' if x['plates'] != 1 else ''}" if x.get("plates")
                                       else "")
    if col == "c":
        return f"upgrade {piece}"
    return "–"


def _cost_txt(x: dict) -> str:
    c = float(x.get("cost_usd") or 0)
    s = f"~${c:.2f}" if c else "0"
    if x.get("cap_usd"):
        s += f", cap ${float(x['cap_usd']):g}"
    return s


def _cell(s: Any) -> str:
    return " ".join(str(s if s is not None else "").replace("|", "/").split())


def render_md(plan: dict) -> str:
    v = int(plan.get("version") or 0)
    head = f"# Motion plan v{v:03d}: {plan.get('episode')}"
    b = plan.get("bar")
    lv = plan.get("last_video")
    head += "          bar: " + (f"{b['episode']} (baseline)" if b else "none yet (the first approved video sets it)")
    if lv:
        head += (f", last video: {lv.get('motion_moments') if lv.get('motion_moments') is not None else '?'} motion "
                 f"moments, {lv.get('custom') if lv.get('custom') is not None else '?'} custom")
    note = (f"Written from `motion-plan-v{v:03d}.json` by `crewcut motion plan --check`. Edit the JSON; the density "
            "and budget lines are computed.") + (f" Based on {plan['based_on']}." if plan.get("based_on") else "")
    L = [head, "", note, "",
         "## Beats", "| # | Time | The viewer must … | Picture | Column | Piece | Length | Cost |",
         "|---|---|---|---|---|---|---|---|"]
    for bt in plan.get("beats") or []:
        col = bt.get("column") or "?"
        moves = col in MOTION
        cells = [str(bt.get("n")), tc(bt.get("at") if bt.get("at") is not None else bt.get("start")),
                 _cell(bt.get("purpose") or "…"), _cell(bt.get("picture") or "…"), col if col != "-" else "–",
                 _cell(_piece_txt(plan, bt)) if moves else "–",
                 f"{float(bt['length_s']):.1f} s" if moves and bt.get("length_s") else "–",
                 _cost_txt(bt) if moves else "–"]
        if bt.get("struck"):
            cells = [f"~~{c}~~" if c not in ("–", "") else c for c in cells]
            cells[-1] += " (struck)"
        L.append("| " + " | ".join(cells) + " |")
    a = [bt for bt in moving(plan) if bt.get("column") == "a"]
    counts: dict[str, int] = {}
    for bt in a:
        counts[str(bt.get("piece"))] = counts.get(str(bt.get("piece")), 0) + 1
    names = ", ".join(f"{k} ×{n}" if n > 1 else k for k, n in counts.items()) or "none"
    L += ["", f"## (a) What we have that fits        {len(a)} piece{'s' if len(a) != 1 else ''}: {names} "
          "(params above)"]
    new = [x for x in plan.get("new") or [] if not x.get("struck")]
    L += ["", f"## (b) What we build new for this video      {len(new)} piece{'s' if len(new) != 1 else ''}"
          + (": " + ", ".join(str(x.get("id")) for x in new) if new else "")]
    for x in plan.get("new") or []:
        line = (f"- {x.get('id')} (beat {x.get('beat')}): {_cell(x.get('brief'))} Why new: {_cell(x.get('why_new'))} "
                f"Effort {x.get('effort') or '?'}, {_cost_txt(x)}")
        L.append(f"- ~~{line[2:]}~~ (struck)" if x.get("struck") else line)
    L += ["", "## (c) What would make this video clearly better than the last one",
          "| Upgrade | Why (lesson or reference it comes from) | Effort | Cost | Chosen |", "|---|---|---|---|---|"]
    for u in plan.get("upgrades") or []:
        src = u.get("source") if isinstance(u.get("source"), dict) else {}
        why = f"{src.get('kind') or '?'} {src.get('ref') or ''}".strip()
        if src.get("why"):
            why += f": {src['why']}"
        cells = [_cell(f"{u.get('id')}: {u.get('upgrade') or '…'}"), _cell(why), u.get("effort") or "?",
                 _cost_txt(u), "yes" if u.get("chosen") else "no"]
        if u.get("struck"):
            cells = [f"~~{c}~~" for c in cells]
            cells[-1] += " (struck)"
        L.append("| " + " | ".join(cells) + " |")
    dl = (plan.get("density") or {}).get("line") or "not computed yet"
    bl = (plan.get("budget") or {}).get("line") or ""
    L += ["", f"## Budget and density       {dl} · {bl}".rstrip(" ·"), ""]
    if plan.get("marks"):
        L += ["## The Writer's marks (wishes, may be dropped)", ""]
        L += [f"- beat {m.get('beat') or '?'}: {m.get('what')}: \"{m.get('quote')}\"" for m in plan["marks"]]
        L.append("")
    if plan.get("lessons"):
        L += ["## Lessons read before planning", ""] + [f"- {x['id']}: {x['rule']}" for x in plan["lessons"][-12:]]
        L.append("")
    shelf = [r["name"] for r in plan.get("shelf") or [] if r.get("origin") != "episode"]
    L += ["## The shelf (read after the beats)", "", ", ".join(shelf) or "empty", ""]
    return "\n".join(L)


def write(ep_dir: Path, plan: dict, version: int | None = None) -> Path:
    """Write the plan as the next version (or ``version``): JSON and Markdown. Returns the JSON path."""
    v = version or (max([version_of(p) for p in plans(ep_dir)], default=0) + 1)
    plan["version"] = v
    compute(plan, ep_dir)
    (ep_dir / "edit").mkdir(parents=True, exist_ok=True)
    p = ep_dir / "edit" / f"motion-plan-v{v:03d}.json"
    if version is None and p.exists():
        raise PlanError(f"{p.name} exists already")
    p.write_text(json.dumps(plan, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    md_of(p).write_text(render_md(plan), encoding="utf-8")
    return p


def cards_for(episode: str, p: Path) -> list[dict]:
    from .. import approvals
    rel = f"edit/{md_of(p).name}"
    return [c for c in approvals.list_cards(episode=episode) if c["kind"] == "motion-plan" and c.get("file") == rel]


def run_check(episode: str, p: Path | None = None) -> tuple[Path, list[str], list[str]]:
    """Validate a plan file (newest without ``p``). A version without a card gets its computed fields and its
    Markdown rewritten; a version a card shows is only read."""
    ep_dir = paths.episode_dir(episode)
    p = p or newest(ep_dir)
    if p is None:
        raise PlanError(f"no motion plan in {episode}: run `crewcut motion plan {episode}` first")
    plan = load(p)
    errors, warns = check(plan, ep_dir)
    if not cards_for(episode, p):
        p.write_text(json.dumps(plan, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        md_of(p).write_text(render_md(plan), encoding="utf-8")
    return p, errors, warns


# ---------------------------------------------------------------- the card


def _media(plan: dict, b: dict) -> dict:
    row = next((r for r in plan.get("shelf") or [] if r["name"] == str(b.get("piece") or "").partition("@")[0]
                and r.get("origin") != "episode"), {})
    return {"loop": row.get("loop"), "poster": row.get("poster")}


def card_data(plan: dict, p: Path, ep_dir: Path) -> dict:
    """What the ``motion-plan`` card carries: the three columns as rows with media, the beats left to the speaker,
    the density and budget lines and the cap."""
    rel = p.relative_to(ep_dir).as_posix()
    a, b_rows, c_rows, quiet = [], [], [], []
    for b in plan.get("beats") or []:
        base = {"row": f"beat:{b['n']}", "beat": b["n"], "time": tc(b.get("at") if b.get("at") is not None
                                                                     else b.get("start")),
                "purpose": b.get("purpose"), "picture": b.get("picture"), "struck": bool(b.get("struck"))}
        if b.get("column") == "a":
            a.append({**base, "piece": b.get("piece"), "params": b.get("params") or {}, "length_s": b.get("length_s"),
                      "render": render_of(plan, b), "cost_usd": float(b.get("cost_usd") or 0),
                      "media": _media(plan, b)})
        elif b.get("column") in ("b", "c"):
            (b_rows if b["column"] == "b" else c_rows).append({**base, "piece": b.get("piece"),
                                                               "length_s": b.get("length_s")})
        else:
            quiet.append(base)
    new = [{"row": f"new:{x.get('id')}", "id": x.get("id"), "beat": x.get("beat"), "brief": x.get("brief"),
            "why_new": x.get("why_new"), "kind": x.get("kind") or "full", "plates": int(x.get("plates") or 0),
            "effort": x.get("effort"), "cost_usd": float(x.get("cost_usd") or 0), "cap_usd": x.get("cap_usd"),
            "struck": bool(x.get("struck")),
            "beats": [r for r in b_rows if r["piece"] == x.get("id")]} for x in plan.get("new") or []]
    ups = [{"row": f"upgrade:{u.get('id')}", "id": u.get("id"), "upgrade": u.get("upgrade"),
            "source": u.get("source"), "effort": u.get("effort"), "cost_usd": float(u.get("cost_usd") or 0),
            "chosen": bool(u.get("chosen")), "struck": bool(u.get("struck")),
            "beats": [r for r in c_rows if r["piece"] == u.get("id")]} for u in plan.get("upgrades") or []]
    images = [r["media"]["poster"] for r in a if r["media"].get("poster") and not r["struck"]][:3]
    return {"motion_plan": {"version": plan.get("version"), "file": rel, "md": md_of(p).relative_to(ep_dir).as_posix(),
                            "json_sha256": sha256(p), "columns": {"a": a, "b": new, "c": ups}, "quiet": quiet,
                            "density": (plan.get("density") or {}).get("line"),
                            "budget": (plan.get("budget") or {}).get("line"),
                            "estimate_usd": (plan.get("budget") or {}).get("estimate_usd"),
                            "cap_usd": plan.get("cap_usd"), "bar": (plan.get("bar") or {}).get("episode"),
                            "short": bool(plan.get("short"))},
            "cap_usd": plan.get("cap_usd"), "images": images}


def _title(plan: dict) -> str:
    n = len(moving(plan))
    return f"Motion plan v{int(plan.get('version') or 0):03d}: {n} motion moment{'s' if n != 1 else ''}"


def _body(plan: dict) -> str:
    chosen = [u for u in plan.get("upgrades") or [] if u.get("chosen") and not u.get("struck")]
    return (f"{(plan.get('density') or {}).get('line')} · {(plan.get('budget') or {}).get('line')}. Upgrade: "
            + "; ".join(str(u.get("upgrade")) for u in chosen) + ". Shelf pieces may be built while this card is "
            "open; new pieces and upgrades wait for your yes. Tap a row to strike it.")


def propose_card(episode: str, p: Path | None = None, identity: str | None = None) -> dict:
    """Open the ``motion-plan`` card for a plan that passes the check (one card per video: an open one for an earlier
    version is closed as replaced)."""
    from .. import approvals, db, events
    ep_dir = paths.episode_dir(episode)
    p, errors, _w = run_check(episode, p)
    if errors:
        raise PlanError(f"{p.name} does not pass the check: " + "; ".join(errors))
    plan = load(p)
    for c in approvals.list_cards(episode=episode, status="open"):
        if c["kind"] == "motion-plan":
            db.update("cards", c["id"], status="declined", reason="replaced by a newer motion plan",
                      decided_at=db.now())
            old = approvals.get(c["id"])
            events.emit("card", episode=episode, identity=old["identity"], text=old["title"], data=approvals.view(old))
    return approvals.propose(episode, "edit", "motion-plan", _title(plan), body=_body(plan),
                             file=md_of(p).relative_to(ep_dir).as_posix(), data=card_data(plan, p, ep_dir),
                             identity=identity or "editor")


def strike(card_id: int, row: str, struck: bool = True) -> dict:
    """Tap to strike (or bring back) one row of an open ``motion-plan`` card: ``beat:N``, ``new:ID`` or
    ``upgrade:ID``. Writes the next plan version and points the same card at it. Returns the card."""
    from .. import approvals, db, events
    card = approvals.get(card_id)
    if card is None:
        raise KeyError(f"no card {card_id}")
    if card["kind"] != "motion-plan":
        raise PlanError("only a motion plan card has rows to strike")
    if card["status"] != "open":
        raise PlanError("this card is answered already")
    ep_dir = paths.episode_dir(card["episode"])
    src = ep_dir / ((card.get("data") or {}).get("motion_plan") or {}).get("file", "")
    plan = load(src)
    kind, _, rid = str(row).partition(":")
    hit = False
    if kind == "beat":
        for b in plan.get("beats") or []:
            if str(b.get("n")) == rid and b.get("column") in MOTION:
                b["struck"], hit = bool(struck), True
    elif kind in ("new", "upgrade"):
        items = plan.get("new" if kind == "new" else "upgrades") or []
        col = "b" if kind == "new" else "c"
        for x in items:
            if str(x.get("id")) == rid:
                x["struck"], hit = bool(struck), True
                for b in plan.get("beats") or []:
                    if b.get("column") == col and str(b.get("piece")) == rid:
                        b["struck"] = bool(struck)
    if not hit:
        raise PlanError(f"no row {row} with motion on this card")
    if struck and kind == "upgrade" and not any(u.get("chosen") and not u.get("struck")
                                                for u in plan.get("upgrades") or []):
        raise PlanError("This is the only chosen upgrade, and every video needs one. Say in the chat which other "
                        "upgrade to take instead.")
    errors, _w = check(plan, ep_dir)
    errors = [e for e in errors if not e.startswith(f"column (c) holds {UPGRADES[0]}")]
    if errors:
        raise PlanError("striking this row leaves the plan broken: " + "; ".join(errors))
    plan["based_on"] = src.name
    rows = set(plan.get("struck_rows") or [])
    plan["struck_rows"] = sorted(rows | {row} if struck else rows - {row})
    p = write(ep_dir, plan)
    md_rel = md_of(p).relative_to(ep_dir).as_posix()
    db.update("cards", card_id, file=md_rel, sha256=approvals.sha256(md_of(p)), data=card_data(plan, p, ep_dir),
              title=_title(plan), body=_body(plan))
    card = approvals.get(card_id)
    events.emit("card", episode=card["episode"], identity=card["identity"], text=card["title"],
                data=approvals.view(card))
    return card


def check_card(card: dict) -> None:
    """Before a yes on a ``motion-plan`` card: the JSON is still the one the card showed."""
    mp = (card.get("data") or {}).get("motion_plan") or {}
    p = paths.inside(paths.episode_dir(card["episode"]), mp.get("file", ""))
    if not p.is_file() or sha256(p) != mp.get("json_sha256"):
        raise ValueError("The motion plan changed after this card was made. Approving it would approve something you "
                         "did not see; the Editor makes a new version and a new card.")


# ---------------------------------------------------------------- the gate for the render path


def _plan_cards(episode: str) -> tuple[dict | None, dict | None]:
    """(newest accepted, newest open) ``motion-plan`` card of the episode."""
    from .. import approvals
    acc = opn = None
    for c in approvals.list_cards(episode=episode):
        if c["kind"] != "motion-plan":
            continue
        if c["status"] == "accepted":
            acc = c
        elif c["status"] == "open":
            opn = c
    return acc, opn


def _card_plan(ep_dir: Path, card: dict | None) -> tuple[dict | None, str | None]:
    if card is None:
        return None, None
    mp = (card.get("data") or {}).get("motion_plan") or {}
    try:
        p = paths.inside(ep_dir, mp.get("file", ""))
    except ValueError:
        return None, "the card names a file outside the episode"
    if not p.is_file():
        return None, f"{mp.get('file')} is missing"
    if sha256(p) != mp.get("json_sha256"):
        return None, f"{p.name} changed after card #{card['id']}; make a new version and a new card"
    return load(p), None


def _row_problem(plan: dict, e: dict) -> str | None:
    beat, col = e.get("beat"), e.get("column")
    row = next((b for b in plan.get("beats") or [] if str(b.get("n")) == str(beat)), None)
    v = f"motion plan v{int(plan.get('version') or 0):03d}"
    if row is None:
        return f"beat {beat} is not in {v}"
    if row.get("struck"):
        return f"beat {beat} was struck on the card"
    if row.get("column") != col:
        return f"it says column {col}, {v} has {row.get('column')} for beat {beat}"
    if col == "a":
        want = str(row.get("piece") or "").partition("@")[0]
        if str(e.get("scene") or "").partition("@")[0] != want:
            return f"it uses {e.get('scene') or 'no scene'}, beat {beat} of {v} says {want}"
    if col == "b" and e.get("kind") == "motion" and not e.get("source"):
        return f"column b is a piece built for this video (source motion/<id>/comp.jsx), beat {beat}"
    return None


def gated(plan_json: dict) -> list[dict]:
    """The inserts that need a row of the approved motion plan: every motion insert and every full-frame 2D or 3D
    insert (recordings, 2D overlays over the speaker and keywords do not)."""
    return [e for e in (plan_json or {}).get("inserts") or [] if isinstance(e, dict)
            and (e.get("kind") == "motion" or (e.get("kind") in ("2d", "3d") and not e.get("transparent")
                                               and e.get("scene") not in dens.KEYWORD_SCENES))]


def motion_gate(episode_dir: Path | str, plan_json: dict) -> list[str]:
    """Refusals for ``crewcut render plan``: motion inserts and full-frame 2D and 3D inserts without a row in an
    approved motion plan (motion plan 3.1 check 2). Each insert names its row with ``"beat"`` and ``"column"``; two
    full-frame inserts never share a row, so the plan counts every full-frame picture. Column (a) may also come from a
    plan whose card is still open (shelf pieces may be built meanwhile); columns (b) and (c) wait for the yes. An empty
    list means every insert may render. The caller skips this with ``--no-gate`` (tests only)."""
    ep_dir = Path(episode_dir)
    inserts = gated(plan_json)
    if not inserts:
        return []
    acc, opn = _plan_cards(ep_dir.name)
    approved, why_a = _card_plan(ep_dir, acc)
    pending, why_o = _card_plan(ep_dir, opn) if opn and (not acc or opn["id"] > acc["id"]) else (None, None)
    out = []
    rows_used: dict[str, str] = {}
    for e in inserts:
        iid = e.get("id")
        if e.get("beat") is None or e.get("column") not in MOTION:
            what = "motion insert" if e.get("kind") == "motion" else f"full-frame {str(e.get('kind')).upper()} insert"
            out.append(f"{iid}: no beat and column; every {what} comes from a row of the approved motion plan "
                       '("beat": N, "column": "a", "b" or "c")')
            continue
        if not e.get("transparent"):
            first = rows_used.setdefault(str(e.get("beat")), str(iid))
            if first != str(iid):
                out.append(f"{iid}: beat {e.get('beat')} is already the row of {first}; give every full-frame picture "
                           "its own row (split the beat: 12a, 12b), so the motion plan counts it")
                continue
        prob = _row_problem(approved, e) if approved else None
        if approved and prob is None:
            continue
        if pending and e.get("column") == "a" and _row_problem(pending, e) is None:
            continue
        if approved:
            out.append(f"{iid}: {prob}")
        elif pending:
            out.append(f"{iid}: column {e.get('column')} waits for your yes on the motion plan card #{opn['id']} "
                       "(only shelf pieces, column a, may be built meanwhile)"
                       if _row_problem(pending, e) is None else f"{iid}: {_row_problem(pending, e)}")
        elif why_a or why_o:
            out.append(f"{iid}: {why_a or why_o}")
        else:
            out.append(f"{iid}: no approved motion plan: run `crewcut motion plan {ep_dir.name}`, then its card")
    return out


def approved_cap(episode_dir: Path | str) -> float | None:
    """The money cap of the video's approved motion plan (the number on its motion-plan card), or None."""
    ep_dir = Path(episode_dir)
    acc, _ = _plan_cards(ep_dir.name)
    plan, _why = _card_plan(ep_dir, acc)
    if plan and plan.get("cap_usd"):
        return float(plan["cap_usd"])
    return None
