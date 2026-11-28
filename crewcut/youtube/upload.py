"""Upload exactly what the publish card showed: the package file's checksum must match the accepted card. A video goes
up once: the lock, the episode's record and a look at the channel come first (guard.py)."""

from __future__ import annotations

import json
import os
import re
import threading
import time
from datetime import datetime
from pathlib import Path

from .. import approvals, config, db, paths
from . import guard

REQUIRED = ("video", "title", "description")
# The Short's link comment. YouTube refused it every time it came right after the upload, while the video was still
# processing (four Shorts on 24.11.2026); the same call worked once the video was processed. So the comment waits for
# uploadStatus "processed": up to COMMENT_WAIT_S inside the upload, after that the worker tries again (comments_tick).
COMMENT_WAIT_S = 45
COMMENT_POLL_S = 5
COMMENT_RETRY_S = 60
COMMENT_RETRY_MAX_S = 900
COMMENT_GIVE_UP_S = 24 * 3600
PENDING = "youtube_comment_pending:"
GONE = ("failed", "rejected", "deleted")
PIN_NOTE = "pin it in YouTube Studio and set \"Related video\" in the YouTube app (no API for either)"


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
    tags = [*(pkg.get("tags") or []), "x" * guard.MARKER_LEN]   # the upload adds its marker tag (guard.py)
    if sum(len(t) + (2 if " " in t else 0) for t in tags) + max(0, len(tags) - 1) > 500:
        errs.append(f"tags longer than 500 characters together (Crewcut adds a {guard.MARKER_LEN}-character marker tag)")
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
            scheduled = datetime.fromisoformat(pkg["publish_at"].replace("Z", "+00:00"))
            if scheduled.tzinfo is None:
                errs.append("publish_at must include a timezone")
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


def approval(episode: str, package_path: Path, pkg: dict, rel: str) -> dict | None:
    """The user's yes for this package: an accepted card, or (Shorts only) the standing approval, logged as a card."""
    card = approved_card(episode, package_path)
    if card is not None:
        data = card.get("data") or {}
        if data.get("auto_revision"):
            from .. import full_auto
            if not full_auto.active(episode) or full_auto.policy(episode).get("revision") != data["auto_revision"]:
                return None
            full_auto.publish_allowed(card)
        return card
    ok, _why = approvals.standing_covers(episode, pkg)
    return approvals.accept_under_standing(episode, rel) if ok else None


def body_of(pkg: dict, publish_at: str | None = None, marker: str | None = None) -> dict:
    """The videos.insert body. marker: the tag that tells this video apart on YouTube (guard.marker)."""
    publish_at = publish_at or pkg.get("publish_at")
    status = {"privacyStatus": "private" if publish_at else pkg.get("privacy", "private"),
              "selfDeclaredMadeForKids": bool(pkg.get("made_for_kids", False))}
    if publish_at:
        status["publishAt"] = publish_at
    if "contains_synthetic_media" in pkg:
        status["containsSyntheticMedia"] = bool(pkg["contains_synthetic_media"])
    tags = guard.without_markers(pkg.get("tags")) + ([marker] if marker else [])
    snippet = {"title": pkg["title"], "description": pkg["description"], "tags": tags,
               "categoryId": str(pkg.get("category_id", 28))}
    for src, dst in (("default_language", "defaultLanguage"), ("default_audio_language", "defaultAudioLanguage")):
        if pkg.get(src):
            snippet[dst] = pkg[src]
    return {"snippet": snippet, "status": status}


def _client():
    from googleapiclient.discovery import build

    from .auth import credentials
    return build("youtube", "v3", credentials=credentials(), cache_discovery=False)


def _media(path: Path, **kw):
    from googleapiclient.http import MediaFileUpload
    return MediaFileUpload(str(path), **kw)


def upload(episode: str, rel: str = "export/upload.json", publish_at: str | None = None, dry_run: bool = False,
           progress=None, youtube=None, media=None, new_video: bool = False) -> dict:
    """Upload the approved package once. Returns the result with "status": "uploaded", or "exists" when YouTube has this
    episode's video already (nothing goes up then). Raises guard.Busy while another upload of the episode runs and
    guard.CheckFailed when YouTube cannot be asked whether the video is there."""
    approvals.require_right("publish")
    if new_video and os.environ.get("CREWCUT_IDENTITY"):
        raise PermissionError("A second video of an episode (--new-video) is for the person at the terminal, not for "
                              "a crew member.")
    ep = paths.episode_dir(episode)
    pkg_path, pkg = load_package(episode, rel)
    errs = validate(episode, pkg)
    if errs:
        raise ValueError("The upload package has problems: " + "; ".join(errs))
    version = guard.version_of(paths.inside(ep, pkg["video"]))
    body = body_of(pkg, publish_at, marker=guard.marker(episode, version))
    if dry_run:
        return {"dry_run": True, "body": body, "video": pkg["video"], "thumbnail": pkg.get("thumbnail"),
                "captions": pkg.get("captions") or [], "version": version}
    if publish_at and publish_at != pkg.get("publish_at"):
        raise PermissionError("The schedule differs from the upload package. Put publish_at in the package and "
                              "request a new publish card before uploading.")
    job = int(os.environ["CREWCUT_JOB"]) if os.environ.get("CREWCUT_JOB", "").isdigit() else None
    with guard.locked(episode, job=job, what=rel) as lock:   # raises guard.Busy: another upload of it runs
        yt = youtube if youtube is not None else _client()
        found = guard.existing(yt, episode, version, pkg.get("title"), new_video=new_video)
        if found:
            return _already(episode, ep, found, rel)
        card = approval(episode, pkg_path, pkg, rel)
        if card is None:
            _ok, why = approvals.standing_covers(episode, pkg)
            raise PermissionError("There is no accepted publish card for this exact package. Propose a card with "
                                  f"--kind publish --file {rel} and wait for the user's yes."
                                  + (f" (Standing approval: {why}.)" if approvals.standing("shorts") else ""))
        return {**_send(episode, ep, yt, media or _media, pkg, body, rel, card, version, job, lock, progress),
                "status": "uploaded"}


def _already(episode: str, ep: Path, found: dict, rel: str) -> dict:
    """YouTube has the video: record it in export/upload-result.json when that names another one, report, upload
    nothing."""
    vid = found["video_id"]
    res = guard.result_file(episode)
    if res.get("video_id") != vid:
        res = {"video_id": vid, "url": f"https://youtu.be/{vid}", "at": found.get("at") or db.now(),
               "card": found.get("card"), "privacy": found.get("privacy"), "publish_at": found.get("publish_at"),
               "standing": False, "package": rel, "found": found["why"],
               "notes": [f"found on YouTube, not uploaded again: {found['why']}"]}
        _write_result(ep, res)
    return {**res, "status": "exists", "why": found["why"],
            "message": f"Already on YouTube: https://youtu.be/{vid} ({found['why']}). Nothing was uploaded again."}


def _send(episode: str, ep: Path, yt, media, pkg: dict, body: dict, rel: str, card: dict, version: str,
          job: int | None, lock: dict, progress) -> dict:
    short = _is_short(episode)
    final_status = dict(body["status"])
    if short:
        # Shorts go up private first, are read back, and only then become public or scheduled
        body["status"] = {k: v for k, v in body["status"].items() if k != "publishAt"}
        body["status"]["privacyStatus"] = "private"
    video = media(paths.inside(ep, pkg["video"]), chunksize=8 * 1024 * 1024, resumable=True)
    req = yt.videos().insert(part="snippet,status", body=body, media_body=video, notifySubscribers=True)
    resp = None
    while resp is None:
        st, resp = req.next_chunk()
        guard.beat(lock)
        if st and progress:
            progress(st.progress())
    vid = resp["id"]
    guard.remember(episode, vid, "upload", version=version, package=rel, card=card["id"], job=job)
    result = {"video_id": vid, "url": f"https://youtu.be/{vid}", "at": db.now(), "card": card["id"],
              "privacy": body["status"]["privacyStatus"], "publish_at": body["status"].get("publishAt"),
              "standing": bool((card.get("data") or {}).get("standing")), "package": rel, "version": version,
              "notes": []}
    _write_result(ep, result)   # the video is up: its id is on disk before anything else can fail or wait
    if short:
        result.update(finish_short(yt, vid, pkg, final_status))
    if pkg.get("thumbnail"):
        try:
            yt.thumbnails().set(videoId=vid, media_body=media(paths.inside(ep, pkg["thumbnail"]))).execute()
        except Exception as e:  # noqa: BLE001 - the video is up; report and go on
            result["notes"].append(f"thumbnail not set: {type(e).__name__} (custom thumbnails need a verified channel)")
    for c in pkg.get("captions") or []:
        try:
            yt.captions().insert(part="snippet", body={"snippet": {"videoId": vid, "language": c.get("language", "en"),
                                                                   "name": c.get("name", ""), "isDraft": False}},
                                 media_body=media(paths.inside(ep, c["file"]))).execute()
        except Exception as e:  # noqa: BLE001
            result["notes"].append(f"captions {c.get('file')} not uploaded: {type(e).__name__}")
    _write_result(ep, result)
    if short and result.get("read_back") and comment_text(pkg):
        wait_s = float(config.get("crewcut", "youtube.comment_wait_s", COMMENT_WAIT_S))
        _hold_comment(episode, vid, rel, wait_s + COMMENT_RETRY_S)   # a stopped upload still leaves the retry
        result.update(_record_comment(episode, result, post_comment(yt, vid, pkg, wait_s=wait_s), rel))
    return result


def _write_result(ep: Path, result: dict) -> None:
    destination = ep / "export" / "upload-result.json"
    temporary = destination.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(result, indent=1), encoding="utf-8")
    temporary.replace(destination)


def _is_short(episode: str) -> bool:
    from .. import episodes
    try:
        return episodes.read(episode).get("kind") == "short"
    except FileNotFoundError:
        return False


def finish_short(yt, vid: str, pkg: dict, final_status: dict) -> dict:
    """Read the private Short back; only when title and description match, set the planned visibility or time.
    The link comment comes after this (post_comment), once YouTube has processed the video."""
    out: dict = {"read_back": False, "notes": []}
    items = yt.videos().list(part="snippet,status", id=vid).execute().get("items") or []
    if not items:
        out["notes"].append("could not read the Short back; it stays private")
        return out
    sn = items[0].get("snippet") or {}
    if sn.get("title") != pkg["title"] or (sn.get("description") or "").strip() != pkg["description"].strip():
        out["notes"].append("title or description differ after the upload; the Short stays private")
        return out
    out["read_back"] = True
    if final_status.get("privacyStatus") != "private" or final_status.get("publishAt"):
        status = {"privacyStatus": final_status.get("privacyStatus", "private"),
                  "selfDeclaredMadeForKids": final_status.get("selfDeclaredMadeForKids", False)}
        if final_status.get("publishAt"):
            status.update(privacyStatus="private", publishAt=final_status["publishAt"])
        if "containsSyntheticMedia" in final_status:
            status["containsSyntheticMedia"] = final_status["containsSyntheticMedia"]
        yt.videos().update(part="status", body={"id": vid, "status": status}).execute()
        out.update(privacy=status["privacyStatus"], publish_at=status.get("publishAt"))
    return out


# ---- the link comment under a Short ---------------------------------------------------------------------------------
def comment_text(pkg: dict) -> str | None:
    """The comment the publish card showed: the package's related_comment, or a default line with related_url."""
    if not pkg.get("related_url"):
        return None
    return pkg.get("related_comment") or f"The whole video: {pkg['related_url']}"


def error_text(e: Exception) -> str:
    """Status, reason and message of an API error. The class name alone ("HttpError") hid the cause."""
    status = getattr(getattr(e, "resp", None), "status", None)
    message, reasons = "", []
    try:
        err = json.loads(getattr(e, "content", None) or b"{}").get("error") or {}
        message = str(err.get("message") or "")
        reasons = [str(x["reason"]) for x in err.get("errors") or [] if isinstance(x, dict) and x.get("reason")]
    except (ValueError, TypeError, AttributeError):
        pass
    head = " ".join([type(e).__name__] + ([f"HTTP {status}"] if status else []) + reasons)
    return f"{head}: {message}" if message else head if status else f"{head}: {e}"


def _processing(yt, vid: str) -> tuple[str | None, str | None]:
    """YouTube's uploadStatus ("uploaded" while it processes, then "processed") and the video's channel id."""
    items = yt.videos().list(part="snippet,status", id=vid).execute().get("items") or []
    if not items:
        return None, None
    return (items[0].get("status") or {}).get("uploadStatus"), (items[0].get("snippet") or {}).get("channelId")


def _existing(yt, vid: str, channel: str | None, url: str) -> str | None:
    """The id of the channel's own top-level comment that already carries the link, so a retry never posts twice."""
    res = yt.commentThreads().list(part="snippet", videoId=vid, maxResults=100, order="time").execute()
    for thread in res.get("items") or []:
        sn = ((thread.get("snippet") or {}).get("topLevelComment") or {}).get("snippet") or {}
        author = (sn.get("authorChannelId") or {}).get("value")
        if url in (sn.get("textOriginal") or sn.get("textDisplay") or "") and (not channel or author == channel):
            return thread.get("id")
    return None


def post_comment(yt, vid: str, pkg: dict, wait_s: float = 0, sleep=time.sleep, clock=time.monotonic) -> dict:
    """Post the link comment once the video is processed, as the channel (commentThreads.insert), never twice.

    Returns {"status": "added" | "exists" | "pending" | "failed", "text", "at", and "id" or "error"}. "pending" means
    try again later: YouTube still processes the video, or the request failed on the network or on YouTube's side."""
    text = comment_text(pkg)
    out: dict = {"text": text, "at": db.now()}
    try:
        deadline = clock() + wait_s
        state, channel = _processing(yt, vid)
        while state not in ("processed", *GONE) and clock() < deadline:
            sleep(COMMENT_POLL_S)
            state, channel = _processing(yt, vid)
        if state in GONE:
            return {**out, "status": "failed", "error": f"the video is {state} on YouTube"}
        if state != "processed":
            return {**out, "status": "pending", "error": f"YouTube is still processing the video ({state or 'not found'})"}
        found = _existing(yt, vid, channel, pkg["related_url"])
        if found:
            return {**out, "status": "exists", "id": found}
        res = yt.commentThreads().insert(part="snippet", body={"snippet": {"videoId": vid, "topLevelComment": {
            "snippet": {"textOriginal": text}}}}).execute()
        return {**out, "status": "added", "id": res.get("id")}
    except Exception as e:  # noqa: BLE001 - the Short is up; report and go on
        status = getattr(getattr(e, "resp", None), "status", None)
        again = status is None or int(status) >= 500 or int(status) == 429
        return {**out, "status": "pending" if again else "failed", "error": error_text(e)}


def _note(episode: str, res: dict) -> str:
    if res["status"] == "added":
        return f"comment with the link to the long video added ({res.get('id')}); {PIN_NOTE}"
    if res["status"] == "exists":
        return f"the comment with the link to the long video is there ({res.get('id')}); {PIN_NOTE}"
    if res["status"] == "pending":
        return (f"comment not added yet: {res.get('error')}; Crewcut tries again on its own "
                f"(now: crewcut youtube comment {episode})")
    return f"comment not added: {res.get('error')}"


def _pending(episode: str) -> dict:
    try:
        return json.loads(db.kv_get(PENDING + episode) or "{}")
    except ValueError:
        return {}


def _hold_comment(episode: str, vid: str, rel: str, delay_s: float, now: float | None = None) -> None:
    """Note the comment as waiting before trying it, so the worker takes over if the upload is stopped meanwhile."""
    now = time.time() if now is None else now
    db.kv_set(PENDING + episode, json.dumps({"video_id": vid, "package": rel, "since": now, "tries": 0,
                                             "next": now + delay_s}))


def _clear(episode: str) -> None:
    with db.conn() as c:
        c.execute("DELETE FROM kv WHERE k = ?", (PENDING + episode,))


def _record_comment(episode: str, result: dict, res: dict, rel: str, now: float | None = None) -> dict:
    """Write the comment's outcome into upload-result.json and keep or clear the worker's retry."""
    now = time.time() if now is None else now
    if res["status"] == "pending":
        p = _pending(episode)
        since, tries = float(p.get("since", now)), int(p.get("tries", 0)) + 1
        if now - since >= COMMENT_GIVE_UP_S:
            res = {**res, "status": "failed", "error": f"{res.get('error')}; gave up after {tries} tries"}
        else:
            db.kv_set(PENDING + episode, json.dumps({"video_id": result.get("video_id"), "package": rel,
                                                     "since": since, "tries": tries,
                                                     "next": now + min(COMMENT_RETRY_S * 2 ** (tries - 1),
                                                                       COMMENT_RETRY_MAX_S)}))
    if res["status"] != "pending":
        _clear(episode)
    notes = [n for n in result.get("notes") or [] if not n.startswith(("comment ", "the comment "))]
    update = {"comment": res, "notes": notes + [_note(episode, res)]}
    result.update(update)
    _write_result(paths.episode_dir(episode), result)
    return update


def comment(episode: str, rel: str | None = None, youtube=None, wait_s: float = 0, sleep=time.sleep,
            clock=time.monotonic, now: float | None = None) -> dict:
    """Post (or find) the Short's link comment under the recorded video. The text is the one of the package that the
    accepted publish card covers; a package changed after the card is refused."""
    approvals.require_right("publish")
    ep = paths.episode_dir(episode)
    path = ep / "export" / "upload-result.json"
    if not path.is_file():
        raise FileNotFoundError("The episode has no upload result (export/upload-result.json): nothing to comment on.")
    result = json.loads(path.read_text(encoding="utf-8"))
    if not result.get("video_id"):
        raise ValueError("The episode has no recorded YouTube video ID.")
    rel = rel or _pending(episode).get("package") or result.get("package") or "export/upload.json"
    pkg_path, pkg = load_package(episode, rel)
    if not comment_text(pkg):
        raise ValueError("The package has no related_url: there is no link comment to post.")
    if approved_card(episode, pkg_path) is None:
        raise PermissionError("The package differs from every accepted publish card: the comment text must be the "
                              "one the user approved. Propose a publish card for the package first.")
    done = result.get("comment") or {}
    if done.get("status") in ("added", "exists") and done.get("text") == comment_text(pkg):
        _clear(episode)
        return done
    if youtube is None:
        from googleapiclient.discovery import build

        from .auth import credentials
        youtube = build("youtube", "v3", credentials=credentials(), cache_discovery=False)
    res = post_comment(youtube, result["video_id"], pkg, wait_s=wait_s, sleep=sleep, clock=clock)
    return _record_comment(episode, result, res, rel, now)["comment"]


_tick_lock = threading.Lock()


def due_comments(now: float | None = None) -> list[str]:
    """Episodes whose link comment waits and is due for the next try."""
    now = time.time() if now is None else now
    with db.conn() as c:
        rows = list(c.execute("SELECT k, v FROM kv WHERE k LIKE ?", (PENDING + "%",)))
    due = []
    for row in rows:
        try:
            nxt = float(json.loads(row["v"] or "{}").get("next", 0))
        except (ValueError, TypeError):
            nxt = 0
        if nxt <= now:
            due.append(row["k"].removeprefix(PENDING))
    return due


def comments_tick(now: float | None = None, youtube=None, background: bool = True) -> None:
    """Runs in the worker: try the waiting link comments that are due, one batch at a time, off the queue thread."""
    episodes = due_comments(now)
    if not episodes or not _tick_lock.acquire(blocking=False):
        return

    def go() -> None:
        from ..conductor import flow
        try:
            for episode in episodes:
                try:
                    res = comment(episode, youtube=youtube, now=now)
                except (FileNotFoundError, ValueError, PermissionError) as e:
                    _clear(episode)
                    flow.post(episode, f"The link comment was not posted: {e}", author="publisher")
                    continue
                except Exception:  # noqa: BLE001 - e.g. an expired login: try again later, not on every tick
                    p = _pending(episode)
                    if p:
                        p["next"] = (time.time() if now is None else now) + COMMENT_RETRY_MAX_S
                        db.kv_set(PENDING + episode, json.dumps(p))
                    continue
                if res["status"] == "added":
                    flow.post(episode, f"Link comment posted under the Short: \"{res['text']}\". Pin it in YouTube "
                              "Studio (the API cannot pin comments).", author="publisher")
                elif res["status"] == "failed":
                    flow.post(episode, f"The link comment was not posted: {res.get('error')}", author="publisher")
        finally:
            _tick_lock.release()

    if background:
        threading.Thread(target=go, daemon=True, name="youtube-comments").start()
    else:
        go()


def safe_name(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", s)[:60]


__all__ = ["upload", "validate", "load_package", "approved_card", "body_of", "safe_name", "comment",
           "post_comment", "comments_tick", "os"]
