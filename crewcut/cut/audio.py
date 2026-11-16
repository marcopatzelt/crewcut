"""Sound measurements: channel levels, sound to the end of a file, pauses, loudness and true peak.

Every measurement has three parts: a command builder (`*_cmd`), a pure parser (`parse_*`) that reads ffmpeg's text
output, and a thin wrapper that runs ffmpeg. The parsers are unit-tested with real ffmpeg output text.
The render step uses `measure_loudness()` and `loudness_problems()` for the finished mix.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from . import media
from .common import CutError

SPLIT_LEVELS = "channelsplit=channel_layout=stereo[L][R];[L]volumedetect[a];[R]volumedetect[b];[a][b]amix"
_NUM = r"(-?[\d.]+|-?inf|nan)"


def _db(v: str) -> float:
    v = v.strip().lower()
    if v in ("-inf", "inf", "nan"):
        return -99.0 if v != "inf" else 99.0
    return float(v)


# ---- channel levels and microphone check ------------------------------------------------------------------------
def channel_levels_cmd(src: Path, start: float = 0.0, seconds: float | None = None) -> list:
    argv = ["ffmpeg", "-nostdin", "-hide_banner"]
    if start:
        argv += ["-ss", f"{start:g}"]
    if seconds:
        argv += ["-t", f"{seconds:g}"]
    return argv + ["-i", str(src), "-vn", "-af", SPLIT_LEVELS, "-f", "null", "-"]


_VOLDET = re.compile(r"volumedetect_(\d+)[^\n]*mean_volume: " + _NUM + " dB")


def parse_channel_levels(text: str) -> list[float]:
    """Mean level per channel in dB, left first. ffmpeg prints the two results in any order; the filter number
    tells left (lower) from right (higher)."""
    found = {int(k): _db(v) for k, v in _VOLDET.findall(text)}
    return [found[k] for k in sorted(found)]


def channel_levels(src: Path, start: float = 0.0, seconds: float | None = None) -> list[float]:
    return parse_channel_levels(media.run(channel_levels_cmd(src, start, seconds), check=False).stderr)


def mic_verdict(levels: list[float]) -> dict:
    """Guess the sound source from the two channel levels.

    A radio microphone into the camera: the voice on one channel, the other near silent.
    Only the camera's own microphone: both channels alike and quiet. (A real episode had only the camera microphone
    and nobody noticed until the cut.)
    """
    if len(levels) < 2:
        return {"levels_db": levels or None, "verdict": "unknown", "channel": None,
                "message": "The sound channels could not be measured (mono file or no sound)."}
    left, right = levels[0], levels[1]
    if abs(left - right) > 10:
        side, ch = ("left", 0) if left > right else ("right", 1)
        return {"levels_db": [left, right], "verdict": "external_one_side", "channel": ch,
                "message": f"External microphone on the {side} channel. Plan and build put it on both sides."}
    if abs(left - right) < 3 and max(left, right) < -20:
        return {"levels_db": [left, right], "verdict": "camera_mic_suspected", "channel": None,
                "message": "WARNING: both channels are alike and quiet. Probably only the camera's own microphone "
                           "was recording and the external microphone is missing. Check the receiver, the "
                           "transmitter and the transmitter's own recording before recording more."}
    return {"levels_db": [left, right], "verdict": "stereo", "channel": None, "message": "Sound on both channels."}


def mic_check(src: Path, duration: float | None = None, seconds: float = 120.0) -> dict:
    """Measure two minutes, starting 30 s in (the start is often silent), or earlier in short files."""
    start = 30.0 if duration is None or duration > 60 else max(0.0, (duration or 0) / 4)
    return mic_verdict(channel_levels(src, start, seconds))


# ---- sound to the end of a file ---------------------------------------------------------------------------------
def level_windows_cmd(src: Path, channel: int, window: float = 10.0, rate: int = 48000) -> list:
    af = (f"pan=mono|c0=c{channel},aresample={rate},asetnsamples={int(rate * window)},"
          "astats=metadata=1:reset=1,ametadata=print:key=lavfi.astats.Overall.RMS_level")
    return ["ffmpeg", "-nostdin", "-hide_banner", "-i", str(src), "-vn", "-af", af, "-f", "null", "-"]


_RMS = re.compile(r"RMS_level=" + _NUM)


def parse_rms(text: str) -> list[float]:
    """RMS levels printed by astats + ametadata, in order; -inf (digital silence) becomes -99."""
    return [_db(v) for v in _RMS.findall(text)]


def silent_tail(left: list[float], right: list[float] | None = None, window: float = 10.0, silent_db: float = -50.0,
                limit_s: float = 30.0, duration: float | None = None) -> dict:
    """How long the end of a file is silent on the louder channel.

    A real episode lost 110 s: the radio microphone stopped while the speaker went on talking, and nobody noticed
    until the cut. A few seconds of silence after the last sentence are normal; more than limit_s is a WARNING.
    """
    lv = [max(a, b) for a, b in zip(left, right, strict=True)] if right and len(right) == len(left) else list(left)
    if not lv:
        return {"verdict": "unknown", "silent_tail_seconds": None, "last_sound_at_seconds": None,
                "message": "The level over the file could not be measured."}
    n = 0
    while n < len(lv) and lv[-1 - n] < silent_db:
        n += 1
    total = float(duration) if duration else len(lv) * window
    last = min(total, (len(lv) - n) * window)
    still = round(total - last, 1)
    out = {"windows_db": [round(v) for v in lv], "window_seconds": window, "silent_tail_seconds": still,
           "last_sound_at_seconds": round(last, 1), "duration_seconds": round(total, 1), "verdict": "ok",
           "message": f"Sound until {last:.0f} s of {total:.0f} s, then {still:.0f} s of silence."}
    if still > limit_s:
        out["verdict"] = "silent_tail"
        out["message"] = (f"WARNING: the last {still:.0f} s are silent (below {silent_db:g} dB on every channel): "
                          f"sound only until about {last:.0f} s of {total:.0f} s. Look at a frame after {last:.0f} s "
                          "now. If someone still speaks there, the sound is missing (microphone off) and that part "
                          "has to be recorded again.")
    return out


def sound_to_end(src: Path, channels: int = 2, duration: float | None = None, window: float = 10.0,
                 silent_db: float = -50.0, limit_s: float = 30.0) -> dict:
    """Level of the louder channel in windows of 10 s over the WHOLE file."""
    left = parse_rms(media.run(level_windows_cmd(src, 0, window), check=False).stderr)
    right = parse_rms(media.run(level_windows_cmd(src, 1, window), check=False).stderr) if channels > 1 else None
    return silent_tail(left, right, window, silent_db, limit_s, duration)


# ---- pauses ------------------------------------------------------------------------------------------------------
def silencedetect_cmd(src: Path, noise_db: float = -38.0, min_seconds: float = 0.12) -> list:
    return ["ffmpeg", "-nostdin", "-hide_banner", "-i", str(src), "-af",
            f"silencedetect=noise={noise_db:g}dB:d={min_seconds:g}", "-f", "null", "-"]


_SIL = re.compile(r"silence_(start|end): (-?[\d.]+)")


def parse_silences(text: str, duration: float | None = None) -> list[tuple[float, float]]:
    """Pauses as (start, end). A pause that runs to the end of the file has no silence_end line in some ffmpeg
    versions; with the duration known it ends there."""
    out: list[tuple[float, float]] = []
    start = None
    for kind, v in _SIL.findall(text):
        if kind == "start":
            start = max(0.0, float(v))
        elif start is not None:
            out.append((round(start, 4), round(float(v), 4)))
            start = None
    if start is not None and duration is not None and duration > start:
        out.append((round(start, 4), round(float(duration), 4)))
    return out


def format_silences(sil: list[tuple[float, float]]) -> str:
    return "".join(f"{a:g} {b:g}\n" for a, b in sil)


def read_silences(text: str) -> list[tuple[float, float]]:
    out = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            out.append((float(parts[0]), float(parts[1])))
    return out


# ---- loudness (EBU R128) -----------------------------------------------------------------------------------------
def ebur128_cmd(src: Path) -> list:
    return ["ffmpeg", "-nostdin", "-hide_banner", "-nostats", "-i", str(src), "-vn",
            "-af", "ebur128=peak=true:framelog=quiet", "-f", "null", "-"]


def parse_ebur128(text: str) -> dict:
    """Integrated loudness, range and true peak from the Summary block of ffmpeg's ebur128 filter."""
    i = text.rfind("Summary:")
    block = text[i:] if i >= 0 else text

    def grab(pattern: str) -> float | None:
        m = re.search(pattern, block)
        return _db(m.group(1)) if m else None

    return {
        "integrated_lufs": grab(r"\bI:\s+" + _NUM + r"\s+LUFS"),
        "threshold_lufs": grab(r"Integrated loudness:\s+I:[^\n]*\n\s+Threshold:\s+" + _NUM),
        "lra_lu": grab(r"\bLRA:\s+" + _NUM + r"\s+LU\b"),
        "lra_low_lufs": grab(r"LRA low:\s+" + _NUM),
        "lra_high_lufs": grab(r"LRA high:\s+" + _NUM),
        "true_peak_dbtp": grab(r"Peak:\s+" + _NUM + r"\s+dBFS"),
    }


def measure_loudness(src: Path) -> dict:
    """Integrated loudness (LUFS) and true peak (dBTP) of a file's sound."""
    m = parse_ebur128(media.run(ebur128_cmd(src), check=False).stderr)
    if m["integrated_lufs"] is None:
        raise CutError(f"no loudness measured for {Path(src).name} (no sound track?)")
    return m


def loudness_problems(m: dict, target_lufs: float | None = None, max_true_peak: float | None = None,
                      tolerance: float = 1.0) -> list[str]:
    """What is off compared with the style pack (edit_style.loudness_lufs and true_peak_db unless given)."""
    if target_lufs is None or max_true_peak is None:
        from .. import brand
        pack = brand.load()
        target_lufs = pack.value("edit_style.loudness_lufs", -14.0) if target_lufs is None else target_lufs
        max_true_peak = pack.value("edit_style.true_peak_db", -1.5) if max_true_peak is None else max_true_peak
    out = []
    i, tp = m.get("integrated_lufs"), m.get("true_peak_dbtp")
    if i is None:
        out.append("integrated loudness was not measured")
    elif abs(i - target_lufs) > tolerance:
        out.append(f"integrated loudness {i:.1f} LUFS is more than {tolerance:g} LU away from {target_lufs:g} LUFS")
    if tp is None:
        out.append("true peak was not measured")
    elif tp > max_true_peak:
        out.append(f"true peak {tp:.1f} dBTP is above {max_true_peak:g} dBTP")
    return out


# ---- loudnorm (two passes) ---------------------------------------------------------------------------------------
def loudnorm_filter(i: float, tp: float, lra: float, measured: dict | None = None) -> str:
    base = f"loudnorm=I={i:g}:TP={tp:g}:LRA={lra:g}"
    if not measured:
        return base + ":print_format=json"
    keys = [("measured_I", "input_i"), ("measured_TP", "input_tp"), ("measured_LRA", "input_lra"),
            ("measured_thresh", "input_thresh"), ("offset", "target_offset")]
    return base + ":linear=true:" + ":".join(f"{k}={measured[v]}" for k, v in keys)


def parse_loudnorm(text: str) -> dict:
    """The JSON block that loudnorm prints with print_format=json (the last one, if there are several)."""
    found = re.findall(r"\{[^{}]+\"input_i\"[^{}]+\}", text)
    if not found:
        raise CutError("loudnorm printed no measurement")
    return json.loads(found[-1])
