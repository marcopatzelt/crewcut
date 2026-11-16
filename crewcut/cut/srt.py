"""SRT subtitles for a finished video from its speaker cut: text from the selects, times from the cut decisions.

The text comes from the selects (the right spelling, not the recognizer's). The times hold for every video built on
this speaker cut: inserts on top do not change the timeline. Per select: blocks of at most 84 characters, preferably
split at punctuation, at most 2 lines of 42 characters. With the words of the finished voice track (--words), block
borders sit on word times (more exact); without, time is spread by character count.

Afterwards ALWAYS check three blocks (start, middle, end) against the sound of the finished video.
"""

from __future__ import annotations

import re

from .tokens import tokens

MAX_BLOCK, MAX_LINE = 84, 42


def groups(manifest: dict) -> list[dict]:
    """Clips of one select (id, id_2, ...) belong together: [{"id", "start", "end", "text"}] in seconds."""
    fps = manifest["fps"]
    out: list[dict] = []
    for c in manifest["clips"]:
        base = re.sub(r"_\d+$", "", c["id"])
        a, b = c["timeline_in_frame"] / fps, c["timeline_out_frame"] / fps
        if out and out[-1]["id"] == base and out[-1]["text"] == c["expected_text"]:
            out[-1]["end"] = b
        else:
            out.append({"id": base, "start": a, "end": b, "text": c["expected_text"]})
    return out


def blocks(text: str, max_chars: int = MAX_BLOCK) -> list[str]:
    """Text in blocks of at most max_chars, preferably at punctuation."""
    parts, rest = [], text.strip()
    while len(rest) > max_chars:
        k = max(rest.rfind(z, 0, max_chars) for z in (". ", ", ", "? ", "! ", ": ", "; "))
        if k < max_chars * 0.4:
            k = rest.rfind(" ", 0, max_chars) - 1
        if k < 0:
            k = max_chars - 1
        parts.append(rest[:k + 1].strip())
        rest = rest[k + 1:].strip()
    return parts + ([rest] if rest else [])


def lines(t: str, max_chars: int = MAX_LINE) -> str:
    """One or two lines, broken at the space nearest the middle."""
    if len(t) <= max_chars or " " not in t:
        return t
    k = min((i for i, ch in enumerate(t) if ch == " "), key=lambda i: abs(i - len(t) / 2))
    return t[:k] + "\n" + t[k + 1:]


def stamp(s: float) -> str:
    ms = int(round(max(0.0, s) * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def cues(manifest: dict, words: list[dict] | None = None) -> list[tuple[float, float, str]]:
    out = []
    for g in groups(manifest):
        a, b, text = g["start"], g["end"], g["text"]
        parts = blocks(text)
        if not parts:
            continue
        n = sum(len(x) for x in parts)
        pos, end = a + 0.05, b - 0.05
        near = [w for w in (words or []) if a - 0.1 <= w["s"] <= b + 0.1]
        for i, x in enumerate(parts):
            e = pos + (end - a - 0.05) * len(x) / n if i < len(parts) - 1 else end
            if near and i < len(parts) - 1:
                # put the border on the start of the word the next block begins with
                first = (tokens(parts[i + 1].split()[0]) or [""])[0]
                hits = [w["s"] for w in near if (tokens(w["w"]) or [""])[0] == first and abs(w["s"] - e) < 1.5]
                if hits:
                    e = min(hits, key=lambda s: abs(s - e)) - 0.04
            e = max(pos + 0.5, e)
            out.append((pos, e, x))
            pos = e + 0.02
    return out


def render(cue_list: list[tuple[float, float, str]]) -> str:
    return "".join(f"{i}\n{stamp(a)} --> {stamp(b)}\n{lines(x)}\n\n" for i, (a, b, x) in enumerate(cue_list, 1))
