#!/usr/bin/env python3
"""Check a speaker cut (the cut of the user's recording) before anything is built on it or shown.

  python3 skills/cut-check/scripts/cut_check.py <episode>/work/edit-decisions-vNNN.json
          [--verification FILE] [--islands DIR …] [--voice FILE] [--episode DIR]
          [--exceptions FILE] [--report FILE] [--pack DIR]

General checks (any style):
  verify      the cut verification ran for this cut, is newer than the decisions, has no bad joins
  edge        a cut edge where the heard text differs from the expected text (often only spelling)
  channels    the voice is on both sides
  doubled     the same word (or a same-meaning word from the pack) on both sides of a cut
  leftover    a cut edge close to a discarded attempt, or a start inside a speech island: a word rest is likely
  take-change a sentence that runs over a take change (tone often differs): goes on the listening list
  level       a level jump of 4 dB or more between neighbouring pieces
  stutter     a repeated word or a filler word (fillers come from the pack) in what the transcriber heard
Language-specific word lists (fillers, same-meaning words, transcript noise) come from the style pack
(edit-style.json, key cut_words). The neutral pack has none, so those checks only use exact repeats.

Input files (written by `crewcut cut plan|build|verify|islands`):
  decisions     {"voice": path, "fps": 25, "clips": [{"id", "source", "start", "end", "expected_text",
                 "timeline_in_frame", "timeline_out_frame"}]}
  verification  cut-verification-vNNN.json next to the decisions: {"status", "selects": [{"id", "text"}],
                 "joins": [...], "bad_joins": [{"from", "to", "pause", "at"}],
                 "edge_issues": [{"select", "where", "expected", "heard"}], "channel_levels_db": [left, right]}
  islands       <source stem>-islands.json: [{"start", "end", "text"}] (speech islands of each take)
Paths inside the files are relative to the episode folder. Prints ERROR / CHECK / NOTE / OK, the listening list and
the manual list. Writes review/speaker-cut-check-vNNN.json. Exit 0 = no ERROR, 1 = at least one ERROR, 2 = usage.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import checklib as cl  # noqa: E402

EDGE_MIN = 0.28  # s between a cut edge and a discarded attempt in the same take
LEVEL_JUMP = 4.0  # dB, voiced level 2.5 s before vs after a cut
MANUAL = [
    "Listened to every spot on the listening list. Without sound in this session: give the times to the user, never "
    "claim a listening check.",
    "The whole cut once in one go: no stutter, no doubled sentence start, joins flow.",
    'Spoken instructions during the recording were followed ("the first take was fine", "cut that part").',
    "Where the cut differs from the script, the list of differences is in the report to the user.",
]


# ---------------------------------------------------------------- pure functions


def words(text: str | None, same: dict | None = None) -> list[str]:
    """Lower-case words of a text, hyphenated parts split, spelling variants mapped (pack: cut_words.same_spelling)."""
    same = same or {}
    out = []
    for w in re.findall(r"[\w.\-']+", (text or "").lower()):
        for part in w.strip(".-'").split("-"):
            part = part.strip(".'")
            if part:
                out.append(same.get(part, part))
    return out


def same_word(a: str, b: str, same_meaning: list[list[str]]) -> bool:
    if len(a) <= 1:
        return False
    return a == b or any(a in g and b in g for g in (set(x) for x in same_meaning))


def doubled_at_cuts(
    clips: list[dict], heard: dict, same_meaning: list[list[str]], same: dict | None = None
) -> list[dict]:
    """The same word on both sides of a cut, in the expected text or in what was heard."""
    out = []
    for a, b in zip(clips, clips[1:], strict=False):
        for src, ta, tb in (
            ("script", a.get("expected_text"), b.get("expected_text")),
            ("heard", heard.get(a["id"]), heard.get(b["id"])),
        ):
            if src == "script" and ta == tb:
                continue  # pieces of one select
            wa, wb = words(ta, same), words(tb, same)
            if wa and wb and same_word(wa[-1], wb[0], same_meaning):
                out.append(
                    {
                        "a": a["id"],
                        "b": b["id"],
                        "source": src,
                        "word_a": wa[-1],
                        "word_b": wb[0],
                        "frame": b["timeline_in_frame"],
                    }
                )
                break
    return out


def is_discarded(island: dict, used: list[tuple[float, float]], noise: set[str]) -> bool:
    """A speech island that no clip uses and that is real speech (not transcript noise or a marker)."""
    raw = island.get("text") or ""
    txt = re.sub(r"[^\w ]", "", raw.lower()).strip()
    if not txt or txt in noise or raw.strip().startswith("*"):
        return False
    return not any(island["end"] > s + 0.05 and island["start"] < e - 0.05 for s, e in used)


def leftovers(
    clips: list[dict], islands: dict, noise: set[str], edge_min: float = EDGE_MIN, same: dict | None = None
) -> list[dict]:
    """Cut edges where a word rest is possible (CHECK) or likely (ERROR)."""
    used: dict[str, list] = {}
    for c in clips:
        used.setdefault(c["source"], []).append((c["start"], c["end"]))
    out = []
    for c in clips:
        il = islands.get(c["source"])
        if not il:
            continue
        il = sorted(il, key=lambda i: i["start"])
        s, e = c["start"], c["end"]
        before = [i for i in il if i["end"] <= s + 0.05 and is_discarded(i, used[c["source"]], noise)]
        after = [i for i in il if i["start"] >= e - 0.05 and is_discarded(i, used[c["source"]], noise)]
        if before and s - before[-1]["end"] < edge_min:
            out.append(
                {
                    "id": c["id"],
                    "where": "start",
                    "level": "CHECK",
                    "gap": s - before[-1]["end"],
                    "text": before[-1]["text"],
                    "frame": c["timeline_in_frame"],
                    "at": s,
                }
            )
        if after and after[0]["start"] - e < edge_min:
            out.append(
                {
                    "id": c["id"],
                    "where": "end",
                    "level": "CHECK",
                    "gap": after[0]["start"] - e,
                    "text": after[0]["text"],
                    "frame": c["timeline_out_frame"],
                    "at": e,
                }
            )
        for i in il:
            if i["start"] + 0.3 < s < i["end"] - 0.1:
                iw, ew = words(i.get("text"), same), words(c.get("expected_text"), same)
                if ew and iw and iw[:2] != ew[:2]:
                    k = next((n for n in range(len(iw)) if iw[n : n + 2] == ew[:2]), None)
                    lead = " ".join(iw[:k]) if k else " ".join(iw[:4]) + " …"
                    out.append(
                        {
                            "id": c["id"],
                            "where": "middle",
                            "level": "ERROR",
                            "gap": s - i["start"],
                            "text": lead,
                            "frame": c["timeline_in_frame"],
                            "at": s,
                        }
                    )
    return out


def take_change_sentences(clips: list[dict]) -> list[dict]:
    """A sentence that continues over a change of take (other file, or a jump of more than 1 s in the same file)."""
    out = []
    for a, b in zip(clips, clips[1:], strict=False):
        ta = (a.get("expected_text") or "").strip()
        cont = a.get("expected_text") == b.get("expected_text") or not re.search(r"[.?!]\s*$", ta)
        jump = a["source"] != b["source"] or abs(b["start"] - a["end"]) > 1.0
        if cont and jump:
            out.append(
                {
                    "a": a["id"],
                    "b": b["id"],
                    "tail": ta[-25:],
                    "head": (b.get("expected_text") or "")[:25],
                    "frame": b["timeline_in_frame"],
                }
            )
    return out


def stutters(clips: list[dict], heard: dict, fillers: set[str], same: dict | None = None) -> list[dict]:
    """Repeated words (not across a sentence mark, not numbers) and filler words in what was heard."""
    out = []
    for c in clips:
        raw = (heard.get(c["id"]) or "").split()
        rep = []
        for k in range(1, len(raw)):
            wk, wp = words(raw[k], same), words(raw[k - 1], same)
            if wk and wk == wp and raw[k - 1][-1] not in ".,?!:;" and not wk[0].isdigit():
                rep.append(raw[k])
        fill = [x for x in words(heard.get(c["id"], ""), same) if x in fillers]
        if rep or fill:
            out.append({"id": c["id"], "found": rep + fill, "frame": c["timeline_in_frame"]})
    return out


def level_jumps(
    levels: np.ndarray, voiced: np.ndarray, clips: list[dict], fps: float, jump: float = LEVEL_JUMP
) -> list[dict]:
    """Median voiced level (10 ms steps) 2.5 s before and after each cut; a difference of `jump` dB or more."""
    out = []
    for a, b in zip(clips, clips[1:], strict=False):
        t = b["timeline_in_frame"] / fps
        lo = int(max(a["timeline_in_frame"] / fps, t - 2.5) * 100)
        hi = int(min(b["timeline_out_frame"] / fps, t + 2.5) * 100)
        ia = [k for k in range(lo, int(t * 100)) if k < len(voiced) and voiced[k]]
        ib = [k for k in range(int(t * 100), hi) if k < len(voiced) and voiced[k]]
        if len(ia) > 30 and len(ib) > 30:
            d = float(np.median(levels[ib]) - np.median(levels[ia]))
            if abs(d) >= jump:
                out.append({"a": a["id"], "b": b["id"], "db": d, "frame": b["timeline_in_frame"]})
    return out


def cut_words(pack) -> dict:
    """Language-specific word lists from the style pack (edit-style.json, cut_words)."""
    cw = pack.value("edit_style.cut_words", {}) if pack is not None else {}
    return {
        "fillers": {w.lower() for w in cw.get("fillers") or []},
        "same_meaning": [[w.lower() for w in g] for g in cw.get("same_meaning") or []],
        "noise": {w.lower() for w in cw.get("transcript_noise") or []},
        "same_spelling": {k.lower(): v.lower() for k, v in (cw.get("same_spelling") or {}).items()},
    }


# ---------------------------------------------------------------- files and media


def read_islands(path: Path) -> list[dict] | None:
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("islands", []) if isinstance(data, dict) else data


def voice_levels(path) -> tuple[np.ndarray, np.ndarray]:
    """Level in dB in 10 ms steps and a mask of voiced steps (15 dB over the quiet floor)."""
    raw = cl.run(
        ["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", "16000", "-f", "f32le", "-"], text=False
    ).stdout
    x = np.frombuffer(raw, np.float32)
    r = 20 * np.log10(np.sqrt(np.convolve(x**2, np.ones(640) / 640, "same")[::160]) + 1e-9)
    return r, r > np.percentile(r, 8) + 15


def episode_of(decisions: Path) -> Path:
    for p in decisions.resolve().parents:
        if (p / "project.json").exists():
            return p
    return decisions.resolve().parent.parent


def check(dec_path: Path, ep: Path, ver_path: Path, island_dirs: list[Path], voice: Path | None, pack, rep: cl.Report):
    area = "Cut"
    dec = json.loads(dec_path.read_text(encoding="utf-8"))
    clips, fps = dec.get("clips", []), dec.get("fps") or pack.value("edit_style.fps", 25)
    cw = cut_words(pack)
    same = cw["same_spelling"]
    heard: dict = {}
    if not ver_path.is_file():
        rep.add(
            area,
            "ERROR",
            "verify",
            f"The cut verification did not run for {dec_path.name}.",
            fix=f"crewcut cut verify {dec_path.name}",
        )
    else:
        v = json.loads(ver_path.read_text(encoding="utf-8"))
        heard = {s["id"]: s.get("text", "") for s in v.get("selects", [])}
        old = ver_path.stat().st_mtime < dec_path.stat().st_mtime
        if old:
            rep.add(
                area,
                "ERROR",
                "verify",
                "The cut verification is older than the decisions: verify again.",
                fix=f"crewcut cut verify {dec_path.name}",
            )
        bad = v.get("bad_joins", [])
        for j in bad:
            rep.add(
                area,
                "ERROR",
                f"join:{j['from']}>{j['to']}",
                f"Pause at a cut {j['pause']:.2f} s is outside the allowed range, {j['from']} > {j['to']}",
                j.get("at"),
            )
        for e in v.get("edge_issues", []):
            rep.add(
                area,
                "CHECK",
                f"edge:{e['select']}:{e['where']}",
                f'Edge {e["where"]} of {e["select"]}: expected "{e["expected"]}", heard "{e["heard"]}" (often only spelling)',
            )
        lv = v.get("channel_levels_db") or []
        if len(lv) == 2 and abs(lv[0] - lv[1]) > 10:
            rep.add(area, "ERROR", "channels", f"Voice on one side only: left {lv[0]} dB, right {lv[1]} dB")
        if not old and not bad:
            rep.add(
                area,
                "OK",
                "verify",
                f"Cut verification: {v.get('status', 'ok')}, {len(v.get('joins', []))} joins in range",
            )
    for d in doubled_at_cuts(clips, heard, cw["same_meaning"], same):
        rep.add(
            area,
            "ERROR",
            f"doubled:{d['a']}>{d['b']}",
            f'Doubled word at a cut ({d["source"]}): "{d["word_a"]}" | "{d["word_b"]}", {d["a"]} > {d["b"]}',
            d["frame"] / fps,
            fix="Take the whole sentence from one take, or move the edge to a pause",
        )
    islands, missing = {}, []
    for src in {c["source"] for c in clips}:
        found = None
        for d in island_dirs:
            found = read_islands(d / f"{Path(src).stem}-islands.json")
            if found is not None:
                break
        if found is None:
            missing.append(Path(src).stem)
        islands[src] = found
    if missing:
        rep.add(
            area,
            "NOTE",
            "islands",
            f"No speech islands for {', '.join(sorted(missing))}: the word-rest check is off there.",
        )
    lo = leftovers(clips, islands, cw["noise"], same=same)
    for x in lo:
        if x["where"] == "middle":
            rep.add(
                area,
                "ERROR",
                f"leftover:{x['id']}:middle",
                f'{x["id"]} starts inside a speech island, {x["gap"]:.2f} s after its start, after "{x["text"]}": '
                "a word rest is likely",
                x["frame"] / fps,
                fix="Set the edge at a measured dip (crewcut cut islands … dips) or take the whole sentence from one take",
            )
        else:
            rel = "starts" if x["where"] == "start" else "ends"
            rep.add(
                area,
                "CHECK",
                f"leftover:{x['id']}:{x['where']}",
                f'{x["id"]} {rel} {x["gap"]:.2f} s from a discarded attempt ("{x["text"][:30]}"): a word rest is possible',
                x["frame"] / fps,
                fix=f"Probe the edge at {x['at']:.2f} s in the source",
            )
    if not lo and not missing:
        rep.add(area, "OK", "leftover", "No cut edge right next to a discarded attempt")
    tcs = take_change_sentences(clips)
    for x in tcs:
        rep.add(
            area,
            "CHECK",
            f"take-change:{x['a']}>{x['b']}",
            f'A sentence runs over a take change ("…{x["tail"]}" | "{x["head"]}…"): listen to the tone',
            x["frame"] / fps,
            fix="If it sounds different: take the whole sentence from one take",
        )
    if not tcs:
        rep.add(area, "OK", "take-change", "No sentence runs over a take change")
    vp = voice or (ep / dec["voice"] if dec.get("voice") else None)
    if vp and Path(vp).is_file():
        r, vo = voice_levels(vp)
        js = level_jumps(r, vo, clips, fps)
        for x in js:
            rep.add(
                area,
                "CHECK",
                f"level:{x['a']}>{x['b']}",
                f"Level jump {x['db']:+.1f} dB at the cut {x['a']} > {x['b']}",
                x["frame"] / fps,
            )
        if not js:
            rep.add(area, "OK", "level", f"No level jump of {LEVEL_JUMP:.0f} dB or more between neighbouring pieces")
    else:
        rep.add(area, "NOTE", "level", "Voice file not found: level jumps not measured.")
    st = stutters(clips, heard, cw["fillers"], same)
    for x in st:
        rep.add(
            area,
            "CHECK",
            f"stutter:{x['id']}",
            f"{x['id']}: repeated or filler word heard ({', '.join(x['found'])}); a repeat is sometimes correct grammar",
            x["frame"] / fps,
            fix="Cut the stutter out if it is one",
        )
    if heard and not st:
        rep.add(
            area,
            "OK",
            "stutter",
            "No repeated word and no filler word heard (the transcriber does not hear everything)",
        )
    return fps


def main(argv=None):
    ap = argparse.ArgumentParser(description="Check a speaker cut before anything is built on it or shown.")
    ap.add_argument("decisions", help="edit decisions of the speaker cut (edit-decisions-vNNN.json)")
    ap.add_argument("--verification", help="default: cut-verification-vNNN.json next to the decisions")
    ap.add_argument("--islands", action="append", default=[], help="folder with <stem>-islands.json (more than once)")
    ap.add_argument("--voice", help="voice file of the cut (default: 'voice' in the decisions)")
    ap.add_argument("--episode", help="episode folder (default: the folder with project.json above the decisions)")
    ap.add_argument("--exceptions", help="default: <episode>/review/cut-check-exceptions.json")
    ap.add_argument("--report", help="default: <episode>/review/speaker-cut-check-vNNN.json")
    ap.add_argument("--pack", help="style pack folder (default: studio/brand, else packs/neutral)")
    a = ap.parse_args(argv)
    dec = Path(a.decisions)
    if not dec.is_file():
        ap.error(f"decisions not found: {dec}")
    ep = Path(a.episode) if a.episode else episode_of(dec)
    v = cl.version_of(dec)
    ver = Path(a.verification) if a.verification else dec.parent / f"cut-verification-{v}.json"
    dirs = [Path(x) for x in a.islands] or [dec.parent, ep / "brief", ep / "work"]
    pack = cl.load_pack(a.pack)
    exc = Path(a.exceptions) if a.exceptions else ep / "review" / "cut-check-exceptions.json"
    rep = cl.Report(cl.load_exceptions(exc))
    check(dec, ep, ver, dirs, Path(a.voice) if a.voice else None, pack, rep)
    print(f"Speaker cut check {ep.name}, cut {v}, style pack {'neutral' if pack.is_neutral else pack.dir.name}")
    rep.print(["Cut"])
    print("\nBy hand:")
    for line in cl.manual_list(MANUAL, pack, "cut"):
        print("  " + line)
    n = rep.count()
    print(f"\nResult: {n['ERROR']} ERROR, {n['CHECK']} CHECK, {n['OK']} OK, {n['NOTE']} NOTE")
    out = Path(a.report) if a.report else ep / "review" / f"speaker-cut-check-{v}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {"episode": ep.name, "cut": v, "decisions": dec.name, "counts": n, "findings": rep.items},
            ensure_ascii=False,
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Report: {out}")
    if n["ERROR"]:
        print("NOT PASSED: fix the errors first, then build on this cut.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
