"""Check a built speaker cut against its expected script, clip by clip.

Each clip is read on its own: a transcript of the whole cut can hide a repeated sentence start; single clips cannot.
The joined words are compared with `expected_script` from the cut plan and every missing, extra or changed word is
listed. Recognizers also invent words in silence, so every finding needs a listening check.

Also checked, each one fails the check (exit 2):
  - edges: the first and last word of every select must be the expected first and last word. Catches a clipped word
    end and a leaked next word.
  - joins (`bad_joins`): the pause at every cut, measured on the voice track against its own noise floor, must be
    join_min..join_max (0.17-0.45 s). A natural sentence pause is about 0.25 s; 0.09 s sounds chopped.
  - channels: left and right voice level may differ by at most 10 dB (camera microphone on one side).
Report: work/cut-verification-vNNN.json, next to the decisions (the cut-check skill reads it there).
"""

from __future__ import annotations

import difflib
import json
from pathlib import Path

from . import audio
from .common import CutError, cut_settings, inside, read_json, rel, write_replace
from .tokens import spelling, tokens


def diff_issues(expected: str, heard: str, same: dict[str, str] | None = None) -> list[dict]:
    a, b = tokens(expected, same), tokens(heard, same)
    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes():
        # Same letters, other spacing or hyphens ("Free LLM API" / "free-llm-api"): not a cut error.
        if op == "replace" and "".join(a[i1:i2]) == "".join(b[j1:j2]):
            continue
        if op != "equal":
            out.append({"type": op, "expected": " ".join(a[i1:i2]), "heard": " ".join(b[j1:j2]),
                        "context": " ".join(a[max(0, i1 - 4):i2 + 4])})
    return out


def edge_issues(clips: list[dict], heard: list[dict], same: dict[str, str] | None = None) -> list[dict]:
    """Group consecutive clips of one select (same expected_text) and compare the first and last words."""
    groups: list[dict] = []
    for c, h in zip(clips, heard, strict=False):
        if groups and groups[-1]["text"] == c["expected_text"]:
            groups[-1]["heard"] += " " + h["text"]
            groups[-1]["ids"].append(c["id"])
        else:
            groups.append({"text": c["expected_text"], "heard": h["text"], "ids": [c["id"]]})
    issues = []
    for g in groups:
        e, h = tokens(g["text"], same), tokens(g["heard"], same)
        if not e or not h:
            continue
        for pos, where in ((0, "start"), (-1, "end")):
            if e[pos] != h[pos]:
                issues.append({"type": "edge", "where": where, "select": g["ids"][0 if pos == 0 else -1],
                               "expected": e[pos], "heard": h[pos],
                               "fix": "read the edge with `crewcut cut probe` and move it"})
    return issues


def level_track(x, rate: int = 16000):
    """Level in dB every 10 ms, smoothed over 20 ms (as measured for the join rule)."""
    import numpy as np
    win = max(1, int(rate * 0.02))
    hop = max(1, int(rate * 0.01))
    power = np.convolve(np.square(x.astype(np.float64)), np.ones(win) / win, "same")[::hop]
    return 20 * np.log10(np.sqrt(power) + 1e-9)


def join_pauses(rms, clips: list[dict], fps: int, reach: float = 0.4) -> list[dict]:
    """The longest quiet run within `reach` seconds of every cut, relative to the voice's own noise floor."""
    import numpy as np
    thr = float(np.percentile(rms, 8)) + 10 if len(rms) else 0.0
    n = int(reach * 100)
    out = []
    for a, b in zip(clips, clips[1:], strict=False):
        t = b["timeline_in_frame"] / fps
        i = int(t * 100)
        best = cur = 0
        for quiet in rms[max(0, i - n):i + n] < thr:
            cur = cur + 1 if quiet else 0
            best = max(best, cur)
        out.append({"at": round(t, 2), "from": a["id"], "to": b["id"], "pause": best / 100})
    return out


def bad(joins: list[dict], lo: float, hi: float) -> list[dict]:
    return [j for j in joins if not lo <= j["pause"] <= hi]


def status(issues: list, edges: list, bad_joins: list, one_sided: bool) -> str:
    if edges or bad_joins or one_sided:
        return "review_needed"
    return "words_to_review" if issues else "match"


def report_path(ep_dir: Path, version: str) -> Path:
    return ep_dir / "work" / f"cut-verification-{version}.json"


def verify(decisions_path: Path, ep_dir: Path, engine, log=print) -> dict:
    """Read every clip, measure the joins and channels, write the report. engine: transcribe.Engine."""
    from .transcribe import SAMPLE_RATE, load_audio
    manifest = read_json(decisions_path)
    plan = read_json(inside(ep_dir, manifest["plan"]))
    expected = plan.get("expected_script")
    if not expected:
        raise CutError("expected_script is missing in the cut plan")
    same = spelling()
    heard = []
    for c in manifest["clips"]:
        text = engine.text(load_audio(inside(ep_dir, c["file"])))
        heard.append({"id": c["id"], "text": text})
        log(f"{c['id']:18s} {text}")
    issues = diff_issues(expected, " ".join(h["text"] for h in heard), same)
    edges = edge_issues(manifest["clips"], heard, same)
    voice = inside(ep_dir, manifest["voice"])
    joins = join_pauses(level_track(load_audio(voice), SAMPLE_RATE), manifest["clips"], int(manifest["fps"]))
    s = cut_settings(plan)
    bad_joins = bad(joins, float(s["join_min"]), float(s["join_max"]))
    levels = audio.channel_levels(voice)
    one_sided = len(levels) == 2 and abs(levels[0] - levels[1]) > 10
    report = {"decisions": rel(ep_dir, decisions_path), "selects": heard, "issues": issues, "edge_issues": edges,
              "joins": joins, "bad_joins": bad_joins, "join_range": [s["join_min"], s["join_max"]],
              "channel_levels_db": levels, "status": status(issues, edges, bad_joins, one_sided),
              "engine": engine.describe()}
    out = report_path(ep_dir, manifest["version"])
    write_replace(out, json.dumps(report, ensure_ascii=False, indent=1) + "\n")
    report["report"] = rel(ep_dir, out)
    return report


def describe(r: dict) -> str:
    lines = [f"status: {r['status']}"]
    for i in r["issues"]:
        lines.append(f"  {i['type']}: expected «{i['expected']}» heard «{i['heard']}» "
                     f"(…{i['context']}…)")
    for e in r["edge_issues"]:
        lines.append(f"  edge: {e['select']} {e['where']}: expected «{e['expected']}» heard "
                     f"«{e['heard']}»")
    lo, hi = r["join_range"]
    for j in r["bad_joins"]:
        fix = ("give the select before a tail (about 0.24) or move its end into the silence" if j["pause"] < lo
               else "start the next select at the real start of speech (measure with dips)")
        lines.append(f"  bad join at {j['at']} s ({j['from']} -> {j['to']}): pause {j['pause']:.2f} s, "
                     f"allowed {lo}-{hi} s: {fix}")
    lv = r["channel_levels_db"]
    if len(lv) == 2 and abs(lv[0] - lv[1]) > 10:
        lines.append(f"  the voice is one-sided: channels {lv} dB")
    lines.append(f"report: {r['report']}")
    if r["status"] == "review_needed":
        lines.append("CHECK FAILED: fix edges, joins or channels, then build a new version.")
    return "\n".join(lines)
