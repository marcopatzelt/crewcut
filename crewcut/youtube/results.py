"""Read period-based video results. Missing data is not a zero-view result."""

from __future__ import annotations

import json
import math
import re
from datetime import date

from .. import db, paths
from .analytics import NoData, api_query, upload

METRICS = ("views", "estimatedMinutesWatched", "averageViewDuration", "averageViewPercentage", "likes", "comments",
           "shares", "subscribersGained", "subscribersLost")


def results(episode: str, start: str, end: str, video: str | None = None, query=None) -> dict:
    root = paths.episode_dir(episode)
    if not (root / "project.json").is_file():
        raise FileNotFoundError("The episode does not exist.")
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
