"""The web teleprompter: the approved script on any phone in the same network, opened from a QR code.

The script is shown as numbered speaking blocks (one paragraph each; several blank lines start a new section). Every
screen (phones and the desktop window on the prompter glass) follows one shared timeline: an anchor (block and offset
inside it), the server time the anchor was set, and the speed. A screen computes where the text is now from that
timeline, so no screen reports its scroll position back and none can undo another screen's command. Every write gets
a newer sequence number, and screens apply only newer states. Jumps, repeats, play and pause are written to the
episode's take log, brief/prompter-log-<UTC date>.jsonl, so the editor can line takes up with the camera files.

A cue sheet (crewcut.cuesheet) is shown in pages: one page per part (opening, each unit, payoff, close), one block per
fixed line and per bullet. Previous, Next and Repeat move by page, and every command that lands at the start of a page
counts a new take of that page; the count is in the shared state and in every line of the take log. Playing stops at
the end of every page (the last block of a page is an end on the timeline, like the end of the script): the speaker
talks freely on a unit page, and Next starts the next one, paused until Play."""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import math
import os
import re
import time
from datetime import UTC, datetime
from pathlib import Path

from . import config, cuesheet, db, episodes, paths

DEFAULT_CONTROL = {"playing": False, "speed": 1.0, "position": 0.0, "mirror": False, "size": 1.0, "mode": "full",
                   "guide": 33.0, "block": 0, "offset": 0.0, "at": 0.0, "seq": 0, "by": "", "cue": 0,
                   "takes": {}}
# The reading pace at speed 1.0, in characters per second. 17 keeps the pace the desktop prompter had at speed 1.0
# and text size 1.0 (about 0.55 lines per second at 30 characters per line), now the same on every screen.
CHARS_PER_SECOND = 17.0
PAUSE_CHARS = 8           # a breath after each block, counted as characters of the timeline
SECTION_PAUSE_CHARS = 24  # a longer breath before a new section
JUMP_HOLD_MS = 1500.0     # after a jump while playing, the text waits this long before it moves on
JUMPS = ("jump", "next", "prev", "repeat", "start")
_CLIENT = re.compile(r"[A-Za-z0-9_-]{1,64}")


def lan_host() -> str:
    # A stable studio address (for example Tailscale) takes precedence over
    # the desktop's automatically detected Wi-Fi address.
    return config.get("crewcut", "server.prompter_host") or os.environ.get("CREWCUT_LAN_HOST") or "localhost"


def url_for(episode: str) -> str:
    token = episodes.read(episode)["prompter_token"]
    port = int(os.environ.get("CREWCUT_PUBLIC_PROMPTER_PORT") or os.environ.get("CREWCUT_PROMPTER_PORT") or
               config.get("crewcut", "server.prompter_port", 4748))
    return f"http://{lan_host()}:{port}/p/{token}"


def qr_svg(text: str) -> str:
    import qrcode
    import qrcode.image.svg
    img = qrcode.make(text, image_factory=qrcode.image.svg.SvgPathImage, box_size=8, border=2)
    return img.to_string(encoding="unicode")


def _sheet_order(p: Path) -> tuple:
    """Cue sheets by version number; the plain name before a suffixed one of the same number."""
    m = cuesheet.NAME.match(p.name)
    return (int(m["n"]), not m["rest"], p.name) if m else (-1, False, p.name)


def script_file(episode: str) -> Path | None:
    """The approved script if there is one, else the selected recording script, else the newest cue sheet
    (brief/CUES-vNNN.md or brief/DREHZETTEL-vNNN.md, the script format), else the newest script draft."""
    d = paths.episode_dir(episode)
    with db.conn() as c:
        r = c.execute("SELECT file FROM cards WHERE episode = ? AND kind = 'script' AND status = 'accepted' "
                      "ORDER BY id DESC LIMIT 1", (episode,)).fetchone()
    if r and r["file"]:
        p = paths.inside(d, r["file"])
        if p.is_file():
            return p
    selected = episodes.read(episode).get("recording_script")
    if selected:
        selected_path = paths.inside(d, selected["file"])
        if not selected_path.is_file():
            raise FileNotFoundError("The selected recording script is missing. Select another script explicitly.")
        return selected_path
    sheets = [p for p in (d / "brief").glob("*.md") if cuesheet.is_name(p.name) and p.is_file()]
    if sheets:
        return max(sheets, key=_sheet_order)
    drafts = sorted((d / "brief").glob("SCRIPT-v*.md"))
    return drafts[-1] if drafts else None


def select_script(episode: str, relative: str, partial: bool = False) -> dict:
    root = paths.episode_dir(episode)
    selected = paths.inside(root, relative)
    if selected.suffix.lower() not in (".md", ".txt") or not selected.is_file():
        raise ValueError("Select an existing Markdown or text script inside this episode.")
    with db.conn() as connection:
        approved = connection.execute("SELECT file FROM cards WHERE episode = ? AND kind = 'script' "
                                      "AND status = 'accepted' ORDER BY id DESC LIMIT 1", (episode,)).fetchone()
    if approved and approved["file"] and paths.inside(root, approved["file"]) != selected:
        raise ValueError("Another script is approved. Request a new script review before replacing it.")
    project = episodes.read(episode)
    project["recording_script"] = {"file": selected.relative_to(root).as_posix(), "partial": partial}
    episodes.write(episode, project)
    return project["recording_script"]


def _points(par: str, n: int = 8) -> list[str]:
    bold = re.findall(r"\*\*(.+?)\*\*", par)
    if bold:
        return bold[:3]
    words = re.sub(r"[*_`#>]", "", par).split()
    return [" ".join(words[:n]) + (" …" if len(words) > n else "")]


def parse_script(text: str) -> list[dict]:
    """Numbered speaking blocks for the teleprompter: one block per paragraph, a new section after two or more blank
    lines or at a heading. Everything after the first line that is only `---` is notes for the edit, and so is a notes
    section ("Bildideen:", "Shots:") that slipped above it (crewcut.spoken.prompter_text)."""
    from . import spoken
    m = re.search(r"(?m)^---\s*$", text)
    if not m or text[:m.start()].strip():
        text = spoken.prompter_text(text)
    paragraphs: list[tuple[int, str]] = []  # (blank lines before it, text)
    lines: list[str] = []
    blank = 0
    for line in text.splitlines() + [""]:
        if line.strip():
            lines.append(line)
            continue
        if lines:
            paragraphs.append((blank, "\n".join(lines).strip()))
            lines, blank = [], 0
        blank += 1
    blocks: list[dict] = []
    section = 1
    for blank_before, par in paragraphs:
        if par.startswith("<!--"):
            continue
        if blocks and (blank_before >= 2 or par.startswith("#")) and blocks[-1]["section"] == section:
            section += 1
        if par.startswith("#"):
            line, _, par = par.partition("\n")
            heading = line.lstrip("#").strip()
            blocks.append({"text": heading, "points": [heading], "heading": True, "section": section})
            if not par.strip():
                continue
        clean = re.sub(r"[*_`>]", "", par)
        clean = re.sub(r"^\s*-\s+", "", clean, flags=re.M)
        blocks.append({"text": " ".join(clean.split()), "points": _points(par), "section": section})
    return _finish(blocks)


def _finish(blocks: list[dict]) -> list[dict]:
    """Number the spoken blocks (headings have no number) and give each block its length on the shared timeline: its
    characters plus a breath, a longer one before a new section."""
    n = 0
    for i, b in enumerate(blocks):
        if b.get("heading"):
            b["n"] = None
        else:
            n += 1
            b["n"] = n
        following = blocks[i + 1] if i + 1 < len(blocks) else None
        pause = SECTION_PAUSE_CHARS if following and following["section"] != b["section"] else PAUSE_CHARS
        b["weight"] = max(1, len(b["text"])) + pause
    return blocks


def reading_blocks(p: Path) -> list[dict]:
    """Optional paragraph-only layout, tied to the exact script and its words."""
    text = p.read_text(encoding="utf-8")
    blocks = parse_script(text)
    layout = p.with_suffix(".prompter.json")
    if layout.is_symlink() or not layout.is_file() or layout.stat().st_size > 1_000_000:
        return blocks
    try:
        saved = json.loads(layout.read_text(encoding="utf-8"))
        paragraphs = saved["paragraphs"]
        if saved["source_sha256"] != hashlib.sha256(text.encode()).hexdigest():
            return blocks
        if not isinstance(paragraphs, list) or not paragraphs or not all(isinstance(s, str) and s.strip() for s in paragraphs):
            return blocks
        original = " ".join(b["text"] for b in blocks).split()
        if " ".join(paragraphs).split() != original:
            return blocks
        # each layout paragraph keeps the section of the script paragraph its first word comes from
        sections = [b["section"] for b in blocks for _ in b["text"].split()]
        out, word = [], 0
        for s in paragraphs:
            out.append({"text": s, "points": _points(s), "section": sections[min(word, len(sections) - 1)]})
            word += len(s.split())
        return _finish(out)
    except (ValueError, KeyError, TypeError, OSError):
        return blocks


BIG_ROLES = ("hook", "punch")  # with the opening's first line: said word for word in the full text size


def cue_sheet_blocks(text: str) -> dict:
    """A cue sheet as speaking blocks in pages: one page per part, one block per fixed line and per bullet, in order.

    Each block has `kind` (fixed or bullet), `role` (fixed: hook, punch, ask, bridge, line1, …; bullet: its tag, "" if
    none), `page` (the part: "opening", "unit 1", …, "payoff", "close"), `unit` (the unit's number or None),
    `picture`, `question` (a bullet's leading question), `groups` (a bullet's cue word groups), `big` (hook, punch and
    the opening's first line), `text` (fixed: the spoken words without picture cues; bullet: the cue words joined with
    " · "), `points`, `section` (one per page), `n` and `weight`. Returns {"blocks", "pages", "errors"}; each page is
    {"page", "label", "first" (index of its first block), "short"}."""
    sheet = cuesheet.parse(text)
    blocks: list[dict] = []
    pages: list[dict] = []
    for part in sheet.parts:
        if not part.lines:
            continue
        page, copy = part.label, 1
        while any(p["page"] == page for p in pages):  # a doubled heading (the parser reports it): its own take count
            copy += 1
            page = f"{part.label} ({copy})"
        pages.append({"page": page, "label": part.heading.split("|")[0].strip() or part.label, "first": len(blocks),
                      "short": part.short})
        for x in part.lines:
            if x.kind == "fixed":
                spoken, groups = x.spoken, []
                points = [spoken] if spoken else []
            else:
                groups = x.groups
                spoken = " · ".join(groups) or (x.question or "")
                points = list(groups)
            blocks.append({"text": spoken, "points": points, "section": len(pages), "kind": x.kind, "role": x.role,
                           "page": page, "unit": part.number, "picture": x.picture,
                           "question": x.question if x.kind == "bullet" else None, "groups": groups,
                           "big": x.kind == "fixed" and (x.role in BIG_ROLES or (part.kind == "opening" and
                                                                                 x.role == "line1"))})
    return {"blocks": _finish(blocks), "pages": pages, "errors": list(sheet.errors)}


def shown_view(p: Path) -> dict:
    """What the screens show for one file: {"format": "cuesheet" | "script", "blocks", "pages", "errors"}. A normal
    script keeps its paragraphs (and its optional .prompter.json layout) and has no pages."""
    text = p.read_text(encoding="utf-8")
    if cuesheet.is_cue_sheet(p, text):
        return {"format": "cuesheet", **cue_sheet_blocks(text)}
    return {"format": "script", "blocks": reading_blocks(p), "pages": [], "errors": []}


_EMPTY_VIEW = {"format": "script", "blocks": [], "pages": [], "errors": []}
_BLOCKS: dict[tuple, dict] = {}


def _shown(episode: str) -> tuple[str | None, dict]:
    """The shown script (episode-relative path) and its view, cached while the file stays the same."""
    try:
        p = script_file(episode)
        if p is None:
            return None, _EMPTY_VIEW
        stat = p.stat()
        layout = p.with_suffix(".prompter.json")
        key = (str(p), stat.st_mtime_ns, stat.st_size, layout.stat().st_mtime_ns if layout.is_file() else 0)
        if key not in _BLOCKS:
            if len(_BLOCKS) > 16:
                _BLOCKS.clear()
            _BLOCKS[key] = shown_view(p)
        return p.relative_to(paths.episode_dir(episode)).as_posix(), _BLOCKS[key]
    except (OSError, ValueError):
        return None, _EMPTY_VIEW


def _version(episode: str) -> str:
    """Changes when the shown script changes, so open screens load the new text."""
    try:
        p = script_file(episode)
        if p is None:
            return ""
        stat = p.stat()
        return f"{p.name}:{stat.st_size}:{stat.st_mtime_ns}"
    except (OSError, ValueError):
        return ""


def script(episode: str) -> dict:
    p = script_file(episode)
    project = episodes.read(episode)
    if p is None:
        return {"title": project.get("title"), "mode": "full", "format": "script", "blocks": [], "pages": [],
                "cps": CHARS_PER_SECOND, "version": "", "note": "No script yet. The Writer makes one in step 4."}
    relative = str(p.relative_to(paths.episode_dir(episode)))
    selected = project.get("recording_script") or {}
    partial = selected.get("file") == relative and selected.get("partial", False)
    view = _shown(episode)[1]
    notes = ["Partial script. The remaining sections are not ready."] if partial else []
    if view["errors"]:
        more = len(view["errors"]) - 1
        notes.append(f"Check the cue sheet: {view['errors'][0]}" + (f" ({more} more)." if more else "."))
    return {"title": project.get("title"), "mode": control(episode).get("mode", "full"), "format": view["format"],
            "blocks": view["blocks"], "pages": view["pages"], "file": relative, "cps": CHARS_PER_SECOND,
            "version": _version(episode), "note": " ".join(notes) or None}


def _now_ms() -> float:
    return time.time() * 1000.0


def _stored(episode: str) -> dict:
    raw = db.kv_get(f"prompter:{episode}")
    d = dict(DEFAULT_CONTROL)
    if raw:
        try:
            saved = json.loads(raw)
        except ValueError:
            saved = None
        if isinstance(saved, dict):
            d.update({k: v for k, v in saved.items() if k in DEFAULT_CONTROL})
            if "seq" not in saved:
                d["playing"] = False  # a state from before the shared timeline has no anchor to play from
    d["takes"] = _takes(d.get("takes"))
    return d


def _takes(value) -> dict[str, int]:
    """The take count per page, as a new dict (a state from before the take count has none)."""
    if not isinstance(value, dict):
        return {}
    return {k: int(v) for k, v in value.items()
            if isinstance(k, str) and isinstance(v, int) and not isinstance(v, bool) and v > 0}


def control(episode: str) -> dict:
    """The shared state, with the server time (`now`, ms) so screens can follow the timeline on their own clock."""
    d = _stored(episode)
    d["now"] = _now_ms()
    d["version"] = _version(episode)
    return d


def advance(weights: list[float], block: int, offset: float, units: float,
            stops: frozenset[int] | set[int] | tuple = ()) -> tuple[int, float, bool]:
    """Move `units` characters forward from (block, offset). Returns the block, the offset in it and whether an end is
    reached: the end of the script, or the end of a block in `stops` (a cue sheet's page ends). The web page has the same
    function (web/src/prompter/timeline.ts)."""
    if not weights:
        return 0, 0.0, True
    i = min(max(0, int(block)), len(weights) - 1)
    f = min(max(0.0, float(offset)), 1.0)
    left = max(0.0, units)
    while True:
        weight = max(1.0, float(weights[i]))
        rest = (1.0 - f) * weight
        if left < rest:
            return i, f + left / weight, False
        if i == len(weights) - 1 or i in stops:
            return i, 1.0, True
        left -= rest
        i, f = i + 1, 0.0


def where(d: dict, weights: list[float], now_ms: float,
          stops: frozenset[int] | set[int] | tuple = ()) -> tuple[int, float, bool]:
    """Where the shared timeline is at server time now_ms."""
    units = 0.0
    if d["playing"]:
        units = max(0.0, now_ms - float(d["at"])) / 1000.0 * CHARS_PER_SECOND * float(d["speed"])
    return advance(weights, d["block"], d["offset"], units, stops)


def stops_of(pages: list[dict], count: int) -> frozenset[int]:
    """The last block of every page of a cue sheet: playing stops there. Empty for a normal script (no pages)."""
    firsts = [int(p["first"]) for p in pages]
    return frozenset(nxt - 1 for nxt in firsts[1:] + [count] if nxt > 0) if pages and count else frozenset()


def _ended_at(d: dict, weights: list[float], stops: frozenset[int], now_ms: float) -> float:
    """The server time at which a playing timeline reached its end (a page end or the end of the script)."""
    i = min(max(0, int(d["block"])), len(weights) - 1)
    f = min(max(0.0, float(d["offset"])), 1.0)
    units = 0.0
    while True:
        units += (1.0 - f) * max(1.0, float(weights[i]))
        if i == len(weights) - 1 or i in stops:
            break
        i, f = i + 1, 0.0
    return min(now_ms, float(d["at"]) + units / (CHARS_PER_SECOND * float(d["speed"])) * 1000.0)


def _index(value, count: int) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or count == 0:
        return None
    return min(max(0, int(value)), count - 1)


def _fraction(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return min(max(0.0, float(value)), 1.0)


def _page_at(firsts: list[int], block: int) -> int:
    """The index of the page that holds `block` (firsts: each page's first block, ascending, the first one 0)."""
    return max((k for k, first in enumerate(firsts) if first <= block), default=0)


def _page_target(pages: list[dict], action: str, requested, here: int, count: int) -> int | None:
    """Where next/prev/repeat go on a cue sheet: always the first block of a page. With a `block` from the screen (the
    target it computed): next goes to the page that starts at or after it, prev and repeat to the start of its page.
    Without one: the page after, before or of the block on the reading line now. None at either end."""
    firsts = [int(p["first"]) for p in pages]
    ref = _index(requested, count)
    if ref is None:
        if requested is not None:
            return None  # a bad value never moves the text
        i = _page_at(firsts, here)
        j: int | None = {"next": i + 1, "prev": i - 1, "repeat": i}[action]
    elif action == "next":
        j = next((k for k, first in enumerate(firsts) if first >= ref), None)
    else:
        j = _page_at(firsts, ref)
    return firsts[j] if j is not None and 0 <= j < len(firsts) else None


def set_control(episode: str, values: dict) -> dict:
    """Apply one screen's command. `action` moves the anchor: jump/next/prev/repeat (`block` = list index, to its start),
    start (the beginning, paused), scroll/scrolled (`block` and `offset`, a hand scroll; scrolled ends it), end (the
    timeline reached the end). Every write gets a newer `seq`; `client` names the screen that wrote it.

    On a cue sheet next, prev and repeat move by page (_page_target), and every jump, next, prev, repeat or start that
    lands at the first block of a page counts a new take of that page (`takes`, {page: count}). Playing ends at the
    end of every page (stops_of). A command that arrives after a page ended but before any screen sent `end` first
    ends it there (logged as "end" at the time the page ended), so Next or Repeat never play on by themselves."""
    old = _stored(episode)
    now = _now_ms()
    file, view = _shown(episode)
    blocks, pages = view["blocks"], view["pages"]
    weights = [b["weight"] for b in blocks]
    stops = stops_of(pages, len(blocks))
    block, offset, at_end = where(old, weights, now, stops)
    if stops and old["playing"] and at_end and values.get("action") != "end":
        ended = _ended_at(old, weights, stops, now)
        old = {**old, "playing": False, "block": block, "offset": offset, "at": ended}
        _log(episode, file, blocks, "end", block, offset, False, ended, old["takes"])
    d = dict(old)
    d["takes"] = dict(old["takes"])
    for k, v in values.items():
        if k not in DEFAULT_CONTROL or k in ("block", "offset", "at", "seq", "by", "cue", "takes"):
            continue
        if k in ("playing", "mirror"):
            d[k] = bool(v)
        elif k == "mode":
            d[k] = "points" if v == "points" else "full"
        else:
            lo, hi = {"speed": (0.2, 4.0), "position": (0.0, 1.0), "size": (0.5, 3.0), "guide": (10.0, 85.0)}[k]
            try:
                number = float(v)
            except (TypeError, ValueError):
                continue
            if math.isfinite(number):
                d[k] = max(lo, min(hi, number))
    action = values.get("action")
    moved = hold = False
    if action in JUMPS:
        if action == "start":
            target = 0
        elif pages and action in ("next", "prev", "repeat"):
            target = _page_target(pages, action, values.get("block"), block, len(blocks))
        else:
            target = _index(values.get("block"), len(blocks))
        if target is not None:
            block, offset, moved = target, 0.0, True
            if action == "start":
                d["playing"] = False
            d["cue"] = int(old["cue"]) + 1
            hold = bool(d["playing"])
            page = next((p["page"] for p in pages if p["first"] == target), None)
            if page is not None:
                d["takes"][page] = d["takes"].get(page, 0) + 1
    elif action in ("scroll", "scrolled"):
        target, fraction = _index(values.get("block"), len(blocks)), _fraction(values.get("offset"))
        if target is not None and fraction is not None:
            block, offset, moved = target, fraction, True
    elif action == "end":
        if not (at_end and old["playing"]):
            return control(episode)  # another screen paused or moved the text already
        d["playing"] = False
    d["block"], d["offset"] = block, offset
    if hold:
        d["at"] = now + JUMP_HOLD_MS
    elif moved or not d["playing"] or not old["playing"]:
        d["at"] = now
    else:
        d["at"] = max(now, float(old["at"]))  # the anchor is where the text is now; a running hold keeps going
    total = sum(weights)
    if total:  # the old fraction, for a page opened before this version
        d["position"] = (sum(weights[:block]) + offset * weights[block]) / total
    d["seq"] = max(int(old["seq"]) + 1, int(now))
    client = values.get("client")
    d["by"] = client if isinstance(client, str) and _CLIENT.fullmatch(client) else ""
    db.kv_set(f"prompter:{episode}", json.dumps(d))
    _LATEST[_key(episode)] = d["seq"]
    if moved and action != "scroll":
        _log(episode, file, blocks, "scroll" if action == "scrolled" else action, block, offset, d["playing"], now,
             d["takes"])
    elif d["playing"] != old["playing"]:
        _log(episode, file, blocks, "end" if action == "end" else ("play" if d["playing"] else "pause"), block,
             offset, d["playing"], now, d["takes"])
    d["now"] = now
    d["version"] = _version(episode)
    return d


def log_file(episode: str, when_ms: float | None = None) -> Path:
    """The take log of one UTC day: brief/prompter-log-<YYYY-MM-DD>.jsonl."""
    day = datetime.fromtimestamp((when_ms if when_ms is not None else _now_ms()) / 1000.0, UTC)
    return paths.inside(paths.episode_dir(episode), f"brief/prompter-log-{day:%Y-%m-%d}.jsonl")


def _log(episode: str, file: str | None, blocks: list[dict], action: str, index: int, offset: float, playing: bool,
         now: float, takes: dict | None = None) -> None:
    """One line per jump, repeat, hand scroll, play or pause: UTC time with milliseconds and the block number on the
    screens. On a cue sheet also the page, the unit and the page's take number (the count after this line; None for a
    normal script, or for a page no command has started yet). A failure to write never stops the prompter."""
    b = blocks[index] if 0 <= index < len(blocks) else {}
    page = b.get("page")
    when = datetime.fromtimestamp(now / 1000.0, UTC)
    entry = {"time": when.isoformat(timespec="milliseconds").replace("+00:00", "Z"), "unix_ms": int(now),
             "action": action, "block": b.get("n"), "section": b.get("section"), "offset": round(offset, 3),
             "playing": playing, "script": file, "words": " ".join(str(b.get("text", "")).split()[:10]),
             "page": page, "unit": b.get("unit"), "take": ((takes or {}).get(page) or None) if page else None}
    try:
        target = log_file(episode, now)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except (OSError, ValueError):
        pass


_LATEST: dict[tuple[str, str], int] = {}


def _key(episode: str) -> tuple[str, str]:
    return str(paths.studio_root()), episode


async def wait_change(episode: str, after: int, timeout: float) -> None:
    """Return as soon as the shared state's seq differs from `after`, or after `timeout` seconds. Writes in this process
    are seen within 25 ms; the database is read again every second for writes from elsewhere."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + max(0.0, timeout)
    checked = -1.0
    while True:
        now = loop.time()
        seq = _LATEST.get(_key(episode))
        if seq is None or now - checked >= 1.0:
            seq = int(_stored(episode)["seq"])
            _LATEST[_key(episode)] = seq
            checked = now
        if seq != after or now >= deadline:
            return
        await asyncio.sleep(0.025)


def terminal_qr(text: str) -> str:
    import qrcode
    q = qrcode.QRCode(border=1)
    q.add_data(text)
    q.make()
    buf = io.StringIO()
    q.print_ascii(out=buf, invert=True)
    return buf.getvalue()
