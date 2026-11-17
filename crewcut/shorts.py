"""Shorts: the standing approval, the next free publishing slot, and the results table (docs/shorts.md).

- `crewcut shorts standing on|off|status`: the user's own choice to publish Shorts without a card. Never the default;
  what it covers is in `approvals.standing_covers()`.
- `crewcut shorts slot --episode <short>`: the next free time: at most `shorts.per_day_max` a day at
  `shorts.publish_times`, never two Shorts with the same core message (the project's `core`, else its source episode)
  on the same day. "All at once" is one sentence away: the Publisher then uploads without a time.
- `crewcut shorts results --episode <short>`: after 48 hours, views, average view percentage and subscribers from the
  YouTube Analytics API, as one row of `studio/shorts.tsv` (mode, form, length, captions, first sentence, results).
  From ten rows on the Scout may propose rules from them; before that, it says nothing about patterns.
"""

from __future__ import annotations

import csv
import datetime as dt
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from . import approvals, brand, episodes, paths

TABLE_COLUMNS = ["date", "episode", "video_id", "mode", "form", "seconds", "captions", "first_sentence", "views",
                 "average_view_percentage", "average_view_seconds", "subscribers_gained"]
RULES_FROM = 10


def settings() -> dict:
    s = brand.load().value("edit_style.shorts") or {}
    return {"per_day_max": int(s.get("per_day_max", 2)), "publish_times": list(s.get("publish_times") or ["12:00",
                                                                                                          "18:00"]),
            "timezone": brand.load().value("channel.timezone") or "UTC"}


def _short_ids() -> list[str]:
    out = []
    for eid in episodes.list_ids():
        try:
            if episodes.read(eid).get("kind") == "short":
                out.append(eid)
        except (FileNotFoundError, ValueError):
            continue
    return out


def core_of(project: dict) -> str:
    return str(project.get("core") or project.get("source_episode") or project.get("id"))


def scheduled() -> list[dict]:
    """Shorts with a publish time: from their upload results and from their planned slot."""
    out = []
    for eid in _short_ids():
        p = episodes.read(eid)
        ep = paths.episode_dir(eid)
        at = None
        res = ep / "export" / "upload-result.json"
        if res.is_file():
            try:
                at = json.loads(res.read_text(encoding="utf-8")).get("publish_at")
            except ValueError:
                at = None
        at = at or p.get("slot")
        if at:
            out.append({"episode": eid, "at": at, "core": core_of(p)})
    return out


def next_slot(episode: str, now: dt.datetime | None = None) -> str:
    """The next free publishing time for this Short, as an ISO UTC time."""
    s = settings()
    tz = ZoneInfo(s["timezone"])
    now = (now or dt.datetime.now(dt.UTC)).astimezone(tz)
    me = core_of(episodes.read(episode))
    taken = [x for x in scheduled() if x["episode"] != episode]
    by_day: dict[dt.date, list[dict]] = {}
    for x in taken:
        when = dt.datetime.fromisoformat(x["at"].replace("Z", "+00:00")).astimezone(tz)
        by_day.setdefault(when.date(), []).append({**x, "when": when})
    for d in range(0, 60):
        day = (now + dt.timedelta(days=d)).date()
        used = by_day.get(day, [])
        if len(used) >= s["per_day_max"] or any(u["core"] == me for u in used):
            continue
        for t in sorted(s["publish_times"]):
            hh, mm = (int(v) for v in t.split(":"))
            when = dt.datetime(day.year, day.month, day.day, hh, mm, tzinfo=tz)
            if when <= now + dt.timedelta(minutes=30) or any(u["when"] == when for u in used):
                continue
            return when.astimezone(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    raise RuntimeError("no free slot in the next 60 days")


def table_path() -> Path:
    return paths.studio_root() / "shorts.tsv"


def add_result(row: dict) -> None:
    p = table_path()
    new = not p.is_file()
    with p.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=TABLE_COLUMNS, delimiter="\t", extrasaction="ignore")
        if new:
            w.writeheader()
        w.writerow({k: row.get(k, "") for k in TABLE_COLUMNS})


def table() -> list[dict]:
    p = table_path()
    if not p.is_file():
        return []
    with p.open(encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def results(episode: str, analytics=None) -> dict:
    """48-hour numbers of a published Short (YouTube Analytics API) as one row of the table."""
    ep = paths.episode_dir(episode)
    res = json.loads((ep / "export" / "upload-result.json").read_text(encoding="utf-8"))
    p = episodes.read(episode)
    if analytics is None:
        from googleapiclient.discovery import build

        from .youtube.auth import credentials
        analytics = build("youtubeAnalytics", "v2", credentials=credentials(), cache_discovery=False)
    start = (res.get("publish_at") or res["at"])[:10]
    end = dt.date.today().isoformat()
    rep = analytics.reports().query(ids="channel==MINE", startDate=start, endDate=end, filters=f"video=={res['video_id']}",
                                    metrics="views,averageViewPercentage,averageViewDuration,subscribersGained").execute()
    vals = (rep.get("rows") or [[0, 0, 0, 0]])[0]
    row = {"date": end, "episode": episode, "video_id": res["video_id"], "mode": p.get("mode", ""),
           "form": p.get("form", ""), "seconds": p.get("seconds", ""),
           "captions": brand.load().value("edit_style.shorts.captions") or "",
           "first_sentence": p.get("first_sentence", ""), "views": vals[0], "average_view_percentage": vals[1],
           "average_view_seconds": vals[2], "subscribers_gained": vals[3]}
    add_result(row)
    return row


def start_clip(source: str) -> dict:
    """"Make a Short" on an episode: a new Short in clip mode from it, and the Scout's job to find the passages.
    Returns {episode, job}. The job shows up in Working now like any other."""
    from .conductor import queue
    src = episodes.read(source)
    if src.get("kind") == "short":
        raise ValueError("this is a Short already; make Shorts from a long episode")
    title = f"Short from {src.get('title') or source}"
    short = episodes.create(title[:90], kind="short", mode="clip", source_episode=source)
    task = (f"Make a Short in clip mode from episode {source} (skills/shorts, \"Clip\"). Find stand-alone passages with "
            f"`crewcut cut candidates {source}`, then propose the best three on one card.")
    jid = queue.add(short["id"], "scout", "idea", task)
    return {"episode": short["id"], "job": jid}


def standing_line() -> str:
    s = approvals.standing("shorts")
    if not s:
        return "Shorts need your yes on a card, like every video."
    since = dt.datetime.fromisoformat(s["since"].replace("Z", "+00:00")).strftime("%-d %b")
    return f"Shorts are published without asking, since {since}"


__all__ = ["next_slot", "scheduled", "results", "table", "add_result", "standing_line", "RULES_FROM"]
