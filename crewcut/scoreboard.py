"""The scoreboard per show format: which formats win on this channel, from measured results only.

Episodes are grouped by `project.show_format` (else `form`). The fair measure (skills/idea/references/method.md,
section 10) is the video's first days, never today's total: `crewcut youtube results <id> --first 7` (and `--first 28`)
write reports with a `window`. Per episode:

- `x_7d` = views in the first 7 days / median of the first 7 days of the channel's last 10 videos of the same
  length (long or Short) before it; `x_28d` the same for 28 days. Search formats (`traffic_type` "search": from the
  report's traffic shares, the project, or the format library) are judged on `x_28d`, browse formats on `x_7d`.
- `ctr_rel` and `avp_rel`: click-through rate and average view percentage against the same last 10. Click-through
  rate is not in the YouTube Analytics API: it comes from `analytics/ctr.json` (`{"ctr": 0.051, "impressions": 12000}`,
  copied from YouTube Studio). The 2x2 diagnosis of the two comes before any stop.
- subscribers gained per 1,000 views, and the median drop per minute of the units (`analytics/retention-units.json`).

Without window reports the newest `review/results-*.json` (or, for Shorts, `studio/shorts.tsv`) gives total views,
compared with the channel median of the same length (Shorts against Shorts, long against long) and marked as unfair to
new videos. Subscribers per 1,000 views are compared within the same length too.

Verdict per format: too little data under 2 measured episodes; with 2 or 3 a stop when the first two are both under
0.5 and both weak on click and view share, else watch; from 4 on (the last 4): more of this at a median of at least
1.2 (1.0 for a format that already runs, more than 4 episodes) or with more subscribers per 1,000 views than the
channel, drop under 0.8 without that, else change after the diagnosis and measure 2 more. A hint, not a rule.
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path

from . import paths

MIN_EPISODES = 2
DECIDE_AFTER = 4
REFERENCE = 10
COVIEW_FROM = "2026-11-01"
VERDICTS = {"more": "more of this", "thin": "too little data", "watch": "watch", "stop": "stop early",
            "drop": "drop", "change": "change after the diagnosis, measure 2 more"}
DIAGNOSES = {(True, True): "format carries", (True, False): "packaging carries, script or opening weak",
             (False, True): "content carries, packaging weak", (False, False): "weak for us"}


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


def _windows(ep: Path) -> dict[int, dict]:
    """The newest first-days report per window (7, 28)."""
    out: dict[int, dict] = {}
    for p in sorted((ep / "review").glob("results-*.json")):
        r = _json(p)
        w = (r or {}).get("window") if isinstance(r, dict) else None
        if not isinstance(w, dict) or w.get("first_days") not in (7, 28) or not isinstance(r.get("metrics"), dict):
            continue
        k = w["first_days"]
        if k not in out or str(r.get("fetched_at", "")) >= str(out[k].get("fetched_at", "")):
            out[k] = r
    return out


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
    from . import showformats
    from .youtube.results import published_day
    lib = showformats.load()
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
        win = _windows(ep)
        first = {k: _num(w["metrics"].get("views")) for k, w in win.items()}
        main = win.get(7) or win.get(28)
        if main:   # the first days are the fair numbers: subscribers and view share from that window
            m = main["metrics"]
            pct, subs = _num(m.get("averageViewPercentage")), _num(m.get("subscribersGained"))
            views, source = _num(m.get("views")), "first days"
        shares = (win.get(28) or {}).get("traffic") or (win.get(7) or {}).get("traffic") or {}
        traffic = (shares.get("type") if shares else None) or project.get("traffic_type") \
            or (lib.get(fid) or {}).get("traffic_type") or "browse"
        published = ((main or {}).get("window") or {}).get("published") or published_day(ep)
        rows.append({"episode": ep.name, "title": project.get("title"), "format": fid, "kind": project.get("kind"),
                     "length": "short" if project.get("kind") == "short" else "long", "published": published,
                     "views": views, "avg_view_pct": pct, "subs": subs,
                     "subs_per_1000": round(subs / views * 1000, 2) if subs is not None and views else None,
                     "views_7d": first.get(7), "views_28d": first.get(28), "traffic_type": traffic,
                     "retention_drop_per_min": _retention(ep), "ctr": _ctr(ep), "source": source})
    _relative(rows)
    return rows


def _relative(rows: list[dict]) -> None:
    """x_7d, x_28d, ctr_rel, avp_rel and the diagnosis against the last REFERENCE videos of the same length."""
    for r in rows:
        before = sorted((o for o in rows if o is not r and o["length"] == r["length"] and o.get("published")
                         and r.get("published") and o["published"] < r["published"]),
                        key=lambda o: o["published"], reverse=True)
        others = before if len(before) >= 3 else sorted(
            (o for o in rows if o is not r and o["length"] == r["length"]),
            key=lambda o: abs(_days(o.get("published")) - _days(r.get("published"))))
        ref = others[:REFERENCE]
        r["x_7d"] = _rel(r, ref, lambda o: o["views_7d"])
        r["x_28d"] = _rel(r, ref, lambda o: o["views_28d"])
        r["ctr_rel"] = _rel(r, ref, lambda o: (o.get("ctr") or {}).get("ctr"))
        r["avp_rel"] = (_rel(r, [o for o in ref if o["source"] == "first days"], lambda o: o["avg_view_pct"])
                        if r["source"] == "first days" else None)
        r["x"] = r["x_28d"] if r["traffic_type"] == "search" else r["x_7d"]
        r["diagnosis"] = (DIAGNOSES[(r["ctr_rel"] >= 1.0, r["avp_rel"] >= 1.0)]
                          if r["ctr_rel"] is not None and r["avp_rel"] is not None else None)
        eras = {(o.get("published") or "") >= COVIEW_FROM for o in ref + [r] if o.get("published")}
        r["coview_mixed"] = len(eras) > 1


def _rel(r: dict, ref: list[dict], value) -> float | None:
    """The row's value against the median of the reference rows (at least 3 with a value)."""
    vals = [v for v in (value(o) for o in ref) if v is not None]
    mine = value(r)
    base = statistics.median(vals) if len(vals) >= 3 else None
    return round(mine / base, 2) if mine is not None and base else None


def _days(day: str | None) -> int:
    from datetime import date
    try:
        return date.fromisoformat(str(day)[:10]).toordinal()
    except (TypeError, ValueError):
        return 0


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
    channel = _medians(measured)
    by_length = {ln: _medians([r for r in measured if r["length"] == ln]) for ln in ("long", "short")}
    channel["by_length"] = by_length
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
        fair = sorted((r for r in rs if r.get("x") is not None), key=lambda r: r.get("published") or "")
        if fair:
            basis, xs = "first days", [r["x"] for r in fair]
        else:   # total views only: unfair to young videos, marked as such; Shorts against Shorts, long against long
            basis = "total views"
            fair = [r for r in m if by_length[r["length"]]["median_views"]]
            xs = [r["views"] / by_length[r["length"]]["median_views"] for r in fair]
        lengths = [r["length"] for r in rs]
        length = max(("long", "short"), key=lengths.count)   # the format's episodes are judged within their length
        verdict, median_x = decide(fair, xs, mine["subs_per_1000"],
                                   by_length.get(length, channel)["subs_per_1000"])
        if basis == "total views" and any(r["traffic_type"] == "search" and r.get("x_7d") is not None for r in rs):
            basis, verdict, median_x = "search: judged on the first 28 days", "watch", None
        traffic = sorted({r["traffic_type"] for r in rs})
        out.append({"format": fid, "name": (lib.get(fid) or {}).get("name") or fid,
                    "length": (lib.get(fid) or {}).get("length"), "episodes": len(rs), "measured": len(m), **mine,
                    "retention_drop_per_min": _median([r["retention_drop_per_min"] for r in rs]),
                    "ctr": _median(ctrs, 4) if ctrs else None, "verdict": verdict, "verdict_text": VERDICTS[verdict],
                    "basis": basis, "judged": len(fair), "median_x": median_x,
                    "traffic_type": traffic[0] if len(traffic) == 1 else "mixed",
                    "ctr_rel": _median([r["ctr_rel"] for r in fair]), "avp_rel": _median([r["avp_rel"] for r in fair]),
                    "diagnosis": next((r["diagnosis"] for r in reversed(fair) if r.get("diagnosis")), None),
                    "coview_mixed": any(r.get("coview_mixed") for r in fair),
                    "episode_ids": [r["episode"] for r in rs]})
    order = {"more": 0, "change": 1, "watch": 2, "thin": 3, "stop": 4, "drop": 5}
    out.sort(key=lambda f: (order[f["verdict"]], -(f["median_views"] or 0), f["format"]))
    return {"channel": channel, "formats": out}


def _medians(rows: list[dict]) -> dict:
    return {"median_views": _median([r["views"] for r in rows]),
            "median_avg_view_pct": _median([r["avg_view_pct"] for r in rows]),
            "subs_per_1000": _median([r["subs_per_1000"] for r in rows]), "episodes": len(rows)}


def decide(fair: list[dict], xs: list[float], subs: float | None, channel_subs: float | None) -> tuple[str, float | None]:
    """The verdict of one format from its judged episodes (oldest first) and their ratios xs."""
    n = len(xs)
    if n < MIN_EPISODES:
        return "thin", (round(xs[0], 2) if xs else None)
    if n < DECIDE_AFTER:
        first = fair[:2]
        weak = all(x < 0.5 for x in xs[:2]) and all(r.get("diagnosis") == DIAGNOSES[(False, False)] for r in first)
        return ("stop" if weak else "watch"), round(statistics.median(xs), 2)
    last = statistics.median(xs[-DECIDE_AFTER:])
    more_subs = subs is not None and channel_subs is not None and subs > channel_subs
    if last >= (1.0 if n > DECIDE_AFTER else 1.2) or more_subs:
        return "more", round(last, 2)
    if last < 0.8:
        return "drop", round(last, 2)
    return "change", round(last, 2)


def _fmt(v, unit: str = "") -> str:
    if v is None:
        return "-"
    return f"{v:,.0f}{unit}" if abs(v) >= 100 else f"{v:g}{unit}"


def line(f: dict) -> str:
    ctr = "CTR " + (f"{f['ctr'] * 100:.1f} %" if f.get("ctr") is not None else "missing")
    ret = (f", units lose {f['retention_drop_per_min']:g} points/min" if f.get("retention_drop_per_min") is not None
           else "")
    fair = ""
    if f.get("basis") == "first days" and f.get("median_x") is not None:
        days = "28" if f.get("traffic_type") == "search" else "7"
        fair = f", first {days} days {f['median_x']:g}x of our last {REFERENCE} ({f.get('traffic_type')})"
        if f.get("diagnosis"):
            fair += f", diagnosis: {f['diagnosis']}"
        if f.get("coview_mixed"):
            fair += ", co-views counted since Nov 2026 in part of the comparison"
    return (f"{f['name']} ({f['format']}): {f['episodes']} episodes, {f['measured']} measured, median "
            f"{_fmt(f['median_views'])} views, {_fmt(f['median_avg_view_pct'], ' %')} watched, "
            f"{_fmt(f['subs_per_1000'])} subs/1000 views, {ctr}{ret}{fair}: {f['verdict_text']}")


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
    for ln, name in (("long", "Long videos"), ("short", "Shorts")):
        b = (c.get("by_length") or {}).get(ln) or {}
        if b.get("episodes"):
            print(f"  {name} ({b['episodes']} measured): median {_fmt(b['median_views'])} views, "
                  f"{_fmt(b['median_avg_view_pct'], ' %')} watched, {_fmt(b['subs_per_1000'])} subs/1000 views")
    for f in board["formats"]:
        print("  " + line(f))
    return 0


__all__ = ["MIN_EPISODES", "briefing_lines", "build", "cli", "episode_rows", "line"]
