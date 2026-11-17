"""The quality ratchet: the bar only goes up (motion plan 3.8).

    brand/baseline.json "motion"      the best video so far for motion: episode, its report, 3 to 6 named strengths with
                                      frames, measured values, history. Moves only through a ``baseline`` card yes, and
                                      never down.
    review/motion-report-vNNN.md/json the video against the bar: better, behind, upgrades landed, proposals. Written by
                                      ``crewcut motion report`` from what the Critic fills in (``--skeleton`` gives
                                      the form); it fails unless it appends at least one lesson.
    brand/rules/motion.md             the lessons (``lessons.py``)
    brand/references/motion/          the references (``references.py``)

The Critic writes the report after the user has seen the video. If nothing is named better than the bar, the version
goes back to the Editor once; if the second try is still not better, the Showrunner tells the user plainly.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .. import brand, paths
from . import density as dens
from . import director, library
from . import lessons as lessons_mod
from . import references as refs_mod

HIGHER_IS_BETTER = ("caused_share", "upgrades_landed_share", "retention_held_share")
LOWER_IS_BETTER = ("critic_errors",)
STRENGTHS = (3, 6)
VERDICTS = {"better": "better than the bar", "first": "the first motion report: it can become the bar",
            "back": "back to the Editor: nothing is named better than the bar, or the bar's strengths got worse",
            "tell": "not better after the second try: the Showrunner tells the user plainly on the preview card"}
REPORT = re.compile(r"motion-report-v(\d{3,})\.json")


class ReportError(ValueError):
    """The report cannot be written. The message says what is missing."""


def today() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


# ---------------------------------------------------------------- the bar


def bar() -> dict | None:
    return director.bar()


def _baseline_path() -> Path:
    from .. import approvals
    return approvals.ensure_user_pack() / "baseline.json"


def _write_motion_block(block: dict) -> None:
    p = _baseline_path()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {"schema": 1}
    data["motion"] = block
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    tmp.replace(p)


# ---------------------------------------------------------------- measured values


def _newest(folder: Path, pattern: str) -> Path | None:
    files = sorted(folder.glob(pattern), key=lambda f: (len(f.stem), f.stem))
    return files[-1] if files else None


def measured(ep_dir: Path) -> dict:
    """What the machine can count for a finished video: motion moments, full-frame, overlays, custom pieces and heroes
    from the newest edit plan; the Critic's errors from the newest review bundle; retention from
    ``review/retention.json`` when it exists."""
    out: dict[str, Any] = {}
    plan_p = _newest(ep_dir / "edit", "plan-v*.json")
    if plan_p:
        try:
            plan = json.loads(plan_p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            plan = {}
        ms = [e for e in plan.get("inserts") or [] if isinstance(e, dict) and e.get("kind") == "motion"]
        out.update(plan=plan_p.name, motion_moments=len(ms), full_frame=sum(1 for e in ms if not e.get("transparent")),
                   overlays=sum(1 for e in ms if e.get("transparent")), custom=sum(1 for e in ms if e.get("source")),
                   heroes=sum(1 for e in ms if str(e.get("scene") or "").partition("@")[0] in dens.HEROES))
    bundles = sorted((ep_dir / "review").glob("motion-v*/bundle.json"), key=lambda f: (len(f.parent.name),
                                                                                       f.parent.name))
    b = bundles[-1] if bundles else None
    if b:
        try:
            data = json.loads(b.read_text(encoding="utf-8"))
            out["critic_errors"] = sum(1 for f in data.get("findings") or [] if isinstance(f, dict)
                                       and f.get("level") == "ERROR" and f.get("insert"))
            out["bundle"] = str(b.parent.relative_to(ep_dir))
        except (OSError, ValueError):
            pass
    r = ep_dir / "review" / "retention.json"
    if r.is_file():
        try:
            s = json.loads(r.read_text(encoding="utf-8")).get("summary") or {}
            if s.get("held_share") is not None:
                out["retention_held_share"] = s["held_share"]
        except (OSError, ValueError):
            pass
    return out


# ---------------------------------------------------------------- the report


def reports(ep_dir: Path) -> list[Path]:
    found = [(int(m.group(1)), p) for p in (ep_dir / "review").glob("motion-report-v*.json")
             if (m := REPORT.fullmatch(p.name))]
    return [p for _n, p in sorted(found)]


def approved_plan(ep_dir: Path) -> dict | None:
    acc, _ = director._plan_cards(ep_dir.name)
    plan, _why = director._card_plan(ep_dir, acc)
    return plan


def skeleton(episode: str) -> dict:
    """The form the Critic fills (``crewcut motion report <episode> --skeleton``): the chosen upgrades of the approved
    motion plan, the bar's strengths to compare with, the references the plan used, the machine's measured values."""
    ep_dir = paths.episode_dir(episode)
    plan = approved_plan(ep_dir) or {}
    b = bar()
    chosen = [u for u in plan.get("upgrades") or [] if u.get("chosen") and not u.get("struck")]
    return {
        "episode": episode, "bar": (b or {}).get("episode"),
        "bar_strengths": (b or {}).get("strengths") or [],
        "better": [{"what": "", "time": "", "frame": "", "against": "which strength of the bar"}],
        "behind": [{"what": "", "against": "bar or a reference id", "time": "", "frame": ""}],
        "upgrades": [{"id": u.get("id"), "upgrade": u.get("upgrade"), "landed": None, "evidence": ""} for u in chosen],
        "pieces": [{"insert": "", "reference_better": ""}],
        "lessons": [{"rule": "", "time": "", "frame": "", "source": "review"}],
        "strengths": [{"name": "", "time": "", "frame": ""}],
        "proposals": {"library": [], "baseline": False},
        "measured": measured(ep_dir),
    }


def _filled(items: Any, key: str) -> list[dict]:
    return [x for x in items or [] if isinstance(x, dict) and str(x.get(key) or "").strip()]


def _tc(t: Any) -> str:
    if isinstance(t, (int, float)) and not isinstance(t, bool):
        return dens.tc(t)
    return str(t or "").strip()


def report(episode: str, data: dict, propose: bool = True, identity: str | None = None) -> dict:
    """Write ``review/motion-report-vNNN.md`` and ``.json`` from the Critic's ``data`` (the filled skeleton), append
    its lessons to ``brand/rules/motion.md``, add review notes to the library, and propose the baseline card when this
    video is better (or is the first). Raises ReportError (nothing written) when no lesson is given, a lesson lacks
    evidence, or a chosen upgrade has no landed/not-landed answer."""
    ep_dir = paths.episode_dir(episode)
    if not (ep_dir / "project.json").is_file():
        raise ReportError(f"no episode {episode}")
    b = bar()
    plan = approved_plan(ep_dir) or {}
    better = _filled(data.get("better"), "what")
    behind = _filled(data.get("behind"), "what")
    behind_bar = [x for x in behind if str(x.get("against") or "bar").strip().lower() in ("bar", "baseline", "")]
    lessons_in = _filled(data.get("lessons"), "rule")
    if not lessons_in:
        raise ReportError("A finished video adds at least one lesson to brand/rules/motion.md; the report is not "
                          "written without one.")
    problems = []
    for x in lessons_in:
        ev = {"episode": x.get("episode") or episode, "time": x.get("time"), "frame": x.get("frame"),
              "card": x.get("card")}
        src = x.get("source") or "review"
        if src == "retention":
            problems.append(f"lesson '{x['rule'][:40]}': retention findings become lessons only through "
                            "`crewcut youtube retention` after they repeat in 3 videos")
        problems += [f"lesson '{x['rule'][:40]}': {p}" for p in lessons_mod.check(x["rule"], ev, src)]
    chosen = [u for u in plan.get("upgrades") or [] if u.get("chosen") and not u.get("struck")]
    answers = {str(u.get("id")): u for u in data.get("upgrades") or [] if isinstance(u, dict)}
    for u in chosen:
        a = answers.get(str(u.get("id")))
        if not a or not isinstance(a.get("landed"), bool):
            problems.append(f"upgrade {u.get('id')}: say whether it landed (true or false) with evidence")
        elif not str(a.get("evidence") or "").strip():
            problems.append(f"upgrade {u.get('id')}: give the evidence (time and frame)")
    strengths = _filled(data.get("strengths"), "name")
    for s in strengths:
        if not s.get("frame"):
            problems.append(f"strength '{s['name'][:40]}': name its frame")
    if problems:
        raise ReportError("; ".join(problems))

    earlier = reports(ep_dir)
    if b is None or b.get("episode") == episode:
        verdict = "first" if b is None else ("better" if better and not behind_bar else "back")
    elif better and not behind_bar:
        verdict = "better"
    else:
        tries = 0
        for p in earlier:
            try:
                if json.loads(p.read_text(encoding="utf-8")).get("verdict") in ("back", "tell"):
                    tries += 1
            except (OSError, ValueError):
                continue
        verdict = "tell" if tries else "back"

    appended = []
    for x in lessons_in:
        ev = {"episode": x.get("episode") or episode, "time": x.get("time"), "frame": x.get("frame"),
              "card": x.get("card")}
        appended.append(lessons_mod.append(x["rule"], ev, x.get("source") or "review"))

    meas = {**measured(ep_dir), **{k: v for k, v in (data.get("measured") or {}).items() if v is not None}}
    if chosen:
        landed = sum(1 for u in chosen if answers.get(str(u.get("id")), {}).get("landed") is True)
        meas["upgrades_landed_share"] = round(landed / len(chosen), 3)
    retention = None
    rp = ep_dir / "review" / "retention.json"
    if rp.is_file():
        try:
            retention = json.loads(rp.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            retention = None
    version = (max([int(REPORT.fullmatch(p.name).group(1)) for p in earlier], default=0) + 1)
    upgrades = [{"id": u.get("id"), "upgrade": u.get("upgrade"),
                 "landed": answers.get(str(u.get("id")), {}).get("landed"),
                 "evidence": answers.get(str(u.get("id")), {}).get("evidence")} for u in chosen]
    pieces = _filled(data.get("pieces"), "reference_better")
    props = data.get("proposals") if isinstance(data.get("proposals"), dict) else {}
    lib_props = [x for x in props.get("library") or [] if isinstance(x, dict) and x.get("insert")]
    summary = {
        "better": "; ".join(f"{x['what']} ({_tc(x.get('time'))})" for x in better) or "nothing named",
        "behind": "; ".join(f"{x['what']} (against {x.get('against') or 'the bar'})" for x in behind) or "nothing named",
        "next": (VERDICTS[verdict] if verdict in ("back", "tell") else
                 "; ".join([*(f"promote {x['insert']}" + (f" as {x['name']}" if x.get("name") else "")
                              for x in lib_props),
                            *([f"propose {episode} as the new bar"] if props.get("baseline") or verdict == "first"
                              else [])]) or "carry the lessons into the next motion plan"),
    }
    out = {
        "schema": 1, "episode": episode, "version": version, "date": today(), "bar": (b or {}).get("episode"),
        "verdict": verdict, "verdict_text": VERDICTS[verdict], "better": better, "behind": behind,
        "behind_bar": behind_bar, "upgrades": upgrades, "pieces": pieces, "strengths": strengths,
        "lessons": appended, "proposals": {"library": lib_props, "baseline": bool(props.get("baseline")),
                                           "merge_lessons": lessons_mod.needs_merge()},
        "measured": meas, "bar_measured": (b or {}).get("measured") or {}, "retention": retention,
        "motion_plan": plan.get("version"), "summary": summary,
    }
    (ep_dir / "review").mkdir(parents=True, exist_ok=True)
    jp = ep_dir / "review" / f"motion-report-v{version:03d}.json"
    jp.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    jp.with_suffix(".md").write_text(render_md(out), encoding="utf-8")
    _library_notes(ep_dir, data)
    out["file"] = jp.relative_to(ep_dir).as_posix()
    if propose and verdict in ("better", "first") and (props.get("baseline") or verdict == "first"):
        try:
            card = propose_baseline(episode, jp, identity=identity)
            out["baseline_card"] = card["id"] if card else None
        except ReportError as e:
            out["baseline_card"] = None
            out["baseline_refused"] = str(e)
    if propose and out["proposals"]["merge_lessons"]:
        from .. import approvals
        n = len(lessons_mod.read())
        c = approvals.propose(episode, "edit", "other", f"Merge the motion lessons ({n} lines, above "
                              f"{lessons_mod.MERGE_ABOVE})", body="The Critic merges duplicates and shows the merged "
                              "file before it replaces the old one.", data={"motion_merge": True, "lessons": n},
                              identity=identity or "critic")
        out["merge_card"] = c["id"]
    return out


def _library_notes(ep_dir: Path, data: dict) -> None:
    """Review notes on the shelf: per library template the plan used, where and how it reviewed."""
    plan_p = _newest(ep_dir / "edit", "plan-v*.json")
    if not plan_p:
        return
    try:
        plan = json.loads(plan_p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    said = {str(x.get("insert")): x.get("reference_better") for x in data.get("pieces") or [] if isinstance(x, dict)}
    for e in plan.get("inserts") or []:
        if not isinstance(e, dict) or e.get("kind") != "motion" or not e.get("scene"):
            continue
        name = str(e["scene"]).partition("@")[0]
        _b, errors = library.last_bundle(ep_dir, str(e.get("id")))
        text = f"used in {ep_dir.name} ({e.get('id')}): review {errors} error(s)"
        if said.get(str(e.get("id"))):
            text += f"; the reference still does better: {said[str(e.get('id'))]}"
        library.add_note(name, text, "review")


def render_md(r: dict) -> str:
    L = [f"# Motion report v{r['version']:03d}: {r['episode']}          bar: {r.get('bar') or 'none yet'}", "",
         f"Verdict: **{r['verdict_text']}**", "",
         f"Better: {r['summary']['better']}  ", f"Behind: {r['summary']['behind']}  ", f"Next: {r['summary']['next']}",
         "", "## Better (named, with time and frame)", ""]
    L += [f"- {_tc(x.get('time'))} {x['what']} (against: {x.get('against') or 'the bar'}), frame `{x.get('frame')}`"
          for x in r["better"]] or ["- nothing named"]
    L += ["", "## Behind (against the bar and against each reference used)", ""]
    L += [f"- against {x.get('against') or 'the bar'}: {x['what']}" + (f" ({_tc(x.get('time'))})" if x.get("time")
                                                                         else "") for x in r["behind"]] or ["- nothing"]
    L += ["", "## Upgrades landed", ""]
    L += [f"- {u['id']} {u.get('upgrade') or ''}: {'landed' if u['landed'] else 'not landed'}. Evidence: "
          f"{u.get('evidence')}" for u in r["upgrades"]] or ["- no chosen upgrade in an approved motion plan"]
    L += ["", "## Per piece: what the reference still does better", ""]
    L += [f"- {x['insert']}: {x['reference_better']}" for x in r["pieces"]] or ["- none written"]
    L += ["", "## Proposals", ""]
    L += [f"- library: {x['insert']}" + (f" as {x['name']}" if x.get("name") else "") + (f" ({x['why']})"
                                                                                         if x.get("why") else "")
          for x in r["proposals"]["library"]]
    if r["proposals"]["baseline"] or r["verdict"] == "first":
        L.append(f"- baseline: {r['episode']} as the new bar (a card asks the user)")
    if r["proposals"]["merge_lessons"]:
        L.append(f"- lessons: above {lessons_mod.MERGE_ABOVE} lines, merge duplicates (a card asks the user)")
    L.append("- lessons appended: " + ", ".join(x["id"] for x in r["lessons"]))
    L += ["", "## Measured", "", "| value | this video | bar |", "|---|---|---|"]
    keys = sorted(set(r["measured"]) | set(r["bar_measured"]))
    L += [f"| {k} | {r['measured'].get(k, '-')} | {r['bar_measured'].get(k, '-')} |" for k in keys]
    L += ["", "## Retention", ""]
    ret = r.get("retention")
    if not ret:
        L.append("no retention data")
    else:
        L.append(f"Fetched {ret.get('fetched')}. A hint, not proof: single findings are 'watch'.")
        L += [f"- {m['id']} ({m.get('scene') or 'custom'}) {dens.tc(m['start'])}: {m['label']}, "
              f"{m['delta'] * 100:+.1f} points against the video's own slope ({m['status']})"
              for m in ret.get("moments") or []]
    L.append("")
    return "\n".join(L)


# ---------------------------------------------------------------- the baseline card


def _never_down(old: dict, new: dict) -> list[str]:
    out = []
    for k in HIGHER_IS_BETTER:
        if isinstance(old.get(k), (int, float)) and isinstance(new.get(k), (int, float)) and new[k] < old[k] - 1e-9:
            out.append(f"{k} {new[k]} < {old[k]}")
    for k in LOWER_IS_BETTER:
        if isinstance(old.get(k), (int, float)) and isinstance(new.get(k), (int, float)) and new[k] > old[k] + 1e-9:
            out.append(f"{k} {new[k]} > {old[k]}")
    return out


def _report_ok(rep: dict) -> str | None:
    if rep.get("verdict") not in ("better", "first"):
        return f"its report says: {VERDICTS.get(rep.get('verdict'), rep.get('verdict'))}"
    if rep.get("verdict") == "better" and (not rep.get("better") or rep.get("behind_bar")):
        return "its report names nothing better, or a strength of the bar got worse"
    return None


def propose_baseline(episode: str, report_path: Path | str, identity: str | None = None) -> dict | None:
    """Open the ``baseline`` card: this video becomes the bar. Refuses (ReportError) when the report does not say it
    is better than the current bar, or when a measured value is worse (the bar never moves down)."""
    from .. import approvals
    ep_dir = paths.episode_dir(episode)
    rp = Path(report_path)
    rp = rp if rp.is_absolute() else ep_dir / rp
    rep = json.loads(rp.read_text(encoding="utf-8"))
    b = bar()
    if b and b.get("episode") == episode:
        raise ReportError(f"{episode} is the bar already")
    why = _report_ok(rep)
    if why:
        raise ReportError(f"{episode} cannot become the bar: {why}")
    down = _never_down((b or {}).get("measured") or {}, rep.get("measured") or {})
    if down:
        raise ReportError(f"{episode} measures worse than the bar ({'; '.join(down)}); the bar never moves down")
    strengths = rep.get("strengths") or []
    if not STRENGTHS[0] <= len(strengths) <= STRENGTHS[1]:
        raise ReportError(f"the bar needs {STRENGTHS[0]} to {STRENGTHS[1]} named strengths with frames; the report has "
                          f"{len(strengths)}")
    md = rp.with_suffix(".md")
    images = [f"/api/files/{episode}/{s['frame']}" for s in strengths if (ep_dir / str(s.get("frame"))).is_file()][:3]
    data = {"old": {"episode": (b or {}).get("episode"), "strengths": (b or {}).get("strengths") or [],
                    "measured": (b or {}).get("measured") or {}},
            "new": {"episode": episode, "report": rp.relative_to(ep_dir).as_posix(), "strengths": strengths,
                    "measured": rep.get("measured") or {}, "better": rep.get("better") or []},
            "report_sha256": sha256(rp), "images": images}
    title = (f"Make {episode} the motion bar?" if b is None else
             f"Raise the motion bar from {b['episode']} to {episode}?")
    body = ("Better: " + "; ".join(x["what"] for x in rep.get("better") or []) if rep.get("better") else
            "The first video with a motion report becomes the bar.")
    return approvals.propose(episode, "edit", "baseline", title, body=body, file=md.relative_to(ep_dir).as_posix(),
                             data=data, identity=identity or "critic")


def check_baseline_card(card: dict) -> None:
    """Before a yes on a ``baseline`` card: the bar has not moved since, the report is unchanged and still says
    better, and nothing measured is worse. Raises ValueError otherwise (the bar stays)."""
    d = card.get("data") or {}
    old, new = d.get("old") or {}, d.get("new") or {}
    b = bar()
    if (b or {}).get("episode") != old.get("episode"):
        raise ValueError("The bar moved since this card was made; this video would be compared with the wrong bar. "
                         "The Critic writes a new report against the current bar.")
    ep_dir = paths.episode_dir(str(new.get("episode")))
    rp = paths.inside(ep_dir, str(new.get("report") or ""))
    if not rp.is_file() or sha256(rp) != d.get("report_sha256"):
        raise ValueError("The motion report changed after this card was made; the Critic proposes again.")
    rep = json.loads(rp.read_text(encoding="utf-8"))
    why = _report_ok(rep)
    if why:
        raise ValueError(f"This video cannot become the bar: {why}.")
    down = _never_down((b or {}).get("measured") or {}, rep.get("measured") or {})
    if down:
        raise ValueError(f"The bar never moves down: {'; '.join(down)}.")


def apply_baseline(card: dict) -> dict:
    """The yes of a ``baseline`` card: the ``motion`` block of ``brand/baseline.json`` points at the new video. The
    only place the motion bar is ever written."""
    check_baseline_card(card)
    d = card.get("data") or {}
    new = d["new"]
    b = bar()
    history = list((b or {}).get("history") or [])
    if b:
        history.append({"episode": b.get("episode"), "since": b.get("since"), "card": b.get("card")})
    block = {"episode": new["episode"], "report": new["report"], "since": today(), "card": card.get("id"),
             "strengths": new.get("strengths") or [], "measured": new.get("measured") or {},
             "frames": [{"file": f"episodes/{new['episode']}/{s['frame']}", "label": s.get("name")}
                        for s in new.get("strengths") or [] if s.get("frame")],
             "history": history}
    _write_motion_block(block)
    return block


def report_lines(ep_dir: Path) -> dict | None:
    """The newest report's three lines for the episode view: better, behind, next."""
    rs = reports(ep_dir)
    if not rs:
        return None
    try:
        r = json.loads(rs[-1].read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return {**(r.get("summary") or {}), "verdict": r.get("verdict"), "file": f"review/{rs[-1].name}",
            "url": f"/api/files/{ep_dir.name}/review/{rs[-1].with_suffix('.md').name}"}


def brand_snapshot() -> dict:
    """The bar, the lessons and the references for the UI (``GET /api/motion/ratchet``)."""
    pack = brand.load()
    b = pack.value("baseline.motion")
    return {"bar": b if isinstance(b, dict) and b.get("episode") else None,
            "lessons": lessons_mod.read(), "merge_needed": lessons_mod.needs_merge(),
            "references": refs_mod.read()}
