"""Run ffmpeg and ffprobe. The only place in crewcut.cut that starts a media program (tests replace `run`)."""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from .common import CutError


def run(argv: list, *, check: bool = True, binary: bool = False, timeout: float | None = None,
        ) -> subprocess.CompletedProcess:
    """Run a program and capture its output. check=True raises CutError with the end of stderr on failure."""
    args = [str(a) for a in argv]
    if shutil.which(args[0]) is None:
        raise CutError(f"{args[0]} is not installed (it is part of the Crewcut image)")
    p = subprocess.run(args, capture_output=True, text=not binary, timeout=timeout)
    if check and p.returncode:
        err = p.stderr if isinstance(p.stderr, str) else p.stderr.decode("utf-8", "replace")
        raise CutError(f"{Path(args[0]).name} failed: {err[-3000:].strip()}")
    return p


def probe_cmd(path: Path) -> list:
    return ["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)]


def probe(path: Path) -> dict:
    return json.loads(run(probe_cmd(path)).stdout)


def duration(info: dict) -> float | None:
    try:
        return float(info["format"]["duration"])
    except (KeyError, TypeError, ValueError):
        return None


def video_stream(info: dict) -> dict | None:
    for s in info.get("streams", []):
        if s.get("codec_type") == "video" and not (s.get("disposition") or {}).get("attached_pic"):
            return s
    return None


def audio_streams(info: dict) -> list[dict]:
    return [s for s in info.get("streams", []) if s.get("codec_type") == "audio"]


def is_hdr(stream: dict) -> bool:
    return stream.get("color_transfer") in ("smpte2084", "arib-std-b67") or any(
        "DOVI" in s.get("side_data_type", "") for s in stream.get("side_data_list", []) or [])


def rotation(stream: dict) -> int:
    for s in stream.get("side_data_list", []) or []:
        if "rotation" in s:
            return int(round(float(s["rotation"])))
    try:
        return int((stream.get("tags") or {}).get("rotate", 0))
    except ValueError:
        return 0


def created_at(info: dict) -> datetime | None:
    """Recording start from the container's creation_time tag (cameras write it; 1 s resolution)."""
    tags = (info.get("format") or {}).get("tags") or {}
    raw = tags.get("creation_time") or next(
        (((s.get("tags") or {}).get("creation_time")) for s in info.get("streams", []) if (s.get("tags") or {}).get(
            "creation_time")), None)
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def summary(info: dict) -> dict:
    """The few probe values a person needs, for reports (the full probe stays in the ingest file)."""
    v = video_stream(info) or {}
    a = audio_streams(info)
    return {
        "duration": duration(info),
        "video": {k: v.get(k) for k in ("codec_name", "width", "height", "avg_frame_rate", "pix_fmt", "color_transfer")}
        if v else None,
        "audio": [{"codec": s.get("codec_name"), "channels": s.get("channels"), "rate": s.get("sample_rate")} for s in a],
    }
