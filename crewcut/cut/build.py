"""Build the speaker cut from a cut plan: one clip per cut, the joined picture, and the cleaned voice.

All plan paths are relative to the episode. Sources stay untouched. Output names are versioned and never overwritten:
  work/cut-vNNN/NN-<id>.mov         one clip per cut (DNxHR HQX, 10 bit, PCM sound)
  work/speaker-vNNN.mov             the joined speaker picture with camera sound (the edit plan's "base")
  audio/voice-vNNN.wav              the cleaned, levelled voice (the edit plan's "voice")
  work/edit-decisions-vNNN.json     what was built, frame by frame (verify, srt and the cut-check skill read it)

ffmpeg applies the source rotation before scaling; nothing is cropped or mirrored except the planned zoom.
Optional per cut: "zoom" with "zoom_center" (punch-in without a lens change), "tail" (picture after the last word with
the voice faded out), "audio" {"source", "offset"} (sound from a separate recorder: recorder time = picture time -
offset).
"""

from __future__ import annotations

import json
import math
import os
import shutil
from collections.abc import Callable
from pathlib import Path

from . import audio, media
from .common import CutError, check_version, inside, read_json, rel, write_new_json

RATE = 48000


def out_paths(ep_dir: Path, version: str) -> dict[str, Path]:
    return {"folder": ep_dir / "work" / f"cut-{version}", "rough": ep_dir / "work" / f"speaker-{version}.mov",
            "voice": ep_dir / "audio" / f"voice-{version}.wav",
            "manifest": ep_dir / "work" / f"edit-decisions-{version}.json"}


def frames_of(c: dict, fps: int) -> int:
    return round((c["end"] - c["start"] + float(c.get("tail", 0))) / float(c.get("speed", 1)) * fps)


def check_clip(c: dict, info: dict, width: int, height: int) -> int:
    """Validate one cut against its source probe. Returns the source rotation."""
    start, end, speed = c["start"], c["end"], c.get("speed", 1)
    if not all(math.isfinite(float(n)) for n in (start, end, speed)) or not 0 <= start < end or not 0.5 <= speed <= 2:
        raise CutError(f"cut {c.get('id')}: start, end or speed out of range")
    video = media.video_stream(info)
    if not video:
        raise CutError(f"cut {c['id']}: the source has no picture")
    if media.is_hdr(video):
        raise CutError(f"cut {c['id']}: HDR source. Decide the colour conversion first; nothing is converted on its own.")
    rot = media.rotation(video)
    w, h = int(video["width"]), int(video["height"])
    if rot % 180:
        w, h = h, w
    if abs(w / h - width / height) > 0.002:
        raise CutError(f"cut {c['id']}: source is {w}x{h}, the cut is {width}x{height}. Decide the framing first.")
    dur = media.duration(info)
    if dur is not None and end > dur:
        raise CutError(f"cut {c['id']}: ends at {end} s, after the end of the source ({dur:.2f} s)")
    if not media.audio_streams(info) and not c.get("audio"):
        raise CutError(f"cut {c['id']}: the source has no sound and no separate sound is given")
    return rot


def clip_filters(c: dict, fps: int, width: int, height: int) -> tuple[str, str, float]:
    """(video filter, audio filter, clip duration in seconds) for one cut."""
    speed = float(c.get("speed", 1))
    frames = frames_of(c, fps)
    if frames < 2:
        raise CutError(f"cut {c['id']} is too short")
    duration = frames / fps
    z = float(c.get("zoom", 1))
    cx, cy = c.get("zoom_center", [0.5, 0.5])
    crop = f"crop=iw/{z}:ih/{z}:(iw-iw/{z})*{cx}:(ih-ih/{z})*{cy}," if z > 1 else ""
    tail = float(c.get("tail", 0))
    speak = (c["end"] - c["start"]) / speed
    # The clip is `frames` long (rounded); trim must pass at least that much picture plus one frame, else ffmpeg waits
    # for a last frame that never comes (a real hang on a 1.52 s clip with a 1.50 s trim).
    keep = max(c["end"] - c["start"] + tail, duration * speed + 1 / fps)
    vf = (f"trim=duration={keep},setpts=(PTS-STARTPTS)/{speed},{crop}"
          f"fps={fps},scale={width}:{height}:flags=lanczos,setsar=1")
    # With a tail the fade-out already silences everything after the last word. A leading atrim there deadlocked
    # ffmpeg (sound cut 0.5 s before the picture, the last frames never came).
    head = (f"asetpts=PTS-STARTPTS,atempo={speed}," if tail
            else f"atrim=duration={c['end'] - c['start']},asetpts=PTS-STARTPTS,atempo={speed},")
    af = (head + (f"afade=t=out:st={max(0, speak - 0.03)}:d=0.03," if tail else "")
          + f"apad,atrim=end_sample={round(duration * RATE)},"
          + f"afade=t=in:d=0.004,afade=t=out:st={max(0, duration - 0.006)}:d=0.006")
    return vf, af, duration


def clip_cmd(c: dict, ep_dir: Path, dest: Path, fps: int, width: int, height: int) -> list:
    vf, af, duration = clip_filters(c, fps, width, height)
    a = c.get("audio")
    a_in = ["-ss", c["start"] - float(a["offset"]), "-i", inside(ep_dir, a["source"])] if a else []
    return ["ffmpeg", "-nostdin", "-v", "error", "-n", "-threads", "3", "-ss", c["start"],
            "-i", inside(ep_dir, c["source"]), *a_in, "-map", "0:v:0", "-map", "1:a:0" if a else "0:a:0",
            "-vf", vf, "-af", af, "-filter_threads", "2", "-t", duration,
            "-c:v", "dnxhd", "-profile:v", "dnxhr_hqx", "-pix_fmt", "yuv422p10le", "-threads", "3",
            "-c:a", "pcm_s24le", "-ar", str(RATE), "-ac", "2", "-map_metadata", "-1",
            "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", "-color_range", "tv",
            "-video_track_timescale", "30000", dest]


def concat_text(clips: list[dict], fps: int) -> str:
    """concat demuxer list; file names are relative to the list's own folder."""
    out = []
    for c in clips:
        name = Path(c["file"]).name.replace("'", "'\\''")
        out.append(f"file '{name}'\nduration {c['frames'] / fps}\n")
    return "".join(out)


def voice_cmds(rough: Path, voice: Path, filters: str, total_seconds: float, plan: dict,
               ) -> tuple[list, Callable[[dict], list]]:
    """First pass measures loudness; the returned function builds the second pass from the measurement."""
    i, tp, lra = float(plan.get("voice_lufs", -16)), float(plan.get("voice_tp", -2)), float(plan.get("voice_lra", 7))
    measure = ["ffmpeg", "-nostdin", "-hide_banner", "-i", rough, "-vn", "-af",
               f"{filters},{audio.loudnorm_filter(i, tp, lra)}", "-f", "null", "-"]

    def apply(measured: dict) -> list:
        return ["ffmpeg", "-nostdin", "-v", "error", "-n", "-i", rough, "-vn", "-af",
                f"{filters},{audio.loudnorm_filter(i, tp, lra, measured)}", "-ar", str(RATE), "-ac", "2",
                "-t", total_seconds, "-c:a", "pcm_s24le", voice]
    return measure, apply


CLIP_KEYS = ("source", "start", "end", "speed", "zoom", "zoom_center", "tail", "audio")


def same_clip(a: dict, b: dict) -> bool:
    """A clip of an older version can be reused when every value that shapes it is the same."""
    return all(a.get(k) == b.get(k) for k in CLIP_KEYS)


def prepare(plan_path: Path, ep_dir: Path, probe=media.probe) -> tuple[dict, list[dict], dict[str, Path]]:
    """Read and check the plan and all sources. No file is written."""
    cfg = read_json(plan_path)
    fps, version = int(cfg["fps"]), check_version(cfg["version"])
    if not 1 <= fps <= 120:
        raise CutError("frame rate must be between 1 and 120")
    width, height = int(cfg["width"]), int(cfg["height"])
    out = out_paths(ep_dir, version)
    clips, total, infos = [], 0, {}
    for i, c in enumerate(cfg["cuts"], 1):
        src = inside(ep_dir, c["source"])
        if not src.is_file():
            raise CutError(f"cut {c['id']}: source not found: {c['source']}")
        if c["source"] not in infos:
            infos[c["source"]] = probe(src)
        rot = check_clip(c, infos[c["source"]], width, height)
        a = c.get("audio")
        if a:
            a_src = inside(ep_dir, a["source"])
            a_start = c["start"] - float(a["offset"])
            a_len = media.duration(probe(a_src)) if a_src.is_file() else None
            if a_len is None or a_start < 0 or a_start + (c["end"] - c["start"]) > a_len:
                raise CutError(f"cut {c['id']}: the separate sound does not cover the cut")
        frames = frames_of(c, fps)
        if frames < 2:
            raise CutError(f"cut {c['id']} is too short")
        dest = out["folder"] / f"{i:02d}-{c['id']}.mov"
        clips.append({**c, "file": rel(ep_dir, dest), "frames": frames,
                      "timeline_in_frame": total, "timeline_out_frame": total + frames, "source_rotation": rot})
        total += frames
    return cfg, clips, out


def reuse_from(ep_dir: Path, old_version: str, clips: list[dict], folder: Path) -> list[str]:
    """Hard-link unchanged clips of an older version into the new folder. Returns the reused ids."""
    old_manifest = ep_dir / "work" / f"edit-decisions-{check_version(old_version)}.json"
    old = {Path(c["file"]).name: c for c in read_json(old_manifest)["clips"]}
    reused = []
    for c in clips:
        prev = old.get(Path(c["file"]).name)
        if prev and same_clip(prev, c) and prev.get("frames") == c["frames"]:
            src = inside(ep_dir, prev["file"])
            dest = inside(ep_dir, c["file"])
            if src.is_file() and not dest.exists():
                try:
                    os.link(src, dest)
                except OSError:
                    shutil.copy2(src, dest)
                reused.append(c["id"])
    return reused


def build(plan_path: Path, ep_dir: Path, resume: bool = False, reuse: str | None = None, log=print) -> dict:
    cfg, clips, out = prepare(plan_path, ep_dir)
    fps, width, height = int(cfg["fps"]), int(cfg["width"]), int(cfg["height"])
    for key in ("rough", "voice", "manifest"):
        if out[key].exists():
            raise CutError(f"{rel(ep_dir, out[key])} exists already. Make a new plan version.")
    if out["folder"].exists() and not (resume or reuse):
        raise CutError(f"{rel(ep_dir, out['folder'])} exists. Use --resume to continue an interrupted build.")
    out["folder"].mkdir(parents=True, exist_ok=True)
    reused = reuse_from(ep_dir, reuse, clips, out["folder"]) if reuse else []
    for c in clips:
        dest = inside(ep_dir, c["file"])
        if dest.is_file():
            got = probe_frames(dest)
            if got == c["frames"]:
                log(f"reused: {c['id']}")
                continue
            dest.unlink()
        media.run(clip_cmd(c, ep_dir, dest, fps, width, height))
        got = probe_frames(dest)
        if got != c["frames"]:
            raise CutError(f"frame count of {c['id']} is {got}, expected {c['frames']}")
        log(f"prepared: {c['id']} {c['frames']} frames")
    concat = out["folder"] / "concat.txt"
    concat.write_text(concat_text(clips, fps), encoding="utf-8")
    media.run(["ffmpeg", "-nostdin", "-v", "error", "-n", "-f", "concat", "-safe", "0", "-i", concat, "-c", "copy",
               out["rough"]])
    total = sum(c["frames"] for c in clips)
    measure, apply = voice_cmds(out["rough"], out["voice"], cfg["voice_filter"], total / fps, cfg)
    measured = audio.parse_loudnorm(media.run(measure).stderr)
    media.run(apply(measured))
    levels = audio.channel_levels(out["voice"])
    if len(levels) == 2 and abs(levels[0] - levels[1]) > 10:
        raise CutError(f"the voice is one-sided (channels {levels} dB). Set mic_channel in the selects "
                       "(0 left, 1 right) and make a new plan version.")
    manifest = {"version": cfg["version"], "fps": fps, "frames": total, "duration_seconds": total / fps,
                "width": width, "height": height, "clips": clips, "rough": rel(ep_dir, out["rough"]),
                "voice": rel(ep_dir, out["voice"]), "voice_measurement_before_normalization": measured,
                "voice_channel_levels_db": levels, "framing": "full rotated source frame, only the planned zoom",
                "plan": rel(ep_dir, plan_path), "reused": reused}
    write_new_json(out["manifest"], manifest)
    from . import prune
    prune.after_write(ep_dir, log)   # only the newest two speaker cuts and clip folders stay
    return {"frames": total, "seconds": round(total / fps, 2), "clips": len(clips),
            "manifest": rel(ep_dir, out["manifest"]), "speaker": manifest["rough"], "voice": manifest["voice"]}


def probe_frames(path: Path) -> int | None:
    """Frame count from the clip header (MOV writes it); counted from the packets only when missing."""
    for extra, key in (([], "nb_frames"), (["-count_packets"], "nb_read_packets")):
        out = media.run(["ffprobe", "-v", "error", "-select_streams", "v:0", *extra, "-show_entries",
                         f"stream={key}", "-of", "json", path]).stdout
        try:
            return int((json.loads(out).get("streams") or [{}])[0][key])
        except (KeyError, TypeError, ValueError):
            continue
    return None
