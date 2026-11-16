#!/usr/bin/env python3
"""Find the next video idea in data (skill: skills/idea).

Commands:
  channel <@handle | channel id | URL>   channel size, median of long uploads, recent and top videos
  scan [--channel X ...] [--search Q ...]  fresh outliers on the reference channels (channel.json reference_channels);
                                           with --search also small channels that broke through
  check "<topic>" [--query Q ...]          saturation of a format in the source market and the gap in the user's market

Thresholds come from the style pack (channel.json "idea"; the user's market from "language" and "country").

Data: YouTube Data API v3 with a key in the environment variable YOUTUBE_API_KEY (free, with a daily quota of
10,000 units; channel, playlist and video reads cost 1 unit, a search costs 100). The key is never printed.
yt-dlp is an opt-in fallback the user switches on with CREWCUT_IDEA_YTDLP=1; then pass --source ytdlp.

Status: the measuring functions (outliers, saturation, gap) are unit-tested. Both data sources are UNTESTED
against the live services.

Exit: 0 ok, 1 error, 2 wrong call, 4 missing key.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

DEFAULTS = {"market_language": "en", "market_region": "US", "fresh_days": 14, "long_min_seconds": 181,
            "outlier_x_median": 2.0, "outlier_per_sub": 1.0, "small_channel_subs": [1000, 100000],
            "breakthrough_per_sub": 3.0, "gap_thin_views": 30000}
STRONG_MIN_VIEWS = 10000   # a first strong hit needs at least this many views ...
STRONG_SHARE = 0.25        # ... and at least this share of the best video
WINDOW_DAYS = 112          # copies are counted over 16 weeks


class SourceError(Exception):
    pass


class MissingKey(Exception):
    pass


def _brand():
    try:
        from crewcut import brand
    except ImportError:  # run from a checkout without the package installed
        sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
        from crewcut import brand
    return brand


def settings(pack) -> dict:
    cfg = dict(DEFAULTS)
    cfg.update({k: v for k, v in (pack.value("channel.idea", {}) or {}).items() if v is not None})
    cfg["home_language"] = pack.value("channel.language")
    cfg["home_region"] = pack.value("channel.country")
    return cfg


# ---------- pure helpers (tested) ----------
def median(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def parse_duration(iso: str | None) -> int | None:
    """ISO 8601 duration from the API ('PT1H2M3S') to seconds."""
    if not iso:
        return None
    m = re.fullmatch(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?", iso)
    if not m:
        return None
    d, h, mi, s = (int(x or 0) for x in m.groups())
    return ((d * 24 + h) * 60 + mi) * 60 + s


def parse_time(s: str | None) -> dt.datetime | None:
    if not s:
        return None
    try:
        t = dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=dt.UTC)


def is_long(v: dict, long_min: int) -> bool:
    return v.get("duration_s") is None or v["duration_s"] >= long_min


def channel_median(uploads: list[dict], long_min: int, n: int = 30) -> float | None:
    """Median views of the last n long uploads (newest first)."""
    longs = [v for v in uploads if is_long(v, long_min) and v.get("views") is not None]
    return median([v["views"] for v in longs[:n]])


def outliers(uploads: list[dict], subs: int | None, now: dt.datetime, cfg: dict) -> list[dict]:
    """Fresh long uploads with their ratios. uploads: newest first, each {id, title, views, published, duration_s}.

    x_median: views / median of the last 30 long uploads of the channel.
    x_last5:  views / average of the 5 long uploads before it (the early signal after at most 3 days).
    per_sub:  views / subscribers.
    """
    longs = [v for v in uploads if is_long(v, cfg["long_min_seconds"]) and v.get("views") is not None]
    med = median([v["views"] for v in longs[:30]])
    out = []
    for i, v in enumerate(longs):
        t = parse_time(v.get("published"))
        if t is None:
            continue
        age = (now - t).total_seconds() / 86400
        if age > cfg["fresh_days"]:
            continue
        before = [x["views"] for x in longs[i + 1:i + 6]]
        avg5 = sum(before) / 5 if len(before) == 5 else None
        row = dict(v, age_days=round(age, 1),
                   x_median=round(v["views"] / med, 2) if med else None,
                   x_last5=round(v["views"] / avg5, 2) if avg5 else None,
                   per_sub=round(v["views"] / subs, 3) if subs else None)
        row["outlier"] = is_outlier(row, cfg)
        out.append(row)
    return out


def is_outlier(v: dict, cfg: dict) -> bool:
    return bool((v.get("x_median") or 0) >= cfg["outlier_x_median"]
                or (v.get("per_sub") or 0) >= cfg["outlier_per_sub"]
                or (v.get("age_days", 99) <= 3 and (v.get("x_last5") or 0) > 1))


def breakthrough(views: int, subs: int | None, cfg: dict) -> bool:
    lo, hi = cfg["small_channel_subs"]
    return bool(subs and lo <= subs <= hi and views / subs >= cfg["breakthrough_per_sub"])


def word_matcher(topic: str, share: float = 0.6):
    """A title matches a free topic when it holds at least 60 % of the topic's content words.

    Content words: 4 or more letters, or numbers. Matched on the first 5 characters, so plural and other endings
    still count. Language-neutral on purpose; use --pattern for a precise format rule.
    """
    toks = [w for w in re.findall(r"[^\W_]+", topic.lower()) if len(w) >= 4 or w.isdigit()]
    stems = list(dict.fromkeys(w[:5] for w in toks))
    need = max(1, round(share * len(stems))) if stems else 1

    def match(title: str) -> bool:
        t = (title or "").lower()
        return sum(1 for s in stems if re.search(r"(?<!\w)" + re.escape(s), t)) >= need
    match.describe = f"at least {need} of {len(stems)} words: {', '.join(toks)}"
    return match


def regex_matcher(pattern: str):
    rx = re.compile(pattern, re.I)

    def match(title: str) -> bool:
        return bool(rx.search(title or ""))
    match.describe = f"pattern {pattern}"
    return match


def brief(v: dict) -> dict:
    return {k: v.get(k) for k in ("id", "title", "channel", "channel_id", "views", "published")}


def saturation(copies: list[dict], now: dt.datetime) -> dict:
    """How far copies have filled a format. copies: market videos that match the format, any order.

    Verdicts (rules in skills/idea/references/method.md):
      no proof  no video over 10,000 views in 16 weeks
      closed    first strong hit older than 21 days, at least 10 copies after it, late copies weak
      closing   first strong hit at most 21 days old and at least 3 copies, or late copies falling
      open      fewer than 3 copies in the last 28 days
      stable    late copies still reach 10 % of the first strong hit
    """
    dated = []
    for v in copies:
        t = parse_time(v.get("published"))
        if t is not None and (now - t).days <= WINDOW_DAYS and v.get("views") is not None:
            dated.append(dict(v, _t=t))
    dated.sort(key=lambda v: v["_t"])
    if not dated:
        return {"verdict": "no proof", "reason": "no dated copy in 16 weeks", "copies": 0}
    best = max(dated, key=lambda v: v["views"])
    if best["views"] < STRONG_MIN_VIEWS:
        return {"verdict": "no proof", "reason": f"best video has only {best['views']} views", "best": brief(best),
                "copies": len(dated)}
    first = next(v for v in dated if v["views"] >= max(STRONG_MIN_VIEWS, STRONG_SHARE * best["views"]))
    after = [v for v in dated if v["_t"] > first["_t"]]
    age = (now - first["_t"]).days
    ripe = [v for v in after if (now - v["_t"]).days >= 7]
    last28 = [v for v in after if (now - v["_t"]).days <= 28]
    if len(ripe) >= 16:
        late, late_how = median([v["views"] for v in ripe[15:30]]), "copies 16 to 30, at least 7 days old"
    elif ripe:
        late, late_how = median([v["views"] for v in ripe[-5:]]), f"the last {min(5, len(ripe))} copies, at least 7 days old"
    else:
        late, late_how = None, "no copy is 7 days old yet"
    if age > 21 and len(after) >= 10 and late is not None and late < max(1000, 0.01 * best["views"]):
        verdict = "closed"
    elif age <= 21 and len(after) >= 3:
        verdict = "closing"
    elif len(last28) < 3:
        verdict = "open"
    elif late is not None and late >= 0.1 * first["views"]:
        verdict = "stable"
    else:
        verdict = "closing"
    return {"verdict": verdict, "first": brief(first), "first_age_days": age, "best": brief(best),
            "copies": len(after), "copies_28_days": len(last28),
            "copies_7_days": sum(1 for v in after if (now - v["_t"]).days <= 7),
            "late_median": late, "late_how": late_how, "copies_median": median([v["views"] for v in after]),
            "send_by": (first["_t"] + dt.timedelta(days=14)).date().isoformat(),
            "window_until": (first["_t"] + dt.timedelta(days=21)).date().isoformat()}


def gap(home_videos: list[dict], thin_views: int) -> dict:
    """The user's market: empty (no video on the format), thin (best under thin_views), taken."""
    if not home_videos:
        return {"gap": "empty", "best": None}
    best = max(home_videos, key=lambda v: v.get("views") or 0)
    return {"gap": "thin" if (best.get("views") or 0) < thin_views else "taken", "best": brief(best)}


def hints(sat: dict, g: dict | None, imports: list[dict]) -> list[str]:
    out = []
    best = (sat.get("best") or {}).get("views") or 0
    if sat.get("copies_median") and best and sat["copies_median"] < 0.05 * best:
        out.append("Way 1: the typical copy is weak; the best version of this format can still win.")
    if g and g["gap"] in ("empty", "thin") and best >= 100000:
        out.append("Way 2: a proven format with no strong version in the user's market.")
    if sat.get("verdict") == "closed":
        out.append("Closed in the source market: only with a test subject that belongs to the user's market.")
    if imports:
        out.append(f"{len(imports)} video(s) from the source market show up in the user's search with a translated "
                   f"title; the largest has {max(v.get('views') or 0 for v in imports)} views.")
    return out


def lang_of(v: dict) -> str:
    return (v.get("lang") or "").lower()


# ---------- data sources ----------
class YouTubeAPI:
    """YouTube Data API v3, read only, with an API key. Untested against the live service."""
    BASE = "https://www.googleapis.com/youtube/v3/"
    COST = {"search": 100}

    def __init__(self, key: str):
        self._key = key
        self.units = 0

    def _get(self, endpoint: str, **params) -> dict:
        params = {k: v for k, v in params.items() if v not in (None, "")}
        params["key"] = self._key
        url = self.BASE + endpoint + "?" + urllib.parse.urlencode(params)
        self.units += self.COST.get(endpoint, 1)
        req = urllib.request.Request(url, headers={"User-Agent": "crewcut-idea"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:  # never echo the URL: it holds the key
            try:
                msg = json.loads(e.read().decode("utf-8"))["error"]["message"]
            except Exception:  # noqa: BLE001
                msg = e.reason
            raise SourceError(f"YouTube API {endpoint}: HTTP {e.code} {msg}") from None
        except urllib.error.URLError as e:
            raise SourceError(f"YouTube API {endpoint}: {e.reason}") from None

    def channel(self, ref: str) -> dict:
        kind, val = parse_channel_ref(ref)
        params = {"forHandle": val} if kind == "handle" else {"id": val}
        d = self._get("channels", part="snippet,statistics,contentDetails", **params)
        if not d.get("items"):
            raise SourceError(f"channel not found: {ref}")
        it = d["items"][0]
        st = it.get("statistics", {})
        return {"id": it["id"], "title": it["snippet"].get("title"),
                "subs": None if st.get("hiddenSubscriberCount") else int(st.get("subscriberCount", 0) or 0),
                "country": it["snippet"].get("country"), "lang": it["snippet"].get("defaultLanguage"),
                "uploads": it.get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads")}

    def uploads(self, ch: dict, n: int = 50) -> list[dict]:
        ids, token = [], None
        while len(ids) < n and ch.get("uploads"):
            d = self._get("playlistItems", part="contentDetails", playlistId=ch["uploads"],
                          maxResults=min(50, n - len(ids)), pageToken=token)
            ids += [x["contentDetails"]["videoId"] for x in d.get("items", [])]
            token = d.get("nextPageToken")
            if not token:
                break
        vids = self.videos(ids)
        vids.sort(key=lambda v: v.get("published") or "", reverse=True)
        return vids

    def videos(self, ids: list[str]) -> list[dict]:
        out = []
        for i in range(0, len(ids), 50):
            d = self._get("videos", part="snippet,statistics,contentDetails", id=",".join(ids[i:i + 50]))
            for it in d.get("items", []):
                sn, st = it.get("snippet", {}), it.get("statistics", {})
                out.append({"id": it["id"], "title": sn.get("title"), "channel": sn.get("channelTitle"),
                            "channel_id": sn.get("channelId"), "published": sn.get("publishedAt"),
                            "views": int(st["viewCount"]) if "viewCount" in st else None,
                            "duration_s": parse_duration(it.get("contentDetails", {}).get("duration")),
                            "lang": sn.get("defaultAudioLanguage") or sn.get("defaultLanguage")})
        return out

    def search(self, q: str, *, order: str = "relevance", after: dt.datetime | None = None,
               lang: str | None = None, region: str | None = None, n: int = 50) -> list[dict]:
        d = self._get("search", part="snippet", type="video", q=q, order=order, maxResults=min(50, n),
                      publishedAfter=after.strftime("%Y-%m-%dT%H:%M:%SZ") if after else None,
                      relevanceLanguage=lang, regionCode=region)
        ids = [x["id"]["videoId"] for x in d.get("items", []) if x.get("id", {}).get("videoId")]
        return self.videos(ids)

    def subscribers(self, channel_ids: list[str]) -> dict[str, int | None]:
        out = {}
        ids = list(dict.fromkeys(c for c in channel_ids if c))
        for i in range(0, len(ids), 50):
            d = self._get("channels", part="statistics", id=",".join(ids[i:i + 50]))
            for it in d.get("items", []):
                st = it.get("statistics", {})
                out[it["id"]] = None if st.get("hiddenSubscriberCount") else int(st.get("subscriberCount", 0) or 0)
        return out


class YtDlp:
    """Opt-in fallback through yt-dlp (public pages, no key). Flat lists carry no exact dates, so only up to
    `exact` candidates per call get their date from the video page. Untested."""

    def __init__(self, exact: int = 6):
        if os.environ.get("CREWCUT_IDEA_YTDLP") != "1":
            raise SourceError("yt-dlp is off. The user switches it on with CREWCUT_IDEA_YTDLP=1.")
        if not shutil.which("yt-dlp"):
            raise SourceError("yt-dlp is not installed.")
        self.units = 0
        self.exact = exact

    def _run(self, *args, timeout=120) -> dict:
        p = subprocess.run(["yt-dlp", "-J", "--flat-playlist", "--sleep-requests", "1", *args],
                           capture_output=True, text=True, timeout=timeout)
        if p.returncode:
            raise SourceError("yt-dlp: " + (p.stderr.strip().splitlines() or ["failed"])[-1][:200])
        return json.loads(p.stdout)

    @staticmethod
    def _video(e: dict, d: dict | None = None) -> dict:
        ts = e.get("timestamp")
        return {"id": e.get("id"), "title": e.get("title"), "channel": e.get("channel") or (d or {}).get("channel"),
                "channel_id": e.get("channel_id") or (d or {}).get("channel_id"), "views": e.get("view_count"),
                "duration_s": int(e["duration"]) if e.get("duration") else None, "lang": e.get("language"),
                "published": dt.datetime.fromtimestamp(ts, dt.UTC).isoformat() if ts else None}

    def channel(self, ref: str) -> dict:
        kind, val = parse_channel_ref(ref)
        url = f"https://www.youtube.com/{val}" if kind == "handle" else f"https://www.youtube.com/channel/{val}"
        d = self._run("--playlist-end", "50", url + "/videos")
        self._cache = [self._video(e, d) for e in d.get("entries", [])]
        return {"id": d.get("channel_id"), "title": d.get("channel"), "subs": d.get("channel_follower_count"),
                "country": None, "lang": None, "uploads": url}

    def uploads(self, ch: dict, n: int = 50) -> list[dict]:
        vids = getattr(self, "_cache", [])[:n]
        return self._dates(vids)

    def _dates(self, vids: list[dict]) -> list[dict]:
        for v in sorted([v for v in vids if not v.get("published")], key=lambda v: -(v.get("views") or 0))[:self.exact]:
            p = subprocess.run(["yt-dlp", "-J", "--skip-download", f"https://www.youtube.com/watch?v={v['id']}"],
                               capture_output=True, text=True, timeout=120)
            if p.returncode == 0:
                d = json.loads(p.stdout)
                if d.get("timestamp"):
                    v["published"] = dt.datetime.fromtimestamp(d["timestamp"], dt.UTC).isoformat()
                v["lang"] = v.get("lang") or d.get("language")
        return vids

    def search(self, q: str, *, order: str = "relevance", after=None, lang=None, region=None, n: int = 50):
        d = self._run(f"ytsearch{n}:{q}")
        return self._dates([self._video(e) for e in d.get("entries", [])])

    def subscribers(self, channel_ids):
        return {}


def parse_channel_ref(ref: str) -> tuple[str, str]:
    """'@name', 'UC…' or a channel URL to ('handle', '@name') or ('id', 'UC…')."""
    ref = ref.strip()
    m = re.search(r"youtube\.com/(@[\w.-]+)", ref) or re.fullmatch(r"(@[\w.-]+)", ref)
    if m:
        return "handle", m.group(1)
    m = re.search(r"(UC[\w-]{22})", ref)
    if m:
        return "id", m.group(1)
    return "handle", "@" + ref.lstrip("@")


def make_source(name: str):
    if name == "ytdlp":
        return YtDlp()
    key = os.environ.get("YOUTUBE_API_KEY")
    if not key:
        raise MissingKey("YOUTUBE_API_KEY is not set. The user creates a free key in the Google Cloud console "
                         "(YouTube Data API v3) and puts it in .env.")
    return YouTubeAPI(key)


# ---------- commands ----------
def cmd_channel(a, cfg, src, now) -> dict:
    ch = src.channel(a.ref)
    ups = src.uploads(ch, a.count)
    med = channel_median(ups, cfg["long_min_seconds"])
    longs = [v for v in ups if is_long(v, cfg["long_min_seconds"])]
    return {"channel": ch, "median_long_views": med, "uploads_read": len(ups),
            "recent": [brief(v) for v in longs[:a.recent]],
            "top": [brief(v) for v in sorted(longs, key=lambda v: -(v.get("views") or 0))[:a.top]],
            "outliers": [o for o in outliers(ups, ch.get("subs"), now, cfg) if o["outlier"]]}


def cmd_scan(a, cfg, src, now, pack) -> dict:
    refs = list(a.channel) or list(pack.value("channel.reference_channels", []) or [])
    rows, errors = [], []
    for ref in refs:
        try:
            ch = src.channel(ref)
            ups = src.uploads(ch, 50)
        except SourceError as e:
            errors.append(f"{ref}: {e}")
            continue
        for o in outliers(ups, ch.get("subs"), now, cfg):
            rows.append(dict(o, channel=ch.get("title"), subs=ch.get("subs")))
    found = sorted([r for r in rows if r["outlier"]], key=lambda r: -(r.get("x_median") or 0))
    small = []
    for q in a.search:
        vids = src.search(q, order="relevance", after=now - dt.timedelta(days=cfg["fresh_days"] * 2), n=50)
        vids = [v for v in vids if is_long(v, cfg["long_min_seconds"]) and v.get("views")]
        subs = src.subscribers([v["channel_id"] for v in vids])
        for v in vids:
            s = subs.get(v["channel_id"])
            if breakthrough(v["views"], s, cfg):
                small.append(dict(brief(v), subs=s, per_sub=round(v["views"] / s, 2), query=q))
    small.sort(key=lambda v: -v["per_sub"])
    return {"channels": len(refs), "fresh_videos": len(rows), "outliers": found, "breakthroughs": small,
            "errors": errors, "no_channels": not refs}


def cmd_check(a, cfg, src, now) -> dict:
    match = regex_matcher(a.pattern) if a.pattern else word_matcher(a.topic)
    home_match = regex_matcher(a.home_pattern) if a.home_pattern else match
    mlang, mreg = cfg["market_language"], cfg["market_region"]
    hlang, hreg = cfg.get("home_language"), cfg.get("home_region")
    queries = a.query or [a.topic]
    market: dict[str, dict] = {}
    for q in queries:
        for order, days in (("relevance", WINDOW_DAYS), ("date", 28)):
            for v in src.search(q, order=order, after=now - dt.timedelta(days=days), lang=mlang, region=mreg, n=50):
                if not match(v.get("title")) or not is_long(v, cfg["long_min_seconds"]):
                    continue
                if lang_of(v) and not lang_of(v).startswith(mlang):
                    continue
                market.setdefault(v["id"], v)
    copies = list(market.values())
    sat = saturation(copies, now)
    proof = []
    top = sorted(copies, key=lambda v: -(v.get("views") or 0))[:a.proof]
    for v in top:
        row = brief(v)
        try:
            ch = src.channel(v["channel_id"]) if v.get("channel_id") else None
            ups = src.uploads(ch, 30) if ch else []
            med = channel_median(ups, cfg["long_min_seconds"])
            row.update(subs=ch.get("subs") if ch else None,
                       x_median=round(v["views"] / med, 2) if med else None,
                       per_sub=round(v["views"] / ch["subs"], 2) if ch and ch.get("subs") else None)
        except SourceError as e:
            row["error"] = str(e)
        proof.append(row)
    g, home, imports = None, [], []
    same_market = not hlang or hlang.split("-")[0] == mlang.split("-")[0]
    if not same_market:
        found: dict[str, dict] = {}
        for q in a.home_query or queries:
            for v in src.search(q, order="relevance", after=now - dt.timedelta(days=365), lang=hlang, region=hreg,
                                n=25):
                if (home_match(v.get("title")) or match(v.get("title"))) and is_long(v, cfg["long_min_seconds"]):
                    found.setdefault(v["id"], v)
        home = [v for v in found.values() if lang_of(v).startswith(hlang.lower())]
        imports = [v for v in found.values() if lang_of(v).startswith(mlang)]
        g = gap(home, cfg["gap_thin_views"])
    return {"topic": a.topic, "date": now.date().isoformat(), "rule": match.describe, "queries": queries,
            "market": {"language": mlang, "region": mreg, "matches": len(copies), "saturation": sat},
            "proof": proof,
            "home": None if same_market else {"language": hlang, "region": hreg, "gap": g,
                                              "videos": [brief(v) for v in sorted(home, key=lambda v: -(v.get("views") or 0))[:10]],
                                              "imports": [brief(v) for v in imports[:5]]},
            "hints": hints(sat, g, imports)}


def show(cmd: str, r: dict) -> None:
    def vid(v):
        return f"{v.get('views') or 0:>10,}  {(v.get('published') or '?')[:10]}  {(v.get('channel') or '')[:22]:22} " \
               f"{(v.get('title') or '')[:64]}  https://youtu.be/{v.get('id')}"
    if cmd == "channel":
        ch = r["channel"]
        print(f"{ch['title']}: {ch.get('subs') or '?'} subscribers, median of long uploads "
              f"{r['median_long_views'] or '?'} ({r['uploads_read']} uploads read)")
        print("Recent:")
        for v in r["recent"]:
            print("  " + vid(v))
        print("Top:")
        for v in r["top"]:
            print("  " + vid(v))
    elif cmd == "scan":
        if r["no_channels"]:
            print("No channels. Add reference_channels to channel.json or pass --channel.")
        print(f"{r['channels']} channels, {r['fresh_videos']} fresh long uploads, {len(r['outliers'])} outliers")
        for o in r["outliers"][:40]:
            print(f"  {o.get('x_median') or 0:>5}x median  {o.get('x_last5') or 0:>5}x last 5  "
                  f"{o.get('per_sub') or 0:>6}/sub  " + vid(o))
        for b in r["breakthroughs"][:20]:
            print(f"  SMALL {b['per_sub']:>5}/sub  subs {b['subs']:>7}  " + vid(b))
        for e in r["errors"]:
            print("  error: " + e)
    else:
        s = r["market"]["saturation"]
        print(f"Topic: {r['topic']}  ({r['rule']})")
        print(f"Source market {r['market']['language']}/{r['market']['region']}: {s['verdict'].upper()}, "
              f"{r['market']['matches']} matching videos" + (f" ({s['reason']})" if s.get("reason") else ""))
        if s.get("first"):
            print(f"  First strong hit ({s['first_age_days']} days ago): " + vid(s["first"]))
            print(f"  Copies after it: {s['copies']} (7 days {s['copies_7_days']}, 28 days {s['copies_28_days']}), "
                  f"late copies median {s['late_median']} ({s['late_how']})")
            print(f"  Window: send by {s['send_by']}, open until about {s['window_until']}")
        print("Proof (largest matches):")
        for p in r["proof"]:
            print(f"  {p.get('x_median') or '?':>5}x median  {p.get('per_sub') or '?':>6}/sub  " + vid(p))
        if r["home"]:
            g = r["home"]["gap"]
            print(f"User's market {r['home']['language']}: gap {g['gap'].upper()}"
                  + (f", best {g['best']['views']}" if g.get("best") else ""))
            for v in r["home"]["videos"][:6]:
                print("  " + vid(v))
        else:
            print("User's market is the source market: the saturation is the gap.")
        for h in r["hints"]:
            print("Hint: " + h)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Find the next video idea in data: outliers, saturation, gap.")
    ap.add_argument("--source", choices=("api", "ytdlp"), default="api", help="data source (ytdlp is opt-in)")
    ap.add_argument("--pack", help="style pack folder (default: the active pack)")
    ap.add_argument("--json", action="store_true", help="print JSON")
    ap.add_argument("--out", help="also write the JSON result to this file")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("channel", help="channel size, median, recent and top videos")
    c.add_argument("ref", help="@handle, channel id or channel URL")
    c.add_argument("--count", type=int, default=200, help="uploads to read (50 per unit)")
    c.add_argument("--recent", type=int, default=10)
    c.add_argument("--top", type=int, default=10)
    s = sub.add_parser("scan", help="fresh outliers on the reference channels")
    s.add_argument("--channel", action="append", default=[], help="@handle, id or URL (repeatable)")
    s.add_argument("--search", action="append", default=[], help="search for small channels that broke through "
                   "(100 units each)")
    k = sub.add_parser("check", help="saturation in the source market and the gap in the user's market")
    k.add_argument("topic", help="the format or topic in a few words")
    k.add_argument("--query", action="append", default=[], help="search in the source market (2 searches each)")
    k.add_argument("--home-query", action="append", default=[], help="search in the user's language")
    k.add_argument("--pattern", help="regex that a title must match to count as a copy")
    k.add_argument("--home-pattern", help="regex for titles in the user's language")
    k.add_argument("--proof", type=int, default=5, help="largest matches to measure against their channel")
    a = ap.parse_args(argv)
    pack = _brand().load(a.pack)
    cfg = settings(pack)
    now = dt.datetime.now(dt.UTC)
    try:
        src = make_source(a.source)
        if a.cmd == "channel":
            r = cmd_channel(a, cfg, src, now)
        elif a.cmd == "scan":
            r = cmd_scan(a, cfg, src, now, pack)
        else:
            r = cmd_check(a, cfg, src, now)
    except MissingKey as e:
        print(f"Error: {e}", file=sys.stderr)
        return 4
    except SourceError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    r["api_units"] = getattr(src, "units", 0)
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(r, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=1, default=str))
    else:
        show(a.cmd, r)
        if a.source == "api":
            print(f"\nAPI units used: {r['api_units']} (daily quota 10,000).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
