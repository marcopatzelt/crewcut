#!/usr/bin/env python3
"""Find the next video idea in data (skill: skills/idea). Rules: skills/idea/references/method.md.

Commands:
  channel <@handle | channel id | URL>   channel size, median of long uploads, recent and top videos, own outliers
  scan [--channel X ...] [--search Q ...]  fresh outliers on the reference channels (channel.json reference_channels);
                                           with --search also small channels that broke through
  collect --channel X ... | --channels-file F   every long upload of 12 months per channel, flops too (JSONL)
  formats <videos.jsonl> [--labels F]      hit rate of each format against each channel's normal rate, evidence level
  check "<topic>" [--query Q ...]          saturation of a format in the source market and the gap in the user's market
  audience "<title or topic>"              the audience score (pack channel.json idea.audience)
  rank review/idea-*.json [--cards]        grade, audience and the matching show format; --cards writes idea cards

Thresholds come from the style pack (channel.json "idea"; the user's market from "language" and "country").

Data: YouTube Data API v3. Reads cost 1 unit, a search 100, of 10,000 a day. `--source auto` (default) takes the key
in YOUTUBE_API_KEY, else the channel's own YouTube login (crewcut youtube auth). Keys and tokens are never printed.
yt-dlp is opt-in (CREWCUT_IDEA_YTDLP=1 or channel.json idea.search_source "ytdlp"): then searches go through yt-dlp
(no units) and only the cheap reads through the API; `--source ytdlp` takes everything from public pages.

Status: the measuring functions (baseline, outliers, hit-rate tests, evidence, saturation, gap, grade, audience) are
unit-tested with fixed data. The data sources are not tested against the live services in CI.

Exit: 0 ok, 1 error, 2 wrong call, 4 missing key or login.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import glob
import hashlib
import json
import math
import os
import random
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
            "outlier_x_median": 2.0, "strong_x_median": 3.0, "very_strong_x_median": 10.0,
            "outlier_per_sub": 1.0, "per_sub_max_days": 90, "small_channel_subs": [1000, 100000],
            "breakthrough_per_sub": 3.0, "min_views_market": 10000, "min_views_other": 3000,
            "well_proven_views": 50000, "baseline_before": 15, "baseline_after": 15, "baseline_months": 6,
            "baseline_min_uploads": 10, "baseline_min_median": 500, "mature_days": 28, "collect_months": 12,
            "decay_window_days": 56, "gap_thin_views": 30000, "gap_thin_x_market": 2.0,
            "imports_penalty_views": 100000, "coview_from": "2026-11-01", "search_source": "api", "audience": None}
STRONG_MIN_VIEWS = 10000   # a first strong hit needs at least this many views ...
STRONG_SHARE = 0.25        # ... and at least this share of the best video
WINDOW_DAYS = 112          # copies are counted over 16 weeks
BASE_PRIOR = 10            # a channel's normal hit rate is shrunk toward the pooled rate by this many videos
LEVELS = ("none", "one-channel", "hint", "medium", "strong")
FLAGS = ("collab", "news", "ad", "spike")
MECHANICS = ("comparison", "claim test", "self-experiment with a number", "build", "ranking or list", "tutorial",
             "reaction or analysis", "story or case", "news", "challenge with a limit", "tiers", "inversion")
CARD_FIELDS = ("premise", "mechanic", "interest_topic", "viral_vector", "stake", "title_template", "title_chars",
               "title_words", "thumb_pattern", "hook_type", "intro_seconds", "structure", "traffic_type",
               "cuts_per_minute", "topic_changes_per_minute")
STOPWORDS = {
    "de": "der die das und ist nicht mit für ich du wir ein eine einen mein meine dein deine so wie was wenn auch "
          "noch nur jetzt alles ohne gegen oder aber bei vom zum zur über einfach kostenlos endlich getestet",
    "en": "the and is not with for you your my this that what how why when all without against from just "
          "best free new tested every one",
    "es": "el la los las y es no con para tu mi esto que cómo por qué sin gratis nuevo mejor todo",
    "fr": "le la les et est pas avec pour tu ton mon ce que comment pourquoi sans gratuit nouveau tout",
    "pt": "o a os as e é não com para você seu meu isso que como por sem grátis novo melhor tudo",
}


class SourceError(Exception):
    pass


class MissingKey(Exception):
    pass


def _crewcut():
    try:
        import crewcut  # noqa: F401
    except ImportError:  # run from a checkout without the package installed
        sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    import crewcut
    return crewcut


def _brand():
    _crewcut()
    from crewcut import brand
    return brand


def settings(pack) -> dict:
    cfg = dict(DEFAULTS)
    cfg.update({k: v for k, v in (pack.value("channel.idea", {}) or {}).items() if v is not None})
    cfg["home_language"] = pack.value("channel.language")
    cfg["home_region"] = pack.value("channel.country")
    return cfg


def ytdlp_allowed(cfg: dict) -> bool:
    """yt-dlp is the user's choice: the environment switch or the pack's search_source."""
    return os.environ.get("CREWCUT_IDEA_YTDLP") == "1" or cfg.get("search_source") == "ytdlp"


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
    if v.get("kind") == "short":
        return False
    return v.get("duration_s") is None or v["duration_s"] >= long_min


def guess_lang(title: str | None) -> str | None:
    """A rough language guess from common words, for rows without a language. None when unsure."""
    words = re.findall(r"[^\W\d_]+", (title or "").lower())
    if not words:
        return None
    hits = {k: sum(1 for w in words if w in set(v.split())) for k, v in STOPWORDS.items()}
    if re.search(r"[äöüß]", (title or "").lower()):
        hits["de"] += 2
    best = max(hits, key=hits.get)
    return best if hits[best] >= 2 and list(hits.values()).count(hits[best]) == 1 else None


def lang_of(v: dict) -> str:
    return (v.get("lang") or "").lower()


def views_floor(v: dict, cfg: dict) -> int:
    lang = lang_of(v) or (guess_lang(v.get("title")) or "")
    return cfg["min_views_market"] if lang.startswith(cfg["market_language"]) else cfg["min_views_other"]


def channel_median(uploads: list[dict], long_min: int, n: int = 30) -> float | None:
    """Median views of the last n long uploads (newest first). Used for the market size (method section 9)."""
    longs = [v for v in uploads if is_long(v, long_min) and v.get("views") is not None]
    return median([v["views"] for v in longs[:n]])


def _dated_longs(uploads: list[dict], cfg: dict) -> list[dict]:
    out = []
    for v in uploads:
        if not is_long(v, cfg["long_min_seconds"]) or v.get("views") is None or v.get("live"):
            continue
        t = parse_time(v.get("published"))
        if t is not None:
            out.append(dict(v, _t=t))
    out.sort(key=lambda v: v["_t"], reverse=True)
    return out


def window_baseline(longs: list[dict], i: int, now: dt.datetime, cfg: dict) -> dict:
    """The normal views of a channel at the time of longs[i] (longs: dated long uploads, newest first).

    Up to `baseline_before` uploads before and `baseline_after` after it, at most `baseline_months` away, each at
    least `mature_days` old today; the video itself does not count. Fewer than `baseline_min_uploads`: no value.
    """
    v = longs[i]
    span = dt.timedelta(days=round(30.44 * cfg["baseline_months"]))

    def ok(x):
        return abs(x["_t"] - v["_t"]) <= span and (now - x["_t"]).days >= cfg["mature_days"]
    before = [x for x in longs[i + 1:] if ok(x)][:cfg["baseline_before"]]
    after = [x for x in reversed(longs[:i]) if ok(x)][:cfg["baseline_after"]]
    peers = before + after
    med = median([x["views"] for x in peers]) if len(peers) >= cfg["baseline_min_uploads"] else None
    cut = parse_time(cfg.get("coview_from"))
    mixed = bool(cut and peers and any((x["_t"] >= cut) != (v["_t"] >= cut) for x in peers))
    return {"median": med, "n": len(peers), "before": len(before), "after": len(after), "coview_mixed": mixed}


def tier(x: float | None, cfg: dict) -> str | None:
    if x is None:
        return None
    if x >= cfg["very_strong_x_median"]:
        return "very strong"
    if x >= cfg["strong_x_median"]:
        return "strong"
    return "candidate" if x >= cfg["outlier_x_median"] else None


def measure(uploads: list[dict], subs: int | None, now: dt.datetime, cfg: dict) -> list[dict]:
    """Every dated long upload of one channel with its measures (method section 2), newest first.

    basis_median  median views of the window around the video (window_baseline)
    x_median      views / basis_median; final only when the video is at least mature_days old, before that a
                  lower bound (the video still grows)
    x_last5       views / median of the 5 long uploads before it (the early signal)
    per_sub       views / subscribers, only for videos up to per_sub_max_days old
    """
    longs = _dated_longs(uploads, cfg)
    cut = parse_time(cfg.get("coview_from"))
    out = []
    for i, v in enumerate(longs):
        age = (now - v["_t"]).total_seconds() / 86400
        base = window_baseline(longs, i, now, cfg)
        before5 = [x["views"] for x in longs[i + 1:i + 6]]
        med5 = median(before5) if len(before5) == 5 else None
        x = round(v["views"] / base["median"], 2) if base["median"] else None
        row = {k: val for k, val in v.items() if k != "_t"}
        row.update(age_days=round(age, 1), basis_median=base["median"], basis_n=base["n"],
                   x_median=x, final=age >= cfg["mature_days"], log_x=round(math.log10(x), 3) if x else None,
                   x_last5=round(v["views"] / med5, 2) if med5 else None,
                   per_sub=round(v["views"] / subs, 3) if subs and age <= cfg["per_sub_max_days"] else None,
                   tier=tier(x, cfg), coview_era=bool(cut and v["_t"] >= cut), coview_mixed=base["coview_mixed"])
        row["early_signal"] = bool(age <= 3 and (row["x_last5"] or 0) > 1)
        row["outlier"] = is_outlier(row, cfg)
        out.append(row)
    return out


def is_outlier(v: dict, cfg: dict) -> bool:
    """x median or views per subscriber over the threshold, on a channel with a usable baseline and with enough
    views; or the early signal (x last 5 over 1 within 3 days)."""
    if v.get("early_signal") or (v.get("age_days", 99) <= 3 and (v.get("x_last5") or 0) > 1):
        return True
    if v.get("views") is not None and v["views"] < views_floor(v, cfg):
        return False
    if v.get("basis_median") is not None and v["basis_median"] < cfg["baseline_min_median"]:
        return False
    return bool((v.get("x_median") or 0) >= cfg["outlier_x_median"]
                or (v.get("per_sub") or 0) >= cfg["outlier_per_sub"])


def outliers(uploads: list[dict], subs: int | None, now: dt.datetime, cfg: dict) -> list[dict]:
    """The fresh long uploads (at most fresh_days old) with their measures."""
    return [r for r in measure(uploads, subs, now, cfg) if r["age_days"] <= cfg["fresh_days"]]


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


# ---------- statistics (tested) ----------
def binom_sf(k: int, n: int, p: float) -> float:
    """P(X >= k) for X ~ Binomial(n, p)."""
    if k <= 0:
        return 1.0
    if k > n:
        return 0.0
    return min(1.0, sum(math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(k, n + 1)))


def poisson_binomial_sf(ps: list[float], k: int) -> float:
    """P(at least k successes) when trial i succeeds with probability ps[i] (exact, by dynamic programming)."""
    if k <= 0:
        return 1.0
    if k > len(ps):
        return 0.0
    dist = [1.0]
    for p in ps:
        nxt = [0.0] * (len(dist) + 1)
        for j, q in enumerate(dist):
            nxt[j] += q * (1 - p)
            nxt[j + 1] += q * p
        dist = nxt
    return min(1.0, max(0.0, sum(dist[k:])))


def bh(pvals: list[float | None]) -> list[float | None]:
    """Benjamini-Hochberg q values (same order as the input; None stays None)."""
    idx = sorted((i for i, p in enumerate(pvals) if p is not None), key=lambda i: pvals[i])
    m = len(idx)
    q: list[float | None] = [None] * len(pvals)
    running = 1.0
    for rank in range(m, 0, -1):
        i = idx[rank - 1]
        running = min(running, pvals[i] * m / rank)
        q[i] = round(min(1.0, running), 6)
    return q


# ---------- formats: labels, hit rates, evidence (tested) ----------
def load_labels(path: str | Path) -> dict[str, dict]:
    """Labels from JSON (a list or {id: format}) or JSON lines: {"id", "format" ("none" = no format), "flags"?,
    "mechanic"?, "interest_topic"?, "traffic_type"?}."""
    text = Path(path).read_text(encoding="utf-8")
    try:
        data = json.loads(text)
        rows = data if isinstance(data, list) else [{"id": k, "format": v} if not isinstance(v, dict) else
                                                    dict(v, id=k) for k, v in data.items()]
    except ValueError:
        rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    return {str(r["id"]): r for r in rows if isinstance(r, dict) and r.get("id")}


def row_flags(r: dict) -> list[str]:
    flags = [f for f in (r.get("flags") or []) if f in FLAGS]
    flags += [f for f in FLAGS if r.get(f"flag_{f}")]
    return sorted(set(flags))


def label_rows(rows: list[dict], labels: dict[str, dict] | None = None,
               patterns: dict[str, str] | None = None) -> list[dict]:
    """Give every row a format: the labels file first, then the row's own `format`, then the first title pattern
    that matches ("none" when no pattern matches). Rows that stay without any label are left out of the tests."""
    rxs = [(fid, re.compile(p, re.I)) for fid, p in (patterns or {}).items()]
    out = []
    for r in rows:
        r = dict(r)
        lab = (labels or {}).get(str(r.get("id")))
        if lab:
            r["format"] = lab.get("format")
            for k in ("mechanic", "interest_topic", "traffic_type"):
                if lab.get(k):
                    r[k] = lab[k]
            r["flags"] = sorted(set(row_flags(r)) | set(row_flags(lab)))
        elif not r.get("format") and rxs:
            r["format"] = next((fid for fid, rx in rxs if rx.search(r.get("title") or "")), "none")
        if r.get("format") in ("", None):
            r["format"] = None
        r["flags"] = row_flags(r)
        out.append(r)
    return out


def measure_rows(rows: list[dict], now: dt.datetime, cfg: dict) -> list[dict]:
    """Measure raw upload rows (collect output) channel by channel."""
    by: dict[str, list[dict]] = {}
    for r in rows:
        by.setdefault(str(r.get("channel_id") or r.get("channel") or "?"), []).append(r)
    out = []
    for _, ups in sorted(by.items()):
        subs = next((u.get("subs") for u in ups if u.get("subs")), None)
        out += measure(ups, subs, now, cfg)
    return out


def is_hit(r: dict, cfg: dict) -> bool:
    return bool((r.get("x_median") or 0) >= cfg["outlier_x_median"] and (r.get("views") or 0) >= views_floor(r, cfg))


def usable(rows: list[dict], cfg: dict) -> list[dict]:
    """Rows the tests count: final x median, a baseline of at least baseline_min_median, a label, no flag."""
    return [r for r in rows if r.get("final") and r.get("x_median") is not None and r.get("format")
            and (r.get("basis_median") or 0) >= cfg["baseline_min_median"] and not r.get("flags")]


def channel_rates(rows: list[dict], cfg: dict, exclude: str | None = None) -> tuple[dict[str, float], float]:
    """Each channel's normal hit rate (its videos outside the format `exclude`), shrunk toward the pooled rate."""
    per: dict[str, list[int]] = {}
    for r in rows:
        if exclude is not None and r["format"] == exclude:
            continue
        c = per.setdefault(r["channel_id"], [0, 0])
        c[0] += is_hit(r, cfg)
        c[1] += 1
    hits, n = sum(c[0] for c in per.values()), sum(c[1] for c in per.values())
    pooled = hits / n if n else 0.0
    return {ch: (h + BASE_PRIOR * pooled) / (k + BASE_PRIOR) for ch, (h, k) in per.items()}, pooled


def _stats(fr: list[dict], rates: dict[str, float], pooled: float, cfg: dict) -> dict:
    chans: dict[str, list[dict]] = {}
    for r in fr:
        chans.setdefault(r["channel_id"], []).append(r)
    hits_by = {c: sum(is_hit(r, cfg) for r in rs) for c, rs in chans.items()}
    hits = sum(hits_by.values())
    ps = [rates.get(r["channel_id"], pooled) for r in fr]
    wins = sum(1 for rs in chans.values() if median([r["x_median"] for r in rs]) > 1.0)
    lo, hi = cfg["small_channel_subs"]
    small_hits = sum(1 for r in fr if is_hit(r, cfg) and r.get("subs") and lo <= r["subs"] <= hi)
    top = max(chans, key=lambda c: (hits_by[c], len(chans[c]), c)) if chans else None
    p_hits = poisson_binomial_sf(ps, hits) if fr else None
    p_low = 1 - poisson_binomial_sf(ps, hits + 1) if fr else None   # P(at most `hits`)
    edge = None if not fr else "above" if p_hits < 0.05 else "below" if p_low < 0.05 else "no difference"
    return {"n": len(fr), "channels": len(chans), "hits": hits, "hit_rate": round(hits / len(fr), 3) if fr else None,
            "edge": edge,
            "expected_hits": round(sum(ps), 2), "base_rate": round(sum(ps) / len(ps), 3) if ps else None,
            "p_hits": round(p_hits, 6) if fr else None,
            "channel_wins": wins, "p_channel": round(binom_sf(wins, len(chans), 0.5), 6) if chans else None,
            "lift": round(median([r["x_median"] for r in fr]), 2) if fr else None,
            "share_small": round(small_hits / hits, 2) if hits else None,
            "hit_channels": sum(1 for h in hits_by.values() if h), "top_channel": top,
            "top_hits": hits_by.get(top, 0) if top else 0}


def evidence_level(s: dict, q_hits: float | None = None, q_channel: float | None = None,
                   without_top: str | None = None) -> str:
    """strong / medium / hint / one-channel / none (method section 3, our rule).

    q values come from Benjamini-Hochberg over all tested formats; without them (the recount without the top
    channel) the p values stand in. without_top: the level of the same format without its strongest channel.
    hint: hits on at least 2 channels, and either too few videos for the tests or an edge (p under 0.05) that misses
    the bar for medium. A format with enough videos and no edge is none.
    """
    def num(x):
        return 1.0 if x is None else x
    ph = num(s["p_hits"])
    qh = ph if q_hits is None else q_hits
    qc = num(s["p_channel"]) if q_channel is None else q_channel
    rank = LEVELS.index
    if s["hits"] >= 2 and s["top_hits"] > s["hits"] / 2:
        return "one-channel"
    medium = (s["n"] >= 8 and s["channels"] >= 3 and ph < 0.05
              and s["channel_wins"] >= 2 / 3 * s["channels"] and (s["lift"] or 0) >= 1.2)
    strong = (s["n"] >= 20 and s["channels"] >= 4 and qh < 0.05 and qc < 0.10 and (s["lift"] or 0) >= 1.5)
    testable = s["n"] >= 8 and s["channels"] >= 3
    hint = s["hit_channels"] >= 2 and (not testable or ph < 0.05)
    level = "strong" if strong else "medium" if medium else "hint" if hint else "none"
    if without_top is not None:
        if level in ("strong", "medium") and rank(without_top) < rank("hint"):
            return "one-channel"
        if level == "strong" and rank(without_top) < rank("medium"):
            level = "medium"
    return level


def series(fr: list[dict]) -> dict:
    """Repeatability: channels with at least 3 episodes of the format; repeatable when episodes 3 and later still
    have a median x of at least 1.2 (the first episode is usually the best)."""
    chans: dict[str, list[dict]] = {}
    for r in fr:
        chans.setdefault(r["channel_id"], []).append(r)
    rows = []
    for c, rs in chans.items():
        if len(rs) < 3:
            continue
        rs = sorted(rs, key=lambda r: r.get("published") or "")
        later = median([r["x_median"] for r in rs[2:]])
        rows.append({"channel": rs[0].get("channel") or c, "n": len(rs), "later_median_x": round(later, 2),
                     "repeatable": later >= 1.2})
    rows.sort(key=lambda r: (-r["repeatable"], -r["later_median_x"]))
    return {"series": len(rows), "repeatable": sum(r["repeatable"] for r in rows), "best": rows[:3]}


def decay(fr: list[dict], now: dt.datetime, cfg: dict) -> dict:
    """Supply and median x in the last two full windows of decay_window_days (videos must be mature)."""
    w = dt.timedelta(days=cfg["decay_window_days"])
    end = now - dt.timedelta(days=cfg["mature_days"])
    wins = []
    for k in (1, 0):
        a, b = end - (k + 1) * w, end - k * w
        xs = [r["x_median"] for r in fr if (t := parse_time(r.get("published"))) and a <= t < b]
        wins.append({"from": a.date().isoformat(), "to": b.date().isoformat(), "supply": len(xs),
                     "median_x": round(median(xs), 2) if xs else None})
    prev, last = wins
    closing = bool(prev["supply"] and prev["median_x"] and last["median_x"] is not None
                   and last["supply"] >= 1.5 * prev["supply"] and last["median_x"] <= 0.7 * prev["median_x"])
    return {"windows": wins, "closing": closing}


def format_table(rows: list[dict], now: dt.datetime, cfg: dict) -> dict:
    """Measured and labelled rows to one line per format with its tests and evidence level."""
    pool = usable(rows, cfg)
    fids = sorted({r["format"] for r in pool if r["format"] != "none"})
    out = []
    for fid in fids:
        rates, pooled = channel_rates(pool, cfg, exclude=fid)
        fr = [r for r in pool if r["format"] == fid]
        s = _stats(fr, rates, pooled, cfg)
        rest = [r for r in fr if r["channel_id"] != s["top_channel"]]
        s["without_top"] = _stats(rest, rates, pooled, cfg)
        s["without_top"]["level"] = evidence_level(s["without_top"])
        out.append(dict(format=fid, **s, series=series(fr), decay=decay(fr, now, cfg),
                        top_channel_name=next((r.get("channel") for r in fr if r["channel_id"] == s["top_channel"]),
                                              None)))
    for key, qkey in (("p_hits", "q_hits"), ("p_channel", "q_channel")):
        for f, q in zip(out, bh([f[key] for f in out]), strict=True):
            f[qkey] = q
    for f in out:
        f["level"] = evidence_level(f, f["q_hits"], f["q_channel"], f["without_top"]["level"])
        f["grade_max"] = max_grade(f["level"])
    out.sort(key=lambda f: (-LEVELS.index(f["level"]), f["p_hits"] if f["p_hits"] is not None else 1, f["format"]))
    labelled = [r for r in rows if r.get("final") and r.get("x_median") is not None]
    return {"date": now.date().isoformat(), "videos": len(rows), "tested": len(pool),
            "unlabelled": sum(1 for r in labelled if not r.get("format")),
            "flagged": sum(1 for r in labelled if r.get("flags")),
            "young": sum(1 for r in rows if not r.get("final")), "channels": len({r["channel_id"] for r in pool}),
            "pooled_hit_rate": round(channel_rates(pool, cfg)[1], 3) if pool else None,
            "coview_mixed": sum(1 for r in pool if r.get("coview_mixed")), "formats": out}


def max_grade(level: str | None) -> int:
    """Grades 4 and 5 need evidence level strong or medium."""
    return 5 if level in ("strong", "medium") else 3


def card_sample(rows: list[dict], cfg: dict, fid: str | None = None, seed: int = 1) -> list[dict]:
    """Videos for the full format card: every hit, and as many non-hits from the same channels (random, seeded)."""
    pool = [r for r in usable(rows, cfg) if fid is None or r["format"] == fid]
    hits = [r for r in pool if is_hit(r, cfg)]
    chans = {r["channel_id"] for r in hits}
    rest = [r for r in pool if not is_hit(r, cfg) and r["channel_id"] in chans]
    rnd = random.Random(seed)
    sample = rnd.sample(rest, min(len(hits), len(rest)))
    out = []
    for r in hits + sample:
        out.append({"id": r["id"], "url": f"https://www.youtube.com/watch?v={r['id']}", "title": r.get("title"),
                    "channel": r.get("channel"), "format": r["format"], "x_median": r["x_median"],
                    "hit": is_hit(r, cfg), "thumbnail_url": r.get("thumbnail_url")
                    or f"https://i.ytimg.com/vi/{r['id']}/hqdefault.jpg",
                    "material": {"title": True, "thumbnail": True, "transcript": None, "frames": None},
                    "card": dict.fromkeys(CARD_FIELDS)})
    return out


# ---------- the market (tested) ----------
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


def gap(home_videos: list[dict], thin_views: int, market_median: float | None = None, x_market: float = 2.0) -> dict:
    """The user's market: empty (no video on the format), thin, taken.

    Thin: the best video stays at most thin_views, and (when the median of the largest channel on the topic in the
    user's language is known) under x_market times that median.
    """
    if not home_videos:
        return {"gap": "empty", "best": None, "market_median": market_median}
    best = max(home_videos, key=lambda v: v.get("views") or 0)
    views = best.get("views") or 0
    thin = views <= thin_views and (market_median is None or views < x_market * market_median)
    return {"gap": "thin" if thin else "taken", "best": brief(best), "market_median": market_median,
            "relative": market_median is not None}


def split_home(found: list[dict], home_lang: str, top: int = 20) -> tuple[list[dict], list[dict]]:
    """The user's search results: videos in the user's language, and imports (every other language among the top
    results: dubbed, translated title or the original)."""
    home, imports = [], []
    for v in found:
        lang = lang_of(v) or guess_lang(v.get("title")) or ""
        (home if lang.startswith(home_lang.lower()) else imports).append(v)
    return home, imports[:top]


def hints(sat: dict, g: dict | None, imports: list[dict], cfg: dict | None = None) -> list[str]:
    cfg = cfg or DEFAULTS
    out = []
    best = (sat.get("best") or {}).get("views") or 0
    if copies_weak(sat):
        out.append("Way 1: the typical copy is weak; the best version of this format can still win.")
    if g and g["gap"] in ("empty", "thin") and best >= 100000:
        out.append("Way 2: a proven format with no strong version in the user's market.")
    if sat.get("verdict") == "closed":
        out.append("Closed in the source market: only with a test subject that belongs to the user's market.")
    if imports:
        big = max(v.get("views") or 0 for v in imports)
        out.append(f"{len(imports)} video(s) in another language rank in the user's search (dubbed, translated or "
                   f"original); the largest has {big} views."
                   + (" One grade off unless the test subject is local." if big > cfg["imports_penalty_views"] else ""))
    if g and g.get("gap") == "thin" and not g.get("relative"):
        out.append("Thin by the fixed limit only: the largest channel on the topic in the user's language is unknown.")
    return out


def copies_weak(sat: dict) -> bool:
    best = (sat.get("best") or {}).get("views") or 0
    return bool(sat.get("copies_median") and best and sat["copies_median"] < 0.05 * best)


def proof_strength(x: float | None, cfg: dict) -> str:
    if x is not None and x >= cfg["strong_x_median"]:
        return "strong"
    return "medium" if x is not None and x >= cfg["outlier_x_median"] else "weak"


def grade(sat: dict, g: dict | None, proof_x: float | None, level: str | None, imports_max: int, cfg: dict,
          local: bool = False) -> dict:
    """The grade from the measured values (method section 6). Barrier and a series that tires stay judgement."""
    p = proof_strength(proof_x, cfg)
    why = [f"proof {p} ({proof_x}x median)" if proof_x is not None else "no measured proof"]
    if g is not None:
        gp = g["gap"]
        table = {"empty": {"strong": 5, "medium": 4, "weak": 2}, "thin": {"strong": 4, "medium": 3, "weak": 2},
                 "taken": {"strong": 2, "medium": 2, "weak": 1}}
        value = table[gp][p]
        why.append(f"gap {gp}")
    else:
        v = sat.get("verdict")
        if v in ("closed", "no proof"):
            value = 1
        elif v == "closing":
            value = 3 if copies_weak(sat) else 2
        elif v == "open":
            value = 5 if p == "strong" and copies_weak(sat) else {"strong": 4, "medium": 3, "weak": 2}[p]
        else:
            value = {"strong": 4, "medium": 3, "weak": 2}[p]
        why.append(f"source market {v}")
    cap = max_grade(level)
    if value > cap:
        why.append(f"at most {cap}: evidence {level or 'not tested'} (4 and 5 need strong or medium)")
    value = min(value, cap)
    if imports_max > cfg["imports_penalty_views"] and not local:
        value = max(1, value - 1)
        why.append(f"one off: an import with {imports_max} views ranks in the user's search")
    return {"grade": value, "grade_max": cap, "evidence": level or "not tested", "why": why}


# ---------- the audience score (tested) ----------
def _rx(words) -> re.Pattern | None:
    words = [w for w in (words or []) if isinstance(w, str) and w.strip()]
    if not words:
        return None
    try:
        return re.compile(r"\b(?:" + "|".join(words) + r")\b", re.I)
    except re.error as e:
        raise SourceError(f"channel.json idea.audience: a word list has a bad pattern ({e})") from None


def audience_score(text: str, cfg: dict) -> dict | None:
    """Would the broad audience of the niche click this and get something out of it? 0 to 5, a word estimate.

    channel.json idea.audience: {"groups": {name: [words]}, "core": [...], "open": [...], "zero": [...],
    "narrow": [...], "insider": [...]}. Words are regular expressions matched as whole words. A match in "zero"
    (for example a company or B2B framing on a channel for individuals) scores 0. None when no audience is set.
    """
    a = cfg.get("audience")
    if not isinstance(a, dict) or not a.get("groups"):
        return None
    t = " ".join(str(text or "").split())
    m = (_rx(a.get("zero")) or re.compile(r"(?!x)x")).search(t)
    if m:
        return {"score": 0, "group": "zero", "why": f"framing that scores 0 ({m.group(0)!r})"}
    groups = {g: len({x.group(0).lower() for x in rx.finditer(t)}) for g, w in a["groups"].items()
              if (rx := _rx(w)) is not None}
    found = [g for g, n in sorted(groups.items(), key=lambda kv: -kv[1]) if n]
    open_ = _rx(a.get("open"))
    is_open = bool(open_ and open_.search(t))
    core = _rx(a.get("core"))
    score = 1 + (1 if core and core.search(t) else 0) + (2 if found else 0) + (1 if len(found) >= 2 or is_open else 0)
    why = ["/".join(found) or "no group"]
    narrow = _rx(a.get("narrow"))
    if narrow and (n := narrow.search(t)):
        score -= 2
        why.append(f"narrow topic ({n.group(0)!r})")
    insider = _rx(a.get("insider"))
    if insider and (n := insider.search(t)) and not is_open:
        score -= 1
        why.append(f"insider words ({n.group(0)!r})")
    return {"score": max(1, min(5, score)), "group": found[0] if found else None, "why": "; ".join(why)}


# ---------- data sources ----------
class YouTubeAPI:
    """YouTube Data API v3, read only, with an API key or the channel's own login. Stops at max_units."""
    BASE = "https://www.googleapis.com/youtube/v3/"
    COST = {"search": 100}

    def __init__(self, key: str | None = None, creds=None, max_units: int = 3000):
        self._key = key
        self._creds = creds
        self.units = 0
        self.max_units = max_units
        self.name = "api" if key else "oauth"

    def _headers(self) -> dict:
        h = {"User-Agent": "crewcut-idea"}
        if self._creds is not None:
            if not self._creds.valid:
                from google.auth.transport.requests import Request
                self._creds.refresh(Request())
            h["Authorization"] = "Bearer " + self._creds.token
        return h

    def _get(self, endpoint: str, **params) -> dict:
        cost = self.COST.get(endpoint, 1)
        if self.units + cost > self.max_units:
            raise SourceError(f"unit limit reached ({self.units} of --max-units {self.max_units}); the result so far "
                              "is incomplete")
        params = {k: v for k, v in params.items() if v not in (None, "")}
        if self._key:
            params["key"] = self._key
        url = self.BASE + endpoint + "?" + urllib.parse.urlencode(params)
        self.units += cost
        req = urllib.request.Request(url, headers=self._headers())
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
        return {"id": it["id"], "title": it["snippet"].get("title"), "handle": it["snippet"].get("customUrl"),
                "subs": None if st.get("hiddenSubscriberCount") else int(st.get("subscriberCount", 0) or 0),
                "country": it["snippet"].get("country"), "lang": it["snippet"].get("defaultLanguage"),
                "uploads": it.get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads")}

    def uploads(self, ch: dict, n: int = 50, since: dt.datetime | None = None) -> list[dict]:
        """The newest n uploads; with since, stop earlier once the uploads reach back to that date."""
        ids, token = [], None
        while ch.get("uploads") and len(ids) < n:
            d = self._get("playlistItems", part="contentDetails", playlistId=ch["uploads"],
                          maxResults=min(50, n - len(ids)), pageToken=token)
            items = d.get("items", [])
            ids += [x["contentDetails"]["videoId"] for x in items]
            token = d.get("nextPageToken")
            oldest = parse_time((items[-1].get("contentDetails") or {}).get("videoPublishedAt")) if items else None
            if not token or (since is not None and oldest is not None and oldest < since):
                break
        vids = self.videos(ids)
        vids.sort(key=lambda v: v.get("published") or "", reverse=True)
        return vids

    def videos(self, ids: list[str]) -> list[dict]:
        out = []
        for i in range(0, len(ids), 50):
            d = self._get("videos", part="snippet,statistics,contentDetails,liveStreamingDetails",
                          id=",".join(ids[i:i + 50]))
            for it in d.get("items", []):
                sn, st = it.get("snippet", {}), it.get("statistics", {})
                out.append({"id": it["id"], "title": sn.get("title"), "channel": sn.get("channelTitle"),
                            "channel_id": sn.get("channelId"), "published": sn.get("publishedAt"),
                            "views": int(st["viewCount"]) if "viewCount" in st else None,
                            "likes": int(st["likeCount"]) if "likeCount" in st else None,
                            "comments": int(st["commentCount"]) if "commentCount" in st else None,
                            "duration_s": parse_duration(it.get("contentDetails", {}).get("duration")),
                            "live": bool(it.get("liveStreamingDetails")),
                            "thumbnail_url": ((sn.get("thumbnails") or {}).get("high") or {}).get("url"),
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


def ytdlp_search_url(q: str, order: str, after: dt.datetime | None, now: dt.datetime) -> str:
    """The public search page with YouTube's own filters: upload date (this month or year) and the sort."""
    days = (now - after).days if after else None
    if order == "date":
        sp = "CAISAggE" if days is not None and days <= 31 else "CAI%3D"
    else:
        sp = "EgIIBA%3D%3D" if days is not None and days <= 31 else "EgIIBQ%3D%3D" if days is not None else ""
    return "https://www.youtube.com/results?" + urllib.parse.urlencode({"search_query": q}) + (f"&sp={sp}" if sp else "")


class YtDlp:
    """Opt-in source through yt-dlp (public pages, no key, no units). Flat lists carry no exact dates, so only up to
    `exact` candidates per call get their date from the video page."""

    def __init__(self, exact: int = 6, allowed: bool = False):
        if not allowed and os.environ.get("CREWCUT_IDEA_YTDLP") != "1":
            raise SourceError("yt-dlp is off. The user switches it on with CREWCUT_IDEA_YTDLP=1 or channel.json "
                              "idea.search_source \"ytdlp\".")
        if not shutil.which("yt-dlp"):
            raise SourceError("yt-dlp is not installed.")
        self.units = 0
        self.exact = exact
        self.name = "ytdlp"

    def _run(self, *args, timeout=180) -> dict:
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

    def uploads(self, ch: dict, n: int = 50, since=None) -> list[dict]:
        vids = getattr(self, "_cache", [])[:n]
        return self._dates(vids)

    def _dates(self, vids: list[dict]) -> list[dict]:
        for v in sorted([v for v in vids if not v.get("published")], key=lambda v: -(v.get("views") or 0))[:self.exact]:
            p = subprocess.run(["yt-dlp", "-J", "--skip-download", "--", v["id"]],
                               capture_output=True, text=True, timeout=120)
            if p.returncode == 0:
                d = json.loads(p.stdout)
                if d.get("timestamp"):
                    v["published"] = dt.datetime.fromtimestamp(d["timestamp"], dt.UTC).isoformat()
                v["lang"] = v.get("lang") or d.get("language")
        return vids

    def flat_search(self, q: str, *, order: str = "relevance", after=None, n: int = 50) -> list[dict]:
        url = ytdlp_search_url(q, order, after, dt.datetime.now(dt.UTC))
        d = self._run("--playlist-end", str(n), url)
        return [self._video(e) for e in d.get("entries", []) if e.get("id")]

    def search(self, q: str, *, order: str = "relevance", after=None, lang=None, region=None, n: int = 50):
        return self._dates(self.flat_search(q, order=order, after=after, n=n))

    def subscribers(self, channel_ids):
        return {}


class Hybrid:
    """Searches through yt-dlp (no units), every other read through the API (1 unit per 50 videos)."""

    def __init__(self, api: YouTubeAPI, ytdlp: YtDlp):
        self.api, self.ytdlp = api, ytdlp
        self.name = f"{api.name}+ytdlp search"

    @property
    def units(self) -> int:
        return self.api.units

    def __getattr__(self, name):
        return getattr(self.api, name)

    def search(self, q: str, *, order: str = "relevance", after=None, lang=None, region=None, n: int = 50):
        flat = self.ytdlp.flat_search(q, order=order, after=after, n=n)
        full = {v["id"]: v for v in self.api.videos([v["id"] for v in flat])}
        out = [full.get(v["id"], v) for v in flat]
        return [v for v in out if after is None or (parse_time(v.get("published")) or after) >= after]


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


def _oauth():
    """The channel's own YouTube login (crewcut youtube auth), or None."""
    try:
        _crewcut()
        from crewcut.youtube import auth
        if not auth.connected():
            return None
        return auth.credentials()
    except Exception:  # noqa: BLE001 - no login, no libraries: not this source
        return None


def make_source(name: str, cfg: dict | None = None, max_units: int = 3000):
    cfg = cfg or DEFAULTS
    if name == "ytdlp":
        return YtDlp(allowed=ytdlp_allowed(cfg))
    key = os.environ.get("YOUTUBE_API_KEY")
    if name == "api" or (name == "auto" and key):
        if not key:
            raise MissingKey("YOUTUBE_API_KEY is not set. The user creates a free key in the Google Cloud console "
                             "(YouTube Data API v3) and puts it in .env.")
        src = YouTubeAPI(key=key, max_units=max_units)
    else:
        creds = _oauth()
        if creds is None:
            raise MissingKey("No YouTube access: set YOUTUBE_API_KEY (a free key from the Google Cloud console, "
                             "YouTube Data API v3) or connect the channel (`crewcut youtube connect`).")
        src = YouTubeAPI(creds=creds, max_units=max_units)
    if ytdlp_allowed(cfg) and shutil.which("yt-dlp"):
        return Hybrid(src, YtDlp(allowed=True))
    return src


# ---------- commands ----------
def cmd_channel(a, cfg, src, now) -> dict:
    ch = src.channel(a.ref)
    ups = src.uploads(ch, a.count)
    med = channel_median(ups, cfg["long_min_seconds"])
    longs = [v for v in ups if is_long(v, cfg["long_min_seconds"])]
    rows = measure(ups, ch.get("subs"), now, cfg)
    return {"channel": ch, "median_long_views": med, "uploads_read": len(ups),
            "recent": [brief(v) for v in longs[:a.recent]],
            "top": [brief(v) for v in sorted(longs, key=lambda v: -(v.get("views") or 0))[:a.top]],
            "outliers": [r for r in rows if r["age_days"] <= cfg["fresh_days"] and (r["outlier"] or r["early_signal"])],
            "coview_note": coview_note(rows)}


def coview_note(rows: list[dict]) -> str | None:
    if any(r.get("coview_mixed") for r in rows):
        return ("Since November 2026 YouTube counts co-views (several people at one TV) into public views; "
                "comparisons across that change are uncertain.")
    return None


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
            rows.append(dict(o, channel=ch.get("title"), subs=ch.get("subs"), audience=audience_score(o.get("title"),
                                                                                                    cfg)))
    found = sorted([r for r in rows if r["outlier"]], key=lambda r: -(r.get("x_median") or 0))
    small = []
    for q in a.search:
        vids = src.search(q, order="relevance", after=now - dt.timedelta(days=cfg["fresh_days"] * 2), n=50)
        vids = [v for v in vids if is_long(v, cfg["long_min_seconds"]) and v.get("views")]
        subs = src.subscribers([v["channel_id"] for v in vids])
        for v in vids:
            s = subs.get(v["channel_id"])
            if breakthrough(v["views"], s, cfg):
                small.append(dict(brief(v), subs=s, per_sub=round(v["views"] / s, 2), query=q,
                                  audience=audience_score(v.get("title"), cfg)))
    small.sort(key=lambda v: -v["per_sub"])
    return {"channels": len(refs), "fresh_videos": len(rows), "outliers": found, "breakthroughs": small,
            "errors": errors, "no_channels": not refs, "coview_note": coview_note(rows)}


def read_channels_file(path: str) -> list[dict]:
    """A channel list: JSON (list of objects or strings) or CSV with channel_id or handle, and optionally market,
    language, niche (German column names markt, sprache, nische work too)."""
    p = Path(path)
    if p.suffix.lower() == ".json":
        data = json.loads(p.read_text(encoding="utf-8"))
        rows = [r if isinstance(r, dict) else {"ref": r} for r in data]
    else:
        with p.open(encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
    out = []
    for r in rows:
        ref = r.get("ref") or r.get("channel_id") or r.get("handle") or r.get("url")
        if ref:
            out.append({"ref": str(ref).strip(), "market": r.get("market") or r.get("markt"),
                        "language": r.get("language") or r.get("sprache"), "niche": r.get("niche") or r.get("nische")})
    return out


def cmd_collect(a, cfg, src, now) -> dict:
    """Every long upload of the last collect_months (and the baseline months before) per channel, flops too."""
    chans = [{"ref": c} for c in a.channel] + (read_channels_file(a.channels_file) if a.channels_file else [])
    months = a.months or cfg["collect_months"]
    since = now - dt.timedelta(days=round(30.44 * (months + cfg["baseline_months"])))
    keep_from = now - dt.timedelta(days=round(30.44 * months))
    rows, errors = [], []
    for c in chans:
        try:
            ch = src.channel(c["ref"])
            ups = src.uploads(ch, 600, since=since)
        except SourceError as e:
            errors.append(f"{c['ref']}: {e}")
            if "unit limit" in str(e):
                break
            continue
        for v in ups:
            if not is_long(v, cfg["long_min_seconds"]) or v.get("live"):
                continue
            rows.append(dict(v, channel=v.get("channel") or ch.get("title"), channel_id=ch["id"],
                             handle=ch.get("handle"), subs=ch.get("subs"), market=c.get("market"),
                             niche=c.get("niche"), lang=v.get("lang") or c.get("language"),
                             in_window=(parse_time(v.get("published")) or now) >= keep_from,
                             fetched_at=now.isoformat()))
    out = Path(a.file_out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    return {"channels": len(chans), "videos": len(rows), "file": str(out), "errors": errors}


def read_rows(path: str) -> list[dict]:
    text = Path(path).read_text(encoding="utf-8")
    if text.lstrip().startswith("["):
        return json.loads(text)
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def cmd_formats(a, cfg, now) -> dict:
    raw = read_rows(a.videos)
    if a.now:
        now = parse_time(a.now)
    elif any(r.get("fetched_at") for r in raw):
        now = max(parse_time(r["fetched_at"]) for r in raw if r.get("fetched_at"))
    patterns = dict(p.split("=", 1) for p in a.pattern)
    patterns = {**library_patterns(), **patterns} if a.library_patterns else patterns
    labels = load_labels(a.labels) if a.labels else None
    rows = label_rows(measure_rows(raw, now, cfg), labels, patterns)
    if a.months:
        start = now - dt.timedelta(days=round(30.44 * a.months))
        rows = [r for r in rows if (parse_time(r.get("published")) or now) >= start]
    res = format_table(rows, now, cfg)
    res["coview_note"] = coview_note(rows)
    if a.todo:
        todo = [{"id": r["id"], "title": r.get("title"), "channel": r.get("channel"),
                 "thumbnail_url": r.get("thumbnail_url") or f"https://i.ytimg.com/vi/{r['id']}/hqdefault.jpg",
                 "format": None} for r in rows if r.get("final") and not r.get("format")]
        Path(a.todo).write_text("".join(json.dumps(t, ensure_ascii=False) + "\n" for t in todo), encoding="utf-8")
        res["todo"] = {"file": a.todo, "videos": len(todo)}
    if a.cards:
        cards = card_sample(rows, cfg, a.format, a.seed)
        if a.transcripts:
            for c in cards:
                c["material"]["transcript"] = fetch_transcript(c["id"], Path(a.cards).parent / "transcripts", cfg)
        Path(a.cards).write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in cards), encoding="utf-8")
        res["cards"] = {"file": a.cards, "videos": len(cards)}
    return res


def fetch_transcript(video_id: str, folder: Path, cfg: dict) -> str | None:
    """Automatic subtitles of one public video through yt-dlp (opt-in), as a text file. None when there are none."""
    if not ytdlp_allowed(cfg) or not shutil.which("yt-dlp"):
        return None
    folder.mkdir(parents=True, exist_ok=True)
    subprocess.run(["yt-dlp", "--skip-download", "--write-auto-subs", "--write-subs", "--sub-format", "vtt",
                    "--sleep-requests", "1", "-o", str(folder / "%(id)s"), "--", video_id],
                   capture_output=True, text=True, timeout=180)
    vtt = sorted(folder.glob(f"{video_id}*.vtt"))
    if not vtt:
        return None
    lines, last = [], None
    for line in vtt[0].read_text(encoding="utf-8", errors="replace").splitlines():
        line = re.sub(r"<[^>]+>", "", line).strip()
        if not line or "-->" in line or line.startswith(("WEBVTT", "Kind:", "Language:")) or line == last:
            continue
        lines.append(line)
        last = line
    out = folder / f"{video_id}.txt"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(out)


def library_patterns() -> dict[str, str]:
    """title_patterns of the show format library, joined per format."""
    try:
        _crewcut()
        from crewcut import showformats
        lib = showformats.load()
    except Exception:  # noqa: BLE001
        return {}
    return {fid: "|".join(f"(?:{p})" for p in f["title_patterns"]) for fid, f in lib.items() if f.get("title_patterns")}


def library_match(text: str, fid: str | None = None) -> dict | None:
    """The show format from the library: the one named, else the rule guess from the text."""
    try:
        _crewcut()
        from crewcut import showformats
        lib = showformats.load()
    except Exception:  # noqa: BLE001
        return None
    if fid:
        f = lib.get(fid)
        return {"format": fid, "name": f["name"], "length": f["length"], "reason": "named at the check"} if f else None
    g = showformats.suggest(text, lib=lib)
    if not g:
        return None
    return {"format": g["format"], "name": lib[g["format"]]["name"], "length": g["length"], "reason": g["reason"]}


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
            pub = parse_time(v.get("published")) or now
            ups = src.uploads(ch, 200, since=pub - dt.timedelta(days=round(30.44 * cfg["baseline_months"]))) if ch else []
            if not any(u.get("id") == v["id"] for u in ups):
                ups = ups + [v]
            mine = next((r for r in measure(ups, ch.get("subs") if ch else None, now, cfg) if r["id"] == v["id"]), {})
            x, how = mine.get("x_median"), "window"
            if x is None and ups:   # no window (too few dated uploads): the old median of the last 30, marked
                med = channel_median(ups, cfg["long_min_seconds"])
                x, how = (round(v["views"] / med, 2) if med else None), "last 30 uploads"
            row.update(subs=ch.get("subs") if ch else None, x_median=x, baseline=how, final=mine.get("final"),
                       tier=tier(x, cfg),
                       per_sub=round(v["views"] / ch["subs"], 2) if ch and ch.get("subs") else None)
        except SourceError as e:
            row["error"] = str(e)
        proof.append(row)
    proof_channels = {p.get("channel_id") for p in proof if (p.get("x_median") or 0) >= cfg["outlier_x_median"]}
    evidence = None
    if a.evidence and a.format:
        evidence = next((f for f in json.loads(Path(a.evidence).read_text(encoding="utf-8")).get("formats", [])
                         if f.get("format") == a.format), None)
    level = (evidence or {}).get("level") or ("hint" if len(proof_channels) >= 2 else "none")
    g, home, imports = None, [], []
    same_market = not hlang or hlang.split("-")[0] == mlang.split("-")[0]
    market_ch = None
    if not same_market:
        found: dict[str, dict] = {}
        for q in a.home_query or queries:
            for v in src.search(q, order="relevance", after=now - dt.timedelta(days=365), lang=hlang, region=hreg,
                                n=25):
                if (home_match(v.get("title")) or match(v.get("title"))) and is_long(v, cfg["long_min_seconds"]):
                    found.setdefault(v["id"], v)
        home, imports = split_home(list(found.values()), hlang)
        market_ch = home_market(a, src, home, cfg)
        g = gap(home, cfg["gap_thin_views"], (market_ch or {}).get("median"), cfg["gap_thin_x_market"])
    proof_x = max([p["x_median"] for p in proof if p.get("x_median") is not None] or [None], key=lambda x: x or 0)
    imports_max = max([v.get("views") or 0 for v in imports] or [0])
    text = " ".join([a.topic] + [p.get("title") or "" for p in proof[:3]])
    return {"topic": a.topic, "date": now.date().isoformat(), "rule": match.describe, "queries": queries,
            "market": {"language": mlang, "region": mreg, "matches": len(copies), "saturation": sat},
            "proof": proof, "evidence": {"level": level, "from": a.evidence if evidence else "proof videos",
                                         "format": a.format},
            "home": None if same_market else {"language": hlang, "region": hreg, "gap": g, "market_channel": market_ch,
                                              "videos": [brief(v) for v in sorted(home, key=lambda v: -(v.get("views") or 0))[:10]],
                                              "imports": [dict(brief(v), lang=v.get("lang")) for v in imports[:5]]},
            "grade": grade(sat, g, proof_x, level, imports_max, cfg, local=a.local),
            "audience": audience_score(text, cfg), "format": library_match(a.topic, a.format),
            "hints": hints(sat, g, imports, cfg)}


def home_market(a, src, home: list[dict], cfg: dict) -> dict | None:
    """The largest channel on the topic in the user's language and its median (the market size, method section 9)."""
    ref = a.market_channel
    if not ref and home:
        ids = [v["channel_id"] for v in home if v.get("channel_id")]
        subs = src.subscribers(ids) if ids else {}
        ref = max(ids, key=lambda c: subs.get(c) or 0) if ids and any(subs.values()) else None
    if not ref:
        return None
    try:
        ch = src.channel(ref)
        return {"channel": ch.get("title"), "subs": ch.get("subs"),
                "median": channel_median(src.uploads(ch, 30), cfg["long_min_seconds"])}
    except SourceError as e:
        return {"channel": ref, "error": str(e), "median": None}


def slug(text: str, n: int = 60) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    if len(s) > n:
        s = s[:n].rstrip("-") + "-" + hashlib.sha1(text.encode()).hexdigest()[:6]
    return s or hashlib.sha1(text.encode()).hexdigest()[:12]


def rank(checks: list[dict]) -> dict:
    """The ranked list from saved checks: grade first, then the audience score, then the proof."""
    ranked, left = [], []
    for c in checks:
        au = c.get("audience")
        row = {"topic": c.get("topic"), "grade": (c.get("grade") or {}).get("grade"),
               "grade_max": (c.get("grade") or {}).get("grade_max"), "evidence": (c.get("evidence") or {}).get("level"),
               "audience": au.get("score") if au else None, "audience_group": au.get("group") if au else None,
               "format": c.get("format"), "verdict": ((c.get("market") or {}).get("saturation") or {}).get("verdict"),
               "gap": (((c.get("home") or {}).get("gap")) or {}).get("gap"), "file": c.get("_file"),
               "proof": [p for p in c.get("proof") or [] if p.get("x_median")][:3],
               "send_by": ((c.get("market") or {}).get("saturation") or {}).get("send_by"),
               "first_age_days": ((c.get("market") or {}).get("saturation") or {}).get("first_age_days"),
               "why": (c.get("grade") or {}).get("why") or []}
        if au and au.get("score") == 0:
            row["left_out"] = f"audience 0: {au.get('why')}"
            left.append(row)
        else:
            ranked.append(row)
    ranked.sort(key=lambda r: (-(r["grade"] or 0), -(r["audience"] if r["audience"] is not None else 2.5),
                               -max([p["x_median"] for p in r["proof"]] or [0])))
    return {"ranked": ranked, "not_ranked": left}


def idea_card(r: dict, date: str) -> dict:
    """One idea card for inbox/ideas/ (crewcut/ideas.py) with the matching show format named."""
    fmt = r.get("format") or {}
    best = (r.get("proof") or [{}])[0]
    parts = [f"Grade {r['grade']} of 5 (at most {r['grade_max']}, evidence {r['evidence']})."]
    if r.get("verdict"):
        parts.append(f"Source market {r['verdict']}" + (f", gap {r['gap']}" if r.get("gap") else "") + ".")
    if best.get("x_median"):
        parts.append(f"Proof: {best['x_median']}x median on {best.get('channel') or '?'}.")
    if r.get("audience") is not None:
        parts.append(f"Audience {r['audience']} of 5 ({r.get('audience_group') or 'no group'}).")
    parts.append(f"Format: {fmt['name']} ({fmt['format']})." if fmt else
                 "No format in the library fits yet: a candidate for a new format.")
    signals = {k: v for k, v in {"grade": r["grade"], "grade_max": r["grade_max"], "evidence": r["evidence"],
                                 "audience": r.get("audience"), "audience_group": r.get("audience_group"),
                                 "saturation": r.get("verdict"), "gap": r.get("gap"), "send_by": r.get("send_by"),
                                 "youtube": [{k: p.get(k) for k in ("title", "channel", "views", "x_median")}
                                             for p in r.get("proof") or []] or None,
                                 "file": r.get("file")}.items() if v not in (None, [], "")}
    fresh = r.get("first_age_days") is not None and r["first_age_days"] <= 21
    return {"id": "idea-" + slug(r["topic"]), "source": "scout",
            "url": f"https://www.youtube.com/watch?v={best['id']}" if best.get("id") else None,
            "title": r["topic"], "summary": " ".join(parts), "signals": signals,
            "topic_type": "trending" if fresh else "manufactured",
            "suggested_format": fmt.get("format"), "reason": fmt.get("reason") if fmt else None,
            "length": fmt.get("length"), "created": date}


def write_cards(rows: list[dict], date: str) -> dict:
    _crewcut()
    from crewcut import paths
    folder = paths.studio_root() / "inbox" / "ideas"
    folder.mkdir(parents=True, exist_ok=True)
    counts = {"written": 0, "decided": 0}
    for r in rows:
        card = idea_card(r, date)
        p = folder / f"{card['id']}.json"
        if p.exists():
            try:
                old = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                old = {}
            if old.get("status") in ("started", "dismissed"):
                counts["decided"] += 1
                continue
            card["created"] = old.get("created") or date
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(card, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        tmp.replace(p)
        counts["written"] += 1
    return dict(counts, folder=str(folder))


def cmd_rank(a, now) -> dict:
    checks = []
    for pat in a.files:
        for f in sorted(glob.glob(pat)) or [pat]:
            try:
                d = json.loads(Path(f).read_text(encoding="utf-8"))
            except (OSError, ValueError) as e:
                raise SourceError(f"{f}: {e}") from None
            if isinstance(d, dict) and d.get("topic"):
                checks.append(dict(d, _file=f))
    res = rank(checks)
    if a.cards:
        res["cards"] = write_cards(res["ranked"][:a.top], now.date().isoformat())
    return res


# ---------- output ----------
def show(cmd: str, r: dict) -> None:
    def vid(v):
        return f"{v.get('views') or 0:>10,}  {(v.get('published') or '?')[:10]}  {(v.get('channel') or '')[:22]:22} " \
               f"{(v.get('title') or '')[:64]}  https://youtu.be/{v.get('id')}"

    def aud(v):
        a = v.get("audience")
        return f"  A{a['score']}" if a else ""
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
        for o in r["outliers"]:
            print(f"  {'EARLY' if o['early_signal'] else 'OUT':5} {o.get('x_median') or 0:>5}x median  "
                  f"{o.get('x_last5') or 0:>5}x last 5  " + vid(o))
    elif cmd == "scan":
        if r["no_channels"]:
            print("No channels. Add reference_channels to channel.json or pass --channel.")
        print(f"{r['channels']} channels, {r['fresh_videos']} fresh long uploads, {len(r['outliers'])} outliers")
        for o in r["outliers"][:40]:
            low = "" if o.get("final") else " (so far)"
            print(f"  {o.get('x_median') or 0:>5}x median{low}  {o.get('x_last5') or 0:>5}x last 5  "
                  f"{o.get('per_sub') or 0:>6}/sub{aud(o)}  " + vid(o))
        for b in r["breakthroughs"][:20]:
            print(f"  SMALL {b['per_sub']:>5}/sub  subs {b['subs']:>7}{aud(b)}  " + vid(b))
        for e in r["errors"]:
            print("  error: " + e)
    elif cmd == "collect":
        print(f"{r['videos']} long uploads from {r['channels']} channels written to {r['file']}")
        for e in r["errors"]:
            print("  error: " + e)
    elif cmd == "formats":
        print(f"{r['tested']} of {r['videos']} videos tested on {r['channels']} channels (pooled hit rate "
              f"{r['pooled_hit_rate']}); {r['unlabelled']} without a label, {r['flagged']} flagged, "
              f"{r['young']} younger than 28 days")
        for f in r["formats"]:
            wt = f["without_top"]
            print(f"  {f['level'].upper():11} {f['format']:<22} n {f['n']:>4}  channels {f['channels']:>3}  hits "
                  f"{f['hits']:>3} ({f['hit_rate']}) vs {f['base_rate']} normal  p {f['p_hits']:.4f} q {f['q_hits']:.4f}"
                  f"  channel wins {f['channel_wins']}/{f['channels']}  lift {f['lift']}x  without "
                  f"{(f['top_channel_name'] or '?')[:18]}: {wt['level']}")
        if r.get("coview_note"):
            print("Note: " + r["coview_note"])
        for k in ("todo", "cards"):
            if r.get(k):
                print(f"{k}: {r[k]['videos']} videos in {r[k]['file']}")
    elif cmd == "audience":
        print(json.dumps(r, ensure_ascii=False))
    elif cmd == "rank":
        for i, x in enumerate(r["ranked"], 1):
            fmt = (x.get("format") or {}).get("format") or "no library format"
            au = f", audience {x['audience']}" if x.get("audience") is not None else ""
            print(f"{i}. {x['topic']}: grade {x['grade']} (max {x['grade_max']}, evidence {x['evidence']}){au}, "
                  f"format {fmt}. {'; '.join(x['why'])}")
        for x in r["not_ranked"]:
            print(f"Not ranked: {x['topic']} ({x['left_out']})")
        if r.get("cards"):
            print(f"Idea cards: {r['cards']['written']} written, {r['cards']['decided']} decided already "
                  f"({r['cards']['folder']})")
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
            low = "" if p.get("final", True) else " so far"
            print(f"  {p.get('x_median') or '?':>5}x median{low}  {p.get('per_sub') or '?':>6}/sub  " + vid(p))
        if r["home"]:
            g = r["home"]["gap"]
            mc = r["home"].get("market_channel") or {}
            print(f"User's market {r['home']['language']}: gap {g['gap'].upper()}"
                  + (f", best {g['best']['views']}" if g.get("best") else "")
                  + (f"; largest channel on the topic {mc.get('channel')} median {mc.get('median')}" if mc else ""))
            for v in r["home"]["videos"][:6]:
                print("  " + vid(v))
        else:
            print("User's market is the source market: the saturation is the gap.")
        gr = r["grade"]
        print(f"Grade {gr['grade']} (at most {gr['grade_max']}, evidence {gr['evidence']}): {'; '.join(gr['why'])}")
        if r.get("audience"):
            print(f"Audience {r['audience']['score']} of 5: {r['audience']['why']}")
        print("Format: " + (f"{r['format']['name']} ({r['format']['format']}), {r['format']['reason']}"
                            if r.get("format") else "no format in the library fits"))
        for h in r["hints"]:
            print("Hint: " + h)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Find the next video idea in data: outliers, formats, saturation, gap.")
    ap.add_argument("--source", choices=("auto", "api", "oauth", "ytdlp"), default="auto",
                    help="auto: the API key, else the channel's login; ytdlp is opt-in")
    ap.add_argument("--max-units", type=int, default=3000, help="stop before this many API units (daily quota 10,000)")
    ap.add_argument("--pack", help="style pack folder (default: the active pack)")
    ap.add_argument("--json", action="store_true", help="print JSON")
    ap.add_argument("--out", help="also write the JSON result to this file")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("channel", help="channel size, median, recent and top videos, own outliers")
    c.add_argument("ref", help="@handle, channel id or channel URL")
    c.add_argument("--count", type=int, default=200, help="uploads to read (50 per unit)")
    c.add_argument("--recent", type=int, default=10)
    c.add_argument("--top", type=int, default=10)
    s = sub.add_parser("scan", help="fresh outliers on the reference channels")
    s.add_argument("--channel", action="append", default=[], help="@handle, id or URL (repeatable)")
    s.add_argument("--search", action="append", default=[], help="search for small channels that broke through "
                   "(100 units each, none through yt-dlp)")
    co = sub.add_parser("collect", help="every long upload per channel (flops too) for the format test")
    co.add_argument("--channel", action="append", default=[], help="@handle, id or URL (repeatable)")
    co.add_argument("--channels-file", help="CSV or JSON channel list (channel_id or handle, market, language, niche)")
    co.add_argument("--months", type=int, help="months to collect (default collect_months)")
    co.add_argument("--file", dest="file_out", default="review/market-videos.jsonl", help="JSON lines to write")
    f = sub.add_parser("formats", help="hit rate per format against each channel's normal rate (no network)")
    f.add_argument("videos", help="JSON lines from collect (or any rows with id, channel_id, published, views)")
    f.add_argument("--labels", help="labels: JSON lines {id, format ('none' = no format), flags?}")
    f.add_argument("--pattern", action="append", default=[], help="FORMAT=REGEX title rule (repeatable)")
    f.add_argument("--library-patterns", action="store_true", help="also the title_patterns of the format library")
    f.add_argument("--months", type=int, help="only videos of the last N months (the baseline still uses older ones)")
    f.add_argument("--now", help="measure as of this date (default: the newest fetched_at)")
    f.add_argument("--todo", help="write the videos without a label here (title and thumbnail, for labelling)")
    f.add_argument("--cards", help="write the sample for full format cards here (hits and as many others)")
    f.add_argument("--format", help="only this format's sample for --cards")
    f.add_argument("--seed", type=int, default=1)
    f.add_argument("--transcripts", action="store_true", help="fetch automatic subtitles for the cards (yt-dlp)")
    k = sub.add_parser("check", help="saturation in the source market and the gap in the user's market")
    k.add_argument("topic", help="the format or topic in a few words")
    k.add_argument("--query", action="append", default=[], help="search in the source market (2 searches each)")
    k.add_argument("--home-query", action="append", default=[], help="search in the user's language")
    k.add_argument("--pattern", help="regex that a title must match to count as a copy")
    k.add_argument("--home-pattern", help="regex for titles in the user's language")
    k.add_argument("--proof", type=int, default=5, help="largest matches to measure against their channel")
    k.add_argument("--format", help="the show format from the library this idea is for")
    k.add_argument("--evidence", help="the JSON of `formats --out` with this format's evidence level")
    k.add_argument("--market-channel", help="the largest channel on the topic in the user's language")
    k.add_argument("--local", action="store_true", help="the test subject belongs to the user's market")
    au = sub.add_parser("audience", help="the audience score of a title or topic")
    au.add_argument("text")
    r = sub.add_parser("rank", help="rank saved checks; --cards writes idea cards with the matching format")
    r.add_argument("files", nargs="+", help="review/idea-*.json")
    r.add_argument("--cards", action="store_true", help="write idea cards into the studio's inbox/ideas/")
    r.add_argument("--top", type=int, default=5, help="cards for the best N")
    a = ap.parse_args(argv)
    pack = _brand().load(a.pack)
    cfg = settings(pack)
    now = dt.datetime.now(dt.UTC)
    src = None
    try:
        if a.cmd == "formats":
            r = cmd_formats(a, cfg, now)
        elif a.cmd == "audience":
            r = audience_score(a.text, cfg) or {"score": None, "why": "no audience in channel.json idea.audience"}
        elif a.cmd == "rank":
            r = cmd_rank(a, now)
        else:
            src = make_source(a.source, cfg, a.max_units)
            if a.cmd == "channel":
                r = cmd_channel(a, cfg, src, now)
            elif a.cmd == "scan":
                r = cmd_scan(a, cfg, src, now, pack)
            elif a.cmd == "collect":
                r = cmd_collect(a, cfg, src, now)
            else:
                r = cmd_check(a, cfg, src, now)
    except MissingKey as e:
        print(f"Error: {e}", file=sys.stderr)
        return 4
    except SourceError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    if src is not None:
        r["api_units"] = getattr(src, "units", 0)
        r["source"] = getattr(src, "name", a.source)
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(r, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=1, default=str))
    else:
        show(a.cmd, r)
        if src is not None and getattr(src, "units", 0):
            print(f"\nAPI units used: {r['api_units']} (daily quota 10,000; source {r['source']}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
