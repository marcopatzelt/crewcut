"""Music bed for a Short (`crewcut render music-bed`): a music track under the Short's voice, mixed and brought to the
loudness target, with a music source file next to the result.

Why its own step: a Short's sound is the voice plus one quiet music bed, and the rights to that music are written down
before anything is published. Rule: only music with clear rights. The track needs source info with a licence
(`<track stem>.source.json` next to the track, `--source`, or `--licence`); without a licence the step refuses. The music
of a long video is no exception: it goes under a Short only when its licence is stated.

The steps, each an ffmpeg run (command builders below, so tests can check the argument lists):
1. measure the voice and the used part of the track (EBU R128, both as 48 kHz stereo, as they are mixed);
2. set the music `music_db` below the voice's loudness (pack `edit_style.shorts.music_db`, neutral -15 dB), duck it
   under speech (sidechaincompress keyed by the voice; the threshold follows the voice's loudness, so a quiet
   recording ducks as much as a loud one), cut a hole of `music_hole_s` (0.5 s) before every punchline time with short
   ramps (the music comes back on the punchline), fade in and out, mix with the voice;
3. loudness: the first pass aims `limiter_headroom_db` (1.4 dB) above `loudness_lufs` (-14) because the limiter takes
   about that much back; each pass is measured, the gain corrected and the limiter lowered until the result is within
   0.5 LU of the target and the true peak under `true_peak_db`.

The result is `<voice stem>-bed-vNNN.wav` (24 bit, 48 kHz, voice length plus `end_tail_s`) and `<result>.music.json`:
track, start second, licence, credit line for the description, how the track was made, how the bed was made (levels,
holes, passes, measured loudness) and a short list of places for a human to listen to.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from .. import brand
from . import media
from .plan import PlanError

STEREO = "aresample=48000,aformat=sample_rates=48000:channel_layouts=stereo"
HOLE_GAIN = 0.05            # music level inside a hole (-26 dB), as in the cut's gaps
HOLE_RAMP_S = 0.05          # ramps into and out of a hole, so it does not click
DUCK_BELOW_DB = 14.0        # ducking starts this far below the voice's loudness
DUCK_RATIO, DUCK_ATTACK_MS, DUCK_RELEASE_MS = 2.0, 25, 450
LUFS_TOLERANCE = 0.5
PASSES = 4
NO_LICENCE = {"", "?", "-", "none", "no", "unknown", "unclear", "n/a", "na", "tbd", "todo", "unknown licence",
              "unknown license", "not stated"}


class MusicRefused(PlanError):
    """The track has no stated licence, so it is not used."""


@dataclass
class Bed:
    """How the bed is made. Defaults come from the style pack (edit_style.shorts)."""
    music_db: float = -15.0
    hole_s: float = 0.5
    tail_s: float = 1.0
    lufs: float = -14.0
    headroom_db: float = 1.4
    true_peak_db: float = -1.5
    fade_in_s: float = 0.5
    fade_out_s: float = 1.2

    @classmethod
    def from_pack(cls, pack: brand.Pack | None = None, **over: float | None) -> Bed:
        pack = pack or brand.load()

        def v(key: str, default: float) -> float:
            return float(pack.value(f"edit_style.shorts.{key}", default))

        b = cls(music_db=v("music_db", -15.0), hole_s=v("music_hole_s", 0.5), tail_s=v("end_tail_s", 1.0),
                lufs=v("loudness_lufs", float(pack.value("edit_style.loudness_lufs", -14.0))),
                headroom_db=v("limiter_headroom_db", 1.4),
                true_peak_db=float(pack.value("edit_style.true_peak_db", -1.5)))
        for k, x in over.items():
            if x is not None:
                setattr(b, k, float(x))
        return b


# ---- source info -------------------------------------------------------------------------------------------------
def source_file_for(track: Path) -> Path:
    return track.with_name(track.stem + ".source.json")


def source_info(track: Path, source: Path | None = None, **given: str | None) -> dict:
    """The track's source info: a JSON file (`source`, else `<track stem>.source.json`) plus values given directly
    (licence, credit, made). Refuses a track without a licence."""
    info: dict = {}
    f = source or source_file_for(track)
    if source is not None and not source.is_file():
        raise PlanError(f"source info not found: {source}")
    if f.is_file():
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except ValueError as e:
            raise PlanError(f"source info is not valid JSON: {f} ({e})") from e
        if not isinstance(d, dict):
            raise PlanError(f"source info must be a JSON object: {f}")
        us = d.pop("license", None)                  # the US spelling counts the same
        info.update(d)
        if not info.get("licence"):
            info["licence"] = us
        info["source_file"] = str(f)
    info.update({k: v for k, v in given.items() if v})
    lic = " ".join(str(info.get("licence") or "").split())
    if lic.lower().rstrip(".") in NO_LICENCE:
        raise MusicRefused(
            f"{track.name}: no licence stated, so Crewcut does not use it (only music with clear rights; the music "
            f"of a long video is no exception). Write the licence into {f.name} next to the track, e.g. "
            '{"licence": "CC0 1.0", "credit": "Music: ...", "made": "how the track was made"}, or pass --licence.')
    info["licence"] = lic
    return info


# ---- commands ----------------------------------------------------------------------------------------------------
def duration_cmd(path: Path) -> list[str]:
    return [media.ffprobe(), "-v", "error", "-show_entries", "format=duration", "-of",
            "default=noprint_wrappers=1:nokey=1", str(path)]


def duration(path: Path, runner: media.Runner = media.run) -> float:
    rc, out = runner(duration_cmd(path), timeout=120)
    vals = re.findall(r"^\s*(\d+(?:\.\d+)?)\s*$", out or "", re.M)
    if rc or not vals or float(vals[-1]) <= 0:
        raise RuntimeError(f"cannot read the length of {path}: {media.tail(out or '', 300)}")
    return float(vals[-1])


def loudness_cmd(path: Path, start: float = 0.0, seconds: float | None = None) -> list[str]:
    """EBU R128 of a file (or a part of it) as it is mixed: 48 kHz stereo."""
    cmd = [media.ffmpeg(), "-hide_banner", "-nostats"]
    if start:
        cmd += ["-ss", f"{start:.3f}"]
    if seconds:
        cmd += ["-t", f"{seconds:.3f}"]
    return cmd + ["-i", str(path), "-af", f"{STEREO},ebur128=peak=true", "-f", "null", "-"]


def measure(path: Path, runner: media.Runner = media.run, start: float = 0.0, seconds: float | None = None) -> dict:
    rc, out = runner(loudness_cmd(path, start, seconds), timeout=900)
    if rc:
        raise RuntimeError(f"loudness measurement failed for {path}: {media.tail(out, 400)}")
    return media.parse_loudness(out)


def holes(punches: list[float], hole_s: float, seconds: float) -> list[tuple[float, float]]:
    """A music hole of hole_s seconds before every punchline time."""
    out = []
    for p in sorted(float(x) for x in punches):
        if not 0 < p <= seconds:
            raise PlanError(f"punchline at {p:g} s lies outside the Short (0 to {seconds:.2f} s)")
        out.append((round(max(0.0, p - hole_s), 3), round(p, 3)))
    return out


def hole_expr(hs: list[tuple[float, float]], ramp: float = HOLE_RAMP_S, floor: float = HOLE_GAIN) -> str:
    """ffmpeg volume expression of t: 1 outside the holes, `floor` inside, linear ramps of `ramp` s around each."""
    if not hs:
        return "1"
    inside = [f"clip(min((t-{a - ramp:.3f})/{ramp:g},({b + ramp:.3f}-t)/{ramp:g}),0,1)" for a, b in hs]
    expr = inside[0]
    for x in inside[1:]:
        expr = f"max({expr},{x})"
    return f"1-{1 - floor:g}*{expr}"


def duck_threshold(voice_lufs: float) -> float:
    """sidechaincompress threshold (linear) below the voice's loudness, inside the filter's range."""
    return min(1.0, max(0.001, 10 ** ((voice_lufs - DUCK_BELOW_DB) / 20)))


def mix_cmd(voice: Path, track: Path, start: float, seconds: float, music_gain_db: float, threshold: float,
            hs: list[tuple[float, float]], bed: Bed, loop: bool, out: Path) -> list[str]:
    """Voice plus music: music level, holes, fades, ducking under the voice, mix. 32-bit float WAV, no limiter."""
    T = seconds
    fin, fout = min(bed.fade_in_s, T / 3), min(bed.fade_out_s, T / 3)
    music_in = (["-stream_loop", "-1"] if loop else []) + (["-ss", f"{start:.3f}"] if start else []) + ["-i", str(track)]
    hole = f",asetnsamples=n=480:p=0,volume=volume='{hole_expr(hs)}':eval=frame" if hs else ""
    f = [
        f"[0:a]{STEREO},apad=whole_dur={T:.3f},atrim=0:{T:.3f},asplit=2[vo][key]",
        f"[1:a]{STEREO},atrim=0:{T:.3f},asetpts=PTS-STARTPTS,volume={music_gain_db:.2f}dB{hole},"
        f"afade=t=in:d={fin:.3f},afade=t=out:st={T - fout:.3f}:d={fout:.3f}[mu]",
        f"[mu][key]sidechaincompress=threshold={threshold:.5f}:ratio={DUCK_RATIO:g}:attack={DUCK_ATTACK_MS}:"
        f"release={DUCK_RELEASE_MS}:makeup=1[duck]",
        "[vo][duck]amix=inputs=2:normalize=0:duration=first[mix]",
    ]
    return [media.ffmpeg(), "-y", "-loglevel", "error", "-i", str(voice), *music_in, "-filter_complex", ";".join(f),
            "-map", "[mix]", "-c:a", "pcm_f32le", "-ar", "48000", "-t", f"{T:.3f}", str(out)]


def master_cmd(mix: Path, gain_db: float, limit_db: float, out: Path) -> list[str]:
    """Gain and limiter, 24-bit WAV."""
    return [media.ffmpeg(), "-y", "-loglevel", "error", "-i", str(mix), "-af",
            f"volume={gain_db:.2f}dB,alimiter=limit={10 ** (limit_db / 20):.4f}:level=false",
            "-c:a", "pcm_s24le", "-ar", "48000", str(out)]


def next_bed(voice: Path) -> Path:
    """<voice stem>-bed-vNNN.wav next to the voice, the next free version."""
    pat = re.compile(rf"^{re.escape(voice.stem)}-bed-v(\d{{3}})\b")
    n = max((int(m.group(1)) for f in voice.parent.glob(f"{voice.stem}-bed-v*") if (m := pat.match(f.name))),
            default=0) + 1
    return voice.with_name(f"{voice.stem}-bed-v{n:03d}.wav")


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def _clock(s: float) -> str:
    return f"{int(s // 60)}:{s % 60:04.1f}"


def _audible(m: dict) -> bool:
    return m.get("lufs") is not None and math.isfinite(m["lufs"]) and m["lufs"] > -60


# ---- the bed -----------------------------------------------------------------------------------------------------
def music_bed(voice: Path, track: Path, out: Path | None = None, *, punches: list[float] | tuple = (),
              start: float = 0.0, bed: Bed | None = None, source: dict | None = None,
              runner: media.Runner = media.run, log: Callable = print) -> dict:
    """Mix the track under the voice and write the result plus <result stem>.music.json. Returns that info."""
    voice, track = Path(voice).resolve(), Path(track).resolve()
    for f, what in ((voice, "voice"), (track, "music track")):
        if not f.is_file():
            raise PlanError(f"{what} not found: {f}")
    source = source if source is not None else source_info(track)       # refuses before any program runs
    if " ".join(str(source.get("licence") or "").split()).lower().rstrip(".") in NO_LICENCE:
        raise MusicRefused(f"{track.name}: no licence stated, so Crewcut does not use it (only music with clear rights)")
    bed = bed or Bed.from_pack()
    out = Path(out).resolve() if out else next_bed(voice)
    if out.exists():
        raise PlanError(f"{out.name} exists; a bed is never overwritten, use a new version")
    if start < 0:
        raise PlanError("the start second must be at least 0")
    T = round(duration(voice, runner) + max(0.0, bed.tail_s), 3)
    track_len = duration(track, runner)
    if start >= track_len:
        raise PlanError(f"start {start:g} s lies after the end of the track ({track_len:.1f} s)")
    loop = track_len - start < T
    hs = holes(list(punches), bed.hole_s, T)
    v = measure(voice, runner)
    if not _audible(v):
        raise PlanError(f"the voice is silent: {voice.name}")
    m = measure(track, runner, start, min(T, track_len - start))
    if not _audible(m):
        raise PlanError(f"the used part of the track is silent: {track.name} from {start:g} s")
    gain = round(v["lufs"] + bed.music_db - m["lufs"], 2)
    threshold = duck_threshold(v["lufs"])
    notes: list[str] = []
    out.parent.mkdir(parents=True, exist_ok=True)
    mix = out.with_name(out.stem + ".mix.wav")
    tmp = out.with_name(out.stem + ".tmp.wav")
    try:
        rc, o = runner(mix_cmd(voice, track, start, T, gain, threshold, hs, bed, loop, mix), timeout=900)
        if rc:
            raise RuntimeError("mixing the music bed failed: " + media.tail(o, 600))
        first = media.measure_loudness(mix, runner)
        g = round(bed.lufs + bed.headroom_db - (first["lufs"] if _audible(first) else bed.lufs), 2)
        limit = bed.true_peak_db - 0.5
        passes: list[dict] = []
        for _ in range(PASSES):
            rc, o = runner(master_cmd(mix, g, limit, tmp), timeout=900)
            if rc:
                raise RuntimeError("the loudness pass failed: " + media.tail(o, 600))
            r = media.measure_loudness(tmp, runner)
            passes.append({"gain_db": g, "limit_db": round(limit, 2), "lufs": r["lufs"], "true_peak": r["true_peak"]})
            ok_lufs = r["lufs"] is not None and abs(r["lufs"] - bed.lufs) <= LUFS_TOLERANCE
            ok_peak = r["true_peak"] is None or r["true_peak"] <= bed.true_peak_db
            if ok_lufs and ok_peak:
                break
            if not ok_peak:
                limit -= (r["true_peak"] - bed.true_peak_db) + 0.2
            if not ok_lufs and r["lufs"] is not None:
                g = round(g + bed.lufs - r["lufs"], 2)
        else:
            notes.append(f"after {PASSES} passes: {passes[-1]['lufs']} LUFS (target {bed.lufs:g}), true peak "
                         f"{passes[-1]['true_peak']} dBTP (limit {bed.true_peak_db:g})")
        tmp.replace(out)
    finally:
        mix.unlink(missing_ok=True)
        tmp.unlink(missing_ok=True)
    if not source.get("credit"):
        notes.append("no credit line in the source info: add one if the licence asks for it in the description")
    listen = [f"{_clock(a)}-{_clock(b)} music hole before the punchline at {_clock(b)}" for a, b in hs]
    if loop:
        listen.append(f"{_clock(track_len - start)} the track ends and starts again from 0:00 (loop)")
    listen.append(f"{_clock(max(0.0, T - min(bed.fade_out_s, T / 3)))} music fades out to the end ({_clock(T)})")
    extra = {k: v for k, v in source.items() if k not in ("licence", "credit", "made", "source_file")}
    info = {
        "output": str(out), "created": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "track": str(track), "track_sha256": _sha256(track), "start_s": start, "seconds": T, "loops": loop,
        "licence": source["licence"], "credit": source.get("credit") or "", "made": source.get("made") or "",
        "source_info": source.get("source_file"), "source_extra": extra or None,
        "voice": str(voice),
        "bed": {**asdict(bed), "voice_lufs": v["lufs"], "music_lufs": m["lufs"], "music_gain_db": gain,
                "duck": {"threshold": round(threshold, 5), "ratio": DUCK_RATIO, "attack_ms": DUCK_ATTACK_MS,
                         "release_ms": DUCK_RELEASE_MS, "below_voice_db": DUCK_BELOW_DB},
                "holes": [list(h) for h in hs], "hole_gain": HOLE_GAIN, "passes": passes},
        "lufs": passes[-1]["lufs"], "true_peak": passes[-1]["true_peak"], "listen": listen, "notes": notes,
    }
    info_path = out.with_name(out.stem + ".music.json")
    info_path.write_text(json.dumps(info, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    info["music_source"] = str(info_path)
    for n in notes:
        log("note: " + n)
    return info
