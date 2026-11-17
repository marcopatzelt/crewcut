"""Audience retention from the YouTube Analytics API, mapped onto a video's motion moments (motion plan 3.8, step 5).

``crewcut youtube retention <episode>`` asks ``reports.query`` for ``audienceWatchRatio`` by
``elapsedVideoTimeRatio`` (the share of the audience still watching at each 1 % of the video) and measures, for every
motion moment of the episode's edit plan, how the curve changed over the moment and the 5 s after it, against the
video's own slope around it. The result goes to ``review/retention.json``, into the motion report and into the
library notes ("number_roll: held viewers in 3 of 4 uses").

This is a hint, not proof: one video is a small sample, and what a moment says matters more than its form. Every
finding is "watch" until the same finding (template and direction) repeats in at least ``REPEATS`` videos; then it
becomes a lesson in ``brand/rules/motion.md``. No data (a new video, a Short without a curve, an account without the
permission): "no retention data", and nothing is written.

Needs the read-only scope ``yt-analytics.readonly`` (``auth.SCOPES``). Built and tested against a recorded answer;
unproven against a real channel until a published video has data.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from .. import paths

SCOPE = "https://www.googleapis.com/auth/yt-analytics.readonly"
AFTER_S = 5.0          # the moment and the 5 s after it
SLOPE_S = 20.0         # the video's own slope: the 20 s before the moment (after it, when the moment is early)
HELD = 0.01            # 1 point of the audience against the slope counts as a change
REPEATS = 3            # a finding becomes a lesson when it repeats in this many videos
NO_DATA = "no retention data"


class NoData(LookupError):
    """There is no curve for this video (yet). Nothing is written."""


def query_params(video_id: str, start: str, end: str) -> dict:
    return {"ids": "channel==MINE", "startDate": start, "endDate": end,
            "metrics": "audienceWatchRatio,relativeRetentionPerformance", "dimensions": "elapsedVideoTimeRatio",
            "filters": f"video=={video_id}", "sort": "elapsedVideoTimeRatio"}


def api_query(params: dict) -> dict:
    """The real call (``youtubeAnalytics`` v2 ``reports.query``) with the studio's YouTube login."""
    from googleapiclient.discovery import build

    from . import auth
    creds = auth.credentials()
    granted = set(getattr(creds, "granted_scopes", None) or getattr(creds, "scopes", None) or [])
    if granted and SCOPE not in granted:
        raise PermissionError("Your YouTube login does not include the read-only analytics permission. Sign in once "
                              "more (`crewcut youtube auth`) and allow it.")
    return build("youtubeAnalytics", "v2", credentials=creds, cache_discovery=False).reports().query(
        **params).execute()


def curve(resp: dict) -> list[tuple[float, float]]:
    """``[(elapsed ratio, audience watch ratio)]`` from a ``reports.query`` answer, sorted by time."""
    heads = [str(h.get("name")) for h in (resp or {}).get("columnHeaders") or []]
    if "elapsedVideoTimeRatio" not in heads or "audienceWatchRatio" not in heads:
        return []
    i, j = heads.index("elapsedVideoTimeRatio"), heads.index("audienceWatchRatio")
    out = []
    for row in (resp or {}).get("rows") or []:
        try:
            out.append((float(row[i]), float(row[j])))
        except (IndexError, TypeError, ValueError):
            continue
    return sorted(out)


def at(c: list[tuple[float, float]], x: float) -> float:
    """The curve at elapsed ratio ``x`` (linear between points, flat beyond the ends)."""
    if x <= c[0][0]:
        return c[0][1]
    for (x0, y0), (x1, y1) in zip(c, c[1:], strict=False):
        if x0 <= x <= x1:
            return y0 if x1 == x0 else y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return c[-1][1]


def measure(c: list[tuple[float, float]], duration_s: float, start: float, end: float) -> dict:
    """Change of the audience over a moment and the 5 s after it, against the video's own slope around it."""
    def r(t: float) -> float:
        return at(c, min(1.0, max(0.0, t / duration_s)))
    a, b = start, min(duration_s, end + AFTER_S)
    change = r(b) - r(a)
    s0, s1 = max(0.0, a - SLOPE_S), a
    if s1 - s0 < 3.0:                                  # an early moment: the slope after it
        s0, s1 = b, min(duration_s, b + SLOPE_S)
    slope = (r(s1) - r(s0)) / (s1 - s0) if s1 - s0 > 1e-6 else 0.0
    expected = slope * (b - a)
    delta = change - expected
    label = "held" if delta >= HELD else ("dropped" if delta <= -HELD else "flat")
    return {"at_start": round(r(a), 4), "at_end": round(r(b), 4), "change": round(change, 4),
            "expected": round(expected, 4), "delta": round(delta, 4), "label": label}


def moments(ep_dir: Path) -> tuple[list[dict], float | None, str | None]:
    """The motion moments of the newest edit plan (seconds) and the video's length from the plan."""
    from ..motion import density as dens
    plans = sorted((ep_dir / "edit").glob("plan-v*.json"), key=lambda p: (len(p.stem), p.stem))
    if not plans:
        return [], None, None
    plan = json.loads(plans[-1].read_text(encoding="utf-8"))
    words: list[dict] = []
    if plan.get("words") and (ep_dir / plan["words"]).is_file():
        words = dens.norm_words(json.loads((ep_dir / plan["words"]).read_text(encoding="utf-8")))
    out = []
    ends = [w["e"] for w in words[-1:]]
    for e in plan.get("inserts") or []:
        if not isinstance(e, dict):
            continue
        s, t = dens.span(e, words)
        if t is not None:
            ends.append(t)
        if e.get("kind") == "motion" and s is not None and t is not None:
            out.append({"id": str(e.get("id")), "scene": str(e.get("scene") or "").partition("@")[0] or None,
                        "source": e.get("source"), "start": s, "end": t, "full": not e.get("transparent")})
    total = (max(ends) + float(plan.get("tail") or 0)) if ends else None
    return out, total, plans[-1].name


def upload(ep_dir: Path) -> dict:
    """``export/upload-result.json`` (video id and upload time), or {}."""
    try:
        d = json.loads((ep_dir / "export" / "upload-result.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return d if isinstance(d, dict) else {}


def key(m: dict) -> str:
    return f"{m.get('scene') or 'custom'}:{m['label']}"


def _other_findings(episode: str) -> dict[str, set[str]]:
    """Finding key -> episodes (other than this one) whose retention.json has it."""
    out: dict[str, set[str]] = {}
    for p in paths.episodes_dir().glob("*/review/retention.json"):
        ep = p.parent.parent.name
        if ep == episode:
            continue
        try:
            for m in json.loads(p.read_text(encoding="utf-8")).get("moments") or []:
                if m.get("label") in ("held", "dropped"):
                    out.setdefault(key(m), set()).add(ep)
        except (OSError, ValueError):
            continue
    return out


def retention(episode: str, query: Callable[[dict], dict] | None = None, video: str | None = None,
              duration_s: float | None = None, today: date | None = None) -> dict:
    """Fetch the curve, map it onto the motion moments, write ``review/retention.json``, add library notes, and turn
    a finding that repeats in ``REPEATS`` videos into a lesson. Raises NoData when there is no curve (nothing is
    written then)."""
    ep_dir = paths.episode_dir(episode)
    query = query or api_query
    up = upload(ep_dir)
    vid = video or up.get("video_id")
    if not vid:
        raise NoData("the episode has no uploaded video (export/upload-result.json)")
    ms, plan_total, plan_name = moments(ep_dir)
    total = duration_s or plan_total
    if not total:
        raise NoData("the length of the video is not known (no edit plan)")
    day = today or datetime.now(UTC).date()
    start = str(up.get("at") or "")[:10] if up.get("video_id") == vid else ""
    resp = query(query_params(vid, start or (day - timedelta(days=3650)).isoformat(), day.isoformat()))
    c = curve(resp)
    if len(c) < 2:
        raise NoData(NO_DATA)
    others = _other_findings(episode)
    rows = []
    for m in ms:
        r = {**m, **measure(c, total, m["start"], m["end"])}
        k = key(r)
        seen = len(others.get(k, set())) + 1 if r["label"] != "flat" else 0
        r["videos"] = seen
        r["status"] = "lesson" if seen >= REPEATS else "watch"
        rows.append(r)
    changed = [r for r in rows if r["label"] != "flat"]
    out = {"schema": 1, "episode": episode, "video_id": vid, "fetched": day.isoformat(), "plan": plan_name,
           "duration_s": round(total, 2), "points": len(c), "moments": rows,
           "summary": {"moments": len(rows), "held": sum(1 for r in rows if r["label"] == "held"),
                       "dropped": sum(1 for r in rows if r["label"] == "dropped"),
                       "held_share": round(sum(1 for r in rows if r["label"] == "held") / len(rows), 3) if rows
                       else None,
                       "note": "a hint, not proof: single findings are 'watch'"},
           "lessons": []}
    (ep_dir / "review").mkdir(parents=True, exist_ok=True)
    (ep_dir / "review" / "retention.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n",
                                                       encoding="utf-8")
    _notes(rows, episode)
    out["lessons"] = _lessons(changed, episode, others)
    if out["lessons"]:
        (ep_dir / "review" / "retention.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n",
                                                           encoding="utf-8")
    return out


def _notes(rows: list[dict], episode: str) -> None:
    """Per library template: how often it held viewers over all videos with retention data."""
    from ..motion import library
    scenes = {r["scene"] for r in rows if r.get("scene")}
    if not scenes:
        return
    tally: dict[str, list[str]] = {s: [] for s in scenes}
    for p in paths.episodes_dir().glob("*/review/retention.json"):
        try:
            for m in json.loads(p.read_text(encoding="utf-8")).get("moments") or []:
                if m.get("scene") in tally:
                    tally[m["scene"]].append(m.get("label"))
        except (OSError, ValueError):
            continue
    for s, labels in tally.items():
        held = sum(1 for x in labels if x == "held")
        library.add_note(s, f"retention: held viewers in {held} of {len(labels)} uses (a hint, not proof)",
                         "retention")


def _lessons(changed: list[dict], episode: str, others: dict[str, set[str]]) -> list[dict]:
    """A finding seen in ``REPEATS`` videos becomes one lesson (once)."""
    from ..motion import lessons
    out = []
    have = " ".join(x["rule"] for x in lessons.read() if x.get("source") == "retention")
    for r in changed:
        if r["status"] != "lesson":
            continue
        k = key(r)
        if f"[{k}]" in have:
            continue
        verb = "holds viewers" if r["label"] == "held" else "loses viewers"
        eps = sorted(others.get(k, set()) | {episode})
        rule = (f"{r.get('scene') or 'A custom piece'} {verb} over its moment and the 5 s after, against the video's "
                f"own slope, in {len(eps)} videos [{k}]")
        frame = next(iter(sorted((paths.episode_dir(episode) / "render" / "inserts").glob(f"{r['id']}-*"))), None)
        ev = {"episode": ", ".join(eps), "time": r["start"],
              "frame": frame.relative_to(paths.episode_dir(episode)).as_posix() if frame else f"edit plan {r['id']}"}
        out.append(lessons.append(rule, ev, "retention"))
        have += f" [{k}]"
    return out


def lines(res: dict) -> list[str]:
    """Plain lines for the command line."""
    from ..motion import density as dens
    out = [f"retention of {res['video_id']} ({res['points']} points, fetched {res['fetched']}): "
           f"{res['summary']['held']} held, {res['summary']['dropped']} dropped of {res['summary']['moments']} "
           "motion moments. A hint, not proof."]
    for m in res["moments"]:
        out.append(f"  {m['id']:<6} {dens.tc(m['start'])}  {m.get('scene') or 'custom':<14} {m['label']:<8} "
                   f"{m['delta'] * 100:+.1f} points against the slope  ({m['status']}"
                   + (f", seen in {m['videos']} videos" if m["videos"] > 1 else "") + ")")
    for x in res.get("lessons") or []:
        out.append(f"  lesson {x['id']}: {x['rule']}")
    return out
