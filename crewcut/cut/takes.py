"""Draft selects: which attempt of each script sentence goes into the cut, with the reasons.

The rules (each one was a real mistake in an episode; the agent still reads the list before building):
1. The last full attempt wins. People repeat a sentence until it sits.
2. Spoken instructions to the editor win over rule 1: "scratch that", "take the first version", "leave that out",
   "that part was good, keep it", "I'll just read on". The instruction itself never goes into the video.
3. What the speaker said differently from the script wins. The select keeps the spoken words (with the script's
   spelling where both agree) and the difference is listed.
4. A select starts and ends at an island edge. An attempt that starts or ends inside an island is marked: measure the
   dip there (`crewcut cut dips`) and read the edge (`crewcut cut probe`) before building.
5. A sentence without any full attempt goes on the pickup list: record exactly that sentence again.

Input: the script and the islands of each take (in recording order). Output: edit/selects-vNNN.json (a draft for the
agent to check) and review/takes-vNNN.json (every attempt with its verdict).
"""

from __future__ import annotations

import difflib
import re
from pathlib import Path

from .. import config
from .tokens import spelling, tokens

INSTRUCTIONS: dict[str, list[str]] = {
    "scratch": ["scratch that", "strike that", "let me do that again", "let me start again", "let me try that again",
                "once more", "one more time", "from the top", "noch mal", "nochmal", "noch einmal", "streich das",
                "das war nichts", "von vorne"],
    "first": ["take the first version", "the first version is fine", "the first version was better",
              "the first one was better", "use the first one", "take the first one", "die erste version passt",
              "die erste version war besser", "nimm die erste version", "nimm die erste", "der erste anlauf war besser",
              "die erste war besser"],
    "drop": ["take this part out", "take that part out", "leave that out", "leave this out", "cut this part",
             "cut that part", "drop that part", "i would not say that", "i wouldn't say that", "würde ich rausnehmen",
             "würde ich jetzt nicht sagen", "würde ich nicht sagen", "lass das weg", "das kommt raus",
             "streich den teil"],
    "keep": ["keep that", "keep that in", "leave that in", "that part was good", "we can keep that",
             "können wir drin lassen", "kann drin bleiben", "das können wir drin lassen", "der teil war gut"],
    "continue": ["i'll just read on", "i will just read on", "i'll read on", "moving on", "ich lese einfach weiter",
                 "ich lese weiter", "ich mach weiter"],
}
FULL_COVERAGE = 0.6       # share of the sentence's words an attempt needs to count as full (if it reaches the end)
MAX_GAP = 3               # unmatched words inside an attempt before it is cut off


# ---- script ------------------------------------------------------------------------------------------------------
def script_text(text: str) -> str:
    """The spoken part of a script file: stops at a line '---', drops headings, quote marks, [stage directions],
    markdown emphasis and HTML comments."""
    lines = []
    for line in text.splitlines():
        if line.strip() == "---":
            if lines:
                break
            continue
        if line.lstrip().startswith("#"):
            continue
        lines.append(line.lstrip("> ").strip())
    raw = " ".join(lines)
    raw = re.sub(r"<!--.*?-->", " ", raw)
    raw = re.sub(r"\*?\[[^\]]*\]\*?", " ", raw)
    raw = re.sub(r"[*_`]", "", raw)
    return " ".join(raw.split())


def sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


# ---- the stream of spoken words ----------------------------------------------------------------------------------
def stream(takes: list[tuple[str, list[dict]]], same: dict[str, str] | None = None) -> list[dict]:
    """All spoken words in recording order. Times inside an island are spread by characters (approximate)."""
    out = []
    for take, rows in takes:
        for ri, r in enumerate(sorted(rows, key=lambda r: r["start"])):
            raw = r.get("text", "").split()
            pairs = [(w, tokens(w, same)) for w in raw]
            items = [(w, t) for w, ts in pairs for t in ts] if pairs else []
            if not items:
                continue
            total = sum(len(t) + 1 for _, t in items)
            pos = 0
            a, b = float(r["start"]), float(r["end"])
            for k, (w, t) in enumerate(items):
                t0 = a + (b - a) * pos / total
                pos += len(t) + 1
                out.append({"w": w, "n": t, "take": take, "row": ri, "row_start": a, "row_end": b,
                            "first": k == 0, "last": k == len(items) - 1,
                            "t0": round(t0, 2), "t1": round(a + (b - a) * pos / total, 2)})
    return out


def _dedupe_raw(st: list[dict], i: int, j: int) -> list[str]:
    """Raw words of stream[i..j] (a hyphenated word gives several tokens but appears once)."""
    out, last = [], None
    for t in st[i:j + 1]:
        key = (t["take"], t["row"], t["w"])
        if key != last:
            out.append(t["w"])
        last = key
    return out


# ---- attempts ----------------------------------------------------------------------------------------------------
def _candidates(sent: list[str], st: list[dict]) -> list[int]:
    need = min(2, len(sent) - 1)
    out = []
    for i, t in enumerate(st):
        if t["n"] != sent[0]:
            continue
        ahead = [x["n"] for x in st[i + 1:i + 6] if x["take"] == t["take"]]
        if sum(1 for w in sent[1:4] if w in ahead) >= need:
            out.append(i)
    return out


def _align(sent: list[str], st: list[dict], i: int, j: int) -> dict | None:
    """Match the sentence against stream[i:j]. Returns the attempt span and how well it matches."""
    window = [t["n"] for t in st[i:j]]
    blocks = [b for b in difflib.SequenceMatcher(a=sent, b=window, autojunk=False).get_matching_blocks() if b.size]
    if not blocks:
        return None
    kept, end_b = [], None
    for b in blocks:
        if end_b is not None and b.b - end_b > MAX_GAP:
            break
        kept.append(b)
        end_b = b.b + b.size
    matched = sum(b.size for b in kept)
    last_a = max(b.a + b.size - 1 for b in kept)
    last_b = max(b.b + b.size - 1 for b in kept)
    m = len(sent)
    reached = last_a >= m - 1 - (1 if m >= 6 else 0)
    return {"start": i, "end": i + last_b, "matched": matched, "coverage": round(matched / m, 2), "reached_end": reached}


def attempts(sent_tokens: list[list[str]], st: list[dict]) -> list[list[dict]]:
    """Every attempt of every sentence: [{start, end (stream positions), coverage, verdict}]."""
    out = []
    for sent in sent_tokens:
        found = []
        if not sent:
            out.append(found)
            continue
        cands = _candidates(sent, st)
        for k, i in enumerate(cands):
            limit = min(len(st), i + int(len(sent) * 1.4) + 4)
            if k + 1 < len(cands):
                limit = min(limit, cands[k + 1])
            j = i
            while j < limit and st[j]["take"] == st[i]["take"]:
                j += 1
            a = _align(sent, st, i, j)
            if a is None or a["matched"] < min(2, len(sent)):
                continue
            if a["reached_end"] and a["coverage"] >= FULL_COVERAGE:
                a["verdict"] = "full"
            elif a["coverage"] >= 0.5 or (k + 1 < len(cands) and a["matched"] >= 2):
                a["verdict"] = "broken"
            else:
                continue
            found.append(a)
        out.append(found)
    return out


# ---- spoken instructions -----------------------------------------------------------------------------------------
def instruction_phrases() -> dict[str, list[list[str]]]:
    extra = config.load("speech").get("instructions") or {}
    out = {}
    for kind, phrases in INSTRUCTIONS.items():
        allp = list(phrases) + [str(p) for p in extra.get(kind, []) or []]
        out[kind] = sorted({tuple(tokens(p)) for p in allp if tokens(p)}, key=len, reverse=True)
    return {k: [list(p) for p in v] for k, v in out.items()}


def find_instructions(st: list[dict], covered: set[int], phrases: dict[str, list[list[str]]] | None = None,
                      ) -> list[dict]:
    """Instruction phrases in the parts of the stream that belong to no attempt."""
    phrases = phrases or instruction_phrases()
    out, i = [], 0
    while i < len(st):
        hit = None
        if i not in covered:
            for kind, plist in phrases.items():
                for p in plist:
                    seg = st[i:i + len(p)]
                    if [t["n"] for t in seg] == p and all(k not in covered for k in range(i, i + len(p))) and len(
                            {t["take"] for t in seg}) == 1:
                        if hit is None or len(p) > len(hit[1]):
                            hit = (kind, p)
        if hit:
            kind, p = hit
            out.append({"kind": kind, "pos": i, "end": i + len(p) - 1, "take": st[i]["take"], "at": st[i]["t0"],
                        "text": " ".join(_dedupe_raw(st, i, i + len(p) - 1))})
            i += len(p)
        else:
            i += 1
    return out


# ---- choosing ----------------------------------------------------------------------------------------------------
def _merge_text(script_sentence: str, st: list[dict], i: int, j: int, same: dict[str, str]) -> tuple[str, list[str]]:
    """Spoken words of the attempt, with the script's spelling where both agree. Returns (text, differences)."""
    s_raw = script_sentence.split()
    s_tok = [(w, tokens(w, same)) for w in s_raw]
    h_raw = _dedupe_raw(st, i, j)
    h_tok = [(w, tokens(w, same)) for w in h_raw]
    a = [" ".join(ts) for _, ts in s_tok]
    b = [" ".join(ts) for _, ts in h_tok]
    out, diffs = [], []
    for op, a1, a2, b1, b2 in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes():
        if op == "equal":
            out += s_raw[a1:a2]
        else:
            out += h_raw[b1:b2]
            said = " ".join(h_raw[b1:b2]) or "(left out)"
            diffs.append(f"script: {' '.join(s_raw[a1:a2]) or '(nothing)'} -> said: {said}")
    text = " ".join(out)
    if text and text[-1] not in ".!?" and script_sentence[-1:] in ".!?":
        text += script_sentence[-1]
    return text, diffs


def _edge(st: list[dict], i: int, j: int) -> dict:
    a, b = st[i], st[j]
    return {"start": a["row_start"] if a["first"] else a["t0"], "end": b["row_end"] if b["last"] else b["t1"],
            "check_start": not a["first"], "check_end": not b["last"]}


def choose(script: str, takes: list[tuple[str, list[dict]]]) -> dict:
    """Pick one attempt per sentence. takes: [(take id, island rows)] in recording order."""
    same = spelling()
    sents = sentences(script_text(script))
    st = stream(takes, same)
    sent_tok = [tokens(s, same) for s in sents]
    found = attempts(sent_tok, st)
    covered = {p for att in found for a in att for p in range(a["start"], a["end"] + 1)}
    instr = find_instructions(st, covered)
    flat = sorted(((a["end"], si, ai) for si, att in enumerate(found) for ai, a in enumerate(att)))
    dropped: dict[int, dict] = {}
    pinned: dict[int, int] = {}
    first: dict[int, dict] = {}
    for ins in instr:
        before = [(e, si, ai) for e, si, ai in flat if e < ins["pos"] and st[e]["take"] == ins["take"]]
        if not before:
            ins["applied_to"] = None
            continue
        _, si, ai = before[-1]
        ins["applied_to"] = {"sentence": si + 1, "attempt": ai + 1}
        a = found[si][ai]
        if ins["kind"] == "scratch":
            a["scratched"] = True
        elif ins["kind"] == "drop":
            dropped[si] = ins
        elif ins["kind"] == "keep":
            pinned[si] = ai
        elif ins["kind"] == "first":
            first[si] = ins
    report, selects, pickups = [], [], []
    for si, sent in enumerate(sents):
        att = found[si]
        full = [k for k, a in enumerate(att) if a["verdict"] == "full" and not a.get("scratched")]
        chosen, why = None, ""
        if si in dropped:
            why = f"left out: you said \"{dropped[si]['text']}\" at {dropped[si]['at']:.1f} s"
        elif si in pinned:
            chosen, why = pinned[si], "you said to keep this attempt"
        elif si in first and full:
            chosen, why = full[0], f"first full attempt: you said \"{first[si]['text']}\""
        elif full:
            chosen, why = full[-1], "last full attempt"
        else:
            pickups.append({"sentence": si + 1, "text": sent,
                            "why": "no full attempt" if att else "never said"})
            why = "no full attempt: record this sentence again (pickup)"
        rows = []
        for k, a in enumerate(att):
            e = _edge(st, a["start"], a["end"])
            verdict = "scratched" if a.get("scratched") else a["verdict"]
            rows.append({"take": st[a["start"]]["take"], "start": e["start"], "end": e["end"], "verdict": verdict,
                         "coverage": a["coverage"], "heard": " ".join(_dedupe_raw(st, a["start"], a["end"])),
                         "chosen": k == chosen})
        entry = {"n": si + 1, "script": sent, "attempts": rows, "chosen": None if chosen is None else chosen + 1,
                 "why": why, "differences": []}
        if chosen is not None:
            a = att[chosen]
            text, diffs = _merge_text(sent, st, a["start"], a["end"], same)
            e = _edge(st, a["start"], a["end"])
            entry["differences"] = diffs
            sel = {"id": f"s{si + 1:02d}", "take": st[a["start"]]["take"], "start": round(e["start"], 2),
                   "end": round(e["end"], 2), "text": text}
            if diffs:
                sel["script"] = sent
            sel["_span"] = (a["start"], a["end"])
            sel["_rows"] = (st[a["start"]]["row"], st[a["end"]]["row"])
            sel["_check"] = (e["check_start"], e["check_end"])
            selects.append(sel)
        report.append(entry)
    return {"sentences": report, "selects": merge_adjacent(selects), "instructions": [
        {k: v for k, v in i.items() if k not in ("pos", "end")} for i in instr], "pickups": pickups}


def merge_adjacent(selects: list[dict]) -> list[dict]:
    """Sentences spoken in one go (the next one starts right after the last word, in the same or the next island)
    stay one select: no cut, no edge to check. An island without text between them keeps them apart."""
    out: list[dict] = []
    for sel in selects:
        prev = out[-1] if out else None
        if (prev and prev["take"] == sel["take"] and prev["_span"][1] + 1 == sel["_span"][0]
                and sel["_rows"][0] - prev["_rows"][1] <= 1):
            prev["end"] = sel["end"]
            prev["text"] = f"{prev['text']} {sel['text']}"
            prev["id"] = f"{prev['id']}-{sel['id'][1:]}" if "-" not in prev["id"] else (
                prev["id"].rsplit("-", 1)[0] + "-" + sel["id"][1:])
            if "script" in prev or "script" in sel:
                prev["script"] = f"{prev.get('script', '')} {sel.get('script', '')}".strip()
            prev["_span"] = (prev["_span"][0], sel["_span"][1])
            prev["_rows"] = (prev["_rows"][0], sel["_rows"][1])
            prev["_check"] = (prev["_check"][0], sel["_check"][1])
            continue
        out.append(dict(sel))
    for sel in out:
        checks = [name for name, flag in zip(("start", "end"), sel.pop("_check"), strict=True) if flag]
        sel.pop("_span")
        sel.pop("_rows")
        if checks:
            sel["check"] = checks
    return out


def take_ids(n: int) -> list[str]:
    out = []
    for i in range(n):
        s, k = "", i
        while True:
            s = chr(ord("A") + k % 26) + s
            k = k // 26 - 1
            if k < 0:
                break
        out.append(s)
    return out


def describe(result: dict) -> str:
    lines = []
    for e in result["sentences"]:
        lines.append(f"S{e['n']:02d}  {e['script']}")
        for k, a in enumerate(e["attempts"], 1):
            mark = "  <- " + e["why"] if a["chosen"] else ""
            lines.append(f"     {k}. {a['take']} {a['start']:8.2f}-{a['end']:8.2f}  {a['verdict']:<9} "
                         f"«{a['heard'][:70]}»{mark}")
        if e["chosen"] is None:
            lines.append(f"     -> {e['why']}")
        for d in e["differences"]:
            lines.append(f"     differs: {d}")
    if result["instructions"]:
        lines.append("Spoken instructions (never in the video):")
        for i in result["instructions"]:
            to = i.get("applied_to")
            target = f"applied to S{to['sentence']:02d} attempt {to['attempt']}" if to else "nothing before it"
            lines.append(f"  {i['take']} {i['at']:8.2f}  {i['kind']:<8} «{i['text']}»  {target}")
    if result["pickups"]:
        lines.append("Pickup list (record again):")
        lines += [f"  S{p['sentence']:02d}  {p['text']}" for p in result["pickups"]]
    edge = [s for s in result["selects"] if s.get("check")]
    if edge:
        lines.append("Edges inside an island (measure with `crewcut cut dips`, read with `crewcut cut probe`): "
                     + ", ".join(f"{s['id']} {'/'.join(s['check'])}" for s in edge))
    return "\n".join(lines)


def selects_file(version: str, sources: list[str], result: dict, script_path: str) -> dict:
    ids = take_ids(len(sources))
    return {
        "version": version,
        "note": f"Draft from crewcut cut takes ({script_path}). Check every select before building.",
        "takes": {t: {"source": s, "face": [0.5, 0.4], "lock": []} for t, s in zip(ids, sources, strict=True)},
        "selects": result["selects"],
    }


def script_path_label(p: Path, ep_dir: Path) -> str:
    try:
        return p.resolve().relative_to(ep_dir.resolve()).as_posix()
    except ValueError:
        return p.name
