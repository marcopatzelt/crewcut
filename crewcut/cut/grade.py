"""The colour step: measure, propose, show before and after, then bake the grade into the speaker picture with ffmpeg.

Baked into the picture, the result looks the same in every player and can be measured again.

  check: stills before and after at a few times, one sheet, numbers per still and a verdict per target
         -> review/grade/<name>-check.json and <name>-check.jpg
  apply: graded picture (ProRes 422 HQ), sound untouched -> work/speaker-graded-vNNN.mov (or --out)

Targets for a talking head (8-bit values):
  - wall patch neutral: |R-G| and |B-G| <= 4, and well under 235 so it keeps detail.
  - skin patch: R > G > B, luma 140-190, the same skin luma across times (+-6).
  - frame: YHIGH (90 %) <= 205, YLOW (10 %) >= 24 (no crushed blacks), YMAX <= 245.
Patches are x,y,w,h in pixels of the picture scaled to the episode format (1920x1080 or 1080x1920).
The default filter is a gentle base look (soft S-curve, a little more colour); the style pack can set its own in
edit-style.json "grade_filter".
"""

from __future__ import annotations

import re
from pathlib import Path

from . import media

BASE = "curves=master='0/0.02 0.25/0.23 0.5/0.5 0.75/0.78 1/0.98',eq=contrast=1.04:saturation=1.14"
WALL_TINT, WALL_MAX = 4.0, 235.0
SKIN_LUMA = (140.0, 190.0)
SKIN_SPREAD = 6.0
Y_HIGH_MAX, Y_LOW_MIN, Y_MAX = 205.0, 24.0, 245.0


def base_filter() -> str:
    from .. import brand
    try:
        return str(brand.load().value("edit_style.grade_filter", BASE) or BASE)
    except Exception:
        return BASE


def parse_rect(text: str | None) -> list[int] | None:
    if not text:
        return None
    parts = [int(v) for v in text.split(",")]
    if len(parts) != 4 or parts[2] <= 0 or parts[3] <= 0 or min(parts) < 0:
        raise ValueError("a patch is x,y,w,h in pixels")
    return parts


def frame_cmd(src: Path, t: float, vf: str, out: Path, size: tuple[int, int]) -> list:
    chain = f"scale={size[0]}:{size[1]}" + (f",{vf}" if vf else "")
    return ["ffmpeg", "-nostdin", "-v", "error", "-y", "-ss", f"{t:g}", "-i", str(src), "-frames:v", "1", "-vf", chain,
            str(out)]


def stats_cmd(src: Path, t: float, vf: str, size: tuple[int, int]) -> list:
    chain = (f"scale={size[0]}:{size[1]}" + (f",{vf}" if vf else "")
             + ",format=yuv420p,signalstats,metadata=print:file=-")      # 8-bit numbers
    return ["ffmpeg", "-nostdin", "-v", "error", "-ss", f"{t:g}", "-i", str(src), "-frames:v", "1", "-vf", chain,
            "-f", "null", "-"]


def parse_signalstats(text: str) -> dict:
    out = {}
    for k, v in re.findall(r"signalstats\.(YLOW|YAVG|YHIGH|YMAX|SATAVG)=(-?[\d.]+)", text):
        out[k] = round(float(v), 1)
    return out


def patch(png: Path, rect: list[int]) -> dict:
    """Mean R, G, B and luma (Rec. 709) of a rectangle of a still."""
    from PIL import Image, ImageStat
    x, y, w, h = rect
    with Image.open(png) as im:
        r, g, b = ImageStat.Stat(im.convert("RGB").crop((x, y, x + w, y + h))).mean[:3]
    r, g, b = round(r, 1), round(g, 1), round(b, 1)
    return {"rgb": [r, g, b], "luma": round(0.2126 * r + 0.7152 * g + 0.0722 * b, 1)}


def verdicts(m: dict) -> list[str]:
    """What misses the targets in one graded still: {"wall", "skin", "frame"} (wall and skin optional)."""
    out = []
    wall = m.get("wall")
    if wall:
        r, g, b = wall["rgb"]
        if abs(r - g) > WALL_TINT or abs(b - g) > WALL_TINT:
            out.append(f"wall not neutral: R-G {r - g:+.1f}, B-G {b - g:+.1f} (allowed +-{WALL_TINT:g})")
        if max(r, g, b) >= WALL_MAX:
            out.append(f"wall too bright ({max(r, g, b):.0f}), detail is lost above {WALL_MAX:g}")
    skin = m.get("skin")
    if skin:
        r, g, b = skin["rgb"]
        if not r > g > b:
            out.append(f"skin colour order wrong (R {r}, G {g}, B {b}; expected R > G > B)")
        lo, hi = SKIN_LUMA
        if not lo <= skin["luma"] <= hi:
            out.append(f"skin luma {skin['luma']} outside {lo:g}-{hi:g}")
    f = m.get("frame") or {}
    if f.get("YHIGH") is not None and f["YHIGH"] > Y_HIGH_MAX:
        out.append(f"frame too bright: YHIGH {f['YHIGH']} > {Y_HIGH_MAX:g}")
    if f.get("YLOW") is not None and f["YLOW"] < Y_LOW_MIN:
        out.append(f"blacks crushed: YLOW {f['YLOW']} < {Y_LOW_MIN:g}")
    if f.get("YMAX") is not None and f["YMAX"] > Y_MAX:
        out.append(f"highlights clip: YMAX {f['YMAX']} > {Y_MAX:g}")
    return out


def skin_spread(rows: list[dict]) -> str | None:
    lumas = [r["after"]["skin"]["luma"] for r in rows if (r.get("after") or {}).get("skin")]
    if len(lumas) > 1 and max(lumas) - min(lumas) > 2 * SKIN_SPREAD:
        return f"skin luma differs across times ({min(lumas)}-{max(lumas)}); takes need their own grade"
    return None


def sheet(pngs: list[Path], out: Path, width: int = 960) -> Path:
    """Before | after, one row per time."""
    from PIL import Image
    ims = []
    for p in pngs:
        with Image.open(p) as im:
            h = round(im.height * width / im.width)
            ims.append(im.convert("RGB").resize((width, h)))
    rows = (len(ims) + 1) // 2
    cell_h = max(i.height for i in ims)
    canvas = Image.new("RGB", (2 * width + 12, rows * (cell_h + 4) + 4), (20, 20, 20))
    for k, im in enumerate(ims):
        canvas.paste(im, (4 + (k % 2) * (width + 4), 4 + (k // 2) * (cell_h + 4)))
    canvas.save(out, quality=88)
    return out


def check(ep_dir: Path, picture: Path, times: list[float], vf: str, size: tuple[int, int], wall: list[int] | None,
          skin: list[int] | None) -> dict:
    d = ep_dir / "review" / "grade"
    d.mkdir(parents=True, exist_ok=True)
    stem = picture.stem
    rows, pngs = [], []
    for t in times:
        row: dict = {"t": t}
        for tag, chain in (("before", ""), ("after", vf)):
            png = d / f"{stem}-{t:g}-{tag}.png"
            media.run(frame_cmd(picture, t, chain, png, size))
            pngs.append(png)
            m = {"frame": parse_signalstats(media.run(stats_cmd(picture, t, chain, size)).stdout)}
            if wall:
                m["wall"] = patch(png, wall)
            if skin:
                m["skin"] = patch(png, skin)
            row[tag] = m
        row["misses"] = verdicts(row["after"])
        rows.append(row)
    sheet_path = sheet(pngs, d / f"{stem}-check.jpg")
    notes = [n for n in [skin_spread(rows)] if n]
    return {"picture": picture.name, "filter": vf, "size": list(size), "wall_rect": wall, "skin_rect": skin,
            "rows": rows, "notes": notes, "sheet": sheet_path, "ok": not notes and not any(r["misses"] for r in rows)}


def apply_cmd(src: Path, vf: str, out: Path) -> list:
    return ["ffmpeg", "-nostdin", "-v", "error", "-n", "-i", str(src), "-map", "0", "-vf", vf, "-c:v", "prores_ks",
            "-profile:v", "3", "-pix_fmt", "yuv422p10le", "-c:a", "copy", str(out)]
