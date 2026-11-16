"""2D inserts: PNG frames with tools/render_html.js (Chromium, one frame after the other), then one clip per insert.

Full-frame inserts become H.264 MP4, transparent ones (keyword) QuickTime Animation (qtrle) MOV with alpha.
A rendered insert is kept in render/inserts/<id>-<hash>/ and not rendered again while data, template and brand stay
the same.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path

from .. import paths
from . import media
from .plan import Insert, Plan


def tokens_file(plan: Plan) -> Path:
    """The pack's render tokens as a JSON file next to the inserts (one file per distinct token set)."""
    text = json.dumps(plan.tokens, sort_keys=True, ensure_ascii=False, indent=1)
    h = hashlib.sha1(text.encode()).hexdigest()[:10]
    p = plan.episode_dir / "render" / "inserts" / f"brand-{h}.json"
    if not p.is_file():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text + "\n", encoding="utf-8")
    return p


def render_cmd(template: Path, out_dir: Path, data_file: Path | None, tokens: Path | None, frames: int | None = None,
               transparent: bool = False, frm: int | None = None, to: int | None = None) -> list[str]:
    cmd = [media.node(), str(paths.tools_dir() / "render_html.js"), str(template), str(out_dir)]
    if frames is not None:
        cmd += ["--frames", str(frames)]
    if data_file is not None:
        cmd += ["--data", str(data_file)]
    if tokens is not None:
        cmd += ["--brand", str(tokens)]
    if transparent:
        cmd.append("--transparent")
    if frm is not None:
        cmd += ["--from", str(frm)]
    if to is not None:
        cmd += ["--to", str(to)]
    return cmd


def encode_cmd(frames_dir: Path, clip: Path, fps: int, transparent: bool) -> list[str]:
    if transparent:
        codec = ["-c:v", "qtrle", "-pix_fmt", "argb"]
    else:
        codec = ["-c:v", "libx264", "-crf", "14", "-preset", "slow", "-pix_fmt", "yuv420p"]
    return [media.ffmpeg(), "-y", "-loglevel", "error", "-framerate", str(fps), "-i", str(frames_dir / "%04d.png"),
            *codec, str(clip)]


def clip_fresh(ins: Insert) -> bool:
    """The encoded clip exists and is newer than every frame."""
    if not ins.clip or not ins.clip.is_file() or not ins.out_dir or not ins.out_dir.is_dir():
        return False
    pngs = list(ins.out_dir.glob("*.png"))
    return bool(pngs) and ins.clip.stat().st_mtime > max(p.stat().st_mtime for p in pngs)


def encode(plan: Plan, ins: Insert, runner: media.Runner = media.run, log: Callable = print) -> bool:
    """Encode the frames of a 2D or 3D insert into its clip. True when the clip is there and fresh."""
    if ins.kind == "clip":
        return bool(ins.clip and ins.clip.is_file())
    if plan.missing(ins):
        return False
    if clip_fresh(ins):
        return True
    tmp = ins.clip.with_name(ins.clip.stem + ".tmp" + ins.clip.suffix)
    rc, out = runner(encode_cmd(ins.out_dir, tmp, plan.fps, ins.transparent), timeout=1800)
    if rc:
        log(f"{ins.id}: encoding failed: {media.tail(out, 400)}")
        tmp.unlink(missing_ok=True)
        return False
    tmp.replace(ins.clip)
    return True


def write_data(ins: Insert) -> Path:
    p = ins.data_file
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(ins.data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return p


def render_insert(plan: Plan, ins: Insert, runner: media.Runner = media.run, log: Callable = print) -> bool:
    """Render the missing frames of one 2D insert. True when no frame is missing afterwards."""
    miss = plan.missing(ins)
    if not miss:
        return True
    ins.out_dir.mkdir(parents=True, exist_ok=True)
    cmd = render_cmd(ins.template, ins.out_dir, write_data(ins), tokens_file(plan), frames=ins.render_frames,
                     transparent=ins.transparent, frm=min(miss), to=max(miss))
    rc, out = runner(cmd, timeout=max(600, ins.render_frames * 8))
    left = plan.missing(ins)
    if rc or left:
        log(f"2d {ins.id} ({ins.scene}): failed: {media.tail(out, 500) or f'{len(left)} frames missing'}")
        return False
    log(f"2d {ins.id} ({ins.scene}): {len(miss)} frames")
    return True


def render_2d(plan: Plan, ids: list[str] | None = None, images_only: bool = False, runner: media.Runner = media.run,
              log: Callable = print) -> list[dict]:
    """Render every 2D insert that has missing frames, then encode (unless images_only). One row per insert."""
    rows = []
    for ins in plan.of_kind("2d", ids):
        ok = render_insert(plan, ins, runner, log)
        enc = None if images_only or not ok else encode(plan, ins, runner, log)
        rows.append({"id": ins.id, "scene": ins.scene, "frames_ok": ok, "clip_ok": enc,
                     "clip": str(ins.clip), "missing": len(plan.missing(ins))})
    return rows


def still(plan: Plan, ins: Insert, frame: int, out_dir: Path, runner: media.Runner = media.run,
          scale: float = 0.5) -> Path | None:
    """One 2D frame into out_dir as <id>-<frame>.png (probe), rendered full size and scaled down with Pillow."""
    tmp = out_dir / f".{ins.id}-{frame:04d}"
    tmp.mkdir(parents=True, exist_ok=True)
    cmd = render_cmd(ins.template, tmp, write_data(ins), tokens_file(plan), frames=ins.render_frames,
                     transparent=ins.transparent, frm=frame, to=frame)
    rc, _ = runner(cmd, timeout=300)
    src = tmp / f"{frame:04d}.png"
    if rc or not src.is_file():
        return None
    dst = out_dir / f"{ins.id}-{frame:04d}.png"
    try:
        from PIL import Image
        with Image.open(src) as im:
            im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS).save(dst)
    except Exception:
        return None
    finally:
        src.unlink(missing_ok=True)
        tmp.rmdir()
    return dst
