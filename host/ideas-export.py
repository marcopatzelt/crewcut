#!/usr/bin/env python3
"""Idea cards for Crewcut from sources on this computer: a scout ranking and saved links.

The Crewcut container sees only the studio folder, so this script runs on the host and writes one JSON file per idea
into <studio>/inbox/ideas/<id>.json. Crewcut imports them by itself (docs/formats.md, "Idea cards"). Standard library
only; it reads the sources and never changes them.

    python3 host/ideas-export.py --studio ~/Crewcut --scout research/scout-2026-11-27.json --top 12
    python3 host/ideas-export.py --studio ~/Crewcut --braindump ~/notes/links --project crewcut

Sources:
- `--scout FILE`: a ranking `{"date", "ranked": [{"key", "kind", "name", "url", "desc", "topics", "sources", "sig",
  "score", "total", "excluded", "flags", "claim", "format"?}]}`. The best `--top` entries that are not excluded. The
  audience score (`score.audience` or `score.masse`, with its group) goes into the signals; the show format comes
  from the entry's `format` or from `--format` (the library format the whole ranking is for).
- `--braindump DIR`: saved links, one folder per link with `eintrag.json` and its result `ergebnis` (`titel`, `was`,
  `warum`, `projekte: [{"id", "idee", "wo"}]`, `tags`, `prioritaet`). Only links whose projects contain `--project`.

An idea file that exists is left alone (dedupe by id, and by link: the same post from two sources is one card); with
`--refresh` an open idea is rewritten. A started or dismissed idea (its file says so once Crewcut decided) is never
rewritten.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
from pathlib import Path

DECIDED = ("started", "dismissed")


def slug(text: str, n: int = 60) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    if len(s) > n:
        s = s[:n].rstrip("-") + "-" + hashlib.sha1(text.encode()).hexdigest()[:6]
    return s or hashlib.sha1(text.encode()).hexdigest()[:12]


def norm_url(u) -> str | None:
    if not isinstance(u, str) or not u.strip():
        return None
    u = re.sub(r"^https?://(www\.)?", "", u.strip().lower()).split("#")[0].split("?")[0].rstrip("/")
    return u or None


def iso(ts) -> str | None:
    try:
        return dt.datetime.fromtimestamp(float(ts), dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def from_scout(path: Path, top: int, min_total: float | None, fmt: str | None = None) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    ranked = data.get("ranked") if isinstance(data, dict) else None
    if not isinstance(ranked, list):
        raise ValueError(f"{path}: no list \"ranked\"")
    date = str(data.get("date") or "")
    out = []
    for r in ranked:
        if not isinstance(r, dict) or r.get("excluded") or not (r.get("key") or r.get("url")):
            continue
        total = r.get("total")
        if min_total is not None and (not isinstance(total, (int, float)) or total < min_total):
            continue
        sig = r.get("sig") if isinstance(r.get("sig"), dict) else {}
        score = r.get("score") if isinstance(r.get("score"), dict) else {}
        audience = score.get("audience", score.get("masse"))
        signals = {k: v for k, v in {
            "total": total, "score": r.get("score"), "kind": r.get("kind"), "sources": r.get("sources"),
            "audience": audience, "audience_group": r.get("audience_group") or r.get("gruppe"),
            "stars": sig.get("stars"), "velocity_day": sig.get("velocity_day"), "created": sig.get("created"),
            "gap": (sig.get("gap") or {}).get("gap") if isinstance(sig.get("gap"), dict) else None,
            "youtube": [{k: y.get(k) for k in ("title", "channel", "views", "x_median")} for y in sig.get("yt") or []
                        if isinstance(y, dict)][:3] or None,
            "flags": r.get("flags") or None, "group": r.get("gruppe"), "send_by": r.get("send_by"),
            "claim": r.get("claim"), "claim_source": r.get("claim_src"), "file": path.name,
        }.items() if v not in (None, [], {}, "")}
        idea = {"id": "scout-" + slug(str(r.get("key") or r.get("url"))), "source": "scout",
                "url": r.get("url"), "title": str(r.get("name") or r.get("key")),
                "summary": str(r.get("desc") or r.get("claim") or "")[:1500],
                "signals": signals, "topic_type": "trending",
                "created": (r.get("first_seen") or date or None)}
        f = r.get("format") or fmt
        if f:
            idea.update(suggested_format=str(f), reason=r.get("format_reason") or
                        (f"The scout ranks candidates for the format {f}." if not r.get("format") else None))
        out.append(idea)
        if len(out) >= top:
            break
    return out


def from_braindump(root: Path, projects: list[str]) -> list[dict]:
    out = []
    for f in sorted(root.glob("*/eintrag.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        e = d.get("ergebnis") if isinstance(d, dict) else None
        if not isinstance(e, dict):
            continue
        mine = [p for p in e.get("projekte") or [] if isinstance(p, dict) and p.get("id") in projects]
        if not mine:
            continue
        title = str(e.get("titel") or d.get("titel") or d.get("url") or f.parent.name)
        summary = str(e.get("was") or "")
        ideas = [str(p.get("idee") or "") for p in mine if p.get("idee")]
        if ideas:
            summary += "\n\nIdea for this project: " + " ".join(ideas)
        signals = {k: v for k, v in {
            "priority": e.get("prioritaet"), "why": e.get("warum"), "tags": e.get("tags"), "numbers": d.get("zahlen"),
            "author": d.get("autor"), "published": d.get("veroeffentlicht"), "kind": d.get("art"),
            "where": [p.get("wo") for p in mine if p.get("wo")] or None,
        }.items() if v not in (None, [], {}, "")}
        out.append({"id": "braindump-" + slug(str(d.get("id") or f.parent.name), 80), "source": "braindump",
                    "url": d.get("url"), "title": title[:200], "summary": summary[:4000], "signals": signals,
                    "topic_type": "present", "created": iso(d.get("zeit")) or iso(d.get("empfangen"))})
    return out


def write(ideas: list[dict], folder: Path, refresh: bool, dry: bool) -> dict:
    counts = {"written": 0, "kept": 0, "decided": 0, "same_link": 0}
    if not dry:
        folder.mkdir(parents=True, exist_ok=True)
    now = dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    seen = set()
    links: dict[str, str] = {}   # one card per link: the same post from two sources is one idea
    for f in sorted(folder.glob("*.json")) if folder.is_dir() else []:
        try:
            u = norm_url(json.loads(f.read_text(encoding="utf-8")).get("url"))
        except (OSError, ValueError, AttributeError):
            continue
        if u:
            links.setdefault(u, f.stem)
    for idea in ideas:
        if idea["id"] in seen:
            continue
        seen.add(idea["id"])
        u = norm_url(idea.get("url"))
        if u and links.get(u, idea["id"]) != idea["id"]:
            counts["same_link"] += 1
            continue
        if u:
            links[u] = idea["id"]
        p = folder / f"{idea['id']}.json"
        if p.exists():
            try:
                old = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                old = {}
            if old.get("status") in DECIDED:
                counts["decided"] += 1
                continue
            if not refresh:
                counts["kept"] += 1
                continue
        idea = {**idea, "created": idea.get("created") or now, "exported": now}
        if dry:
            print(json.dumps(idea, ensure_ascii=False)[:300])
        else:
            tmp = p.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(idea, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
            tmp.replace(p)
        counts["written"] += 1
    return counts


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Write Crewcut idea cards into <studio>/inbox/ideas/.")
    ap.add_argument("--studio", type=Path, help="the studio folder (or --out)")
    ap.add_argument("--out", type=Path, help="the ideas folder itself (default <studio>/inbox/ideas)")
    ap.add_argument("--scout", type=Path, action="append", default=[], help="a scout ranking JSON (repeatable)")
    ap.add_argument("--top", type=int, default=12, help="best scout entries per file (default 12)")
    ap.add_argument("--min-total", type=float, help="only scout entries with at least this total score")
    ap.add_argument("--format", help="the show format (library id) the scout rankings are for")
    ap.add_argument("--braindump", type=Path, help="the folder of saved links (<id>/eintrag.json)")
    ap.add_argument("--project", action="append", default=[], help="project id a link must name (default crewcut)")
    ap.add_argument("--refresh", action="store_true", help="rewrite open ideas that exist")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    folder = a.out or (a.studio / "inbox" / "ideas" if a.studio else None)
    if folder is None:
        ap.error("--studio or --out is needed")
    if not a.scout and not a.braindump:
        ap.error("name at least one source: --scout FILE or --braindump DIR")
    ideas: list[dict] = []
    try:
        if a.braindump:   # first: a saved link carries the richer summary when the scout found the same link
            ideas += from_braindump(a.braindump, a.project or ["crewcut"])
        for s in a.scout:
            ideas += from_scout(s, a.top, a.min_total, a.format)
    except (OSError, ValueError) as e:
        print(f"ideas-export: {e}", file=sys.stderr)
        return 1
    counts = write(ideas, folder, a.refresh, a.dry_run)
    print(f"{len(ideas)} ideas found: {counts['written']} written, {counts['kept']} already there, "
          f"{counts['decided']} decided in Crewcut (left alone), {counts['same_link']} with a link that has a card "
          f"already. Folder: {folder}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
