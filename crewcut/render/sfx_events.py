"""The effect layer: quiet sound effects tied to what appears on screen.

An effect sounds only when something appears in the picture: text, a number, a chapter card (a part change) or a
B-roll change. Every part change gets the same quiet pair (a whoosh, then a pop). At most `per_minute_max` (6) effects
in any minute, at least `min_gap_s` (1.0 s) apart; a moment that falls on a loud syllable of the voice moves by up to
`peak_shift_s` (0.2 s) to a quieter spot, or stays silent. No riser, no hit: the layer has none. A video under a minute keeps the same rate (at least two). A dry Short
(`"sound": {"bed": "dry"}`) gets at most `dry_max` (2) quiet pops.

The plan turns it on with `"sound": {"events": "auto"}`; an insert can say `"sfx": false` (silent) or name its class
(`"part"`, `"number"`, `"text"`, `"broll"`). The style pack sets the levels and limits (`edit-style.json` `sfx`).

The layer stays off until the user has listened to the effect set and approved it: `edit-style.json`
`"sfx": {"approved_set": "<set id>"}`. The id covers the files and their levels, so a changed sound or level needs a
new yes. `crewcut render sfx-sheet` writes the listening page and prints the id. Without approval the cut runs without
the layer and says so in its notes.

Pure apart from making the sound kit at first use and, in `voice_levels`, decoding the voice.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..motion import sfx

CLASSES = ("part", "number", "text", "broll")
PRIORITY = {"part": 4, "number": 3, "text": 2, "broll": 1}      # what stays when a minute is too full
SOUND_OF = {"part": ("whoosh_soft", "pop_soft"), "number": ("pop_soft",), "text": ("pop_soft",), "broll": ("swoosh",)}
PEAK_AT = {"pop_soft": 0.008, "whoosh_soft": 0.2, "swoosh": 0.072}   # seconds from file start to the loudest point
SET_SOUNDS = ("pop_soft", "whoosh_soft", "swoosh")
MOTION_CLASS = {"chapter_card": "part", "number_roll": "number", "versus": "number", "ranking": "number",
                "keyword_pop": "text", "lower_third": "text", "word_reel": "text", "quote": "text", "callout": "text",
                "prompt_bar": "text", "card_gallery": "broll", "end_lockup": None, "cursor": None}
SCENE_CLASS = {"counter": "number", "bars": "number", "keyword": "text", "headline": "text", "post": "text"}
NUMBER_CUES = ("landAt", "value", "decideAt", "firstAt", "countAt")
DEFAULTS: dict[str, Any] = {
    "per_minute_max": 6.0,
    "per_minute_min": 3.0,
    "min_gap_s": 1.0,
    "pair_gap_s": 0.22,          # part change: the pop this long after the whoosh's loudest point
    "peak_shift_s": 0.2,
    "dry_max": 2,
    "levels_db": {"pop_soft": -18.0, "whoosh_soft": -20.0, "swoosh": -22.0},
}
ON = (True, "auto", "on")


@dataclass
class Event:
    t: float                      # seconds: the visual moment the effect belongs to
    cls: str
    insert: str
    why: str
    sounds: list[tuple[str, float, float]] = field(default_factory=list)   # (kit sound, start second, dB)


def settings(pack) -> dict:
    """DEFAULTS, then the pack's edit_style.sfx."""
    out = json.loads(json.dumps(DEFAULTS))
    mine = pack.value("edit_style.sfx", {}) or {}
    for k, v in mine.items():
        if k == "levels_db" and isinstance(v, dict):
            out["levels_db"].update({n: float(x) for n, x in v.items() if n in SET_SOUNDS})
        elif k in DEFAULTS and v is not None:
            out[k] = v
    return out


def set_info(pack, kit_dir: Path | None = None) -> dict:
    """The effect set as approved: its sounds (files and sha256), levels and pair gap, and the id that names it."""
    s = settings(pack)
    kit = sfx.ensure_kit(kit_dir)
    files = {n: {"file": str(kit[n]), "sha256": hashlib.sha256(kit[n].read_bytes()).hexdigest()} for n in SET_SOUNDS}
    body = {"sounds": {n: f["sha256"] for n, f in files.items()}, "levels_db": s["levels_db"],
            "pair_gap_s": s["pair_gap_s"]}
    sid = "sfx-" + hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()[:12]
    return {"id": sid, "files": files, "levels_db": s["levels_db"], "pair_gap_s": s["pair_gap_s"],
            "per_minute_max": s["per_minute_max"], "min_gap_s": s["min_gap_s"]}


def approved(pack, kit_dir: Path | None = None) -> tuple[bool, str]:
    sid = set_info(pack, kit_dir)["id"]
    return pack.value("edit_style.sfx.approved_set") == sid, sid


def requested(plan) -> bool:
    return (plan.p.get("sound") or {}).get("events") in ON


# ---- which picture events there are ------------------------------------------------------------------------------
def classify(x) -> str | None:
    """The class of an insert's appearance, or None when it makes no sound. The plan's "sfx" wins."""
    own = (x.raw or {}).get("sfx")
    if own is False:
        return None
    if isinstance(own, str) and own in CLASSES:
        return own
    if x.kind == "motion":
        return MOTION_CLASS.get(x.scene or "", "text" if x.transparent else "broll")
    if x.kind == "2d":
        return SCENE_CLASS.get(x.scene or "", "text" if x.transparent else "broll")
    return "broll"                                   # 3D and clips: a picture change


def moment(plan, x, cls: str) -> float:
    """Seconds of the visual moment: a number lands on its cue, everything else when it appears."""
    t0 = x.start / plan.fps
    if cls != "number":
        return t0
    if x.kind == "motion":
        for c in NUMBER_CUES:
            v = (x.params or {}).get(c)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                return t0 + float(v)
        return t0
    for c in NUMBER_CUES:
        if c in (x.cues or {}):
            return (x.start + x.cues[c]) / plan.fps
    if x.cues:
        return (x.start + min(x.cues.values())) / plan.fps
    return t0


def candidates(plan, end: int) -> tuple[list[Event], list[str]]:
    out, notes = [], []
    T = end / plan.fps
    for x in sorted(plan.inserts, key=lambda i: i.start):
        cls = classify(x)
        if cls is None:
            if (x.raw or {}).get("sfx") is False:
                notes.append(f"{x.id}: silent (\"sfx\": false)")
            continue
        t = moment(plan, x, cls)
        if not 0 <= t < T:
            continue
        out.append(Event(round(t, 3), cls, x.id, f"{cls} appears ({x.kind} {x.scene or Path(str(x.clip)).name})"))
    return out, notes


# ---- limits ------------------------------------------------------------------------------------------------------
def _fits(times: list[float], t: float, cap: int, window: float) -> bool:
    """Would one more event at t keep every window of `window` seconds at or under `cap` events?"""
    pts = sorted([*times, t])
    starts = [s for s in pts if t - window < s <= t]
    return all(sum(1 for u in pts if s <= u < s + window) <= cap for s in starts)


def limit(events: list[Event], seconds: float, s: dict, dry: bool) -> tuple[list[Event], list[str]]:
    """Keep the most important events within the per-minute cap and the minimum gap; part changes first."""
    notes: list[str] = []
    window = 60.0
    per_min = float(s["per_minute_max"])
    if dry:
        cap = int(s["dry_max"])
    elif seconds >= window:
        cap = int(per_min)
    else:                                   # a video under a minute: the same rate, but at least two
        cap = max(2, math.ceil(per_min * seconds / window))
    gap = float(s["min_gap_s"])
    kept: list[Event] = []
    for e in sorted(events, key=lambda e: (-PRIORITY[e.cls], e.t)):
        if dry and len(kept) >= cap:
            notes.append(f"{e.insert}: no effect (a dry Short gets at most {cap} quiet pops)")
            continue
        if any(abs(e.t - k.t) < gap for k in kept):
            notes.append(f"{e.insert}: no effect at {e.t:.2f} s (less than {gap:g} s after another)")
            continue
        if not dry and not _fits([k.t for k in kept], e.t, cap, window):
            notes.append(f"{e.insert}: no effect at {e.t:.2f} s (already {cap} in that minute)")
            continue
        kept.append(e)
    return sorted(kept, key=lambda e: e.t), notes


# ---- the voice: never on a speech peak ---------------------------------------------------------------------------
def voice_levels(path: Path):
    """The voice's level in dB every 10 ms (16 kHz mono decode, 20 ms windows), as the cut's join check measures."""
    from ..cut.transcribe import load_audio
    from ..cut.verify import level_track
    return level_track(load_audio(Path(path)), 16000)


def peak_threshold(levels) -> float | None:
    """Loud syllables: the top tenth of the speech frames (speech = 10 dB over the noise floor)."""
    import numpy as np
    if levels is None or len(levels) == 0:
        return None
    floor = float(np.percentile(levels, 8)) + 10
    speech = levels[levels > floor]
    return float(np.percentile(speech, 90)) if len(speech) > 20 else None


def _loudness_at(levels, t: float, span: float = 0.08) -> float:
    a, b = max(0, int(t * 100)), max(1, int((t + span) * 100))
    seg = levels[a:b]
    return float(seg.max()) if len(seg) else -120.0


def off_peak(events: list[Event], levels, shift: float) -> tuple[list[Event], list[str]]:
    """Move an event that falls on a loud syllable to the quietest spot within `shift` seconds, or drop it."""
    thr = peak_threshold(levels)
    if thr is None:
        return events, []
    out, notes = [], []
    steps = [k * 0.02 for k in range(0, int(round(shift / 0.02)) + 1)]
    offsets = sorted({0.0, *steps, *(-x for x in steps)}, key=lambda d: (abs(d), d))
    for e in events:
        best = min(offsets, key=lambda d: (_loudness_at(levels, e.t + d) >= thr, abs(d)))
        if _loudness_at(levels, e.t + best) >= thr:
            notes.append(f"{e.insert}: no effect at {e.t:.2f} s (on a speech peak, no quiet spot within {shift:g} s)")
            continue
        if best:
            notes.append(f"{e.insert}: effect moved {best * 1000:+.0f} ms off a speech peak")
        e.t = round(max(0.0, e.t + best), 3)
        out.append(e)
    return out, notes


# ---- the layer ---------------------------------------------------------------------------------------------------
def sounds_for(e: Event, s: dict, dry: bool) -> list[tuple[str, float, float]]:
    """(sound, file start second, dB) for one event; each sound's loudest point lands on the moment."""
    names = ("pop_soft",) if dry else SOUND_OF[e.cls]
    out, t = [], e.t
    for i, n in enumerate(names):
        at = t + (float(s["pair_gap_s"]) if i else 0.0)
        out.append((n, round(max(0.0, at - PEAK_AT[n]), 3), float(s["levels_db"][n])))
    return out


def layer(plan, end: int, levels=None, dry: bool = False, kit_dir: Path | None = None) -> tuple[list[Event], list[str]]:
    """The effect layer of a plan: [] with a note when it is not requested or not approved."""
    if not requested(plan):
        return [], []
    ok, sid = approved(plan.pack, kit_dir)
    if not ok:
        return [], [f"effect layer requested but off: the effect set {sid} is not approved yet (listen with "
                    "`crewcut render sfx-sheet`, then the user sets edit-style.json sfx.approved_set)"]
    s = settings(plan.pack)
    seconds = end / plan.fps
    events, notes = candidates(plan, end)
    if levels is not None:
        events, more = off_peak(events, levels, float(s["peak_shift_s"]))
        notes += more
    events, more = limit(events, seconds, s, dry)
    notes += more
    for e in events:
        e.sounds = sounds_for(e, s, dry)
    rate = len(events) / (seconds / 60) if seconds else 0.0
    notes.append(f"effect layer {sid}: {len(events)} effects, {rate:.1f} per minute"
                 + (" (dry Short)" if dry else ""))
    if not dry and seconds >= 60 and rate < float(s["per_minute_min"]):
        notes.append(f"fewer than {s['per_minute_min']:g} effects per minute: the layer adds none without a picture "
                     "event; more inserts would bring more")
    return events, notes


def summary(events: list[Event]) -> list[dict]:
    return [{"t": e.t, "class": e.cls, "insert": e.insert, "why": e.why,
             "sounds": [{"sound": n, "start": a, "db": d} for n, a, d in e.sounds]} for e in events]


# ---- listening sheet and the user's yes --------------------------------------------------------------------------
DEMO = (  # (seconds into the demo, class, what it stands for)
    (1.5, "text", "a keyword appears"),
    (4.0, "number", "a number lands"),
    (7.0, "part", "a chapter card: part change"),
    (10.5, "broll", "a screen recording starts (B-roll change)"),
    (13.0, "text", "a lower third appears"),
    (16.0, "part", "the next chapter card"),
)


def _at_level_cmd(src: Path, db: float, out: Path) -> list[str]:
    from . import media
    return [media.ffmpeg(), "-y", "-loglevel", "error", "-i", str(src), "-af",
            f"aresample=48000,aformat=sample_rates=48000:channel_layouts=stereo,volume={db:g}dB",
            "-c:a", "pcm_s16le", str(out)]


def _demo_cmd(voice: Path | None, start: float, seconds: float, uses: list[tuple[Path, float, float]],
              out: Path) -> list[str]:
    from . import media
    cmd = [media.ffmpeg(), "-y", "-loglevel", "error"]
    f = []
    if voice:
        cmd += ["-ss", f"{start:.3f}", "-t", f"{seconds:.3f}", "-i", str(voice)]
        f.append(f"[0:a]aresample=48000,aformat=sample_rates=48000:channel_layouts=stereo,"
                 f"loudnorm=I=-16:TP=-2:LRA=7,apad=whole_dur={seconds:.3f}[v]")
    else:
        cmd += ["-f", "lavfi", "-t", f"{seconds:.3f}", "-i", "anullsrc=r=48000:cl=stereo"]
        f.append("[0:a]anull[v]")
    labels = ["[v]"]
    for i, (p, at, db) in enumerate(uses, 1):
        cmd += ["-i", str(p)]
        f.append(f"[{i}:a]aresample=48000,aformat=sample_rates=48000:channel_layouts=stereo,volume={db:g}dB,"
                 f"adelay={max(0, int(round(at * 1000)))}:all=1[e{i}]")
        labels.append(f"[e{i}]")
    f.append("".join(labels) + f"amix=inputs={len(labels)}:normalize=0:duration=first,alimiter=limit=0.89[m]")
    return cmd + ["-filter_complex", ";".join(f), "-map", "[m]", "-t", f"{seconds:.3f}", "-c:a", "pcm_s16le", str(out)]


def _html(info: dict, rows: list[dict], demo: dict | None) -> str:
    import html as h
    def audio(name: str) -> str:
        return f'<audio controls preload="none" src="{h.escape(name)}"></audio>'
    trs = "".join(f"<tr><td><b>{h.escape(r['sound'])}</b></td><td>{h.escape(r['for'])}</td><td>{r['db']:g} dB</td>"
                  f"<td>{audio(r['file'])}</td></tr>" for r in rows)
    dm = ""
    if demo:
        marks = "".join(f"<li>{t:.1f} s: {h.escape(what)}</li>" for t, what in demo["marks"])
        dm = (f"<h2>Under the voice</h2><p>{h.escape(demo['what'])}</p>{audio(demo['file'])}<ol>{marks}</ol>")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Effect set {h.escape(info['id'])}</title>
<style>
:root {{ --bg: #faf9f5; --fg: #1f1e1d; --muted: #6b6a65; --line: #e3e1d9; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg: #1f1e1d; --fg: #f0eee6; --muted: #a8a69e; --line: #3a3936; }} }}
body {{ background: var(--bg); color: var(--fg); font: 16px/1.5 system-ui, sans-serif; margin: 0 auto;
  max-width: 760px; padding: 24px 16px; }}
table {{ border-collapse: collapse; width: 100%; }} td {{ border-top: 1px solid var(--line); padding: 8px 6px;
  vertical-align: middle; }} audio {{ width: 100%; max-width: 260px; }} .muted {{ color: var(--muted); }}
code {{ font-size: 14px; }}
</style></head><body>
<h1>Effect set {h.escape(info['id'])}</h1>
<p>The quiet effects of the layer on picture events. Each file plays at the level it gets in the mix (the voice sits
at about -16 LUFS before the final loudness). Listen on headphones and on a phone speaker. Listen for clicks at the
start or end, a whoosh that hisses more than it moves, and any effect that covers a word.</p>
<table>{trs}</table>
{dm}
<h2>Your yes</h2>
<p>The layer stays off until you approve exactly this set. To approve it, run outside a crew job:
<br><code>crewcut render sfx-approve {h.escape(info['id'])}</code><br>
<span class="muted">A changed sound or level gets a new id and needs a new yes.</span></p>
</body></html>
"""


def listening_sheet(out: Path, pack, voice: Path | None = None, start: float = 0.0, seconds: float = 19.0,
                    runner=None, kit_dir: Path | None = None) -> dict:
    """Write the listening folder: every set sound at its mix level, a demo under a voice (or alone), index.html and
    set.json. Returns set.json's content."""
    from . import media
    runner = runner or media.run
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    info = set_info(pack, kit_dir)
    s = settings(pack)
    rows = []
    for n in SET_SOUNDS:
        f = out / f"{n}.wav"
        rc, o = runner(_at_level_cmd(Path(info["files"][n]["file"]), s["levels_db"][n], f), timeout=120)
        if rc:
            raise RuntimeError(f"writing {f.name} failed: {media.tail(o, 300)}")
        rows.append({"sound": n, "file": f.name, "db": s["levels_db"][n],
                     "for": {"pop_soft": "text or a number appears", "whoosh_soft": "a part change, before the pop",
                             "swoosh": "a B-roll or picture change"}[n]})
    uses, marks = [], []
    for t, cls, what in DEMO:
        if t >= seconds:
            continue
        e = Event(t, cls, "demo", what)
        for n, at, db in sounds_for(e, s, False):
            uses.append((Path(info["files"][n]["file"]), at, db))
        marks.append((t, f"{what} ({' + '.join(SOUND_OF[cls])})"))
    demo_file = out / ("demo-under-voice.wav" if voice else "demo-alone.wav")
    rc, o = runner(_demo_cmd(Path(voice) if voice else None, start, seconds, uses, demo_file), timeout=300)
    if rc:
        raise RuntimeError(f"writing the demo failed: {media.tail(o, 300)}")
    demo = {"file": demo_file.name, "marks": marks,
            "what": (f"{seconds:g} s of {Path(voice).name} from {start:g} s, levelled to -16 LUFS, with the effects at "
                     "their mix levels." if voice else "The effects alone, at their mix levels, in the demo order.")}
    (out / "index.html").write_text(_html(info, rows, demo), encoding="utf-8")
    data = {**info, "sheet": str(out / "index.html"), "demo": str(demo_file), "files_at_level": [r["file"] for r in rows]}
    (out / "set.json").write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
    return data


def approve(set_id: str, pack_dir: Path, source: str) -> dict:
    """Write the user's yes for one effect set into the pack's edit-style.json (sfx.approved_set). The id must be the
    set's current id. Refused inside a crew job: only the user approves what they have heard."""
    import os

    from .. import brand
    if os.environ.get("CREWCUT_JOB"):
        raise PermissionError("only the user approves the effect set; a crew job cannot (run it outside a job)")
    pack = brand.load(pack_dir)
    current = set_info(pack)["id"]
    if set_id != current:
        raise ValueError(f"{set_id} is not the current effect set ({current}); listen to the current one first")
    f = Path(pack_dir) / "edit-style.json"
    d = json.loads(f.read_text(encoding="utf-8")) if f.is_file() else {}
    d.setdefault("sfx", {})["approved_set"] = set_id
    d.setdefault("sources", {})["sfx.approved_set"] = source
    tmp = f.with_name(f".{f.name}.tmp")
    tmp.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(f)
    return {"approved_set": set_id, "file": str(f)}
