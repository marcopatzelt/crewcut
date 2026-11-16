"""Shared parts of the cut checks: report, levels, exceptions, style pack loading, small helpers.

Levels, from bad to fine:
  ERROR  breaks a rule; the build does not go to the user
  CHECK  a person must look or listen (goes on the listening list when it has a time)
  NOTE   for information
  OK     checked and fine
An exception file ({"<check id>": "reason, date, who"}) turns an ERROR or CHECK with that id into OK with the reason.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[3]
LEVELS = ("ERROR", "CHECK", "NOTE", "OK")


def load_pack(pack_dir: str | None = None):
    """The active style pack through crewcut.brand (studio/brand, else packs/neutral)."""
    try:
        from crewcut import brand
    except ImportError:
        sys.path.insert(0, str(APP_ROOT))
        from crewcut import brand
    return brand.load(pack_dir) if pack_dir else brand.load()


def tc(t: float | None) -> str:
    """Seconds as m:ss.s, the way people name a spot in a video."""
    if t is None:
        return "-"
    m, s = divmod(max(0.0, float(t)), 60)
    return f"{int(m)}:{s:04.1f}"


def version_of(path: str | Path) -> str:
    m = re.search(r"v(\d+)", Path(path).stem)
    return f"v{m.group(1)}" if m else Path(path).stem


def load_exceptions(path: Path | None) -> dict:
    if path and path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except ValueError:
            return {}
    return {}


class Report:
    def __init__(self, exceptions: dict | None = None):
        self.items: list[dict] = []
        self.exceptions = exceptions or {}

    def add(self, area: str, level: str, cid: str, text: str, t: float | None = None, fix: str | None = None):
        assert level in LEVELS, level
        if level in ("ERROR", "CHECK") and cid in self.exceptions:
            level, text = "OK", f"{text} (exception: {self.exceptions[cid]})"
        self.items.append({"area": area, "level": level, "id": cid, "text": text, "time": t, "fix": fix})

    def count(self) -> dict:
        return {k: sum(1 for i in self.items if i["level"] == k) for k in LEVELS}

    def listening_list(self) -> list[dict]:
        return sorted(
            (i for i in self.items if i["level"] == "CHECK" and i["time"] is not None), key=lambda i: i["time"]
        )

    def print(self, areas: list[str], out=sys.stdout):
        order = {k: n for n, k in enumerate(LEVELS)}
        for area in areas:
            its = sorted(
                (i for i in self.items if i["area"] == area), key=lambda i: (order[i["level"]], i["time"] or 0)
            )
            if its:
                print(f"\n{area}", file=out)
            for i in its:
                at = f" [{tc(i['time'])}]" if i["time"] is not None else ""
                print(f"  {i['level']:<6}{at} {i['text']}", file=out)
                if i["fix"] and i["level"] in ("ERROR", "CHECK"):
                    print(f"         -> {i['fix']}", file=out)
        ll = self.listening_list()
        if ll:
            print("\nListening list (video time):", file=out)
            for i in ll:
                print(f"  {tc(i['time'])}  {i['id']}", file=out)


def manual_list(general: list[str], pack, step: str) -> list[str]:
    """The manual checklist: general items, then the rules of this step from the style pack."""
    out = [f"[ ] {g}" for g in general]
    for r in pack.rules(step) if pack is not None else []:
        out.append(f"[ ] {r['rule']} ({r['date']}{', ' + r['source'] if r.get('source') else ''})")
    return out


def run(argv, text=True, **kw):
    return subprocess.run([str(a) for a in argv], capture_output=True, text=text, **kw)


def duration(path) -> float | None:
    """Length of a media file in seconds (ffprobe)."""
    p = run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path])
    try:
        return float(p.stdout.strip())
    except ValueError:
        return None


def parse_ebur128(stderr: str) -> tuple[float | None, float | None]:
    """Integrated loudness (LUFS) and true peak (dBTP) from the summary of ffmpeg's ebur128 filter."""
    i = re.findall(r"I:\s+(-?[\d.]+) LUFS", stderr)
    pk = re.findall(r"Peak:\s+(-?[\d.]+) dBFS", stderr)
    return (float(i[-1]) if i else None), (float(pk[-1]) if pk else None)


def parse_volumedetect(stderr: str) -> list[float]:
    return [float(x) for x in re.findall(r"mean_volume: (-?[\d.]+) dB", stderr)]


def loudness(path) -> tuple[float | None, float | None]:
    p = run(
        [
            "ffmpeg",
            "-nostdin",
            "-hide_banner",
            "-i",
            path,
            "-vn",
            "-af",
            "ebur128=peak=true:framelog=quiet",
            "-f",
            "null",
            "-",
        ]
    )
    return parse_ebur128(p.stderr)


def channel_levels(path) -> list[float]:
    p = run(
        [
            "ffmpeg",
            "-nostdin",
            "-hide_banner",
            "-i",
            path,
            "-af",
            "channelsplit=channel_layout=stereo[L][R];[L]volumedetect[a];[R]volumedetect[b];[a][b]amix",
            "-f",
            "null",
            "-",
        ]
    )
    return parse_volumedetect(p.stderr)


def loudness_verdict(
    lufs: float | None, peak: float | None, target: float, window: list[float], peak_max: float
) -> tuple[str, str]:
    """ERROR or OK for the integrated loudness and the true peak of an export."""
    if lufs is None:
        return "CHECK", "loudness not measured (ffmpeg ebur128 gave nothing)"
    lo, hi = target + window[0], target + window[1]
    ok = lo <= lufs <= hi and (peak is None or peak <= peak_max)
    return ("OK" if ok else "ERROR"), (
        f"{lufs:.1f} LUFS, true peak {peak} dBTP (target {lo:.1f} to {hi:.1f} LUFS, peak at most {peak_max:.1f})"
    )
