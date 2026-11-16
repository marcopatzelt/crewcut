#!/usr/bin/env python3
"""Get a good still frame of the speaker from a video: candidates, a contact sheet, the chosen frame at full size.

  python3 skills/thumbnail/scripts/still_frame.py sheet VIDEO --out DIR [--range 0:20 --range -30:] [--step 0.5]
          [--max 24] [--spacing 1.0] [--face 0.5,0.38] [--crop face|full] [--all]
  python3 skills/thumbnail/scripts/still_frame.py save VIDEO TIME TARGET.png [--face 0.5,0.38]

sheet:
  Takes one frame every STEP seconds from each range (default: the first 20 s and the last 30 s, where the speaker is
  usually on screen). Measures sharpness in the face window (variance of the Laplace filter) and the skin share.
  Drops frames without a face (skin share under 12 %: a full-screen graphic) and blurred frames (under 60 % of the
  median). Keeps the sharpest, at least --spacing seconds apart. --face is the face centre as shares of the frame
  (take "face" from the edit plan). --crop full shows the whole frame (so inserts at the edge are visible).
  Writes DIR/sheet.png (numbered, with time and sharpness), DIR/candidates.tsv and DIR/candidates/*.jpg.
  A range is "A:B" in seconds; a negative start counts from the end ("-30:" = the last 30 s); an empty end = the end.
save:
  Saves exactly the frame at TIME (seconds, as on the sheet) at full size as PNG. Never overwrites.
Needs ffmpeg, ffprobe, numpy and Pillow. Does not change the video. Exit 1 on error, 2 on usage.
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import shutil
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image, ImageDraw, ImageFont

FONT_PATHS = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"]
MIN_SKIN = 0.12


def font(size: int):
    for p in FONT_PATHS:
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


# ---------------------------------------------------------------- pure functions


def parse_ranges(texts: list[str], length: float) -> list[tuple[float, float]]:
    out = []
    for t in texts:
        m = re.fullmatch(r"\s*(-?\d+(?:[.,]\d+)?)?\s*:\s*(-?\d+(?:[.,]\d+)?)?\s*", t)
        if not m:
            raise ValueError(f'range "{t}" not readable. Form: 0:20, -30:, 95.5:110')
        a = float(m.group(1).replace(",", ".")) if m.group(1) else 0.0
        b = float(m.group(2).replace(",", ".")) if m.group(2) else length
        a, b = (length + a if a < 0 else a), (length + b if b < 0 else b)
        a, b = max(0.0, a), min(length, b)
        if b - a < 0.2:
            raise ValueError(f'range "{t}" is empty (video {length:.1f} s)')
        out.append((a, b))
    return out


def face_window(face: tuple[float, float] = (0.5, 0.38)) -> tuple[float, float, float, float]:
    """x0, y0, x1, y1 as shares of the frame: 44 % wide, 75 % high around the face centre, kept inside the frame."""
    cx, cy = face
    x0 = min(max(0.0, cx - 0.22), 0.56)
    y0 = min(max(0.0, cy - 0.375), 0.25)
    return x0, y0, x0 + 0.44, y0 + 0.75


def laplace_variance(grey: np.ndarray) -> float:
    g = grey.astype(np.float32)
    lap = -4 * g[1:-1, 1:-1] + g[:-2, 1:-1] + g[2:, 1:-1] + g[1:-1, :-2] + g[1:-1, 2:]
    return float(lap.var())


def skin_share(rgb: np.ndarray) -> float:
    """Share of skin-coloured pixels (YCbCr rule). A full-screen graphic has almost none."""
    ycc = np.asarray(Image.fromarray(rgb.astype(np.uint8)).convert("YCbCr"), dtype=np.int16)
    y, cb, cr = ycc[..., 0], ycc[..., 1], ycc[..., 2]
    return float(((cr >= 135) & (cr <= 172) & (cb >= 80) & (cb <= 125) & (y > 60)).mean())


def choose(
    entries: list[dict], count: int, spacing: float = 1.0, min_skin: float = MIN_SKIN, keep_all: bool = False
) -> tuple[list[dict], str]:
    """Entries have time, sharp, skin. Keep faces, drop blur (under 60 % of the median), keep the sharpest apart."""
    no_face = sum(1 for e in entries if e["skin"] < min_skin)
    with_face = [e for e in entries if keep_all or e["skin"] >= min_skin]
    if not with_face:
        return [], f"no frame with a face (skin share under {min_skin:.0%}). Check the range or use --all."
    median = float(np.median([e["sharp"] for e in with_face])) or 1.0
    for e in entries:
        e["rel"] = e["sharp"] / median
    sharp = [e for e in with_face if e["rel"] >= 0.6]
    chosen: list[dict] = []
    for e in sorted(sharp, key=lambda x: -x["rel"]):
        if all(abs(e["time"] - c["time"]) >= spacing - 0.01 for c in chosen):
            chosen.append(e)
        if len(chosen) >= count:
            break
    info = (
        f"{len(entries)} frames, {no_face} without a face{' (kept, --all)' if keep_all else ''}, "
        f"{len(with_face) - len(sharp)} blurred, {len(chosen)} on the sheet"
    )
    return sorted(chosen, key=lambda x: x["time"]), info


def time_text(t: float) -> str:
    tenths = int(round(t * 10))
    return f"{tenths // 600}:{(tenths % 600) / 10:04.1f}"


def crop_face(img: Image.Image, face: tuple[float, float]) -> Image.Image:
    w, h = img.size
    x0, y0, x1, y1 = face_window(face)
    return img.crop((int(x0 * w), int(y0 * h), int(x1 * w), int(y1 * h)))


def build_sheet(
    chosen: list[dict],
    target: str,
    crop: str,
    face: tuple[float, float],
    cols: int = 6,
    width: int = 320,
    title: str = "",
) -> None:
    tiles = []
    for n, e in enumerate(chosen, 1):
        im = Image.open(e["path"]).convert("RGB")
        im = im if crop == "full" else crop_face(im, face)
        tiles.append((n, e, im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)))
    if not tiles:
        return
    th = max(t[2].height for t in tiles)
    rows = (len(tiles) + cols - 1) // cols
    head, foot = 40, 30
    sheet = Image.new("RGB", (cols * (width + 8) + 8, head + rows * (th + foot + 8) + 8), (20, 22, 28))
    d = ImageDraw.Draw(sheet)
    d.text((10, 8), title, fill=(235, 235, 235), font=font(20))
    f = font(17)
    for i, (n, e, im) in enumerate(tiles):
        x, y = 8 + (i % cols) * (width + 8), head + (i // cols) * (th + foot + 8)
        sheet.paste(im, (x, y))
        d.text(
            (x + 4, y + th + 5),
            f"#{n}  {time_text(e['time'])}  ({e['time']:.2f} s)  S {e['rel']:.2f}",
            fill=(235, 235, 235),
            font=f,
        )
    sheet.save(target)


# ---------------------------------------------------------------- media (needs ffmpeg; takes paths)


def video_length(video: str) -> float:
    p = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", video],
        capture_output=True,
        text=True,
    )
    if p.returncode or not p.stdout.strip():
        raise SystemExit(f"ffprobe cannot read {video}")
    return float(p.stdout.strip())


def extract(video: str, a: float, b: float, step: float, folder: str, prefix: str, width: int = 960) -> list[tuple]:
    pattern = os.path.join(folder, f"{prefix}_%05d.jpg")
    p = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-nostdin",
            "-ss",
            f"{a:.3f}",
            "-i",
            video,
            "-t",
            f"{b - a:.3f}",
            "-vf",
            f"fps=1/{step},showinfo,scale={width}:-2",
            "-q:v",
            "3",
            "-an",
            pattern,
        ],
        capture_output=True,
        text=True,
    )
    if p.returncode:
        raise SystemExit("ffmpeg: " + (p.stderr.strip().splitlines() or ["error"])[-1])
    times = [float(z) for z in re.findall(r"pts_time:\s*([-\d.]+)", p.stderr)]
    files = sorted(f for f in os.listdir(folder) if f.startswith(prefix + "_"))
    return [
        (round(a + (times[i] if i < len(times) else i * step), 2), os.path.join(folder, f)) for i, f in enumerate(files)
    ]


def cmd_sheet(a) -> int:
    face = tuple(float(x) for x in a.face.split(","))
    length = video_length(a.video)
    try:
        ranges = parse_ranges(a.range or ["0:20", "-30:"], length)
    except ValueError as e:
        print(e, file=sys.stderr)
        return 2
    os.makedirs(a.out, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="still-")
    try:
        entries = []
        for i, (s, e) in enumerate(ranges):
            for t, path in extract(a.video, s, e, a.step, tmp, f"r{i}"):
                im = Image.open(path).convert("RGB")
                part = np.asarray(crop_face(im, face))
                entries.append(
                    {
                        "time": t,
                        "path": path,
                        "skin": skin_share(part),
                        "sharp": laplace_variance(np.asarray(Image.fromarray(part).convert("L"))),
                    }
                )
        chosen, info = choose(entries, a.max, spacing=a.spacing, keep_all=a.all)
        print(
            f"{os.path.basename(a.video)}: {length:.1f} s, ranges "
            + ", ".join(f"{s:.1f} to {e:.1f} s" for s, e in ranges)
        )
        print(info)
        if not chosen:
            return 1
        cd = os.path.join(a.out, "candidates")
        os.makedirs(cd, exist_ok=True)
        for n, e in enumerate(chosen, 1):
            new = os.path.join(cd, f"k{n:02d}-{e['time']:07.2f}s.jpg")
            shutil.copy(e["path"], new)
            e["path"] = new
        target = os.path.join(a.out, "sheet.png")
        build_sheet(
            chosen,
            target,
            a.crop,
            face,
            title=f"{os.path.basename(a.video)}  S = sharpness / median  "
            "save: still_frame.py save VIDEO TIME TARGET.png",
        )
        with open(os.path.join(a.out, "candidates.tsv"), "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f, delimiter="\t", lineterminator="\n")
            w.writerow(["n", "time_s", "time", "sharp_rel", "skin", "file"])
            for n, e in enumerate(chosen, 1):
                w.writerow(
                    [
                        n,
                        f"{e['time']:.2f}",
                        time_text(e["time"]),
                        f"{e['rel']:.2f}",
                        f"{e['skin']:.3f}",
                        os.path.basename(e["path"]),
                    ]
                )
        print(f"Sheet: {target}")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def cmd_save(a) -> int:
    if os.path.exists(a.target):
        print(f"{a.target} exists. Choose a new name (never overwrite).", file=sys.stderr)
        return 1
    os.makedirs(os.path.dirname(os.path.abspath(a.target)), exist_ok=True)
    p = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-nostdin",
            "-ss",
            f"{a.time:.3f}",
            "-i",
            a.video,
            "-frames:v",
            "1",
            "-an",
            a.target,
        ],
        capture_output=True,
        text=True,
    )
    if p.returncode or not os.path.exists(a.target):
        print("ffmpeg: " + (p.stderr.strip().splitlines() or ["error"])[-1], file=sys.stderr)
        return 1
    im = Image.open(a.target)
    face = tuple(float(x) for x in a.face.split(","))
    print(
        f"{a.target}: {im.width}x{im.height}, time {a.time:.2f} s, "
        f"skin share in the face window {skin_share(np.asarray(crop_face(im.convert('RGB'), face))):.3f}"
    )
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Still frames of the speaker from a video.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sheet", help="candidates and a contact sheet")
    s.add_argument("video")
    s.add_argument("--out", required=True)
    s.add_argument("--range", action="append", help="A:B in seconds, more than once (default 0:20 and -30:)")
    s.add_argument("--step", type=float, default=0.5)
    s.add_argument("--max", type=int, default=24)
    s.add_argument("--spacing", type=float, default=1.0, help="least distance between candidates in seconds")
    s.add_argument("--face", default="0.5,0.38", help="face centre as shares of the frame (plan 'face')")
    s.add_argument("--crop", choices=["face", "full"], default="face")
    s.add_argument("--all", action="store_true", help="keep frames without a face too")
    v = sub.add_parser("save", help="save one frame at full size")
    v.add_argument("video")
    v.add_argument("time", type=lambda x: float(x.replace(",", ".")))
    v.add_argument("target")
    v.add_argument("--face", default="0.5,0.38")
    a = ap.parse_args(argv)
    return cmd_sheet(a) if a.cmd == "sheet" else cmd_save(a)


if __name__ == "__main__":
    sys.exit(main())
