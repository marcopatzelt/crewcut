#!/usr/bin/env python3
"""Measure a reference speaker's voice from transcripts and write a voice profile (profile.json) for a studio.

Runs on the host, where the transcripts live; the container never sees them. Standard library only. It reads the
transcripts, never writes to them (a SQLite database is opened read-only). The metrics come from
crewcut/voicemetrics.py, the same code the style gate uses on a script (crewcut/voicecheck.py), so the profile and the
check count the same way.

Sources (one of them):

  --db FILE         a SQLite database with the tables
                      videos(id, title, duration_s, views, kind 'long'|'short', source, dup_of)
                      chunks(video_id, idx, start_s, text)       (timed chunks of the transcript)
  --folder DIR      one file per video: <id>.json (words [{"w","s","e"}] or caption segments
                    [{"words": [{"start","text"}]}]) or <id>.txt (no times: --wpm estimates them);
                    an optional DIR/videos.csv with id,kind,duration_s,views,title

Which videos are "top": --scores FILE.csv (repeatable; columns id and the --score-column, default "outlier",
e.g. views divided by the channel's usual views); the top --top-share of each kind (default 0.25). Without scores the
top share by views.

Calibration and targets:

  --calibrate NAME=FILE   measure a text of the target language too (a words file of a published video, a caption
                          file or a script .md); repeatable. With --calibrate-lang (default de) and --wpm for scripts.
  --targets FILE          the target bands for scripts in the target language, with a reason per metric:
                          {"script": {"lang": "de", "wpm": 175},
                           "long": {"<metric>": {"min": 8, "max": 14, "severity": "error"|"hint", "why": "…"}},
                           "short": {…}}
                          A metric without a band gets a proposal (the reference's 25th to 75th percentile) as a hint.
  --observed FILE         earlier measurements to keep next to the new ones (JSON, copied as "observed")

Example:

  python3 host/voice-profile.py --db ~/corpus/speaker.db --scores long.csv --scores shorts.csv \\
      --calibrate 014=~/studio/episodes/014/work/words-v006.json --targets targets.json \\
      --out ~/studio/brand/references/<style>/voice/profile.json
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import statistics as st
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from crewcut import voicemetrics as vm  # noqa: E402

TIMED = ("words_per_minute", "numbers_per_minute", "first_number_s", "questions_per_minute", "transitions_per_minute",
         "first_transition_s", "unit_seconds_median")


def read_scores(files: list[str], column: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for f in files:
        with open(Path(f).expanduser(), encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                try:
                    out[row["id"]] = float(row[column])
                except (KeyError, TypeError, ValueError):
                    continue
    return out


def from_db(path: Path, sources: list[str]) -> list[dict]:
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    cols = {r[1] for r in con.execute("PRAGMA table_info(videos)")}
    where = " WHERE 1=1"
    args: list = []
    if "dup_of" in cols:
        where += " AND (v.dup_of IS NULL OR v.dup_of = '')"
    if sources and "source" in cols:
        where += f" AND v.source IN ({','.join('?' * len(sources))})"
        args += sources
    vids = con.execute("SELECT v.id, v.title, v.duration_s, v.views, v.kind FROM videos v" + where, args).fetchall()
    out = []
    for v in vids:
        rows = con.execute("SELECT start_s, text FROM chunks WHERE video_id = ? ORDER BY idx", (v["id"],)).fetchall()
        if rows:
            out.append({"id": v["id"], "title": v["title"], "duration_s": v["duration_s"], "views": v["views"],
                        "kind": v["kind"], "chunks": [(float(r["start_s"]), r["text"]) for r in rows]})
    con.close()
    return out


def normalize_words(data) -> list[dict]:
    """[{"w","s","e"}] as it is, or caption segments [{"words": [{"start","text"}], "end"}] turned into it."""
    if isinstance(data, dict):
        data = data.get("words") or data.get("segments") or []
    if data and isinstance(data[0], dict) and "words" in data[0]:
        flat = []
        for seg in data:
            ws = seg.get("words") or []
            for i, w in enumerate(ws):
                s = float(w.get("start", seg.get("start", 0.0)))
                e = float(ws[i + 1]["start"]) if i + 1 < len(ws) else float(seg.get("end", s + 0.3))
                flat.append({"w": w.get("text") or w.get("w") or "", "s": s, "e": e})
        return flat
    return [d if isinstance(d, dict) else {"s": d[0], "e": d[1], "w": d[2]} for d in data]


def from_folder(folder: Path, wpm: float) -> list[dict]:
    meta = {}
    m = folder / "videos.csv"
    if m.is_file():
        with open(m, encoding="utf-8", newline="") as fh:
            meta = {r["id"]: r for r in csv.DictReader(fh)}
    out = []
    for p in sorted(folder.iterdir()):
        if p.suffix not in (".json", ".txt") or p.name == "videos.csv":
            continue
        info = meta.get(p.stem, {})
        item = {"id": p.stem, "title": info.get("title"), "kind": info.get("kind") or "long",
                "duration_s": float(info["duration_s"]) if info.get("duration_s") else None,
                "views": int(info["views"]) if info.get("views") else None}
        if p.suffix == ".json":
            item["words"] = normalize_words(json.loads(p.read_text(encoding="utf-8")))
        else:
            item["text"] = p.read_text(encoding="utf-8")
            item["wpm"] = wpm
        out.append(item)
    return out


def sentences_of(item: dict) -> list[vm.Sentence]:
    if item.get("chunks"):
        return vm.from_chunks(item["chunks"], item.get("duration_s"))
    if item.get("words"):
        return vm.from_timed(item["words"])
    return vm.from_text(item.get("text") or "", item.get("wpm") or 160)


def speaker_changes(item: dict, seconds: float = 1e9) -> int:
    return sum(t.count(">>") for s0, t in item.get("chunks") or [] if s0 < seconds)


def measure_all(items: list[dict], lang: str) -> list[dict]:
    out = []
    for it in items:
        sents = sentences_of(it)
        if sum(len(s.words) for s in sents) < 20:
            continue
        m = vm.measure(sents, lang, sentence_metrics=vm.punctuated(sents))
        it_out = {k: it.get(k) for k in ("id", "title", "kind", "duration_s", "views", "score")}
        it_out["speaker_changes"] = speaker_changes(it)
        it_out["metrics"] = m
        out.append(it_out)
    return out


def group(rows: list[dict]) -> dict:
    keys = list(vm.METRICS)
    return {"n": len(rows), "metrics": {k: vm.summary([r["metrics"].get(k) for r in rows]) for k in keys}}


def top(rows: list[dict], share: float) -> list[dict]:
    scored = [r for r in rows if r.get("score") is not None]
    if scored:
        scored.sort(key=lambda r: r["score"], reverse=True)
        return scored[:max(1, round(len(scored) * share))]
    rows = sorted([r for r in rows if r.get("views")], key=lambda r: r["views"], reverse=True)
    return rows[:max(1, round(len(rows) * share))] if rows else []


def calibrate(specs: list[str], lang: str, wpm: float) -> dict:
    out = {}
    for spec in specs:
        name, _, f = spec.partition("=")
        p = Path(f).expanduser()
        if p.suffix == ".json":
            sents = vm.from_timed(normalize_words(json.loads(p.read_text(encoding="utf-8"))))
            timing = "measured"
        else:
            text = p.read_text(encoding="utf-8").split("\n---\n")[0]
            lines = []
            for i, raw in enumerate(text.splitlines(), 1):
                s = raw.strip()
                if not s or s.startswith("#"):
                    continue
                if ":" in s[:14] and s.split(":", 1)[0].isupper():   # a cue sheet marker: the fixed line
                    s = s.split(":", 1)[1]
                elif s.startswith(("•", "- ", "* ")):
                    continue                                         # bullets are not said word for word
                lines.append((i, " ".join(vm.NOISE.sub(" ", s).split())))
            sents = vm.from_lines(lines, wpm)
            timing = f"estimated at {wpm:g} words per minute"
        m = vm.measure(sents, lang)
        out[name] = {"file": str(p), "timing": timing, "metrics": {k: (round(v, 3) if isinstance(v, float) else v)
                                                                    for k, v in m.items()}}
    return out


def proposals(ref: dict, fmt: str) -> dict:
    """A band for every metric without a studio target: the reference's 25th to 75th percentile, as a hint."""
    out = {}
    for k, s in (ref.get("metrics") or {}).items():
        if not s or k in ("first_number_word", "first_transition_s", "sentence_words_p25", "sentence_words_p75"):
            continue
        out[k] = {"min": s["p25"], "max": s["p75"], "severity": "hint",
                  "why": f"proposal: the reference's {fmt} top videos, 25th to 75th percentile (median {s['median']})"}
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--db")
    src.add_argument("--folder")
    ap.add_argument("--source", action="append", default=[], help="only these videos.source values (repeatable)")
    ap.add_argument("--scores", action="append", default=[])
    ap.add_argument("--score-column", default="outlier")
    ap.add_argument("--top-share", type=float, default=0.25)
    ap.add_argument("--lang", default="en")
    ap.add_argument("--speaker", default="reference speaker")
    ap.add_argument("--long-min-s", type=float, default=240)
    ap.add_argument("--long-max-s", type=float, default=1500)
    ap.add_argument("--max-speaker-changes", type=int, default=2, help="long videos: at most this many '>>' (solo)")
    ap.add_argument("--wpm", type=float, default=175, help="words per minute for texts without times")
    ap.add_argument("--calibrate", action="append", default=[])
    ap.add_argument("--calibrate-lang", default="de")
    ap.add_argument("--targets")
    ap.add_argument("--observed")
    ap.add_argument("--per-video", help="also write the metrics of every video to this JSON file")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)

    items = from_db(Path(a.db).expanduser(), a.source) if a.db else from_folder(Path(a.folder).expanduser(), a.wpm)
    scores = read_scores(a.scores, a.score_column)
    for it in items:
        it["score"] = scores.get(it["id"])
    rows = measure_all(items, a.lang)
    long_all = [r for r in rows if r["kind"] != "short" and (r["duration_s"] or 0) >= a.long_min_s
                and (r["duration_s"] or 1e9) <= a.long_max_s and r["speaker_changes"] <= a.max_speaker_changes]
    short_all = [r for r in rows if r["kind"] == "short"]
    long_top, short_top = top(long_all, a.top_share), top(short_all, a.top_share)
    reference = {"long_top": group(long_top), "long_all": group(long_all), "short_top": group(short_top),
                 "short_all": group(short_all)}
    for g, rs in (("long_top", long_top), ("short_top", short_top)):
        sc = [r["score"] for r in rs if r.get("score") is not None]
        reference[g]["score_min"] = round(min(sc), 3) if sc else None
        reference[g]["score_median"] = round(st.median(sc), 3) if sc else None
        reference[g]["ids"] = [r["id"] for r in rs[:60]]
    targets = json.loads(Path(a.targets).expanduser().read_text(encoding="utf-8")) if a.targets else {}
    profile = {
        "schema": 1,
        "created": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "speaker": {"name": a.speaker, "lang": a.lang},
        "source": {"kind": "sqlite" if a.db else "folder", "videos_read": len(items), "videos_measured": len(rows),
                   "long": len(long_all), "short": len(short_all), "top_share": a.top_share,
                   "scores": "column " + a.score_column if scores else "views",
                   "filters": {"long_seconds": [a.long_min_s, a.long_max_s],
                               "max_speaker_changes": a.max_speaker_changes, "sources": a.source or "all"},
                   "note": "sentence metrics only from transcripts with sentence marks; times inside a chunk are "
                           "spread evenly; numbers, imperatives, fillers and transitions come from word lists"},
        "metrics": vm.METRICS,
        "reference": reference,
        "calibration": calibrate(a.calibrate, a.calibrate_lang, targets.get("script", {}).get("wpm") or a.wpm),
        "script": targets.get("script") or {"lang": a.calibrate_lang, "wpm": a.wpm},
        "targets": {},
    }
    for fmt, ref in (("long", reference["long_top"]), ("short", reference["short_top"])):
        band = proposals(ref, fmt)
        band.update(targets.get(fmt) or {})
        profile["targets"][fmt] = band
    for key in ("lexicon", "check_names"):
        if targets.get(key):
            profile[key] = targets[key]
    if targets.get("notes"):
        profile["notes"] = targets["notes"]
    if a.observed:
        profile["observed"] = json.loads(Path(a.observed).expanduser().read_text(encoding="utf-8"))
    out = Path(a.out).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(profile, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    if a.per_video:
        Path(a.per_video).expanduser().write_text(json.dumps(rows, ensure_ascii=False) + "\n", encoding="utf-8")
    lt = reference["long_top"]["metrics"]
    print(f"{out}: {len(rows)} videos measured ({len(long_all)} long, {len(short_all)} Shorts); long top "
          f"{len(long_top)}: sentence median {(lt.get('sentence_words_median') or {}).get('median')}, "
          f"{(lt.get('words_per_minute') or {}).get('median')} words/min, "
          f"{(lt.get('numbers_per_minute') or {}).get('median')} numbers/min")
    return 0


if __name__ == "__main__":
    sys.exit(main())
