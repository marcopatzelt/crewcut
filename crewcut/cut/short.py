"""Rough cut of a Clip-mode Short: pieces of a finished episode, cut again from the original recordings in 9:16.

  crewcut cut short <short episode>/edit/pieces-vNNN.json [--words new|carry] [--accept-soft] [--dry-run]

Why from the originals: the finished speaker cut is already scaled to 1920x1080, and a 9:16 crop of it is only 608 px
wide. Each piece is mapped back through the source episode's build record (work/edit-decisions-vNNN.json, written by
`crewcut cut build`) to the original recording and cropped there, around the face.

Pieces spec (in the short's episode folder; times are on the timeline of the source episode's finished speaker cut,
the timeline of its voice and words):
  {"source_episode": "012-ranking",
   "decisions": "work/edit-decisions-v005.json",  optional, in the source episode (default: the newest)
   "words": "work/words-v005.json",               optional: words of the finished voice (default: words-<version>)
   "voice": "audio/voice-v005.wav",               optional: the cleaned voice (default: the one the build wrote);
                                                  null = the camera sound with the cut plan's voice filter
   "face": {"originals/x.MP4": [0.55, 0.4]},      optional: face centre per original, as a share of the frame
   "grade": "<ffmpeg filter>" | null,             optional (default: the pack's grade when the episode was graded)
   "pad_in": 0.10, "pad_out": 0.16,               seconds of silence before the first and after the last word
   "size": [1080, 1920],                          optional output size
   "pieces": [
     {"id": "p1", "from_word": "The", "after": 200.0, "to_word": "first.", "to_after": 203.0},   words, searched
     {"id": "p2", "from": 233.4, "to": 238.9, "zoom": 1.1}                                        or fixed seconds
   ]}
A word may be a phrase of several words ("the ranking"). The face comes from the spec, else the cut, else the take in
the selects file, else the zoom centre of the cut, else the middle of the frame (with a warning).

Outputs, in the short's episode folder; the version comes from the spec's name and nothing is overwritten:
  work/short-vNNN/NN-<id>.mp4   one picture per piece, 9:16
  work/speaker-vNNN.mov         the joined picture with the Short's voice (the edit plan's "base")
  audio/voice-vNNN.wav          the voice, levelled to the Short loudness (edit_style.shorts)
  work/words-vNNN.json          word timings of the Short's voice: recognized again (new), or carried over (carry)
  work/short-cut-vNNN.json      report: pieces with source times, crop and face, levels at the piece edges, word check,
                                warnings and the "please listen" list (`crewcut cut short-check` reads it)

Rules from real Shorts:
  - No piece over a cut boundary of the episode (the picture would jump). The tool stops and names the piece.
  - A crop smaller than the output is soft (a 1080p original gives 608 px). The tool says so before building and
    builds only with --accept-soft.
  - Word times are often off (0.35 s and more were seen). New recognition on the Short's own voice, or a check of the
    carried-over times against the level; fixed seconds (the "from"/"to" in the report) are the way out.
  - Loudness: the limiter takes about limiter_headroom_db, so the voice gets its gain for target + headroom, then the
    limiter, then a measurement; the gain is corrected until the measured value is on target.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from pathlib import Path

from . import audio, build, media
from .common import (
    CutError,
    check_version,
    cut_settings,
    episode_dir,
    inside,
    next_version,
    read_json,
    rel,
    version_in,
    write_new_json,
)

RATE = 48000
OUT_SIZE = (1080, 1920)
PAD_IN, PAD_OUT = 0.10, 0.16
EDGE_WINDOW = (0.03, 0.08)   # seconds inside a piece edge where the level is read (after the fades)
EDGE_LOUD_DB = 12.0          # an edge this far above the voice's noise floor lies inside sound
WORD_OFFSET_MAX = 0.15       # carried word times further off than this need new times or fixed seconds


# ---- words -------------------------------------------------------------------------------------------------------
def norm(word: str) -> str:
    return re.sub(r"^[\W_]+|[\W_]+$", "", str(word).strip().lower())


def load_words(path: Path) -> list[dict]:
    """[{"w", "s", "e"}] sorted by start. Also accepts word/text and start/end keys, and {"words": [...]}."""
    raw = read_json(path)
    if isinstance(raw, dict):
        raw = raw.get("words") or []
    out = []
    for x in raw:
        w = x.get("w", x.get("word", x.get("text")))
        s = x.get("s", x.get("start"))
        if w is None or s is None or not str(w).strip():
            continue
        e = x.get("e", x.get("end"))
        out.append({"w": str(w).strip(), "s": float(s), "e": None if e is None else float(e)})
    out.sort(key=lambda x: x["s"])
    for a, b in zip(out, out[1:] + [None], strict=True):
        if a["e"] is None:
            a["e"] = min(b["s"], a["s"] + 1.0) if b else a["s"] + 0.5
    return out


def find_phrase(words: list[dict], phrase: str, after: float, what: str) -> tuple[int, int]:
    """Index of the first and last word of the first match of `phrase` that starts at `after` seconds or later."""
    toks = [t for t in (norm(x) for x in str(phrase).split()) if t]
    if not toks:
        raise CutError(f"{what}: the word is empty")
    for i, w in enumerate(words):
        if w["s"] < after - 0.05:
            continue
        if all(i + k < len(words) and norm(words[i + k]["w"]) == t for k, t in enumerate(toks)):
            return i, i + len(toks) - 1
    raise CutError(f"{what}: «{phrase}» not found from {after:g} s on in the words")


def words_in(words: list[dict], a: float, b: float) -> list[dict]:
    return [w for w in words if a - 0.001 <= (w["s"] + w["e"]) / 2 < b]


# ---- the source episode ------------------------------------------------------------------------------------------
def newest(folder: Path, prefix: str, suffix: str = ".json") -> Path | None:
    found = []
    for f in folder.glob(f"{prefix}-v*{suffix}"):
        m = re.fullmatch(re.escape(prefix) + r"-v(\d{3,})" + re.escape(suffix), f.name)
        if m:
            found.append((int(m.group(1)), f))
    return max(found)[1] if found else None


def timeline(manifest: dict) -> list[dict]:
    """The clips of a build record with t0/t1 in seconds on the cut timeline."""
    fps = int(manifest["fps"])
    out, frame = [], 0
    for c in manifest["clips"]:
        fin = int(c.get("timeline_in_frame", frame))
        fout = int(c["timeline_out_frame"]) if "timeline_out_frame" in c else fin + build.frames_of(c, fps)
        out.append({**c, "t0": fin / fps, "t1": fout / fps})
        frame = fout
    return out


def clip_at(clips: list[dict], t: float) -> int | None:
    return next((i for i, c in enumerate(clips) if c["t0"] - 1e-6 <= t < c["t1"]), None)


def faces_from_selects(src_dir: Path, cut_plan: dict) -> dict[str, list[float]]:
    sel = cut_plan.get("selects")
    if not sel:
        return {}
    p = inside(src_dir, sel)
    if not p.is_file():
        return {}
    takes = read_json(p).get("takes") or {}
    return {t["source"]: t["face"] for t in takes.values() if t.get("source") and t.get("face")}


def as_face(v) -> list[float]:
    if isinstance(v, (int, float)):
        return [float(v), 0.4]
    return [float(v[0]), float(v[1]) if len(v) > 1 else 0.4]


def face_for(c: dict, spec_faces: dict, sel_faces: dict, face_y: float) -> tuple[list[float], str]:
    """(face centre as a share of the source frame, where it came from)."""
    if c["source"] in spec_faces:
        return as_face(spec_faces[c["source"]]), "spec"
    if c.get("face"):
        return as_face(c["face"]), "cut"
    if c["source"] in sel_faces:
        return as_face(sel_faces[c["source"]]), "selects"
    z = float(c.get("zoom", 1) or 1)
    if z > 1.0001 and c.get("zoom_center"):
        free = 1 - 1 / z
        cx, cy = c["zoom_center"]
        return [round(cx * free + 0.5 / z, 3), round(cy * free + face_y / z, 3)], "zoom centre"
    return [0.5, 0.4], "default"


# ---- framing -----------------------------------------------------------------------------------------------------
def even(v: float) -> int:
    return max(2, 2 * round(v / 2))


def crop_box(src_w: int, src_h: int, face: list[float], out: tuple[int, int] = OUT_SIZE, zoom: float = 1.0,
             face_y: float = 0.40) -> list[int]:
    """[x, y, w, h]: the largest crop of the output's aspect ratio (smaller by zoom), centred on the face."""
    ratio = out[0] / out[1]
    if src_w / src_h > ratio:
        cw, ch = src_h * ratio, float(src_h)
    else:
        cw, ch = float(src_w), src_w / ratio
    cw, ch = min(even(cw / zoom), src_w - src_w % 2), min(even(ch / zoom), src_h - src_h % 2)
    x = min(max(0, round(face[0] * src_w - cw / 2)), src_w - cw)
    y = min(max(0, round(face[1] * src_h - ch * face_y)), src_h - ch)
    return [int(x), int(y), int(cw), int(ch)]


def face_in_crop(face: list[float], src: tuple[int, int], box: list[int]) -> list[float]:
    x, y, w, h = box
    return [round((face[0] * src[0] - x) / w, 3), round((face[1] * src[1] - y) / h, 3)]


def soft_warning(source: str, src: tuple[int, int], box: list[int], out: tuple[int, int]) -> str | None:
    if box[2] >= out[0] and box[3] >= out[1]:
        return None
    scale = out[0] / box[2]
    return (f"{source} is {src[0]}x{src[1]}: the 9:16 crop is {box[2]}x{box[3]} px, scaled up {scale:.1f}x to "
            f"{out[0]}x{out[1]} it looks soft. A 4K landscape original gives a {even(2160 * out[0] / out[1])} px "
            "wide crop; an upright recording gives the full width.")


def source_size(info: dict, name: str) -> tuple[int, int]:
    v = media.video_stream(info)
    if not v:
        raise CutError(f"{name} has no picture")
    if media.is_hdr(v):
        raise CutError(f"{name} is HDR. Decide the colour conversion first; nothing is converted on its own.")
    w, h = int(v["width"]), int(v["height"])
    return (h, w) if media.rotation(v) % 180 else (w, h)


# ---- planning (reads and probes, writes nothing) -----------------------------------------------------------------
def piece_times(p: dict, k: int, words: list[dict] | None, clips: list[dict], fps: int, pad_in: float,
                pad_out: float) -> tuple[float, float, int]:
    """(start, end, clip index) of one piece on the cut timeline, rounded to frames. Refuses a cut boundary."""
    pid = str(p.get("id") or f"p{k + 1}")
    if "from_word" in p or "to_word" in p:
        if not words:
            raise CutError(f"piece {pid}: word pieces need the words of the finished voice (spec key 'words')")
        i0, _ = find_phrase(words, p.get("from_word", ""), float(p.get("after", 0)), f"piece {pid} from_word")
        _, j1 = find_phrase(words, p.get("to_word", ""), float(p.get("to_after", words[i0]["s"])),
                            f"piece {pid} to_word")
        if j1 < i0:
            raise CutError(f"piece {pid}: to_word comes before from_word")
        first, last = words[i0], words[j1]
        ci = clip_at(clips, (first["s"] + first["e"]) / 2)
        if ci is None:
            raise CutError(f"piece {pid}: no cut at {first['s']:.2f} s")
        c = clips[ci]
        a = first["s"] - pad_in
        if i0 > 0:
            a = max(a, words[i0 - 1]["e"] + 0.02)
        b = last["e"] + pad_out
        if j1 + 1 < len(words):
            b = min(b, words[j1 + 1]["s"] - 0.04)
        if last["e"] > c["t1"] + 0.5 / fps:
            raise CutError(boundary_message(pid, c, clips, ci))
        a, b = max(a, c["t0"]), min(b, c["t1"])
    elif "from" in p and "to" in p:
        a, b = float(p["from"]), float(p["to"])
        ci = clip_at(clips, a)
        if ci is None:
            raise CutError(f"piece {pid}: {a:g} s is not inside the cut")
    else:
        raise CutError(f"piece {pid}: give from_word/to_word or from/to (seconds)")
    c = clips[ci]
    a, b = math.floor(a * fps + 0.5 + 1e-9) / fps, math.floor(b * fps + 0.5 + 1e-9) / fps   # half up, not to even
    if b > c["t1"] + 0.5 / fps:
        raise CutError(boundary_message(pid, c, clips, ci))
    if a < c["t0"] - 0.5 / fps:
        raise CutError(f"piece {pid} starts before the cut {c['id']} ({a:.2f} < {c['t0']:.2f} s)")
    if round((b - a) * fps) < 2:
        raise CutError(f"piece {pid} is too short ({b - a:.2f} s)")
    return a, b, ci


def boundary_message(pid: str, c: dict, clips: list[dict], ci: int) -> str:
    nxt = clips[ci + 1]["id"] if ci + 1 < len(clips) else "the end"
    return (f"piece {pid} crosses the cut boundary at {c['t1']:.2f} s (between cuts {c['id']} and {nxt}): the picture "
            "would jump. Split it into two pieces at that boundary.")


def prepare(spec_path: Path, ep_dir: Path, probe=None) -> dict:
    """Read the spec, the source episode and the originals; resolve every piece. Nothing is written."""
    probe = probe or media.probe
    spec = read_json(spec_path)
    version = check_version(spec.get("version") or version_in(spec_path.name)
                            or next_version(ep_dir / "work", "short-cut"))
    if not spec.get("source_episode"):
        raise CutError("the spec needs source_episode (the finished episode the pieces come from)")
    src_id = str(spec["source_episode"])
    src_dir = episode_dir(src_id)
    dec_path = inside(src_dir, spec["decisions"]) if spec.get("decisions") else newest(src_dir / "work",
                                                                                         "edit-decisions")
    if not dec_path or not dec_path.is_file():
        raise CutError(f"{src_id} has no built speaker cut (work/edit-decisions-vNNN.json): build it first")
    manifest = read_json(dec_path)
    fps = int(manifest["fps"])
    clips = timeline(manifest)
    src_version = manifest.get("version") or version_in(dec_path.name)
    cut_plan = {}
    if manifest.get("plan") and inside(src_dir, manifest["plan"]).is_file():
        cut_plan = read_json(inside(src_dir, manifest["plan"]))
    settings = cut_settings(cut_plan)
    words_rel = spec.get("words") or f"work/words-{src_version}.json"
    words_path = inside(src_dir, words_rel)
    words = load_words(words_path) if words_path.is_file() else None
    if "voice" in spec:
        voice_rel = spec["voice"]
    else:
        voice_rel = manifest.get("voice") if manifest.get("voice") and inside(src_dir, manifest["voice"]).is_file() \
            else None
    if voice_rel and not inside(src_dir, voice_rel).is_file():
        raise CutError(f"voice not found in {src_id}: {voice_rel}")
    if "grade" in spec:
        grade_filter = spec["grade"] or None
    elif any((src_dir / "work").glob("speaker-graded-*.mov")):
        from . import grade
        grade_filter = grade.base_filter()
    else:
        grade_filter = None
    size = tuple(int(v) for v in (spec.get("size") or OUT_SIZE))
    if len(size) != 2 or size[0] % 2 or size[1] % 2 or size[0] >= size[1]:
        raise CutError("size must be [width, height], both even, upright")
    pad_in, pad_out = float(spec.get("pad_in", PAD_IN)), float(spec.get("pad_out", PAD_OUT))
    face_y = float(settings["face_y"])
    sel_faces = faces_from_selects(src_dir, cut_plan)
    spec_faces = spec.get("face") or {}
    if not spec.get("pieces"):
        raise CutError("the spec has no pieces")
    infos: dict[str, dict] = {}
    pieces, warnings, soft, t_short, ids = [], [], [], 0.0, set()
    for k, p in enumerate(spec["pieces"]):
        pid = str(p.get("id") or f"p{k + 1}")
        if pid in ids or not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", pid):
            raise CutError(f"piece id {pid!r}: unique, letters, digits, - and _ only")
        ids.add(pid)
        a, b, ci = piece_times(p, k, words, clips, fps, pad_in, pad_out)
        c = clips[ci]
        src = inside(src_dir, c["source"])
        if not src.is_file():
            raise CutError(f"piece {pid}: the original {c['source']} is gone from {src_id}. Clip mode needs it.")
        if c["source"] not in infos:
            infos[c["source"]] = probe(src)
        info = infos[c["source"]]
        if not voice_rel:
            a_src = inside(src_dir, c["audio"]["source"]) if c.get("audio") else src
            if not a_src.is_file() or (a_src == src and not media.audio_streams(info)):
                raise CutError(f"piece {pid}: no cleaned voice and no camera sound for {c['source']}")
        sw, sh = source_size(info, c["source"])
        face, how = face_for(c, spec_faces, sel_faces, face_y)
        zoom = float(p.get("zoom", 1.0) or 1.0)
        if not 1.0 <= zoom <= 2.0:
            raise CutError(f"piece {pid}: zoom must be between 1.0 and 2.0")
        box = crop_box(sw, sh, face, size, zoom, face_y)
        msg = soft_warning(c["source"], (sw, sh), box, size)
        if msg and msg not in soft:
            soft.append(msg)
        if how == "default" and c["source"] not in [x["source"] for x in pieces]:
            warnings.append(f"no face position known for {c['source']}: the crop is centred. Give it in the spec "
                            "(\"face\") or check the contact sheet.")
        speed = float(c.get("speed", 1) or 1)
        frames = round((b - a) * fps)
        src_from = float(c["start"]) + (a - c["t0"]) * speed
        voice_until = (float(c["end"]) - src_from) / speed
        pieces.append({
            "id": pid, "clip": c["id"], "source": c["source"], "from": round(a, 4), "to": round(b, 4),
            "frames": frames, "seconds": round(frames / fps, 4), "source_from": round(src_from, 4), "speed": speed,
            "voice_until": round(voice_until, 4) if voice_until < frames / fps else None,
            "short_from": round(t_short, 4), "short_to": round(t_short + frames / fps, 4),
            "source_size": [sw, sh], "crop": box, "zoom": zoom, "face_source": face, "face_from": how,
            "face": face_in_crop(face, (sw, sh), box), "audio": c.get("audio"),
            "text": " ".join(w["w"] for w in words_in(words or [], a, b))})
        t_short += frames / fps
    return {"version": version, "spec": spec_path, "spec_rel": rel(ep_dir, spec_path), "source_episode": src_id,
            "source_dir": src_dir, "decisions": rel(src_dir, dec_path), "fps": fps, "size": list(size),
            "words": words, "words_file": words_rel if words is not None else None, "voice": voice_rel,
            "voice_filter": cut_plan.get("voice_filter") or settings["voice_filter"], "grade": grade_filter,
            "pieces": pieces, "seconds": round(t_short, 4), "frames": sum(p["frames"] for p in pieces),
            "soft": soft, "warnings": warnings}


def describe_plan(plan: dict) -> str:
    lines = [f"{p['short_from']:6.2f}-{p['short_to']:6.2f}  {p['id']:<6} {p['clip']:<10} "
             f"{p['from']:.2f}-{p['to']:.2f} s  crop {p['crop'][2]}x{p['crop'][3]}  | {p['text']}"
             for p in plan["pieces"]]
    lines.append(f"{len(plan['pieces'])} pieces, {plan['seconds']:.2f} s, voice: "
                 + (plan["voice"] or "camera sound with the voice filter"))
    lines += [f"SOFT: {m}" for m in plan["soft"]] + [f"warning: {m}" for m in plan["warnings"]]
    return "\n".join(lines)


# ---- commands ----------------------------------------------------------------------------------------------------
def out_paths(ep_dir: Path, version: str) -> dict[str, Path]:
    return {"folder": ep_dir / "work" / f"short-{version}", "speaker": ep_dir / "work" / f"speaker-{version}.mov",
            "voice": ep_dir / "audio" / f"voice-{version}.wav", "words": ep_dir / "work" / f"words-{version}.json",
            "report": ep_dir / "work" / f"short-cut-{version}.json"}


def picture_cmd(p: dict, src: Path, dest: Path, fps: int, size: list[int], grade_filter: str | None) -> list:
    n, sp = p["frames"], p["speed"]
    keep = n / fps * sp + 1 / fps
    x, y, w, h = p["crop"]
    vf = (f"trim=duration={keep:.4f},setpts=(PTS-STARTPTS)/{sp:g},fps={fps},crop={w}:{h}:{x}:{y},"
          f"scale={size[0]}:{size[1]}:flags=lanczos," + (f"{grade_filter}," if grade_filter else "")
          + "setsar=1,format=yuv420p")
    return ["ffmpeg", "-nostdin", "-v", "error", "-n", "-ss", f"{p['source_from']:.4f}", "-i", src, "-map", "0:v:0",
            "-an", "-vf", vf, "-frames:v", n, "-c:v", "libx264", "-crf", 14, "-preset", "medium", "-pix_fmt", "yuv420p",
            "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", "-map_metadata", "-1", dest]


def fades(seconds: float, voice_until: float | None = None) -> str:
    """Short fades at both piece edges; silence after the last word when the piece runs into a cut's tail."""
    out = "afade=t=in:d=0.03,"
    if voice_until is not None and voice_until < seconds:
        out += f"afade=t=out:st={max(0.0, voice_until - 0.03):.4f}:d=0.03,"
    return out + f"afade=t=out:st={max(0.0, seconds - 0.06):.4f}:d=0.06,apad,atrim=end_sample={round(seconds * RATE)}"


def voice_cmd(p: dict, plan: dict, dest: Path) -> list:
    """The piece's voice: from the cleaned voice of the episode, else from the camera (or recorder) sound."""
    src_dir, dur = plan["source_dir"], p["seconds"]
    tail = ["-ac", "1", "-ar", RATE, "-c:a", "pcm_s24le", dest]
    if plan["voice"]:
        return ["ffmpeg", "-nostdin", "-v", "error", "-n", "-ss", f"{p['from']:.4f}", "-t", f"{dur + 0.05:.4f}",
                "-i", inside(src_dir, plan["voice"]), "-vn", "-af", f"aresample={RATE}," + fades(dur), *tail]
    a = p.get("audio")
    src = inside(src_dir, a["source"] if a else p["source"])
    start = p["source_from"] - (float(a["offset"]) if a else 0.0)
    sp = p["speed"]
    af = (f"{plan['voice_filter']},asetpts=PTS-STARTPTS,atempo={sp:g},aresample={RATE},"
          + fades(dur, p.get("voice_until")))
    return ["ffmpeg", "-nostdin", "-v", "error", "-n", "-ss", f"{start:.4f}", "-t", f"{dur * sp + 0.1:.4f}",
            "-i", src, "-vn", "-map", "0:a:0", "-af", af, *tail]


def join_voice_cmd(parts: list[Path], dest: Path) -> list:
    ins = [x for f in parts for x in ("-i", f)]
    graph = "".join(f"[{k}:a]" for k in range(len(parts))) + f"concat=n={len(parts)}:v=0:a=1[a]"
    return ["ffmpeg", "-nostdin", "-v", "error", "-y", *ins, "-filter_complex", graph, "-map", "[a]",
            "-ar", RATE, "-ac", "1", "-c:a", "pcm_s24le", dest]


def level_cmd(src: Path, dest: Path, gain_db: float, limit_db: float) -> list:
    lim = min(1.0, max(0.0625, 10 ** (limit_db / 20)))
    return ["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", src, "-af",
            f"volume={gain_db:.2f}dB,alimiter=limit={lim:.4f}:attack=5:release=50:level=false",
            "-ar", RATE, "-ac", "1", "-c:a", "pcm_s24le", dest]


def mux_cmd(concat: Path, voice: Path, seconds: float, dest: Path) -> list:
    return ["ffmpeg", "-nostdin", "-v", "error", "-n", "-f", "concat", "-safe", "0", "-i", concat, "-i", voice,
            "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "pcm_s24le", "-t", f"{seconds:.4f}", dest]


def short_targets() -> dict:
    from .. import brand
    try:
        pack = brand.load()
    except Exception:  # a broken pack must not stop the cut; brand check reports it
        pack = None

    def v(key: str, default):
        return pack.value(key, default) if pack else default
    return {"lufs": float(v("edit_style.shorts.loudness_lufs", v("edit_style.loudness_lufs", -14.0))),
            "headroom_db": float(v("edit_style.shorts.limiter_headroom_db", 1.4)),
            "true_peak_db": float(v("edit_style.true_peak_db", -1.5))}


def level_voice(raw: Path, dest: Path, folder: Path, targets: dict, tries: int = 3) -> dict:
    """Gain for target + headroom, limiter, measure; correct the gain until the measurement is within 0.5 LU."""
    before = audio.measure_loudness(raw)
    if float(before["integrated_lufs"]) < -60:
        raise CutError("the joined voice is silent (below -60 LUFS). Check the voice file or the camera sound.")
    gain = targets["lufs"] + targets["headroom_db"] - float(before["integrated_lufs"])
    tmp = folder / "voice-try.wav"
    m = before
    for _ in range(tries):
        media.run(level_cmd(raw, tmp, gain, targets["true_peak_db"] - 0.5))
        m = audio.measure_loudness(tmp)
        off = targets["lufs"] - float(m["integrated_lufs"])
        if abs(off) <= 0.5:
            break
        gain += off
    if dest.exists():
        raise CutError(f"{dest.name} exists already. Make a new spec version.")
    tmp.replace(dest)
    return {"before_lufs": before["integrated_lufs"], "gain_db": round(gain, 2),
            "measured_lufs": m["integrated_lufs"], "true_peak_dbtp": m["true_peak_dbtp"], **targets}


# ---- checks on the Short's voice ---------------------------------------------------------------------------------
def levels_of(path: Path):
    """Level every 10 ms (dB) of a sound file, and its noise floor (8th percentile, at least -70 dB)."""
    import numpy as np

    from .transcribe import SAMPLE_RATE, load_audio
    from .verify import level_track
    x = load_audio(path)
    lv = level_track(x, SAMPLE_RATE) if len(x) else np.zeros(0)
    floor = float(np.percentile(lv, 8)) if len(lv) else -70.0
    return lv, max(floor, -70.0)              # digital silence would make every breath look loud


def edge_levels(levels, floor: float, pieces: list[dict]) -> list[dict]:
    """Level just inside each piece edge (after the fades). A loud edge lies inside sound: a foreign syllable or a
    clipped word is likely there."""
    import numpy as np
    out = []
    for p in pieces:
        for side, (lo, hi) in (("start", (p["short_from"] + EDGE_WINDOW[0], p["short_from"] + EDGE_WINDOW[1])),
                               ("end", (p["short_to"] - 0.06 - EDGE_WINDOW[1], p["short_to"] - 0.06 - EDGE_WINDOW[0]))):
            seg = levels[max(0, int(lo * 100)):max(0, int(hi * 100))]
            db = float(np.max(seg)) if len(seg) else -99.0
            out.append({"piece": p["id"], "side": side, "at": round(p["short_from"] if side == "start"
                                                                       else p["short_to"], 2),
                        "level_db": round(db, 1), "floor_db": round(floor, 1), "loud": db - floor > EDGE_LOUD_DB})
    return out


def word_check(words: list[dict], levels, floor: float) -> dict:
    """Carried or new word times against the level: words in silence, and how far word starts sit from the sound."""
    thr = floor + 10
    silent, offsets = [], []
    n = len(levels)
    for i, w in enumerate(words):
        seg = levels[int(w["s"] * 100):max(int(w["s"] * 100) + 1, int(w["e"] * 100))]
        if len(seg) and float((seg > thr).mean()) < 0.3:
            silent.append(w)
        prev_e = words[i - 1]["e"] if i else None
        if prev_e is not None and w["s"] - prev_e < 0.15:
            continue
        lo = w["s"] - 0.4 if prev_e is None else max(w["s"] - 0.4, (prev_e + w["s"]) / 2)
        k0, k1 = max(0, int(lo * 100)), min(n, int((w["s"] + 0.5) * 100))
        loud = [k for k in range(k0, k1) if levels[k] > thr]
        offsets.append(round((loud[0] / 100 - w["s"]) if loud else 0.5, 2))
    worst = max((abs(o) for o in offsets), default=0.0)
    ok = worst <= WORD_OFFSET_MAX and len(silent) <= max(1, len(words) // 10)
    msg = (f"word times fit the sound (largest start offset {worst:.2f} s)" if ok else
           f"word times are off: largest start offset {worst:.2f} s, {len(silent)} words in silence. Make new ones "
           "(--words new), or give the pieces in fixed seconds (the from/to values in this report).")
    return {"ok": ok, "checked": len(offsets), "largest_offset_s": worst, "silent_words": silent[:10],
            "floor_db": round(floor, 1), "message": msg}


def edge_words(pieces: list[dict], heard: list[dict]) -> list[dict]:
    """New recognition against the expected text: a different first or last word at a piece edge."""
    from .tokens import spelling, tokens
    same = spelling()

    def key(word: str, pos: int) -> str:
        t = tokens(word, same)
        return t[pos] if t else ""
    out = []
    for p in pieces:
        exp = [w for w in p["text"].split() if tokens(w)]
        got = [w["w"] for w in words_in(heard, p["short_from"], p["short_to"]) if tokens(w["w"])]
        if not exp:
            continue
        if not got:
            out.append({"piece": p["id"], "side": "all", "at": p["short_from"], "expected": p["text"], "heard": ""})
            continue
        for pos, side, at in ((0, "start", p["short_from"]), (-1, "end", p["short_to"])):
            if key(exp[pos], pos) != key(got[pos], pos):
                out.append({"piece": p["id"], "side": side, "at": round(at, 2), "expected": norm(exp[pos]),
                            "heard": norm(got[pos])})
    return out


def listen_list(pieces: list[dict], edges: list[dict], issues: list[dict], seconds: float) -> list[dict]:
    """Where a human has to listen (nobody else hears the sound)."""
    out = [{"at": 0.0, "what": "the first sentence: does it stand alone?"}]
    for a, b in zip(pieces, pieces[1:], strict=False):
        out.append({"at": b["short_from"], "what": f"join {a['id']} -> {b['id']}: no foreign syllable, no clipped "
                                                   "word, the breath sounds natural"})
    out += [{"at": e["at"], "what": f"piece {e['piece']} {e['side']}: sound at the edge ({e['level_db']} dB, floor "
                                    f"{e['floor_db']} dB)"} for e in edges if e["loud"]]
    out += [{"at": i["at"], "what": f"piece {i['piece']} {i['side']}: expected «{i['expected']}», heard "
                                    f"«{i['heard']}»"} for i in issues]
    out.append({"at": round(max(0.0, seconds - 1.5), 2), "what": "the end: a hard stop or about one second of tail"})
    return sorted(out, key=lambda x: x["at"])


# ---- the build ---------------------------------------------------------------------------------------------------
def build_short(plan: dict, ep_dir: Path, words_mode: str = "new", engine_factory: Callable | None = None,
                log=print) -> dict:
    """Cut, join, level, time the words, write the report. `plan` comes from prepare()."""
    if words_mode not in ("new", "carry"):
        raise CutError("words must be new or carry")
    if words_mode == "carry" and plan["words"] is None:
        raise CutError("no words of the finished voice to carry over: use --words new")
    if words_mode == "new" and engine_factory is None:
        raise CutError("new word times need the speech engine")
    out = out_paths(ep_dir, plan["version"])
    for key in ("speaker", "voice", "words", "report"):
        if out[key].exists():
            raise CutError(f"{rel(ep_dir, out[key])} exists already. Make a new spec version.")
    if out["folder"].exists():
        raise CutError(f"{rel(ep_dir, out['folder'])} exists already (an interrupted build?). Make a new spec version.")
    out["folder"].mkdir(parents=True)
    out["voice"].parent.mkdir(parents=True, exist_ok=True)
    fps, src_dir = plan["fps"], plan["source_dir"]
    files, parts = [], []
    for k, p in enumerate(plan["pieces"], 1):
        pic = out["folder"] / f"{k:02d}-{p['id']}.mp4"
        media.run(picture_cmd(p, inside(src_dir, p["source"]), pic, fps, plan["size"], plan["grade"]))
        got = build.probe_frames(pic)
        if got != p["frames"]:
            raise CutError(f"piece {p['id']}: {got} frames, expected {p['frames']}")
        wav = out["folder"] / f"{k:02d}-{p['id']}.wav"
        media.run(voice_cmd(p, plan, wav))
        files.append({"file": rel(ep_dir, pic), "frames": p["frames"]})
        parts.append(wav)
        log(f"cut: {p['id']} {p['frames']} frames")
    raw = out["folder"] / "voice-joined.wav"
    media.run(join_voice_cmd(parts, raw))
    loud = level_voice(raw, out["voice"], out["folder"], short_targets())
    concat = out["folder"] / "concat.txt"
    concat.write_text(build.concat_text(files, fps), encoding="utf-8")
    media.run(mux_cmd(concat, out["voice"], plan["frames"] / fps, out["speaker"]))
    log(f"joined: {rel(ep_dir, out['speaker'])}")

    carried = []
    for p in plan["pieces"]:
        for w in words_in(plan["words"] or [], p["from"], p["to"]):
            carried.append({"w": w["w"], "s": round(max(w["s"], p["from"]) - p["from"] + p["short_from"], 3),
                            "e": round(min(w["e"], p["to"]) - p["from"] + p["short_from"], 3)})
    levels, floor = levels_of(out["voice"])
    issues: list[dict] = []
    words_info: dict = {"mode": words_mode, "file": rel(ep_dir, out["words"]),
                        "carried_from": plan["words_file"]}
    if carried:
        words_info["carried_check"] = word_check(carried, levels, floor)
    if words_mode == "new":
        from .transcribe import load_audio
        engine = engine_factory()
        heard = engine.words(load_audio(out["voice"]))
        if not heard:
            raise CutError("no words recognized on the Short's voice. Check the sound, or use --words carry.")
        issues = edge_words(plan["pieces"], heard) if plan["words"] else []
        words_info["engine"] = engine.describe() if hasattr(engine, "describe") else None
        final = heard
    else:
        final = carried
    words_info["check"] = word_check(final, levels, floor)
    words_info["count"] = len(final)
    words_info["edge_issues"] = issues
    write_new_json(out["words"], final)
    edges = edge_levels(levels, floor, plan["pieces"])
    warnings = list(plan["warnings"]) + list(plan["soft"])
    if not words_info["check"]["ok"]:
        warnings.append(words_info["check"]["message"])
    if loud["measured_lufs"] is not None and abs(loud["measured_lufs"] - loud["lufs"]) > 1.0:
        warnings.append(f"the voice measures {loud['measured_lufs']} LUFS, target {loud['lufs']:g}")
    warnings += [f"piece {e['piece']} {e['side']} at {e['at']} s lies inside sound: listen there" for e in edges
                 if e["loud"]]
    warnings += [f"piece {i['piece']} {i['side']}: expected «{i['expected']}», heard «{i['heard']}»" for i in issues]
    seconds = round(plan["frames"] / fps, 3)
    report = {"version": plan["version"], "spec": plan["spec_rel"], "source_episode": plan["source_episode"],
              "decisions": plan["decisions"], "fps": fps, "width": plan["size"][0], "height": plan["size"][1],
              "frames": plan["frames"], "seconds": seconds, "grade": plan["grade"],
              "speaker": rel(ep_dir, out["speaker"]), "voice": {"file": rel(ep_dir, out["voice"]),
                                                                "from": plan["voice"] or "camera", **loud},
              "words": words_info, "pieces": [{k: v for k, v in p.items() if k != "audio"} for p in plan["pieces"]],
              "edges": edges, "warnings": warnings,
              "listen": listen_list(plan["pieces"], edges, issues, seconds),
              "framing": "9:16 crop of the original around the face, scaled to the output size"}
    write_new_json(out["report"], report)
    return report


def describe(r: dict) -> str:
    lines = [f"{p['short_from']:6.2f}-{p['short_to']:6.2f}  {p['id']:<6} {p['clip']:<10} | {p['text']}"
             for p in r["pieces"]]
    v = r["voice"]
    lines.append(f"{len(r['pieces'])} pieces, {r['seconds']} s -> {r['speaker']}")
    lines.append(f"voice: {v['file']} ({v['from']}), {v['measured_lufs']} LUFS, true peak {v['true_peak_dbtp']} dBTP")
    lines.append(f"words ({r['words']['mode']}): {r['words']['file']}, {r['words']['check']['message']}")
    lines += [f"warning: {w}" for w in r["warnings"]]
    lines.append("please listen:")
    lines += [f"  {x['at']:6.2f} s  {x['what']}" for x in r["listen"]]
    lines.append(f"report: work/short-cut-{r['version']}.json")
    return "\n".join(lines)
