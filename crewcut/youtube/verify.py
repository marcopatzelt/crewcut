"""Read uploaded metadata without changing the video or granting an approval."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from .. import db, paths
from .upload import body_of, load_package


def verify(episode: str, rel: str = "export/upload.json", youtube=None, now: datetime | None = None) -> dict:
    _, package = load_package(episode, rel)
    root = paths.episode_dir(episode)
    uploaded = json.loads((root / "export" / "upload-result.json").read_text(encoding="utf-8"))
    video_id = uploaded.get("video_id")
    if not video_id:
        raise ValueError("The episode has no recorded YouTube video ID.")
    if youtube is None:
        from googleapiclient.discovery import build

        from .auth import credentials
        youtube = build("youtube", "v3", credentials=credentials(), cache_discovery=False)
    items = youtube.videos().list(part="snippet,status", id=video_id).execute().get("items") or []
    if not items:
        raise LookupError("YouTube did not return this video. No verification report was written.")
    actual = items[0]
    expected = body_of(package)
    scheduled = expected["status"].get("publishAt")
    current_time = now or datetime.now(UTC)
    if scheduled and datetime.fromisoformat(scheduled.replace("Z", "+00:00")) <= current_time:
        expected["status"].pop("publishAt")
        expected["status"]["privacyStatus"] = "public"
    checks = []
    for section, fields in expected.items():
        for field, value in fields.items():
            observed = actual.get(section, {}).get(field)
            if field == "tags":
                matches = sorted(observed or []) == sorted(value)
            elif field == "publishAt" and observed:
                matches = (datetime.fromisoformat(observed.replace("Z", "+00:00")) ==
                           datetime.fromisoformat(value.replace("Z", "+00:00")))
            else:
                matches = observed == value
            checks.append({"field": f"{section}.{field}", "matches": matches,
                           "expected": value, "actual": observed})
    if package.get("captions"):
        tracks = youtube.captions().list(part="snippet", videoId=video_id).execute().get("items") or []
        for caption in package["captions"]:
            language, name = caption.get("language", "en"), caption.get("name", "")
            matches = any(track.get("snippet", {}).get("language") == language and
                          track.get("snippet", {}).get("name", "") == name and
                          track.get("snippet", {}).get("status") == "serving" and
                          not track.get("snippet", {}).get("isDraft", False) for track in tracks)
            checks.append({"field": f"captions.{language}.{name}", "matches": matches})
    report = {"schema": 1, "episode": episode, "video_id": video_id, "checked_at": db.now(),
              "package": rel, "matches": all(check["matches"] for check in checks), "checks": checks,
              "not_checked": ["video and audio content", "thumbnail image", "caption text",
                              "A/B tests", "end screen", "playlist membership"]}
    destination = root / "review" / "publication-check.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    temporary.replace(destination)
    return report
