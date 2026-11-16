"""Find doubled sentence starts INSIDE a chosen select, before the cut is built.

A real preview had "so I built ... and so I built": the select began with a broken attempt (0.85 s "so I built",
pause, then the whole sentence). Recognition over the whole cut and `verify` did NOT report it, because recognizers
leave out repeated sentence starts. So: every short speech piece (under 2 s) that is followed by another piece inside
the same select is read on its own, and its first two words are compared with the next piece.

Exit 2 when a doubled start is found. Fix: let the select begin at the second piece (the line names the time).
Needs the islands of each take (`crewcut cut islands`). Report: review/doubles-vNNN.json.
"""

from __future__ import annotations

from collections.abc import Callable

from .tokens import tokens

SHORT = 2.0       # a piece shorter than this may be a broken first attempt
NEXT_READ = 4.0   # read at most this much of the following piece
INSIDE = 0.05


def candidates(cfg: dict, islands_by_take: dict[str, list[dict]], short: float = SHORT) -> list[dict]:
    """Short pieces inside a select that another piece of the same select follows."""
    out = []
    for s in cfg["selects"]:
        rows = [r for r in islands_by_take.get(s["take"], [])
                if r["end"] > s["start"] + INSIDE and r["start"] < s["end"] - INSIDE]
        rows.sort(key=lambda r: r["start"])
        for k, r in enumerate(rows[:-1]):
            if r["end"] - r["start"] < short:
                nxt = rows[k + 1]
                out.append({"select": s["id"], "take": s["take"], "a": round(max(r["start"], s["start"]), 2),
                            "b": r["end"], "c": nxt["start"], "d": round(min(nxt["end"], s["end"]), 2)})
    return out


def first_words(text: str, n: int = 2) -> list[str]:
    return tokens(text)[:n]


def is_double(piece: str, following: str) -> bool:
    w = first_words(piece)
    return bool(w) and w == first_words(following)


def check(cfg: dict, islands_by_take: dict[str, list[dict]], read: Callable[[str, float, float], str]) -> list[dict]:
    """read(take, start, end) -> text of that range read on its own."""
    found = []
    for c in candidates(cfg, islands_by_take):
        x = read(c["take"], c["a"], c["b"])
        y = read(c["take"], c["c"], min(c["d"], c["c"] + NEXT_READ))
        dbl = is_double(x, y)
        found.append({**c, "piece": x, "following": y, "double": dbl,
                      "fix": f"begin the select {c['select']} at {c['c']:.2f}" if dbl else None})
    return found


def in_words(words: list[dict], start: float, end: float, short: float = SHORT, min_pause: float = 0.15,
             ) -> list[dict]:
    """Fast check on a words list: a short run of words, a pause, and the same first two words again.
    Whole-file recognition often drops the repeat, so an empty result proves little."""
    ws = [w for w in words if start - INSIDE <= w["s"] and w["e"] <= end + INSIDE]
    pieces: list[list[dict]] = []
    for w in ws:
        if pieces and w["s"] - pieces[-1][-1]["e"] < min_pause:
            pieces[-1].append(w)
        else:
            pieces.append([w])
    out = []
    for p, q in zip(pieces, pieces[1:], strict=False):
        if p[-1]["e"] - p[0]["s"] < short:
            x, y = " ".join(w["w"] for w in p), " ".join(w["w"] for w in q)
            if is_double(x, y):
                out.append({"a": p[0]["s"], "b": p[-1]["e"], "c": q[0]["s"], "piece": x, "following": y,
                            "double": True, "fix": f"begin the select at {q[0]['s']:.2f}"})
    return out


def describe(rows: list[dict]) -> str:
    lines = []
    for r in rows:
        mark = "DOUBLE " if r["double"] else "ok     "
        sel = r.get("select", "")
        lines.append(f"{mark} {sel:8} {r['a']:.2f}-{r['b']:.2f} «{r['piece']}» | {r['c']:.2f} "
                     f"«{r['following'][:70]}»" + (f"   -> {r['fix']}" if r["double"] else ""))
    n = sum(1 for r in rows if r["double"])
    lines.append(f"{len(rows)} short pieces checked, {n} doubled starts")
    return "\n".join(lines)
