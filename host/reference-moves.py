#!/usr/bin/env python3
"""Find a reference speaker's moves in transcripts and write one reference file per move ("Vorbilder").

Runs on the host, next to the transcripts; standard library only; the database is opened read-only. Two steps:

1. `candidates`: read the best videos (by a score such as views against the channel's usual views) and pull candidate
   passages for each move, word for word from the transcript, with the link to the chunk where the passage starts:

     hook          the first sentence of a long video
     intro         the opening up to the plan: proof, promise, plan in the first ~35 seconds
     proof         an example or a case with a number ("let's say", "I remember", "we had")
     transition    a counted transition ("number two", "the next one", "which brings us to") and the sentence after it
     punch         a short line (at most 8 words) right after a long one (at least 18 words)
     ending        the last sentences of a long video (no goodbye, no promotion)
     short-first   the first sentence of a Short
     short-end     the last sentence of a Short (at most 12 words)

   python3 host/reference-moves.py candidates --db corpus.db --scores long.csv --scores shorts.csv --out cand.json

2. `render`: a person (or an agent) picks passages from the candidates and writes, per passage, a transfer line in the
   target language and the pattern in one line, in a JSON file:

     {"hook": {"title": "…", "intro": "…", "pick": [{"id": "<candidate id>", "pattern": "…", "transfer": "…"}]}, …}

   python3 host/reference-moves.py render --candidates cand.json --picks picks.json --dir <studio>/…/vorbilder

   Each move becomes <dir>/<move>.md: per passage the quote in straight double quotes with a source number [n], the
   pattern, the transfer line in „…“, and the source line `[n] <link>`. That layout is what a quote checker reads
   (every quote must stand word for word in the chunk its link points to).

Quotes are short passages for study with credit and link; the files belong in a private studio, not in a repository.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from crewcut import voicemetrics as vm  # noqa: E402

MOVES = ("hook", "intro", "proof", "transition", "punch", "ending", "short-first", "short-end")
GREETING = re.compile(r"^(hey|hi|hello|what's up|welcome|yo|good morning)\b|\bwelcome (back )?to\b", re.I)
GOODBYE = re.compile(r"\b(bye|see you|catch you|next one|lots of love|strength and honou?r|subscribe|link (below|in)|"
                     r"click (here|the link)|acquisition\.com|thank(s| you) for watching|leave a comment|rate and review)\b",
                     re.I)
PROMISE = re.compile(r"\b(i'm going to|i am going to|i'll show you|i will show you|in this video|by the end|"
                     r"today i|here's how|i'm gonna|let me show you|walk you through)\b", re.I)
PLAN = re.compile(r"\b(two|three|four|five|six|seven|\d+) (things|ways|steps|reasons|mistakes|lessons|rules|levers|"
                  r"questions|parts|pieces|types|stages|models)\b", re.I)
PROOF = re.compile(r"\b(for example|let's say|let me give you|i remember|when i|we had|one of my|this guy|this woman|"
                   r"a guy|a gym owner|in my gym|at my gym|my first|last year|the other day)\b", re.I)


def link(vid: str, t: float) -> str:
    return f"https://www.youtube.com/watch?v={vid}&t={int(t)}s"


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


def chunk_sentences(text: str) -> list[str]:
    """Sentences of one chunk as written (no cleaning: a quote must stand word for word in the chunk)."""
    return [s for s in vm.split(text) if len(s.split()) >= 3]


def videos(con, kind: str, scores: dict, top: int, min_s: float, max_s: float) -> list[dict]:
    rows = con.execute("SELECT id, title, duration_s, views, published FROM videos WHERE kind = ? AND source = 'youtube' "
                       "AND (dup_of IS NULL OR dup_of = '')", (kind,)).fetchall()
    out = [dict(r) | {"score": scores.get(r["id"])} for r in rows if r["id"] in scores]
    out = [v for v in out if min_s <= (v["duration_s"] or 0) <= max_s]
    out.sort(key=lambda v: v["score"], reverse=True)
    return out[:top]


def chunks(con, vid: str) -> list[tuple[float, str]]:
    return [(float(r["start_s"]), r["text"]) for r in
            con.execute("SELECT start_s, text FROM chunks WHERE video_id = ? ORDER BY idx", (vid,))]


def cand(move: str, v: dict, t: float, text: str, why: str = "") -> dict:
    return {"id": f"{move}:{v['id']}:{int(t)}:{zlib.crc32(text.encode()) % 10000}", "move": move, "video": v["id"],
            "title": v["title"], "score": v["score"], "views": v["views"], "published": (v.get("published") or "")[:10],
            "start": int(t), "link": link(v["id"], t), "quote": " ".join(text.split()), "why": why}


def punctuated(cs: list[tuple[float, str]]) -> bool:
    """Transcripts without sentence marks give run-on 'sentences': they are left out."""
    text = " ".join(t for _, t in cs)
    return len(re.findall(r"[.?!](?:\s|$)", text)) * 100 >= 4 * max(len(text.split()), 1)


def long_moves(v: dict, cs: list[tuple[float, str]]) -> list[dict]:
    out: list[dict] = []
    if not cs or ">>" in " ".join(t for _, t in cs[:2]) or not punctuated(cs):
        return out
    t0, first = cs[0]
    sents = vm.split(first)
    if sents and not GREETING.search(sents[0]) and 5 <= len(sents[0].split()) <= 30:
        out.append(cand("hook", v, t0, sents[0]))
        # intro: from the start up to the plan sentence, inside the first chunk, at most ~75 words
        acc, has_promise, has_proof, has_plan = [], False, False, False
        for s in sents[:8]:
            acc.append(s)
            if len(" ".join(acc).split()) > 70 or len(" ".join(acc)) > 390:
                break
            has_promise |= bool(PROMISE.search(s))
            has_plan |= bool(PLAN.search(s))
            has_proof |= bool(vm.numbers_in(s, vm.lexicon("en")))
            if has_proof and (has_promise or has_plan) and len(acc) >= 2:
                out.append(cand("intro", v, t0, " ".join(acc), ", ".join(
                    w for w, ok in (("proof", has_proof), ("promise", has_promise), ("plan", has_plan)) if ok)))
                break
    lex = vm.lexicon("en")
    for i, (t, text) in enumerate(cs):
        ss = vm.split(text)
        for k, s in enumerate(ss):
            if len(s.split()) < 3:
                continue
            low = " ".join(vm.words(s))
            if i > 0 and lex["_transitions"].search(low) and len(s.split()) <= 30:
                nxt = ss[k + 1] if k + 1 < len(ss) else ""
                q = s + (" " + nxt if nxt and len((s + " " + nxt).split()) <= 45 else "")
                out.append(cand("transition", v, t, q))
            if PROOF.search(s) and vm.numbers_in(s, lex) and 8 <= len(s.split()) <= 45 and i > 0:
                out.append(cand("proof", v, t, s))
            if (k > 0 and len(s.split()) <= 8 and len(ss[k - 1].split()) >= 18 and not s.rstrip().endswith("?")
                    and not GOODBYE.search(s) and i > 0 and len(s.split()) >= 3):
                out.append(cand("punch", v, t, ss[k - 1] + " " + s, "long line, then the punch"))
    t_last, last = cs[-1]
    ends = [s for s in chunk_sentences(last) if not GOODBYE.search(s)]
    tail = chunk_sentences(last)
    if ends and tail and not GOODBYE.search(" ".join(tail[-2:])):
        q = " ".join(ends[-2:])
        if len(q.split()) <= 60:
            out.append(cand("ending", v, t_last, q))
    return out


def short_moves(v: dict, cs: list[tuple[float, str]]) -> list[dict]:
    out: list[dict] = []
    if not cs:
        return out
    t0, first = cs[0]
    ss = chunk_sentences(first.replace(">>", " "))
    raw = chunk_sentences(first)
    if raw and len(raw[0].split()) <= 25 and ">>" not in raw[0]:
        out.append(cand("short-first", v, t0, raw[0], "has a number" if vm.numbers_in(raw[0], vm.lexicon("en")) else ""))
    t_last, last = cs[-1]
    tail = [s for s in chunk_sentences(last) if ">>" not in s]
    if tail and len(tail[-1].split()) <= 12 and not GOODBYE.search(tail[-1]) and not tail[-1].rstrip().endswith("?"):
        out.append(cand("short-end", v, t_last, tail[-1]))
    del ss
    return out


def cmd_candidates(a) -> int:
    con = sqlite3.connect(f"file:{Path(a.db).expanduser()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    scores = read_scores(a.scores, a.score_column)
    out: dict[str, list] = {m: [] for m in MOVES}
    for v in videos(con, "long", scores, a.top_long, a.long_min_s, a.long_max_s):
        for c in long_moves(v, chunks(con, v["id"])):
            out[c["move"]].append(c)
    for v in videos(con, "short", scores, a.top_short, 0, 400):
        for c in short_moves(v, chunks(con, v["id"])):
            out[c["move"]].append(c)
    for m in out:   # the same words (a re-upload) only once
        seen_q: set[str] = set()
        uniq = []
        for c in sorted(out[m], key=lambda c: -c["score"]):
            k = " ".join(vm.words(c["quote"]))[:120]
            if k not in seen_q:
                seen_q.add(k)
                uniq.append(c)
        out[m] = uniq
    for m in out:   # best video first, then one passage per video before a second one
        seen: dict[str, int] = {}
        ranked = []
        for c in sorted(out[m], key=lambda c: -c["score"]):
            seen[c["video"]] = seen.get(c["video"], 0) + 1
            ranked.append((seen[c["video"]], -c["score"], c))
        out[m] = [c for _, _, c in sorted(ranked, key=lambda x: (x[0], x[1]))][:a.per_move]
    Path(a.out).expanduser().write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(", ".join(f"{m}: {len(v)}" for m, v in out.items()))
    return 0


def german_quotes(text: str) -> str:
    """Straight double quotes outside the passage become „…“, so a quote checker reads only the passage as a quote."""
    text = re.sub(r'"([^"\n]*)"', "\u201e\\1\u201c", str(text or ""))
    return re.sub("\u201c([^\u201d\n]*)\u201d", "\u201e\\1\u201c", text)


def cmd_render(a) -> int:
    cands = json.loads(Path(a.candidates).expanduser().read_text(encoding="utf-8"))
    picks = json.loads(Path(a.picks).expanduser().read_text(encoding="utf-8"))
    by_id = {c["id"]: c for cs in cands.values() for c in cs}
    folder = Path(a.dir).expanduser()
    folder.mkdir(parents=True, exist_ok=True)
    total = 0
    for move, spec in picks.items():
        if move.startswith("_"):
            continue
        lines = [f"# {german_quotes(spec.get('title') or move)}", ""]
        if spec.get("intro"):
            lines += [german_quotes(spec["intro"].strip()), ""]
        refs = []
        for n, p in enumerate(spec.get("pick") or [], 1):
            c = by_id.get(p["id"])
            if c is None:
                print(f"{move}: no candidate {p['id']}", file=sys.stderr)
                return 1
            score = f"{c['score']:.1f}x".replace(".", ",") if c.get("score") is not None else ""
            lines += [f"## {n}. {german_quotes(c['title'])} ({score}, {c['published']})", "",
                      f"\"{c['quote']}\" [{n}]", "",
                      f"- {a.pattern_label}: {german_quotes(p['pattern'])}",
                      f"- {a.transfer_label}: „{p['transfer']}“", ""]
            refs.append(f"[{n}] {c['link']}")
            total += 1
        lines += [f"## {a.sources_label}", "", *refs, ""]
        (folder / f"{move}.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"{total} passages in {len(picks)} files under {folder}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("candidates")
    c.add_argument("--db", required=True)
    c.add_argument("--scores", action="append", default=[])
    c.add_argument("--score-column", default="outlier")
    c.add_argument("--top-long", type=int, default=120)
    c.add_argument("--top-short", type=int, default=150)
    c.add_argument("--long-min-s", type=float, default=240)
    c.add_argument("--long-max-s", type=float, default=2400)
    c.add_argument("--per-move", type=int, default=60)
    c.add_argument("--out", required=True)
    r = sub.add_parser("render")
    r.add_argument("--candidates", required=True)
    r.add_argument("--picks", required=True)
    r.add_argument("--dir", required=True)
    r.add_argument("--pattern-label", default="Pattern")
    r.add_argument("--transfer-label", default="Transfer")
    r.add_argument("--sources-label", default="Sources")
    a = ap.parse_args(argv)
    return cmd_candidates(a) if a.cmd == "candidates" else cmd_render(a)


if __name__ == "__main__":
    sys.exit(main())
