"""Upload exactly what the publish card showed: the package file's checksum must match the accepted card."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path

from .. import approvals, db, paths

REQUIRED = ("video", "title", "description")


def load_package(episode: str, rel: str = "export/upload.json") -> tuple[Path, dict]:
    p = paths.inside(paths.episode_dir(episode), rel)
    if not p.is_file():
        raise FileNotFoundError(f"No upload package at {rel}. The Publisher writes it with the upload skill.")
    return p, json.loads(p.read_text(encoding="utf-8"))


def validate(episode: str, pkg: dict) -> list[str]:
    ep = paths.episode_dir(episode)
    errs = []
    for k in REQUIRED:
        if not pkg.get(k):
            errs.append(f"missing {k}")
    if pkg.get("title") and len(pkg["title"]) > 100:
        errs.append("title longer than 100 characters (YouTube limit)")
    if pkg.get("description") and len(pkg["description"].encode("utf-8")) > 5000:
        errs.append("description longer than 5000 bytes (YouTube limit)")
    if any(c in (pkg.get("title", "") + pkg.get("description", "")) for c in "<>"):
        errs.append("title and description must not contain < or >")
    tags = pkg.get("tags") or []
    if sum(len(t) + (2 if " " in t else 0) for t in tags) + max(0, len(tags) - 1) > 500:
        errs.append("tags longer than 500 characters together")
    for k in ("video", "thumbnail"):
        if pkg.get(k):
            try:
                if not paths.inside(ep, pkg[k]).is_file():
                    errs.append(f"{k} file not found: {pkg[k]}")
            except ValueError:
                errs.append(f"{k} must be inside the episode folder")
    for c in pkg.get("captions") or []:
        try:
            if not paths.inside(ep, c.get("file", "")).is_file():
                errs.append(f"captions file not found: {c.get('file')}")
        except ValueError:
            errs.append("captions must be inside the episode folder")
    if pkg.get("publish_at"):
        try:
            datetime.fromisoformat(pkg["publish_at"].replace("Z", "+00:00"))
        except ValueError:
            errs.append("publish_at must be an ISO time, for example 2026-11-20T16:00:00Z")
    if pkg.get("privacy", "private") not in ("private", "unlisted", "public"):
        errs.append("privacy must be private, unlisted or public")
    return errs


def approved_card(episode: str, package_path: Path) -> dict | None:
    """The accepted publish card for this exact package version, or None."""
    digest = approvals.sha256(package_path)
    with db.conn() as c:
        rs = db.rows(c.execute("SELECT * FROM cards WHERE episode = ? AND kind = 'publish' AND status = 'accepted' "
                               "ORDER BY id DESC", (episode,)))
    for card in rs:
        if card.get("sha256") == digest:
            return card
    return None


def body_of(pkg: dict, publish_at: str | None = None) -> dict:
    publish_at = publish_at or pkg.get("publish_at")
    status = {"privacyStatus": "private" if publish_at else pkg.get("privacy", "private"),
              "selfDeclaredMadeForKids": bool(pkg.get("made_for_kids", False))}
    if publish_at:
        status["publishAt"] = publish_at
    if "contains_synthetic_media" in pkg:
        status["containsSyntheticMedia"] = bool(pkg["contains_synthetic_media"])
    snippet = {"title": pkg["title"], "description": pkg["description"], "tags": pkg.get("tags") or [],
               "categoryId": str(pkg.get("category_id", 28))}
    for src, dst in (("default_language", "defaultLanguage"), ("default_audio_language", "defaultAudioLanguage")):
        if pkg.get(src):
            snippet[dst] = pkg[src]
    return {"snippet": snippet, "status": status}


def upload(episode: str, rel: str = "export/upload.json", publish_at: str | None = None, dry_run: bool = False,
           progress=None) -> dict:
    approvals.require_right("publish")
    ep = paths.episode_dir(episode)
    pkg_path, pkg = load_package(episode, rel)
    errs = validate(episode, pkg)
    if errs:
        raise ValueError("The upload package has problems: " + "; ".join(errs))
    body = body_of(pkg, publish_at)
    if dry_run:
        return {"dry_run": True, "body": body, "video": pkg["video"], "thumbnail": pkg.get("thumbnail"),
                "captions": pkg.get("captions") or []}
    card = approved_card(episode, pkg_path)
    if card is None:
        raise PermissionError("There is no accepted publish card for this exact package. Propose a card with "
                              f"--kind publish --file {rel} and wait for the user's yes.")
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    from .auth import credentials
    yt = build("youtube", "v3", credentials=credentials(), cache_discovery=False)
    media = MediaFileUpload(str(paths.inside(ep, pkg["video"])), chunksize=8 * 1024 * 1024, resumable=True)
    req = yt.videos().insert(part="snippet,status", body=body, media_body=media, notifySubscribers=True)
    resp = None
    while resp is None:
        st, resp = req.next_chunk()
        if st and progress:
            progress(st.progress())
    vid = resp["id"]
    result = {"video_id": vid, "url": f"https://youtu.be/{vid}", "at": db.now(), "card": card["id"],
              "privacy": body["status"]["privacyStatus"], "publish_at": body["status"].get("publishAt"),
              "notes": []}
    if pkg.get("thumbnail"):
        try:
            yt.thumbnails().set(videoId=vid, media_body=MediaFileUpload(str(paths.inside(ep, pkg["thumbnail"])))).execute()
        except Exception as e:  # noqa: BLE001 - the video is up; report and go on
            result["notes"].append(f"thumbnail not set: {type(e).__name__} (custom thumbnails need a verified channel)")
    for c in pkg.get("captions") or []:
        try:
            yt.captions().insert(part="snippet", body={"snippet": {"videoId": vid, "language": c.get("language", "en"),
                                                                   "name": c.get("name", ""), "isDraft": False}},
                                 media_body=MediaFileUpload(str(paths.inside(ep, c["file"])))).execute()
        except Exception as e:  # noqa: BLE001
            result["notes"].append(f"captions {c.get('file')} not uploaded: {type(e).__name__}")
    (ep / "export" / "upload-result.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    return result


def safe_name(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", s)[:60]


__all__ = ["upload", "validate", "load_package", "approved_card", "body_of", "safe_name", "os"]
