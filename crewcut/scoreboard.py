"""The scoreboard per show format: which formats win on this channel, from measured results only.

Episodes are grouped by `project.show_format` (else `form`). Per episode it takes the newest
`review/results-*.json` (written by `crewcut youtube results`): views, average view percentage and subscribers
gained per 1,000 views. Shorts without such a file count with their newest row in `studio/shorts.tsv` (column
`form`). The retention per unit (`analytics/retention-units.json`) adds the median drop per minute of the units when
it exists. Click-through rate is not in the YouTube Analytics API: it shows as missing unless the episode has
`analytics/ctr.json` (`{"ctr": 0.051, "impressions": 12000}`, copied from YouTube Studio).

Verdict hint per format: "more of this" when it has at least two measured episodes and beats the channel median on
two of three metrics (median views, median view percentage, subscribers per 1,000 views); "too little data" below
two measured episodes; else "watch". A hint, not a rule.
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path

from . import paths

MIN_EPISODES = 2
VERDICTS = {"more": "more of this", "thin": "too little data", "watch": "watch"}


def _num(v) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None


def _json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _newest_result(ep: Path) -> dict | None:
    best = None
    for p in sorted((ep / "review").glob("results-*.json")):
        r = _json(p)
        if not isinstance(r, dict) or not isinstance(r.get("metrics"), dict):
            continue
        if best is None or str(r.get("fetched_at", "")) >= str(best.get("fetched_at", "")):
            best = r
    return best


def _retention(ep: Path) -> float | None:
    r = _json(ep / "analytics" / "retention-units.json")
    if not isinstance(r, dict) or not r.get("measurements"):
        return None
    units = [u for u in (r["measurements"][-1].get("units") or []) if u.get("kind") == "unit"]
    drops = [d for d in (_num(u.get("drop_per_min")) for u in units) if d is not None]
    return round(statistics.median(drops), 1) if drops else None


def _ctr(ep: Path) -> dict | None:
    r = _json(ep / "analytics" / "ctr.json")
    if isinstance(r, dict) and _num(r.get("ctr")) is not None:
        return {"ctr": _num(r["ctr"]), "impressions": _num(r.get("impressions"))}
    return None


def _shorts_rows() -> dict[str, dict]:
    from . import shorts
    out: dict[str, dict] = {}
    for row in shorts.table():
        eid = row.get("episode") or ""
        if eid and (eid not in out or str(row.get("date", "")) >= str(out[eid].get("date", ""))):
            out[eid] = row
    return out


def episode_rows() -> list[dict]:
    """One row per episode with a show format: its measured numbers (None where there are none)."""
    rows = []
    tsv = _shorts_rows()
    root = paths.episodes_dir()
    for ep in sorted(p for p in root.iterdir() if (p / "project.json").is_file()) if root.is_dir() else []:
        project = _json(ep / "project.json") or {}
        fid = project.get("show_format") or project.get("form") or (tsv.get(ep.name) or {}).get("form")
        if not fid:
            continue
        views = pct = subs = None
        source = None
        r = _newest_result(ep)
        if r:
            m = r["metrics"]
            views, pct, subs = _num(m.get("views")), _num(m.get("averageViewPercentage")), _num(m.get("subscribersGained"))
            source = "results"
        elif ep.name in tsv:
            t = tsv[ep.name]
            views, pct, subs = _num(t.get("views")), _num(t.get("average_view_percentage")), _num(t.get("subscribers_gained"))
            source = "shorts.tsv"
        rows.append({"episode": ep.name, "title": project.get("title"), "format": fid, "kind": project.get("kind"),
                     "views": views, "avg_view_pct": pct, "subs": subs,
                     "subs_per_1000": round(subs / views * 1000, 2) if subs is not None and views else None,
                     "retention_drop_per_min": _retention(ep), "ctr": _ctr(ep), "source": source})
    return rows


def _median(xs: list, digits: int = 2) -> float | None:
    xs = [x for x in xs if x is not None]
    return round(statistics.median(xs), digits) if xs else None


def build() -> dict:
    """{"channel": {medians}, "formats": [{format, name, episodes, measured, median_views, median_avg_view_pct,
    subs_per_1000, retention_drop_per_min, ctr, verdict, verdict_text}]}."""
    from . import showformats
    lib = showformats.load()
    rows = episode_rows()
    measured = [r for r in rows if r["views"] is not None]
    channel = {"median_views": _median([r["views"] for r in measured]),
               "median_avg_view_pct": _median([r["avg_view_pct"] for r in measured]),
               "subs_per_1000": _median([r["subs_per_1000"] for r in measured]), "episodes": len(measured)}
    groups: dict[str, list[dict]] = {}
    for r in rows:
        groups.setdefault(r["format"], []).append(r)
    out = []
    for fid, rs in groups.items():
        m = [r for r in rs if r["views"] is not None]
        mine = {"median_views": _median([r["views"] for r in m]),
                "median_avg_view_pct": _median([r["avg_view_pct"] for r in m]),
                "subs_per_1000": _median([r["subs_per_1000"] for r in m])}
        ctrs = [r["ctr"]["ctr"] for r in rs if r.get("ctr")]
        if len(m) < MIN_EPISODES:
            verdict = "thin"
        else:
            wins = sum(1 for k in mine if mine[k] is not None and channel[k] is not None and mine[k] > channel[k])
            verdict = "more" if wins >= 2 else "watch"
        out.append({"format": fid, "name": (lib.get(fid) or {}).get("name") or fid,
                    "length": (lib.get(fid) or {}).get("length"), "episodes": len(rs), "measured": len(m), **mine,
                    "retention_drop_per_min": _median([r["retention_drop_per_min"] for r in rs]),
                    "ctr": _median(ctrs, 4) if ctrs else None, "verdict": verdict, "verdict_text": VERDICTS[verdict],
                    "episode_ids": [r["episode"] for r in rs]})
    out.sort(key=lambda f: ({"more": 0, "watch": 1, "thin": 2}[f["verdict"]], -(f["median_views"] or 0), f["format"]))
    return {"channel": channel, "formats": out}


def _fmt(v, unit: str = "") -> str:
    if v is None:
        return "-"
    return f"{v:,.0f}{unit}" if abs(v) >= 100 else f"{v:g}{unit}"


def line(f: dict) -> str:
    ctr = "CTR " + (f"{f['ctr'] * 100:.1f} %" if f.get("ctr") is not None else "missing")
    ret = (f", units lose {f['retention_drop_per_min']:g} points/min" if f.get("retention_drop_per_min") is not None
           else "")
    return (f"{f['name']} ({f['format']}): {f['episodes']} episodes, {f['measured']} measured, median "
            f"{_fmt(f['median_views'])} views, {_fmt(f['median_avg_view_pct'], ' %')} watched, "
            f"{_fmt(f['subs_per_1000'])} subs/1000 views, {ctr}{ret}: {f['verdict_text']}")


def briefing_lines() -> list[str]:
    """One line per format with measured data, for the channel brief (crewcut/briefing.py)."""
    try:
        board = build()
    except OSError:
        return []
    return [f"- {line(f)}" for f in board["formats"] if f["measured"]]


def cli(as_json: bool = False) -> int:
    board = build()
    if as_json:
        print(json.dumps(board, ensure_ascii=False, indent=1))
        return 0
    if not board["formats"]:
        print("No episode has a show format yet.")
        return 0
    c = board["channel"]
    print(f"Channel ({c['episodes']} measured): median {_fmt(c['median_views'])} views, "
          f"{_fmt(c['median_avg_view_pct'], ' %')} watched, {_fmt(c['subs_per_1000'])} subs/1000 views")
    for f in board["formats"]:
        print("  " + line(f))
    return 0


__all__ = ["MIN_EPISODES", "briefing_lines", "build", "cli", "episode_rows", "line"]
