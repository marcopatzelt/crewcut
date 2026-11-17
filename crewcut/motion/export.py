"""Rendering through EffectCraft's own renderer: single frames, contact sheets, comparison sheets and
videos. Long renders go in chunks, each in a fresh ``effectcraft-cli`` process (a long render holds all
frames in memory), then the chunks are joined. Joining and the final H.264 encode use ffmpeg as an external
tool; every pixel comes from EffectCraft."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from .backend import Backend, BackendError

EXPORT_PRESETS: dict[str, dict[str, Any]] = {
    # chunk format -> final encode
    "h264-hq": {"chunk": ["--format", "prores", "--prores", "hq", "--audio", "off"], "ext": ".mov", "final": "x264", "crf": 14},
    "h264-native": {"chunk": ["--format", "h264", "--audio", "off"], "ext": ".mp4", "final": "copy"},
    "prores4444": {"chunk": ["--format", "prores", "--prores", "4444", "--channels", "rgba", "--audio", "off"], "ext": ".mov", "final": "copy"},
    "prores-hq": {"chunk": ["--format", "prores", "--prores", "hq", "--audio", "off"], "ext": ".mov", "final": "copy"},
}


def chunks(start: float, end: float, step: float, fps: float) -> list[tuple[float, float]]:
    """Split [start, end) into frame-aligned ranges of about ``step`` seconds (no frame lost or doubled)."""
    if end <= start:
        raise ValueError("end must be after start")
    if step <= 0:
        raise ValueError("chunk length must be > 0")
    f0, f1 = round(start * fps), round(end * fps)
    per = max(1, round(step * fps))
    out = []
    f = f0
    while f < f1:
        g = min(f + per, f1)
        out.append((f / fps, g / fps))
        f = g
    return out


def ffmpeg() -> str:
    p = shutil.which("ffmpeg")
    if not p:
        raise BackendError("ffmpeg not found (needed to join chunks): apt install ffmpeg")
    return p


def render_video(backend: Backend, project: str, out: str, comp: str, start: float, end: float, fps: float,
                 preset: str = "h264-hq", chunk: float = 4.0, jobs: int = 1, crf: int | None = None,
                 keep_chunks: bool = False) -> dict[str, Any]:
    """Render [start, end) of ``comp`` to ``out`` in chunks. Returns paths, frame count and timings."""
    if preset not in EXPORT_PRESETS:
        raise ValueError(f"unknown preset {preset!r}; one of: {', '.join(EXPORT_PRESETS)}")
    pr = EXPORT_PRESETS[preset]
    out = os.path.abspath(out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    work = tempfile.mkdtemp(prefix="ecchunks-", dir=os.path.dirname(out))
    parts = chunks(start, end, chunk, fps)

    def one(i_se: tuple[int, tuple[float, float]]) -> str:
        i, (s, e) = i_se
        f = os.path.join(work, f"{i:04d}{pr['ext']}")
        backend.render(project, f, comp=comp, start=s, end=e, extra=pr["chunk"])
        if not os.path.exists(f) or os.path.getsize(f) == 0:
            raise BackendError(f"chunk {i} ({s:.3f}-{e:.3f} s) produced no file")
        return f

    with ThreadPoolExecutor(max_workers=max(1, jobs)) as ex:
        files = list(ex.map(one, enumerate(parts)))
    lst = os.path.join(work, "list.txt")
    with open(lst, "w") as f:
        f.writelines(f"file '{x}'\n" for x in files)
    if pr["final"] == "x264":
        cmd = [ffmpeg(), "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c:v", "libx264", "-preset", "slow",
               "-crf", str(crf if crf is not None else pr["crf"]), "-pix_fmt", "yuv420p", "-r", f"{fps:g}", "-movflags", "+faststart", out]
    else:
        cmd = [ffmpeg(), "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", out]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise BackendError(f"joining chunks failed: {r.stderr.strip()[-300:]}")
    if not keep_chunks:
        shutil.rmtree(work, ignore_errors=True)
    return {"output": out, "bytes": os.path.getsize(out), "chunks": len(parts), "frames": probe_frames(out),
            "expected_frames": round(end * fps) - round(start * fps), "preset": preset}


def probe_frames(path: str) -> int | None:
    p = shutil.which("ffprobe")
    if not p:
        return None
    r = subprocess.run([p, "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
                        "stream=nb_read_frames", "-of", "csv=p=0", path], capture_output=True, text=True)
    try:
        return int(r.stdout.strip())
    except ValueError:
        return None


def tile(images: list[str], out: str, cols: int, labels: list[str] | None = None, cell_w: int = 640) -> str:
    """Tile PNG/JPEG frames into one sheet (Pillow). Used for contact and comparison sheets."""
    from PIL import Image, ImageDraw
    ims = [Image.open(p).convert("RGB") for p in images]
    if not ims:
        raise ValueError("no images")
    w = cell_w
    h = max(round(im.height * w / im.width) for im in ims)
    rows = (len(ims) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * w + (cols - 1) * 4, rows * h + (rows - 1) * 4), (20, 20, 20))
    d = ImageDraw.Draw(sheet)
    for i, im in enumerate(ims):
        im = im.resize((w, round(im.height * w / im.width)))
        x, y = (i % cols) * (w + 4), (i // cols) * (h + 4)
        sheet.paste(im, (x, y))
        if labels and i < len(labels) and labels[i]:
            d.rectangle([x, y, x + 9 * len(labels[i]) + 10, y + 20], fill=(0, 0, 0))
            d.text((x + 5, y + 4), labels[i], fill=(255, 80, 80))
    sheet.save(out, quality=90)
    return out


def contact_sheet(backend: Backend, project: str, comp: str, times: list[float], out: str, cols: int = 4,
                  max_side: int = 640) -> dict[str, Any]:
    d = tempfile.mkdtemp(prefix="ecsheet-")
    frames = []
    for i, t in enumerate(times):
        f = os.path.join(d, f"{i:03d}.png")
        backend.render_frame(project, f, comp=comp, time=t, max_side=max_side)
        frames.append(f)
    tile(frames, out, cols, [f"{t:.3f}s" for t in times], cell_w=max_side)
    shutil.rmtree(d, ignore_errors=True)
    return {"output": os.path.abspath(out), "times": times}


def compare_sheet(backend: Backend, project: str, comp: str, times: list[float], ref: str, ref_times: list[float],
                  out: str, cell_w: int = 640) -> dict[str, Any]:
    """Reference frame | our frame, one row per moment. The reference frames come from a video via ffmpeg."""
    if len(times) != len(ref_times):
        raise ValueError("--times and --ref-times need the same count")
    d = tempfile.mkdtemp(prefix="eccmp-")
    cells, labels = [], []
    for i, (t, rt) in enumerate(zip(times, ref_times, strict=True)):
        rf = os.path.join(d, f"r{i:03d}.png")
        subprocess.run([ffmpeg(), "-v", "error", "-y", "-ss", f"{rt:.4f}", "-i", ref, "-frames:v", "1", rf], check=True)
        of = os.path.join(d, f"o{i:03d}.png")
        backend.render_frame(project, of, comp=comp, time=t, max_side=cell_w)
        cells += [rf, of]
        labels += [f"ref {rt:.3f}s", f"ours {t:.3f}s"]
    tile(cells, out, 2, labels, cell_w=cell_w)
    shutil.rmtree(d, ignore_errors=True)
    return {"output": os.path.abspath(out), "rows": len(times)}
