"""Small helpers around external programs: run a command, find a program, parse ffmpeg's loudness summary.

Every function that starts a program takes a `runner` so tests can pass a fake and assert on the argument list.
"""

from __future__ import annotations

import math
import os
import re
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

Runner = Callable[..., tuple[int, str]]


def run(cmd: list[str], timeout: float = 600, cwd: Path | str | None = None) -> tuple[int, str]:
    """Run a command (never through a shell). Returns (exit code, stdout+stderr). A timeout returns code 124."""
    try:
        r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, timeout=timeout, cwd=cwd)
    except subprocess.TimeoutExpired as e:
        def text(b):
            return b.decode("utf-8", "replace") if isinstance(b, bytes) else (b or "")
        return 124, text(e.stdout) + text(e.stderr) + f"\ntimed out after {timeout:.0f} s"
    except FileNotFoundError as e:
        return 127, f"program not found: {e.filename}"
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def program(name: str, env: str | None = None) -> str:
    """Path of a program: from the env variable when set, else from PATH, else the bare name."""
    if env and os.environ.get(env):
        return os.environ[env]
    return shutil.which(name) or name


def ffmpeg() -> str:
    return program("ffmpeg", "CREWCUT_FFMPEG")


def ffprobe() -> str:
    return program("ffprobe", "CREWCUT_FFPROBE")


def node() -> str:
    return program("node", "CREWCUT_NODE")


_NUM = r"(-?(?:\d+(?:\.\d+)?|inf))"


def _num(s: str) -> float:
    return -math.inf if s == "-inf" else (math.inf if s == "inf" else float(s))


def parse_loudness(text: str) -> dict:
    """Parse the summary of ffmpeg's ebur128 filter (with peak=true): integrated loudness and true peak.

    Returns {"lufs": float or None, "true_peak": float or None}. Silence gives -70 LUFS and -inf dBFS.
    """
    lufs = peak = None
    summary = text[text.rfind("Summary:"):] if "Summary:" in text else text
    for line in summary.splitlines():
        s = line.strip()
        m = re.match(rf"^I:\s+{_NUM}\s+LUFS", s)
        if m:
            lufs = _num(m.group(1))
        m = re.match(rf"^Peak:\s+{_NUM}\s+dBFS", s)
        if m:
            peak = _num(m.group(1))
    return {"lufs": lufs, "true_peak": peak}


def loudness_cmd(path: Path | str) -> list[str]:
    return [ffmpeg(), "-hide_banner", "-nostats", "-i", str(path), "-af", "ebur128=peak=true", "-f", "null", "-"]


def measure_loudness(path: Path | str, runner: Runner = run) -> dict:
    rc, out = runner(loudness_cmd(path), timeout=900)
    if rc:
        raise RuntimeError(f"loudness measurement failed for {path}: {out[-400:]}")
    return parse_loudness(out)


def frame_count_cmd(path: Path | str) -> list[str]:
    return [ffprobe(), "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=nb_frames,duration,r_frame_rate",
            "-of", "default=noprint_wrappers=1", str(path)]


def parse_frame_count(text: str, fps: int) -> int | None:
    """nb_frames from ffprobe; when the container has none (mkv), duration x fps."""
    vals = dict(line.split("=", 1) for line in text.splitlines() if "=" in line)
    nb = vals.get("nb_frames", "N/A")
    if nb.isdigit() and int(nb) > 0:
        return int(nb)
    try:
        return int(round(float(vals.get("duration", "")) * fps))
    except ValueError:
        return None


def frame_count(path: Path | str, fps: int, runner: Runner = run) -> int:
    rc, out = runner(frame_count_cmd(path), timeout=300)
    n = parse_frame_count(out, fps) if rc == 0 else None
    if not n:
        raise RuntimeError(f"cannot read the frame count of {path}: {out[-300:]}")
    return n


def valid_png(path: Path, size: tuple[int, int] | None = None) -> bool:
    """A complete PNG (decodes to the end), optionally of an exact size."""
    try:
        from PIL import Image
        with Image.open(path) as im:
            im.load()
            return size is None or im.size == tuple(size)
    except Exception:
        return False


def tail(text: str, n: int = 600) -> str:
    return text.strip()[-n:]
