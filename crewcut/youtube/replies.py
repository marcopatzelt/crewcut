"""Comment word -> link reply: the "send me the link" funnel, as a reply under the comment (YouTube has no DMs).

A Short ends with a comment ask ("If you want this too, comment GPU."). Its upload package names the word and the
link (`cta_keyword`, `cta_url`, approved on the publish card and recorded in export/upload-result.json). Every
`youtube.cta_replies_every_minutes` the worker reads the newest top-level comments of each published Short with such a
word (commentThreads.list) and answers every comment that contains the word, in any case and as a whole word, once,
with the channel's reply line (channel.json `upload.cta_reply`, "{url}" filled in) through comments.insert.

- Once per comment: answered comment ids are kept in the `cta_replies` table; a thread that already has a reply from
  the channel counts as answered too. The channel's own comments are never answered.
- At most `youtube.cta_replies_per_video_hour` replies per video in any hour and `youtube.cta_replies_per_day` in any
  24 hours for the whole channel (comments.insert costs 50 of the 10,000 daily quota units, an upload 1,600). A comment
  over the limit waits for the next run.
- `youtube.cta_replies`: "on" (default), "dry-run" (counts what it would send, sends and stores nothing) or "off".
  Long videos only with `youtube.cta_replies_long = true`. The config is read on every run: no restart needed.
- Logs, the chat and export/cta-replies.json hold counts and ids only, never a commenter's name or text.

This is the only automatic posting path: the channel owner asked for exactly these replies (keyword comments under
their own videos, the link they approved on the publish card). Everything else still needs a card.
"""

from __future__ import annotations

import json
import threading
import time
import traceback
from datetime import UTC, datetime

from .. import config, cta, db, episodes, paths
from . import guard

MODES = ("on", "dry-run", "off")
MAX_PAGES = 20                     # 2,000 newest comments per video and run
CURSOR = "cta_replies_cursor:"     # kv: per video, the publishedAt up to which every comment was handled
STATUS_FILE = "export/cta-replies.json"
QUOTA = ("quotaExceeded", "dailyLimitExceeded", "rateLimitExceeded", "userRateLimitExceeded")


def settings() -> dict:
    raw = config.get("crewcut", "youtube.cta_replies", "on")
    mode = "on" if raw is True else "off" if raw is False else str(raw or "on").strip().lower().replace("_", "-")
    mode = {"dry": "dry-run", "dryrun": "dry-run"}.get(mode, mode)
    return {"mode": mode if mode in MODES else "off",
            "every_s": max(60.0, float(config.get("crewcut", "youtube.cta_replies_every_minutes", 15)) * 60),
            "per_video_hour": max(0, int(config.get("crewcut", "youtube.cta_replies_per_video_hour", 20))),
            "per_day": max(0, int(config.get("crewcut", "youtube.cta_replies_per_day", 100))),
            "long": bool(config.get("crewcut", "youtube.cta_replies_long", False))}


# ---- which videos -------------------------------------------------------------------------------------------------
def _approved_package_cta(episode: str, rel: str) -> tuple[str, str] | None:
    """For an upload from before the result file recorded the word: the package's word and link, only when an
    accepted publish card covers exactly this package."""
    from . import upload
    try:
        path, pkg = upload.load_package(episode, rel)
    except (FileNotFoundError, ValueError, OSError):
        return None
    if not (pkg.get("cta_keyword") and pkg.get("cta_url")) or upload.approved_card(episode, path) is None:
        return None
    return pkg["cta_keyword"], pkg["cta_url"]


def targets(episode: str | None = None, long: bool = False) -> list[dict]:
    """Uploaded videos with a comment word and its link: {episode, video_id, keyword, url, publish_at}."""
    out = []
    for eid in [episode] if episode else episodes.list_ids():
        try:
            kind = episodes.read(eid).get("kind")
        except (FileNotFoundError, ValueError):
            continue
        if kind != "short" and not long:
            continue
        res = guard.result_file(eid)
        if not res.get("video_id"):
            continue
        pair = (res.get("cta_keyword"), res.get("cta_url"))
        if not all(pair):
            pair = _approved_package_cta(eid, res.get("package") or "export/upload.json") or (None, None)
        word, url = pair
        if not cta.is_keyword(word) or not isinstance(url, str) or not url.strip():
            continue
        out.append({"episode": eid, "video_id": res["video_id"], "keyword": word, "url": url.strip(),
                    "publish_at": res.get("publish_at"), "short": kind == "short"})
    return out


# ---- the store ----------------------------------------------------------------------------------------------------
def _known(video_id: str) -> set[str]:
    with db.conn() as c:
        return {r["comment_id"] for r in c.execute("SELECT comment_id FROM cta_replies WHERE video_id = ?", (video_id,))}


def _record(episode: str, video_id: str, comment_id: str, status: str, reply_id: str | None, at: float) -> None:
    with db.conn() as c:
        c.execute("INSERT OR IGNORE INTO cta_replies (episode, video_id, comment_id, reply_id, status, at) "
                  "VALUES (?, ?, ?, ?, ?, ?)", (episode, video_id, comment_id, reply_id, status, at))


def sent_since(since: float, video_id: str | None = None) -> int:
    q, args = "SELECT COUNT(*) FROM cta_replies WHERE status = 'sent' AND at > ?", [since]
    if video_id:
        q, args = q + " AND video_id = ?", [*args, video_id]
    with db.conn() as c:
        return int(c.execute(q, args).fetchone()[0])


def _cursor(video_id: str) -> str:
    return db.kv_get(CURSOR + video_id) or ""


def _status_path(episode: str):
    return paths.episode_dir(episode) / STATUS_FILE


def read_status(episode: str) -> dict:
    try:
        d = json.loads(_status_path(episode).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return d if isinstance(d, dict) else {}


def _write_status(episode: str, data: dict) -> None:
    p = _status_path(episode)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)


# ---- one video ----------------------------------------------------------------------------------------------------
class Stop(Exception):
    """YouTube refused (comments off, no right, quota): stop this video for this run. `everything`: stop the run."""

    def __init__(self, message: str, everything: bool = False):
        super().__init__(message)
        self.everything = everything


def _http(e: Exception) -> tuple[int | None, list[str]]:
    status = getattr(getattr(e, "resp", None), "status", None)
    reasons: list[str] = []
    try:
        err = json.loads(getattr(e, "content", None) or b"{}").get("error") or {}
        reasons = [str(x.get("reason")) for x in err.get("errors") or [] if isinstance(x, dict)]
    except (ValueError, TypeError, AttributeError):
        pass
    return (int(status) if status is not None else None), reasons


def _call(request):
    """Execute one API request. 4xx: Stop (quota: the whole run); 5xx and network errors are raised as they are."""
    from .upload import error_text
    try:
        return request.execute()
    except Exception as e:  # noqa: BLE001
        status, reasons = _http(e)
        if status is not None and 400 <= status < 500:
            raise Stop(error_text(e), everything=bool(set(reasons) & set(QUOTA)) or status == 429) from e
        raise


def _top(thread: dict) -> tuple[str, dict]:
    top = (thread.get("snippet") or {}).get("topLevelComment") or {}
    return str(top.get("id") or thread.get("id") or ""), top.get("snippet") or {}


def _author(sn: dict) -> str | None:
    return (sn.get("authorChannelId") or {}).get("value")


def _answered_by(thread: dict, channel: str) -> str | None:
    """The id of the channel's own reply in the thread, if YouTube sent it along (the newest few replies)."""
    for r in (thread.get("replies") or {}).get("comments") or []:
        if _author(r.get("snippet") or {}) == channel:
            return r.get("id") or "found"
    return None


def _newest(yt, vid: str, cursor: str) -> tuple[list[dict], bool]:
    """Top-level comment threads newer than (or as old as) the cursor, newest first. reached: the cursor or the
    oldest comment was reached (False when MAX_PAGES stopped the walk)."""
    out, token = [], None
    for _ in range(MAX_PAGES):
        kw = {"part": "snippet,replies", "videoId": vid, "order": "time", "maxResults": 100, "textFormat": "plainText"}
        if token:
            kw["pageToken"] = token
        res = _call(yt.commentThreads().list(**kw)) or {}
        for thread in res.get("items") or []:
            published = str(_top(thread)[1].get("publishedAt") or "")
            if cursor and published and published < cursor:
                return out, True
            out.append(thread)
        token = res.get("nextPageToken")
        if not token:
            return out, True
    return out, False


def _video(yt, t: dict, s: dict, dry: bool, now: float, budget_day: list[int]) -> dict:
    """Answer the keyword comments under one video. Returns the run's counts for it."""
    vid, word = t["video_id"], t["keyword"]
    out = {"episode": t["episode"], "video_id": vid, "keyword": word, "url": t["url"], "mode": "dry-run" if dry else "on",
           "sent": 0, "would_send": 0, "matched": 0, "waiting": 0, "error": None}
    items = (_call(yt.videos().list(part="snippet,status", id=vid)) or {}).get("items") or []
    if not items:
        out["error"] = "the video is not on YouTube (deleted or not visible to this login)"
        return out
    channel = (items[0].get("snippet") or {}).get("channelId")
    privacy = (items[0].get("status") or {}).get("privacyStatus")
    if privacy != "public":
        out["skipped"] = f"not public yet ({privacy or 'unknown'})"
        return out
    cursor = _cursor(vid)
    threads, reached = _newest(yt, vid, cursor)
    known = _known(vid)
    hour_left = s["per_video_hour"] - sent_since(now - 3600, vid)
    text = cta.reply_text(t["url"])

    def wants(thread: dict) -> bool:
        cid, sn = _top(thread)
        return (bool(cid) and cid not in known and not (channel and _author(sn) == channel)
                and (thread.get("snippet") or {}).get("canReply", True) is not False
                and cta.has_keyword(sn.get("textOriginal") or sn.get("textDisplay") or "", word))

    handled_until = None      # publishedAt up to which every comment (oldest first) is handled
    for thread in reversed(threads):          # oldest first: whoever asked first gets the link first
        cid, sn = _top(thread)
        if out["waiting"]:                    # over the limit: the rest waits for the next run
            out["waiting"] += wants(thread)
            continue
        if wants(thread):
            out["matched"] += 1
            found = _answered_by(thread, channel) if channel else None
            if found:
                if not dry:
                    _record(t["episode"], vid, cid, "found", None if found == "found" else found, now)
            elif hour_left <= 0 or budget_day[0] <= 0:
                out["waiting"] = 1
                continue
            elif dry:
                out["would_send"] += 1
                hour_left, budget_day[0] = hour_left - 1, budget_day[0] - 1
            else:
                try:
                    res = _call(yt.comments().insert(part="snippet", body={"snippet": {"parentId": cid,
                                                                                       "textOriginal": text}})) or {}
                except Stop as e:
                    out.update(error=str(e), stop_all=e.everything)
                    break
                except Exception as e:  # noqa: BLE001 - network or YouTube's side: the next run tries again
                    from .upload import error_text
                    out["error"] = f"{error_text(e)} (tried again in the next run)"
                    break
                _record(t["episode"], vid, cid, "sent", res.get("id"), now)
                out["sent"] += 1
                hour_left, budget_day[0] = hour_left - 1, budget_day[0] - 1
            known.add(cid)
        handled_until = str(sn.get("publishedAt") or "") or handled_until
    if not dry and reached and handled_until and handled_until > cursor:
        db.kv_set(CURSOR + vid, handled_until)
    return out


# ---- a run --------------------------------------------------------------------------------------------------------
def _client():
    from googleapiclient.discovery import build

    from .auth import credentials
    return build("youtube", "v3", credentials=credentials(), cache_discovery=False)


def _due(t: dict, now: float) -> bool:
    """A scheduled video has no viewer comments before its time."""
    at = t.get("publish_at")
    if not at:
        return True
    try:
        return datetime.fromisoformat(str(at).replace("Z", "+00:00")).astimezone(UTC).timestamp() <= now
    except ValueError:
        return True


def run(episode: str | None = None, dry_run: bool | None = None, youtube=None, now: float | None = None,
        post: bool = True) -> list[dict]:
    """One pass over the videos with a comment word. dry_run None: from the config ("dry-run"). Returns one result per
    video; never raises for one video's problem."""
    s = settings()
    if s["mode"] == "off" and dry_run is None:
        return []
    dry = (s["mode"] == "dry-run") if dry_run is None else bool(dry_run)
    now = time.time() if now is None else now
    todo = [t for t in targets(episode, long=s["long"] or bool(episode)) if _due(t, now)]
    if not todo:
        return []
    yt = youtube if youtube is not None else _client()
    budget_day = [s["per_day"] - sent_since(now - 86400)]
    results, stop_all = [], None
    for t in todo:
        if stop_all:
            res = {"episode": t["episode"], "video_id": t["video_id"], "keyword": t["keyword"], "url": t["url"],
                   "sent": 0, "would_send": 0, "matched": 0, "waiting": 0, "error": stop_all,
                   "mode": "dry-run" if dry else "on"}
        else:
            try:
                res = _video(yt, t, s, dry, now, budget_day)
                if res.pop("stop_all", False):
                    stop_all = res["error"]
            except Stop as e:
                res = {"episode": t["episode"], "video_id": t["video_id"], "keyword": t["keyword"], "url": t["url"],
                       "sent": 0, "would_send": 0, "matched": 0, "waiting": 0, "error": str(e),
                       "mode": "dry-run" if dry else "on"}
                if e.everything:
                    stop_all = str(e)
            except Exception as e:  # noqa: BLE001 - network or YouTube's side: the next run tries again
                from .upload import error_text
                res = {"episode": t["episode"], "video_id": t["video_id"], "keyword": t["keyword"], "url": t["url"],
                       "sent": 0, "would_send": 0, "matched": 0, "waiting": 0, "mode": "dry-run" if dry else "on",
                       "error": f"{error_text(e)} (tried again in the next run)"}
        results.append(res)
        _report(res, now, post)
    return results


def _report(res: dict, now: float, post: bool) -> None:
    """The status file of the episode, and one chat line when replies went out or a new problem came up."""
    ep = res["episode"]
    before = read_status(ep)
    total = int(before.get("sent_total") or 0) + res["sent"]
    data = {"video_id": res["video_id"], "keyword": res["keyword"], "url": res["url"], "mode": res["mode"],
            "last_run": datetime.fromtimestamp(now, UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), "sent_last_run": res["sent"],
            "sent_total": total, "would_send_last_run": res["would_send"], "waiting": res["waiting"],
            "last_error": res.get("error"), "skipped": res.get("skipped"),
            "last_sent": (datetime.fromtimestamp(now, UTC).strftime("%Y-%m-%dT%H:%M:%SZ") if res["sent"]
                          else before.get("last_sent"))}
    try:
        _write_status(ep, data)
    except OSError:
        traceback.print_exc()
    if not post:
        return
    from ..conductor import flow
    try:
        if res["sent"]:
            flow.post(ep, f"Answered {res['sent']} comment{'s' if res['sent'] != 1 else ''} with the word "
                      f"{res['keyword']} with the link {res['url']}" + (f"; {res['waiting']} wait for the next run "
                                                                         "(hourly or daily limit)" if res["waiting"]
                                                                         else "") + ".", author="publisher")
        if res.get("error") and res["error"] != before.get("last_error"):
            flow.post(ep, f"Comment replies with the link ({res['keyword']}) stopped for this video: {res['error']}",
                      author="publisher")
    except Exception:  # noqa: BLE001 - the chat line must never stop the replies
        traceback.print_exc()


# ---- the worker ---------------------------------------------------------------------------------------------------
_lock = threading.Lock()
_last = {"t": 0.0}


def tick(now: float | None = None, youtube=None, background: bool = True) -> bool:
    """In the worker: every `cta_replies_every_minutes` one run, off the queue thread. Not a crew job: it costs no
    tokens and runs while new jobs are paused. True when a run started."""
    s = settings()
    if s["mode"] == "off":
        return False
    now = time.time() if now is None else now
    if now - _last["t"] < s["every_s"]:
        return False
    _last["t"] = now
    if youtube is None:
        from . import auth
        if not auth.connected():
            return False
    if not targets(long=s["long"]) or not _lock.acquire(blocking=False):
        return False

    def go() -> None:
        try:
            run(youtube=youtube, now=now)
        except Exception:  # noqa: BLE001 - e.g. an expired login: the next run tries again
            traceback.print_exc()
        finally:
            _lock.release()

    if background:
        threading.Thread(target=go, daemon=True, name="youtube-cta-replies").start()
    else:
        go()
    return True


def status(episode: str | None = None) -> dict:
    s = settings()
    now = time.time()
    rows = []
    for t in targets(episode, long=s["long"] or bool(episode)):
        rows.append({**{k: t[k] for k in ("episode", "video_id", "keyword", "url")},
                     "sent_last_hour": sent_since(now - 3600, t["video_id"]), **read_status(t["episode"])})
    return {"mode": s["mode"], "every_minutes": round(s["every_s"] / 60), "per_video_hour": s["per_video_hour"],
            "per_day": s["per_day"], "long_videos": s["long"], "sent_last_24h": sent_since(now - 86400),
            "videos": rows}


__all__ = ["MODES", "STATUS_FILE", "read_status", "run", "sent_since", "settings", "status", "targets", "tick"]
