"""Helpers shared by the render tests (fake runner, sample plan, words). No program is run."""

from __future__ import annotations

import json
from pathlib import Path

WORDS = [
    {"w": "This", "s": 0.4, "e": 0.6}, {"w": "costs", "s": 1.0, "e": 1.3}, {"w": "about", "s": 1.4, "e": 1.6},
    {"w": "thirty", "s": 2.0, "e": 2.3}, {"w": "cents.", "s": 2.4, "e": 2.7}, {"w": "A", "s": 5.0, "e": 5.1},
    {"w": "third", "s": 5.2, "e": 5.5}, {"w": "Thirty,", "s": 8.0, "e": 8.3}, {"w": "people", "s": 9.0, "e": 9.4},
]


def basic_plan(**over) -> dict:
    p = {
        "words": "work/words-v001.json",
        "base": {"color": "soft", "seconds": 12},
        "inserts": [
            {"id": "s1", "kind": "2d", "scene": "counter", "start": 1.0, "end": 3.0,
             "cues": {"value": {"word": "thirty"}, "label": 4}, "data": {"label": "Per million", "value": "30"}},
            {"id": "k1", "kind": "2d", "scene": "keyword", "start": 4.0, "end": 6.0, "transparent": True,
             "data": {"text": "LOCAL"}},
        ],
        "sound": {},
        "output": "export/out-v001.mp4",
    }
    p.update(over)
    return p


def loudness_text(lufs: float, peak: float) -> str:
    return (f"[Parsed_ebur128_0 @ 0x1] Summary:\n\n  Integrated loudness:\n    I:         {lufs:.1f} LUFS\n"
            f"    Threshold: -24.0 LUFS\n\n  Loudness range:\n    LRA:         5.0 LU\n\n  True peak:\n"
            f"    Peak:       {peak:.1f} dBFS\n")


class FakeRunner:
    """Records every command. Writes what the program would write: PNG frames (render_html.js, blender) and the
    output file of ffmpeg. ffprobe answers `frames`; loudness measurements answer `lufs` and the next of `peaks`."""

    def __init__(self, frames: int = 300, lufs: float = -20.0, peaks: list[float] | None = None,
                 real_png: bool = False, fail: str | None = None):
        self.calls: list[list[str]] = []
        self.frames, self.lufs, self.peaks = frames, lufs, list(peaks or [-2.0])
        self.real_png, self.fail = real_png, fail

    def __call__(self, cmd, timeout=600, cwd=None):
        cmd = [str(c) for c in cmd]
        self.calls.append(cmd)
        joined = " ".join(cmd)
        if self.fail and self.fail in joined:
            return 1, "simulated failure"
        name = Path(cmd[0]).name
        if name.startswith("ffprobe"):
            return 0, f"nb_frames={self.frames}\nduration={self.frames / 25}\n"
        if "ebur128=peak=true" in cmd:
            peak = self.peaks.pop(0) if cmd[cmd.index("-i") + 1].endswith(".m4a") and len(self.peaks) > 1 else self.peaks[0]
            return 0, loudness_text(self.lufs, peak)
        if any(c.endswith("render_html.js") for c in cmd):
            out = Path(cmd[3])
            out.mkdir(parents=True, exist_ok=True)
            data = json.loads(Path(cmd[cmd.index("--data") + 1]).read_text()) if "--data" in cmd else {}
            n = int(cmd[cmd.index("--frames") + 1]) if "--frames" in cmd else int(data.get("frames", 10))
            a = int(cmd[cmd.index("--from") + 1]) if "--from" in cmd else 0
            b = int(cmd[cmd.index("--to") + 1]) if "--to" in cmd else n - 1
            a, b = (n + a if a < 0 else a), (n + b if b < 0 else b)
            size = (1080, 1920) if data.get("format") == "portrait" else (1920, 1080)
            for i in range(a, b + 1):
                if self.real_png:
                    from PIL import Image
                    Image.new("RGB", size).save(out / f"{i:04d}.png")
                else:
                    (out / f"{i:04d}.png").write_bytes(b"png")
            return 0, "{}"
        if name.startswith("blender"):
            from PIL import Image
            out = cmd[cmd.index("--out") + 1]
            if "--frame" in cmd:
                Image.new("RGB", (960, 540)).save(out)
            else:
                a, b = int(cmd[cmd.index("--from") + 1]), int(cmd[cmd.index("--to") + 1])
                Path(out).mkdir(parents=True, exist_ok=True)
                for i in range(a, b + 1):
                    Image.new("RGB", (1920, 1080)).save(Path(out) / f"{i:04d}.png")
            return 0, "DONE"
        if name.startswith("ffmpeg"):
            target = Path(cmd[-1])
            if target.name != "-":
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(b"media")
            return 0, ""
        return 0, ""

    def find(self, needle: str) -> list[list[str]]:
        return [c for c in self.calls if any(needle in x for x in c)]
