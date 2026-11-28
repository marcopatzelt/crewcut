"""Read period-based video results. Missing data is not a zero-view result.

With `first_days` (7 or 28) the period is the video's first days from its publication, the window the scoreboard
compares across episodes (skills/idea/references/method.md, section 10). The report also carries the share of views
from search and from browse features when YouTube answers that second query.
"""

from __future__ import annotations

import json
import math
import re
from datetime import date, timedelta

from .. import db, paths
from .analytics import NoData, api_query, upload

METRICS = ("views", "estimatedMinutesWatched", "averageViewDuration", "averageViewPercentage", "likes", "comments",
           "shares", "subscribersGained", "subscribersLost")


TRAFFIC = {"YT_SEARCH": "search", "SUBSCRIBER": "browse"}   # browse features = home page and subscription feed


def published_day(root) -> str | None:
    """The publication day from export/upload-result.json (the scheduled time, else the upload time)."""
    rec = upload(root)
    when = rec.get("publish_at") or rec.get("published_at") or rec.get("at")
    return str(when)[:10] if when else None


def traffic(video_id: str, start: str, end: str, query) -> dict | None:
    """Shares of views by traffic source (search, browse, other). None when YouTube gives no such rows."""
    try:
        response = query({"ids": "channel==MINE", "startDate": start, "endDate": end, "filters": f"video=={video_id}",
                          "metrics": "views", "dimensions": "insightTrafficSourceType"})
    except Exception:  # noqa: BLE001 - a missing breakdown never breaks the results
        return None
    rows = [r for r in response.get("rows") or [] if len(r) >= 2 and isinstance(r[0], str)
            and isinstance(r[1], (int, float)) and not isinstance(r[1], bool)]
    total = sum(r[1] for r in rows)
    if not rows or not total:
        return None
    shares = {"search": 0.0, "browse": 0.0, "other": 0.0}
    for source, views in rows[:50]:
        shares[TRAFFIC.get(source, "other")] += views / total
    shares = {k: round(v, 3) for k, v in shares.items()}
    shares["type"] = "search" if shares["search"] > shares["browse"] else "browse"
    return shares


def results(episode: str, start: str | None, end: str | None, video: str | None = None, query=None,
            first_days: int | None = None) -> dict:
    root = paths.episode_dir(episode)
    if not (root / "project.json").is_file():
        raise FileNotFoundError("The episode does not exist.")
    if first_days is not None:
        if first_days not in (7, 28):
            raise ValueError("first_days is 7 or 28.")
        start = start or published_day(root)
        if not start:
            raise ValueError("No publication day is recorded. Supply --start with the day the video went public.")
        end = (date.fromisoformat(start) + timedelta(days=first_days - 1)).isoformat()
    if not start or not end:
        raise ValueError("Give --start and --end, or --first 7|28.")
    start_day, end_day = date.fromisoformat(start), date.fromisoformat(end)
    if start_day > end_day:
        raise ValueError("The result period ends before it starts.")
    video_id = video or upload(root).get("video_id")
    if not video_id:
        raise NoData("No video ID is recorded. Supply --video for an earlier publication.")
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
        raise ValueError("Expected one YouTube video ID.")
    response = (query or api_query)({"ids": "channel==MINE", "startDate": start_day.isoformat(),
        "endDate": end_day.isoformat(), "filters": f"video=={video_id}", "metrics": ",".join(METRICS)})
    rows = response.get("rows") or []
    if not rows:
        raise NoData("YouTube has no results for this period yet. Previous reports stay unchanged.")
    if len(rows) != 1:
        raise ValueError("Unexpected results shape: expected one aggregate row.")
    headers = [header.get("name") for header in response.get("columnHeaders", [])]
    values = {}
    for metric in METRICS:
        if metric not in headers:
            continue
        index = headers.index(metric)
        if index < len(rows[0]):
            value = rows[0][index]
            if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
                values[metric] = value
    if not values:
        raise NoData("YouTube returned no usable metric values. Nothing was written.")
    report = {"schema": 1, "episode": episode, "video_id": video_id, "fetched_at": db.now(),
              "period": {"start": start_day.isoformat(), "end": end_day.isoformat(), "granularity": "calendar_days"},
              "metrics": values, "missing_metrics": [metric for metric in METRICS if metric not in values],
              **({"window": {"first_days": first_days, "published": start_day.isoformat()}} if first_days else {}),
              **({"traffic": shares} if (shares := traffic(video_id, start_day.isoformat(), end_day.isoformat(),
                                                             query or api_query)) else {}),
              "source": "YouTube Analytics reports.query, channel==MINE",
              "limits": ["Calendar-day period, not an exact rolling 48-hour window; data can be delayed.",
                         "No thumbnail impressions, click-through rate or unique-viewer metrics in this query.",
                         "These numbers do not prove why viewers watched or left. No rules were changed."]}
    destination = root / "review" / f"results-{start_day.isoformat()}-{end_day.isoformat()}.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    temporary.replace(destination)
    return report
