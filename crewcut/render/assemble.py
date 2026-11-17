"""Assembly ("cut"): the finished video from the speaker cut, the inserts and the sound.

Three stages, each its own ffmpeg run (one run with every piece as an input ran out of memory on long videos):
1. every picture piece on its own into <output>.pieces/ (speaker with zoom held on the face, a full-frame insert, or a
   generated background; transparent overlays laid on top already here). Unchanged pieces are kept for the next run.
2. the sound in its own run: voice, music bed (looped, ducked under the voice, gaps before strong moments), hits,
   typing and whooshes, then a limiter.
3. loudness in two passes to the pack target, AAC encode, true peak measured after the encode (AAC raises it) and the
   limiter lowered until it holds, then picture and sound together.

After someone has seen an output, `shown` locks it: `<output>.shown` holds the time and sha256, and `cut` refuses to
overwrite it. Every change is a new plan version with a new output.

Layout "proof-top" (portrait Shorts, see plan.py): while an insert with place "top" runs, its piece stacks two
pictures (vstack): the insert scaled onto the stage (cover: fill and crop; contain: the whole picture as a card on the
stage colour) and below it the speaker, cropped around the face. Without an insert the speaker fills the frame, and the
last `end_face` seconds of the speaker cut always do: a stage insert that reaches into them stops there.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path

from ..motion import sfx
from . import html, media
from .plan import Insert, Plan, PlanError

CARD_MARGIN = 48                 # proof-top, fit contain: space around the card on the stage (px)

SFX = (  # name, plan list key, default dB, default length (s), pre-roll (ms)
    ("hit", "hits", -9.0, 1.2, 40),
    ("typing", "typing", -14.0, 1.0, 0),
    ("whoosh", "whooshes", -16.0, 0.8, 120),
)
# the sound kit's file for each SFX row when neither the plan nor the pack names one (crewcut.motion.sfx)
KIT_SOUND = {"hit": "hit", "typing": "typing", "whoosh": "whoosh"}
STEREO = "aformat=sample_rates=48000:channel_layouts=stereo"


class ShownError(RuntimeError):
    """The output was already shown to someone; it must not be overwritten."""


@dataclass
class Piece:
    index: int
    a: int                       # first frame
    b: int                       # first frame after
    label: str
    source: str                  # insert | base | color
    path: Path | None = None
    seek: float = 0.0            # seconds into the source
    vf: str = ""                 # filters before fps/format, ending with ","
    overlays: list[tuple[Path, float]] = field(default_factory=list)
    color: str | None = None
    low: Piece | None = None     # proof-top: the speaker part stacked under this (stage) picture
    size: tuple[int, int] | None = None     # picture size of this part when it is not the full frame

    @property
    def frames(self) -> int:
        return self.b - self.a


# ---- shown lock -------------------------------------------------------------------------------------------------
def read_shown(p: Path) -> dict:
    """The lock file: {"at": ISO time, "sha256": 64 hex}. An unreadable file still counts as a lock."""
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {"raw": str(d)}
    except (OSError, ValueError):
        return {}


def check_not_shown(plan: Plan) -> None:
    p = plan.shown_path
    if p.is_file():
        d = read_shown(p)
        when = d.get("at", "at an unknown time")
        raise ShownError(f"{plan.output.name} was already shown ({when}, sha256 {str(d.get('sha256', '?'))[:16]}). "
                         "Do not overwrite it: make a new plan version with a new output.")


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def shown(plan: Plan) -> dict:
    """Lock the output right after someone has seen it."""
    out = plan.output
    if not out.is_file():
        raise PlanError(f"{out.name} does not exist yet; nothing to lock")
    digest = sha256(out)
    at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    plan.shown_path.write_text(json.dumps({"at": at, "sha256": digest}) + "\n", encoding="utf-8")
    return {"output": str(out), "shown": str(plan.shown_path), "at": at, "sha256": digest}


# ---- picture ------------------------------------------------------------------------------------------------------
def base_frames(plan: Plan, runner: media.Runner = media.run) -> int:
    b = plan.p.get("base")
    if isinstance(b, dict):
        n = round(float(b.get("seconds") or 0) * plan.fps)
        if n <= 0:
            raise PlanError("a generated base needs seconds above 0, e.g. {\"color\": \"soft\", \"seconds\": 12}")
    elif b:
        n = media.frame_count(plan.local(b), plan.fps, runner)
    else:
        raise PlanError("the plan needs 'base' (the speaker cut) or a generated base {\"color\": \"soft\", \"seconds\": 12}")
    if plan.p.get("base_until") is not None:
        n = min(n, round(float(plan.p["base_until"]) * plan.fps))
    return n


def end_frame(plan: Plan, base_end: int) -> int:
    return base_end + round(float(plan.p.get("tail") or 0) * plan.fps)


def face_from(plan: Plan, base_end: int) -> int:
    """proof-top: first frame of the face-alone end (the stage stops here). Other layouts: no limit."""
    if plan.layout != "proof-top":
        return base_end + 10 ** 9
    return max(0, base_end - round(plan.end_face_s * plan.fps))


def visible(plan: Plan, base_end: int) -> list[tuple[Insert, int, int]]:
    """Full-frame inserts with the frames they are shown: stage inserts end where the face-alone end begins."""
    limit = face_from(plan, base_end)
    out = []
    for x in plan.inserts:
        if x.transparent and not plan.behind_clip(x):
            continue
        a, b = x.start, (min(x.end, limit) if x.place == "top" else x.end)
        if b > a:
            out.append((x, a, b))
    return out


def stage_notes(plan: Plan, base_end: int) -> list[str]:
    """What the face-alone end took away from stage inserts."""
    limit = face_from(plan, base_end)
    return [f"{x.id}: the stage stops at {limit / plan.fps:.2f} s, the last {plan.end_face_s:g} s show the face alone"
            for x in plan.inserts if not x.transparent and x.place == "top" and x.end > limit]


def speaker_vf(plan: Plan, zoom: float) -> str:
    """The full-frame speaker picture: scaled to the frame, then held on the face at `zoom` (ends with ",")."""
    W, H = plan.size
    fx, fy = plan.face
    norm = f"scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,crop={W}:{H},"
    return norm + (f"scale=iw*{zoom:g}:-2:flags=lanczos,crop={W}:{H}:(iw-{W})*{fx:g}:(ih-{H})*{fy:g},"
                   if zoom != 1.0 else "")


def pieces(plan: Plan, base_end: int, end: int) -> list[Piece]:
    """Split the video at every visible cut and every overlay edge. Pure: no files are read."""
    W, H = plan.size
    fps = plan.fps
    full = visible(plan, base_end)
    over = [x for x in plan.inserts if x.transparent and not plan.behind_clip(x)]
    marks = plan.speaker_marks()
    cuts = {0, end} | {a for _, a, _ in full} | {b for _, _, b in full} | {f for f, _ in marks}
    if base_end < end:
        cuts.add(base_end)                      # the tail starts here; it must be covered by an insert
    edges = cuts | {x.start for x in over} | {x.end for x in over}
    bounds = sorted(c for c in edges if 0 <= c <= end)
    color = plan.base_color()
    base = None if color else plan.local(plan.p["base"])
    norm = f"scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,crop={W}:{H},"
    fx, fy = plan.face
    SW, SH = plan.stage_size
    LH = H - SH                                 # height of the speaker part under the stage

    def zoom_at(f: int) -> float:
        z = 1.0
        for at, zz in marks:
            if at <= f:
                z = zz
        return z

    def speed_vf(e: Insert) -> str:
        return f"setpts=(PTS-STARTPTS)/{e.speed:g}," if e.kind == "clip" and e.speed != 1 else ""

    def stage_vf(e: Insert) -> str:
        if e.fit == "contain":
            m = CARD_MARGIN
            return (speed_vf(e) + f"scale={SW - 2 * m}:{SH - 2 * m}:force_original_aspect_ratio=decrease:"
                    f"force_divisible_by=2:flags=lanczos,pad={SW}:{SH}:(ow-iw)/2:(oh-ih)/2:"
                    f"color=0x{plan.stage_color().lstrip('#')},")
        y = "0" if e.anchor == "top" else f"(ih-{SH})/2"
        return (speed_vf(e) + f"scale={SW}:{SH}:force_original_aspect_ratio=increase:flags=lanczos,"
                f"crop={SW}:{SH}:(iw-{SW})/2:{y},")

    def speaker_low(i: int, a: int, b: int) -> Piece:
        """The speaker under the stage: the full frame zoomed like elsewhere, then the part around the face."""
        if color:
            return Piece(i, a, b, "background", "color", None, a / fps, "", color=color, size=(W, LH))
        z = zoom_at(a)
        y = int(min(max(fy * H * z - LH / 2, 0), H * z - LH))
        vf = norm + (f"scale=iw*{z:g}:-2:flags=lanczos," if z != 1.0 else "") + f"crop={W}:{LH}:(iw-{W})*{fx:g}:{y},"
        return Piece(i, a, b, f"speaker x{z:g} (below the stage)", "base", base, a / fps, vf, size=(W, LH))

    out = []
    for i, (a, b) in enumerate(pairwise(bounds)):
        hit = next(((x, s, t) for x, s, t in full if s <= a < t), None)
        e: Insert | None = hit[0] if hit else None
        ov = [(u.clip, (a - u.start) / fps) for u in over if u.start <= a < u.end]
        if e is not None and e.place == "top":
            seek = (e.at + (a - e.start) / fps * e.speed) if e.kind == "clip" else (a - e.start) / fps
            p = Piece(i, a, b, f"{e.id} (stage)", "insert", e.clip, seek, stage_vf(e), ov,
                      low=speaker_low(i, a, b), size=(SW, SH))
        elif e is not None and e.kind == "clip":
            vf = norm + speed_vf(e)
            p = Piece(i, a, b, e.id, "insert", e.clip, e.at + (a - e.start) / fps * e.speed, vf, ov)
        elif e is not None:
            p = Piece(i, a, b, e.id, "insert", plan.behind_clip(e) or e.clip, (a - e.start) / fps, "", ov)
        else:
            if a >= base_end:
                raise PlanError(f"frame {a}: after the end of the base there is no insert. A tail needs a full-frame "
                                "insert (an end card) up to the end.")
            z = zoom_at(a)
            label = f"speaker x{z:g}" if color is None else "background"
            if color:
                p = Piece(i, a, b, label, "color", None, a / fps, "", ov, color=color)
            else:
                p = Piece(i, a, b, label, "base", base, a / fps, speaker_vf(plan, z), ov)
        out.append(p)
    return out


def shots(plan: Plan, base_end: int, end: int) -> list[dict]:
    """The visible cuts (overlay edges are not cuts): frame, seconds, what is shown."""
    full = visible(plan, base_end)
    cuts = sorted({0} | {a for _, a, _ in full} | {b for _, _, b in full if b < end} | {f for f, _ in plan.speaker_marks()})
    rows = []
    for c in cuts:
        if not 0 <= c < end:
            continue
        e = next((x for x, a, b in full if a <= c < b), None)
        rows.append({"frame": c, "s": round(c / plan.fps, 2), "what": e.id if e else "speaker"})
    return rows


def _input(plan: Plan, piece: Piece) -> list[str]:
    """ffmpeg input arguments of one picture part: a generated colour or a file at its seek point."""
    if piece.source == "color":
        W, H = piece.size or plan.size
        return ["-f", "lavfi", "-i",
                f"color=c=0x{piece.color.lstrip('#')}:s={W}x{H}:r={plan.fps}:d={piece.frames / plan.fps + 0.2:.3f}"]
    return ["-ss", f"{max(0.0, piece.seek - 0.004):.3f}", "-i", str(piece.path)]


def piece_cmd(plan: Plan, piece: Piece, out: Path) -> list[str]:
    fps = plan.fps
    cmd = [media.ffmpeg(), "-y", "-loglevel", "error", *_input(plan, piece)]
    tail = f"fps={fps},format=yuv420p,setsar=1,tpad=stop_mode=clone:stop_duration=1"
    first = 1
    if piece.low is None:
        chain = f"[0:v]{piece.vf}{tail}[b0]"
    else:                                       # proof-top: the stage above, the speaker below
        cmd += _input(plan, piece.low)
        chain = f"[0:v]{piece.vf}{tail}[st];[1:v]{piece.low.vf}{tail}[lo];[st][lo]vstack=inputs=2[b0]"
        first = 2
    for j, (clip, seek) in enumerate(piece.overlays):
        cmd += ["-ss", f"{max(0.0, seek - 0.004):.3f}", "-i", str(clip)]
        chain += (f";[{j + first}:v]fps={fps},tpad=stop_mode=clone:stop_duration=1[u{j}]"
                  f";[b{j}][u{j}]overlay=format=auto[b{j + 1}]")
    chain += f";[b{len(piece.overlays)}]format=yuv420p[v]"
    cmd += ["-an", "-filter_complex", chain, "-map", "[v]", "-frames:v", str(piece.frames), "-c:v", "libx264",
            "-crf", "12", "-preset", "veryfast", "-g", str(fps), "-video_track_timescale", str(fps * 512), str(out)]
    return cmd


def piece_key(piece: Piece) -> str:
    """Cache key of a piece: sources with their mtimes, seek, length, filters, overlays (and the part below)."""
    def stamp(p: Path | None) -> str:
        try:
            return f"{p}:{os.stat(p).st_mtime_ns}" if p else ""
        except OSError:
            return f"{p}:missing"
    parts = [piece.source, stamp(piece.path), piece.color or "", f"{piece.seek:.4f}", str(piece.frames), piece.vf]
    parts += [f"{stamp(c)}@{s:.4f}" for c, s in piece.overlays]
    if piece.low is not None:
        lo = piece.low
        parts += ["low", lo.source, stamp(lo.path), lo.color or "", f"{lo.seek:.4f}", lo.vf]
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:10]


# ---- sound ------------------------------------------------------------------------------------------------------
@dataclass
class AudioGraph:
    inputs: list[str]
    filters: list[str]
    notes: list[str]
    seconds: float


def _sound_file(plan: Plan, rel: str | None, pack_key: str | None) -> Path | None:
    """A sound file named by the plan (episode folder) or, when the plan names none, by the pack."""
    def in_pack(name: str) -> Path | None:
        try:
            return plan.pack.file(name)
        except ValueError:
            return None

    if rel:
        found: list[Path | None] = []
        try:
            found.append(plan.local(rel))
        except PlanError:
            pass
        if not os.path.isabs(rel):
            found.append(in_pack(rel))
        return next((p for p in found if p is not None and p.is_file()), None)
    if pack_key:
        name = plan.pack.value(pack_key)
        f = in_pack(name) if isinstance(name, str) and name else None
        return f if f and f.is_file() else None
    return None


def _sfx_file(plan: Plan, sound: dict, name: str, notes: list[str], count: int) -> Path | None:
    """The file of one SFX row: the plan's `<name>_file`, else the pack's `sounds.<name>`, else the sound kit's file
    (made by code at first use). A file the plan or the pack names but that is missing is skipped with a note."""
    rel = sound.get(f"{name}_file")
    if rel:
        f = _sound_file(plan, rel, None)
    else:
        rel = plan.pack.value(f"edit_style.sounds.{name}")
        f = _sound_file(plan, None, f"edit_style.sounds.{name}") if rel else None
    if f:
        return f
    if rel:
        notes.append(f"{count} {name} sound(s) skipped: file not found: {rel}")
        return None
    f = sfx.kit_path(KIT_SOUND[name])
    notes.append(f"{count} {name} sound(s) from Crewcut's sound kit ({f.name}, made by code); set sound.{name}_file "
                 f"in the plan or sounds.{name} in the pack's edit-style.json for your own")
    return f


def audio_graph(plan: Plan, end: int) -> AudioGraph:
    """The ffmpeg inputs and filter graph of the sound. Pure apart from checking that files exist and making the
    sound kit (crewcut.motion.sfx) at first use when a sound has no file of its own."""
    fps = plan.fps
    T = end / fps
    sound = plan.p.get("sound") or {}
    inputs: list[str] = []
    idx: dict[str, int] = {}
    filters: list[str] = []
    notes: list[str] = []

    def add(p: Path, loop: bool = False) -> int:
        key = f"{p}|{loop}"
        if key not in idx:
            idx[key] = len(idx)
            inputs.extend((["-stream_loop", "-1"] if loop else []) + ["-i", str(p)])
        return idx[key]

    lufs = float(plan.value("lufs", "edit_style.loudness_lufs", -14.0, section=sound))
    tp = float(plan.pack.value("edit_style.true_peak_db", -1.5))
    if plan.p.get("voice"):
        k = add(plan.local(plan.p["voice"]))
        filters.append(f"[{k}:a]aresample=48000,{STEREO},volume={float(plan.p.get('voice_db') or 0.0):g}dB,"
                       f"apad=whole_dur={T:.3f}[voice]")
    elif plan.base_color() is None and plan.p.get("base"):
        k = add(plan.local(plan.p["base"]))
        filters.append(f"[{k}:a]highpass=f=70,loudnorm=I={lufs - 1:g}:TP={tp:g}:LRA=7,aresample=48000,{STEREO},"
                       f"apad=whole_dur={T:.3f}[voice]")
    else:
        filters.append(f"anullsrc=r=48000:cl=stereo,atrim=0:{T:.3f}[voice]")
        notes.append("no voice: the sound starts from silence")
    mix = ["[voice]"]

    music = _sound_file(plan, sound.get("music"), None) if sound.get("music") else None
    if sound.get("music") and not music:
        notes.append(f"music file not found, skipped: {sound.get('music')}")
    if music:
        k = add(music, loop=True)
        db = float(plan.value("music_db", "edit_style.music_db", -16.0, section=sound))
        gaps = ""
        for g in sound.get("gaps") or []:
            f0 = plan.ref_frame(g["before"])
            n = int(g.get("frames", 15))
            gaps += f",volume=enable='between(t,{max(0, f0 - n) / fps:.3f},{max(0, f0 - 1) / fps:.3f})':volume=0.05"
        filters.append(f"[{k}:a]atrim=0:{T:.3f},aresample=48000,{STEREO},volume={db:g}dB{gaps},afade=t=in:d=0.4,"
                       f"afade=t=out:st={max(0.0, T - 1.2):.3f}:d=1.2[mu0]")
        if plan.value("duck", "edit_style.duck", True, section=sound):
            filters.append("[voice]asplit=2[vm][vk]")
            mix[0] = "[vm]"
            filters.append(f"[mu0][vk]sidechaincompress=threshold={float(sound.get('duck_threshold', 0.04)):g}:"
                           f"ratio={float(sound.get('duck_ratio', 2.2)):g}:attack=25:release=450:makeup=1[mu]")
        else:
            filters.append("[mu0]anull[mu]")
        mix.append("[mu]")

    _, motion_notes = plan.motion_sounds()
    notes += motion_notes
    for name, key, db_default, length, preroll in SFX:
        entries = plan.sound_entries(key)
        if not entries:
            continue
        f = _sfx_file(plan, sound, name, notes, len(entries))
        if not f:
            continue
        k = add(f)
        db = float(sound.get(f"{name}_db", db_default))
        filters.append(f"[{k}:a]aresample=48000,{STEREO},asplit={len(entries)}" + "".join(f"[{name}{i}]" for i in range(len(entries))))
        for i, s in enumerate(entries):
            if isinstance(s, dict):
                at = plan.ref_frame(s["at"]) + int(s.get("offset", 0))
                ln = int(s["frames"]) / fps if s.get("frames") else length
            elif isinstance(s, list):
                at = plan.ref_frame(s[0]) + int(s[1])
                ln = (int(s[2]) - int(s[1])) / fps
            else:
                at = plan.ref_frame(s)
                ln = length
            ms = max(0, int(round(at / fps * 1000)) - preroll)
            filters.append(f"[{name}{i}]atrim=0:{ln:.3f},volume={db:g}dB,adelay={ms}:all=1[{name}d{i}]")
            mix.append(f"[{name}d{i}]")
    filters.append("".join(mix) + f"amix=inputs={len(mix)}:normalize=0:duration=first,alimiter=limit=0.89[am]")
    return AudioGraph(inputs, filters, notes, T)


def audio_cmd(g: AudioGraph, out: Path) -> list[str]:
    return [media.ffmpeg(), "-y", "-loglevel", "error", *g.inputs, "-filter_complex", ";".join(g.filters),
            "-map", "[am]", "-c:a", "pcm_s16le", "-ar", "48000", "-t", f"{g.seconds:.3f}", str(out)]


def concat_cmd(list_file: Path, seconds: float, out: Path) -> list[str]:
    return [media.ffmpeg(), "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(list_file), "-c", "copy",
            "-t", f"{seconds:.3f}", str(out)]


def aac_cmd(wav: Path, gain_db: float, limit_db: float, out: Path) -> list[str]:
    return [media.ffmpeg(), "-y", "-loglevel", "error", "-i", str(wav), "-af",
            f"volume={gain_db:.2f}dB,alimiter=limit={10 ** (limit_db / 20):.3f}:level=false", "-c:a", "aac", "-b:a", "192k",
            str(out)]


def final_cmd(video: Path, audio: Path, crf: int, fps: int, out: Path) -> list[str]:
    return [media.ffmpeg(), "-y", "-loglevel", "error", "-i", str(video), "-i", str(audio), "-map", "0:v", "-map", "1:a",
            "-c:v", "libx264", "-crf", str(crf), "-preset", "medium", "-pix_fmt", "yuv420p", "-r", str(fps), "-c:a", "copy",
            "-movflags", "+faststart", str(out)]


def loudness_gain(measured: float | None, target: float) -> float:
    """Gain for the second pass. Silence (or no reading) is left alone."""
    if measured is None or not math.isfinite(measured) or measured < -60:
        return 0.0
    return round(target - measured, 2)


def encode_audio(wav: Path, m4a: Path, gain: float, tp_target: float, runner: media.Runner = media.run,
                 tries: int = 4) -> tuple[float | None, list[str]]:
    """AAC raises the true peak by 0.5 to 2 dB: encode, measure, lower the limiter, until it holds."""
    notes = []
    limit_db = tp_target - 1.1
    tp = None
    for _ in range(tries):
        rc, out = runner(aac_cmd(wav, gain, limit_db, m4a), timeout=900)
        if rc:
            raise RuntimeError("encoding the sound failed: " + media.tail(out, 500))
        tp = media.measure_loudness(m4a, runner)["true_peak"]
        if tp is None or tp <= tp_target:
            return tp, notes
        limit_db -= (tp - tp_target) + 0.2
    notes.append(f"true peak {tp:.1f} dBTP is still above {tp_target:g} after {tries} tries")
    return tp, notes


# ---- the whole cut ----------------------------------------------------------------------------------------------
def cut(plan: Plan, runner: media.Runner = media.run, log: Callable = print,
        progress: Callable | None = None) -> dict:
    check_not_shown(plan)
    for ins in plan.inserts:
        if not html.encode(plan, ins, runner, log):
            raise PlanError(f"insert {ins.id} is not rendered yet (run `crewcut render {ins.kind}` first)")
    out = plan.output
    out.parent.mkdir(parents=True, exist_ok=True)
    base_end = base_frames(plan, runner)
    end = end_frame(plan, base_end)
    fps = plan.fps
    ps = pieces(plan, base_end, end)
    tmp = Path(str(out)[: -len(out.suffix)] + ".pieces") if out.suffix else Path(str(out) + ".pieces")
    tmp.mkdir(parents=True, exist_ok=True)
    files = []
    for n, p in enumerate(ps):
        f = tmp / f"{p.index:03d}-{piece_key(p)}.mkv"
        files.append(f)
        if f.is_file():
            continue
        part = f.with_suffix(".tmp.mkv")
        rc, o = runner(piece_cmd(plan, p, part), timeout=900)
        if rc:
            part.unlink(missing_ok=True)
            raise RuntimeError(f"piece {p.index} ({p.label}): {media.tail(o, 600)}")
        part.replace(f)
        if progress:
            progress(f"Cutting: picture piece {n + 1} of {len(ps)}", 0.6 * (n + 1) / len(ps))
    for f in tmp.glob("*.mkv"):
        if f not in files:
            f.unlink()                                  # pieces of an earlier plan
    listing = tmp / "list.txt"
    listing.write_text("".join(f"file '{f}'\n" for f in files), encoding="utf-8")
    stem = Path(str(out)[: -len(out.suffix)]) if out.suffix else out
    raw_video, raw_audio, m4a = Path(f"{stem}.raw.mkv"), Path(f"{stem}.raw.wav"), Path(f"{stem}.raw.m4a")
    g = audio_graph(plan, end)
    for note in g.notes:
        log("note: " + note)
    rc, o = runner(audio_cmd(g, raw_audio), timeout=1800)
    if rc:
        raise RuntimeError("sound: " + media.tail(o, 1500))
    rc, o = runner(concat_cmd(listing, g.seconds, raw_video), timeout=1800)
    if rc:
        raise RuntimeError("picture: " + media.tail(o, 1500))
    if progress:
        progress("Cutting: loudness", 0.75)
    target = float(plan.value("lufs", "edit_style.loudness_lufs", -14.0, section=plan.p.get("sound") or {}))
    tp_target = float(plan.pack.value("edit_style.true_peak_db", -1.5))
    before = media.measure_loudness(raw_audio, runner)["lufs"]
    gain = loudness_gain(before, target)
    notes = list(g.notes)
    if gain == 0.0 and (before is None or before < -60):
        notes.append("the sound is silent; loudness was not adjusted")
    tp, more = encode_audio(raw_audio, m4a, gain, tp_target, runner)
    notes += more + stage_notes(plan, base_end)
    notes += [f"{i}: left out of this cut ({why})" for i, why in plan.dropped.items()]
    final_tmp = out.with_name(out.stem + ".tmp" + out.suffix)
    rc, o = runner(final_cmd(raw_video, m4a, int(plan.p.get("crf") or 17), fps, final_tmp), timeout=3600)
    if rc:
        final_tmp.unlink(missing_ok=True)
        raise RuntimeError("final encode: " + media.tail(o, 800))
    final_tmp.replace(out)
    for f in (raw_video, raw_audio, m4a):
        f.unlink(missing_ok=True)
    after = media.measure_loudness(out, runner)
    info = {"plan": plan.path.name, "output": str(out), "frames": end, "seconds": round(end / fps, 2),
            "layout": plan.layout, "shots": shots(plan, base_end, end), "lufs_before": before, "lufs": after["lufs"],
            "true_peak": after["true_peak"], "target_lufs": target,
            "music_source": (plan.p.get("sound") or {}).get("music_source"), "notes": notes}
    Path(f"{stem}.cut.json").write_text(json.dumps(info, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return info
