"""Graphics behind the speaker: a matte of the speaker from a rented GPU, an edge gate, the composite, the fallback.

    clip = export_shot(source, 12.0, 16.5, ep / "render/matte/s03.mp4")      # picture only, 0.5 s margin each side
    results = matte_rented([Shot("s03", ep, source, 12.0, 16.5)], compute, cap_usd=1.0)   # alpha + foreground PNGs
    check = edge_check(frames_dir, ep / "render/matte/s03/pha", out_dir, face=(820, 180, 300, 380))
    where = decide(check)            # "behind", or "beside" with where.reason and where.side
    argv = composite_args(...)       # speaker picture -> graphic -> person, at the speaker's exact size and position

The matting model is RobustVideoMatting (RVM, github.com/PeterL1n/RobustVideoMatting, GPL-3.0). Crewcut (MIT) never
ships or imports it: the rented machine clones RVM at a pinned commit, downloads the checkpoint from RVM's GitHub
release, checks its sha256 and runs RVM's own `inference.py` as a separate program. Only the picture of the shot (no
sound) goes up, and only after a yes on a spend card that says so (crewcut/compute/privacy.py). The machine is deleted
when the session ends. Everything else here (export, gate, crops, composite) runs on this machine with ffmpeg, numpy
and Pillow. See docs/motion-matte.md.
"""

from __future__ import annotations

import json
import re
import shlex
import shutil
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from ..render import media

# ---- the pinned model --------------------------------------------------------------------------------------------
RVM_REPO = "https://github.com/PeterL1n/RobustVideoMatting.git"
RVM_COMMIT = "53d74c6826735f01f4406b5ca9075eee27bec094"          # master, 13 Mar 2023 (the last commit)
RVM_VARIANT = "resnet50"           # the larger model: finer hair and fewer edge errors than mobilenetv3, still fast
RVM_CHECKPOINT = "rvm_resnet50.pth"
RVM_CHECKPOINT_URL = "https://github.com/PeterL1n/RobustVideoMatting/releases/download/v1.0.0/rvm_resnet50.pth"
RVM_CHECKPOINT_BYTES = 107_905_875
RVM_CHECKPOINT_SHA256 = "c191a807251164c073dce5fa408e7a816070d539b882b2a3150330a9fec112ce"
TORCH_INDEX = "https://download.pytorch.org/whl/cu124"
TORCH_PACKAGES = ("torch==2.5.1", "torchvision==0.20.1")
RVM_PACKAGES = ("numpy==1.26.4", "av==12.3.0", "pims==0.7", "tqdm==4.67.1")   # what RVM's inference_utils imports
SEQ_CHUNK = 12                     # frames per model call (RVM's documented example value)
REMOTE_RVM = "/opt/rvm"
REMOTE_WORK = "/work/matte"

# ---- the shot clip -----------------------------------------------------------------------------------------------
MARGIN_S = 0.5                     # extra picture before and after the span, so the recurrent model settles first
MAX_SHOT_S = 120.0                 # a behind-the-speaker insert is short; longer spans are refused
CLIP_CRF = 10                      # H.264 near-lossless for the model's input
CLIP_SUFFIX = ".mp4"
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


class MatteError(RuntimeError):
    """The matte step failed (export, rented run or fetch). Exit code 1."""


def _safe_id(shot_id: str) -> str:
    if not _SAFE_ID.match(str(shot_id)) or ".." in str(shot_id):
        raise ValueError(f"bad shot id {shot_id!r}: letters, digits, '.', '_' and '-' only")
    return str(shot_id)


@dataclass
class Shot:
    """One span of the speaker picture that gets a graphic behind the speaker."""

    id: str
    episode_dir: Path
    source: Path | None = None            # the speaker recording; needed only when the clip is not cut yet
    start_s: float = 0.0
    end_s: float = 0.0
    fps: float | None = None              # the episode's frame rate (the clip is made constant-rate at it)
    face: tuple[int, int, int, int] | None = None   # x, y, w, h of the face in the source picture, if known

    def __post_init__(self):
        _safe_id(self.id)
        self.episode_dir = Path(self.episode_dir)
        self.source = Path(self.source) if self.source else None

    @property
    def episode(self) -> str:
        return self.episode_dir.name

    @property
    def matte_dir(self) -> Path:
        return self.episode_dir / "render" / "matte"

    @property
    def clip(self) -> Path:
        return self.matte_dir / f"{self.id}{CLIP_SUFFIX}"

    @property
    def out_dir(self) -> Path:
        return self.matte_dir / self.id


@dataclass
class MatteResult:
    id: str
    ok: bool
    dir: Path
    frames: int = 0
    seconds: float = 0.0
    error: str = ""
    decision: dict | None = None
    check: dict | None = field(default=None, repr=False)

    @property
    def alpha_dir(self) -> Path:
        return self.dir / "pha"

    @property
    def fgr_dir(self) -> Path:
        return self.dir / "fgr"

    def to_dict(self) -> dict:
        return {"id": self.id, "ok": self.ok, "dir": str(self.dir), "alpha": str(self.alpha_dir),
                "foreground": str(self.fgr_dir), "frames": self.frames, "seconds": round(self.seconds, 1),
                "error": self.error, "decision": self.decision,
                "passed": None if self.check is None else bool(self.check.get("passed"))}


# ---- 1. export: the picture of one span, nothing else ------------------------------------------------------------
def _check_out(out: Path) -> Path:
    out = Path(out)
    if out.parent.name != "matte" or out.parent.parent.name != "render":
        raise ValueError(f"{out}: a matte clip goes directly into an episode's render/matte/ folder")
    if out.suffix.lower() != CLIP_SUFFIX:
        raise ValueError(f"{out}: a matte clip is an {CLIP_SUFFIX} file")
    _safe_id(out.stem)
    return out


def export_cmd(source: Path, clip_start_s: float, seconds: float, out: Path, fps: float | None = None) -> list[str]:
    """ffmpeg arguments: the first video stream only, no sound, no subtitles, no data, no metadata (no camera or
    location tags), constant frame rate when `fps` is given, H.264 CRF 10."""
    cmd = [media.ffmpeg(), "-hide_banner", "-nostdin", "-y", "-v", "error", "-ss", f"{clip_start_s:.3f}", "-i",
           str(source), "-t", f"{seconds:.3f}", "-map", "0:v:0", "-an", "-sn", "-dn", "-map_metadata", "-1",
           "-map_chapters", "-1"]
    if fps:
        cmd += ["-vf", f"fps={fps:g}"]
    return cmd + ["-c:v", "libx264", "-preset", "medium", "-crf", str(CLIP_CRF), "-pix_fmt", "yuv420p",
                  "-movflags", "+faststart", str(out)]


def probe_cmd(path: Path) -> list[str]:
    return [media.ffprobe(), "-v", "error", "-show_entries", "stream=codec_type,width,height,r_frame_rate,nb_frames",
            "-of", "json", str(path)]


def probe(path: Path, runner: media.Runner = media.run) -> dict:
    """{"types": [...], "width", "height", "fps", "frames"} of a clip (first video stream)."""
    rc, out = runner(probe_cmd(path), timeout=120)
    if rc != 0:
        raise MatteError(f"cannot read {Path(path).name}: {media.tail(out, 300)}")
    try:
        streams = json.loads(out[out.index("{"):]).get("streams") or []
    except (ValueError, AttributeError) as e:
        raise MatteError(f"cannot read {Path(path).name}: {media.tail(out, 300)}") from e
    v = next((s for s in streams if s.get("codec_type") == "video"), {})
    num, _, den = str(v.get("r_frame_rate") or "0/1").partition("/")
    try:
        fps = float(num) / float(den or 1)
    except (ValueError, ZeroDivisionError):
        fps = 0.0
    nb = str(v.get("nb_frames") or "")
    return {"types": [str(s.get("codec_type")) for s in streams], "width": int(v.get("width") or 0),
            "height": int(v.get("height") or 0), "fps": round(fps, 3), "frames": int(nb) if nb.isdigit() else None}


def meta_path(clip: Path) -> Path:
    return Path(clip).with_suffix(".json")


def export_shot(source: Path, start_s: float, end_s: float, out: Path, runner: media.Runner = media.run, *,
                fps: float | None = None, margin_s: float = MARGIN_S) -> Path:
    """Cut the picture of one span (plus `margin_s` each side) into `<episode>/render/matte/<shot>.mp4`.

    Picture only: the result is checked with ffprobe and must hold exactly one video stream. Next to it,
    `<shot>.json` records where the clip starts in the source, so frame k of the matte belongs to
    `clip_start_s + k / fps`. With `fps`, the margin is a whole number of frames, so a span that starts on a frame
    boundary gives a clip that starts on one too (and the matte lines up with the speaker picture frame by frame).
    Returns the clip path."""
    out = _check_out(out)
    start_s, end_s = float(start_s), float(end_s)
    if not end_s > start_s >= 0:
        raise ValueError(f"bad span {start_s}-{end_s} s")
    if end_s - start_s > MAX_SHOT_S:
        raise ValueError(f"span of {end_s - start_s:.0f} s is longer than {MAX_SHOT_S:.0f} s; graphics behind the "
                         "speaker are for short inserts")
    if fps:
        margin_s = round(margin_s * fps) / fps
    clip_start = max(0.0, start_s - margin_s)
    seconds = end_s + margin_s - clip_start
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(f".{out.stem}.part{out.suffix}")
    tmp.unlink(missing_ok=True)
    rc, text = runner(export_cmd(Path(source), clip_start, seconds, tmp, fps), timeout=1800)
    if rc != 0 or not tmp.is_file():
        tmp.unlink(missing_ok=True)
        raise MatteError(f"export of {out.stem} failed: {media.tail(text, 300)}")
    info = probe(tmp, runner)
    if info["types"] != ["video"]:
        tmp.unlink(missing_ok=True)
        raise MatteError(f"export of {out.stem} is not picture-only ({', '.join(info['types'])}); not kept")
    tmp.replace(out)
    meta = {"shot": out.stem, "source": str(source), "start_s": round(start_s, 3), "end_s": round(end_s, 3),
            "clip_start_s": round(clip_start, 3), "seconds": round(seconds, 3), "margin_s": margin_s,
            "fps": fps or info["fps"], "width": info["width"], "height": info["height"]}
    meta_path(out).write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return out


def read_meta(clip: Path) -> dict:
    p = meta_path(clip)
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}


# ---- 2. the rented run -------------------------------------------------------------------------------------------
def downsample_ratio(width: int, height: int) -> float:
    """RVM's own guide for portrait shots (head and shoulders): the first model stage should see about 480 px on the
    long side, i.e. 0.25 at 1920x1080 (and 1080x1920), 0.375 at 1280x720, 0.125 at 3840x2160. The second stage then
    refines at full resolution. A higher ratio is for full-body shots and is not better here."""
    long_side = max(int(width), int(height), 1)
    return round(min(1.0, 480 / long_side), 4)


def _bash(script: str) -> str:
    return "bash -c " + shlex.quote(script.strip() + "\n")


def remote_commands(jobs: list[dict]) -> dict:
    """Every command the rented machine runs, as `bash -c '...'` strings for Machine.run.

    jobs: [{"id": shot id, "ratio": downsample ratio}]. Returns {"setup": str, "matte": {id: str},
    "clean": {id: str}, "wipe": str}. Lines with MATTE_SETUP_OK / MATTE_OK <id> <frames> mark success."""
    r, w = REMOTE_RVM, REMOTE_WORK
    setup = f"""
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_INPUT=1
need=""
for t in git curl ffmpeg python3 sha256sum; do command -v "$t" > /dev/null 2>&1 || need=1; done
python3 -c "import venv, ensurepip" > /dev/null 2>&1 || need=1
if [ -n "$need" ]; then
  apt-get update -qq > /dev/null
  apt-get install -y -qq --no-install-recommends git curl ca-certificates ffmpeg python3 python3-venv python3-pip > /dev/null
fi
mkdir -p {r} {w}/in {w}/frames {w}/out
[ -d {r}/src/.git ] || git clone -q {RVM_REPO} {r}/src
git -C {r}/src checkout -q --detach {RVM_COMMIT}
[ "$(git -C {r}/src rev-parse HEAD)" = {RVM_COMMIT} ] || {{ echo "MATTE_SETUP_FAIL: RVM is not at the pinned commit"; exit 2; }}
if [ ! -f {r}/{RVM_CHECKPOINT} ]; then
  curl -fsSL --retry 3 --max-time 900 -o {r}/{RVM_CHECKPOINT}.part {RVM_CHECKPOINT_URL}
  mv {r}/{RVM_CHECKPOINT}.part {r}/{RVM_CHECKPOINT}
fi
echo "{RVM_CHECKPOINT_SHA256}  {r}/{RVM_CHECKPOINT}" | sha256sum -c --status - || {{ rm -f {r}/{RVM_CHECKPOINT}; echo "MATTE_SETUP_FAIL: checkpoint checksum wrong"; exit 2; }}
[ -x {r}/venv/bin/python ] || python3 -m venv {r}/venv
{r}/venv/bin/pip install -q {' '.join(RVM_PACKAGES)}
{r}/venv/bin/pip install -q --index-url {TORCH_INDEX} {' '.join(TORCH_PACKAGES)}
{r}/venv/bin/python -c "import torch; assert torch.cuda.is_available(), 'no CUDA'; print('torch', torch.__version__, 'cuda', torch.version.cuda, torch.cuda.get_device_name(0))"
cd {r}/src && {r}/venv/bin/python -c "import inference, model; print('rvm: imports ok')"
echo MATTE_SETUP_OK
"""
    matte, clean = {}, {}
    for j in jobs:
        sid = _safe_id(j["id"])
        ratio = float(j.get("ratio") or 0.25)
        if not 0 < ratio <= 1:
            raise ValueError(f"downsample ratio {ratio} is outside (0, 1]")
        matte[sid] = _bash(f"""
set -euo pipefail
IN={w}/in/{sid}{CLIP_SUFFIX}; F={w}/frames/{sid}; O={w}/out/{sid}
trap 'rm -rf "$F" "$IN"' EXIT
[ -f "$IN" ] || {{ echo "MATTE_FAIL {sid}: clip missing"; exit 1; }}
rm -rf "$F" "$O"; mkdir -p "$F" "$O/pha" "$O/fgr"
if ffmpeg -hide_banner -h full 2> /dev/null | grep -c -- '-fps_mode' > /dev/null; then VS="-fps_mode passthrough"; else VS="-vsync 0"; fi
ffmpeg -nostdin -v error -i "$IN" -map 0:v:0 $VS -start_number 0 "$F/%06d.png"
N=$(find "$F" -name '*.png' | wc -l)
cd {r}/src
{r}/venv/bin/python inference.py --variant {RVM_VARIANT} --checkpoint {r}/{RVM_CHECKPOINT} --device cuda \\
  --input-source "$F" --downsample-ratio {ratio:g} --output-type png_sequence \\
  --output-alpha "$O/pha" --output-foreground "$O/fgr" --seq-chunk {SEQ_CHUNK} --disable-progress
A=$(find "$O/pha" -name '*.png' | wc -l); G=$(find "$O/fgr" -name '*.png' | wc -l)
if [ "$N" -lt 1 ] || [ "$A" != "$N" ] || [ "$G" != "$N" ]; then echo "MATTE_FAIL {sid}: frames $N, alpha $A, foreground $G"; exit 1; fi
echo "MATTE_OK {sid} $N"
""")
        clean[sid] = _bash(f"rm -rf {w}/out/{sid} {w}/in/{sid}{CLIP_SUFFIX} {w}/frames/{sid}")
    return {"setup": _bash(setup), "matte": matte, "clean": clean, "wipe": _bash(f"rm -rf {w}")}


def _blocking(e: Exception) -> bool:
    """A refusal (cap, rights, privacy, waiting for a yes: exit 3) or a missing key (exit 4) stops the whole run."""
    return getattr(e, "exit_code", None) in (3, 4)


def _numbered(d: Path) -> list[Path]:
    out = []
    for p in Path(d).glob("*.png") if Path(d).is_dir() else []:
        if p.stem.isdigit():
            out.append(p)
    return sorted(out, key=lambda p: int(p.stem))


def prepare(shot: Shot, runner: media.Runner = media.run) -> dict:
    """Make sure the shot's clip exists (cut it when missing) and describe it for the spend card and the run."""
    meta = read_meta(shot.clip)
    span = (round(shot.start_s, 3), round(shot.end_s, 3))
    stale = bool(shot.source and shot.end_s > 0 and (meta.get("start_s"), meta.get("end_s")) != span)
    if not shot.clip.is_file() or stale:
        if not shot.source:
            raise MatteError(f"shot {shot.id}: no clip in render/matte/ and no source to cut it from")
        export_shot(shot.source, shot.start_s, shot.end_s, shot.clip, runner, fps=shot.fps)
    from ..compute import privacy
    info = probe(shot.clip, runner)
    if info["types"] != ["video"]:
        raise MatteError(f"shot {shot.id}: {shot.clip.name} is not picture-only; cut it again with export")
    meta = read_meta(shot.clip)
    return {"shot": shot.id, "file": str(shot.clip), "sha256": privacy.sha256(shot.clip),
            "seconds": float(meta.get("seconds") or 0.0), "width": info["width"], "height": info["height"],
            "fps": float(meta.get("fps") or info["fps"] or 0.0),
            "ratio": downsample_ratio(info["width"], info["height"])}


def matte_rented(shots: list[Shot], compute, cap_usd: float, log: Callable = print, *,
                 runner: media.Runner = media.run, max_minutes: float = 45, check: bool = True,
                 every: int | None = None) -> list[MatteResult]:
    """Matte the shots on one rented RTX 4090 and fetch alpha and foreground PNGs into render/matte/<shot>/.

    One compute session: rent (after a yes on a spend card that says the shots' picture goes up), install RVM, then per
    shot upload the clip, run RVM, fetch, delete it there. Leaving the session deletes the machine. Afterwards each
    fetched shot gets the edge check on this machine and a decision ("behind" or "beside") in decision.json.
    Raises compute.NeedsApproval / compute.Refused (the caller turns them into exit code 3)."""
    if not shots:
        return []
    episodes = {s.episode_dir.resolve() for s in shots}
    if len(episodes) != 1:
        raise ValueError("one rented run per episode")
    if len({s.id for s in shots}) != len(shots):
        raise ValueError("shot ids must be unique")
    infos = {s.id: prepare(s, runner) for s in shots}
    picture = {"files": [{k: infos[s.id][k] for k in ("shot", "file", "sha256", "seconds")} for s in shots]}
    cmds = remote_commands([{"id": s.id, "ratio": infos[s.id]["ratio"]} for s in shots])
    results: dict[str, MatteResult] = {}
    log(f"matte: {len(shots)} shot{'s' if len(shots) != 1 else ''}, "
        f"{sum(i['seconds'] for i in infos.values()):.1f} s of picture, on one rented GPU")
    with compute.session(episode=shots[0].episode, step="edit", cap_usd=cap_usd, picture=picture, blender=False,
                         purpose="graphics behind the speaker: separate the speaker from the background") as s:
        machines = s.rent(gpus=1, max_minutes=max_minutes, gpu="RTX 4090")
        if not machines:
            raise MatteError("no rented GPU for the matte")
        m = machines[0]
        t0 = time.monotonic()
        rc, out = m.run(cmds["setup"], timeout=1800, doing="installing the matting model")
        if not re.search(r"^MATTE_SETUP_OK$", out, re.M):
            raise MatteError(f"matte setup failed (exit {rc}): {media.tail(out, 300)}")
        log(f"matte: model ready in {time.monotonic() - t0:.0f} s")
        for sh in shots:
            t1 = time.monotonic()
            res = MatteResult(sh.id, False, sh.out_dir)
            results[sh.id] = res
            try:
                for sub in ("pha", "fgr"):
                    shutil.rmtree(sh.out_dir / sub, ignore_errors=True)
                m.put([sh.clip], f"{REMOTE_WORK}/in/")
                frames_hint = max(1, round(infos[sh.id]["seconds"] * (infos[sh.id]["fps"] or 30)))
                rc, out = m.run(cmds["matte"][sh.id], timeout=600 + 2 * frames_hint, doing=f"matting shot {sh.id}")
                ok = re.search(rf"^MATTE_OK {re.escape(sh.id)} (\d+)$", out, re.M)
                if not ok:
                    res.error = f"RVM failed (exit {rc}): {media.tail(out, 300)}"
                    continue
                m.get(f"{REMOTE_WORK}/out/{sh.id}/", sh.out_dir)
                m.run(cmds["clean"][sh.id], timeout=120, doing=f"deleting shot {sh.id} there")
                n = int(ok.group(1))
                got = (len(_numbered(res.alpha_dir)), len(_numbered(res.fgr_dir)))
                if got != (n, n):
                    res.error = f"fetched {got[0]} alpha and {got[1]} foreground frames of {n}"
                    continue
                res.ok, res.frames = True, n
            except Exception as e:
                if _blocking(e):
                    raise
                res.error = f"{type(e).__name__}: {e}"
            finally:
                res.seconds = time.monotonic() - t1
                log(f"matte {sh.id}: " + (f"{res.frames} frames in {res.seconds:.0f} s" if res.ok else res.error))
        try:
            m.run(cmds["wipe"], timeout=120, doing="deleting the work folder")
        except Exception as e:
            if _blocking(e):
                raise
    log("matte: rented machine released")
    for sh in shots:
        res = results.get(sh.id) or MatteResult(sh.id, False, sh.out_dir, error="not run")
        results[sh.id] = res
        if check and res.ok:
            try:
                res.check = check_shot(sh, runner, every=every)
                res.decision = res.check["decision"]
            except Exception as e:     # a check that cannot run is a failed check: the graphic goes beside
                res.error = f"edge check failed to run: {e}"
                res.decision = write_decision(sh.out_dir, {"passed": False, "reasons": [res.error]})
        elif not res.ok:
            res.decision = write_decision(sh.out_dir, {"passed": False, "reasons": [f"no matte: {res.error}"]})
    return [results[s.id] for s in shots]


# ---- 3. the edge gate --------------------------------------------------------------------------------------------
# Every limit of the gate, in one place. Pixel sizes are for 1080 lines and grow with taller pictures.
# The numbers are first settings from synthetic pictures and the physics of mixed edge pixels; measure them on real
# footage and adjust here.
THRESHOLDS: dict = {
    "every": 10,                 # check every Nth frame (and the frame after it, for flicker)
    "rim_px": 3,                 # rim: pixels within this distance of the 0.5 alpha contour, both sides
    "ref_px": (4, 10),           # reference: the band this far inside the contour (the person, not the edge)
    "ref_window_px": 15,         # the reference is averaged locally, over a square this wide around each rim pixel
    "halo_delta": 0.20,          # a rim pixel is "bright" when its luminance (0..1) on a test ground is this much above
                                 # both the person just inside and the ground. Dark hair on a white wall with a correct
                                 # matte peaks near 0.16 (mixed pixels); a matte grown over a white wall gives 0.3 to 0.8
    "halo_share": 0.10,          # halo fails when more rim pixels than this are bright, in any checked frame
    "hard_share": 0.60,          # hard edge fails when more contour pixels than this are opaque (>= 0.98) right next to a
                                 # fully clear pixel (<= 0.02): the binary cut-out look
    "hard_share_hair": 0.30,     # the same limit for the hair at the top of the head, where alpha must be partial
    "hair_band": 0.12,           # without a face box: the hair zone is the top 12 % of the picture height under the
                                 # head's top
    "border_inner_px": (4, 8),   # lines this far from a frame border are compared with the border line itself
    "border_reach": 0.5,         # where the body leaves the frame, the border line needs half the coverage of those lines
    "border_min_share": 0.02,    # ... when those lines are covered on at least 2 % of their length
    "straight_share": 0.06,      # frame edge fails on a straight horizontal (vertical) matte edge inside the picture longer
    "straight_min_px": 12,       # than 6 % of the width (height), and at least this long
    "still_change": 0.06,        # picture change (0..1, mean of 3x3) at which a pixel counts as moving (weight 0)
    "flicker_band_px": 3,        # flicker is measured within this distance of the contour (of either frame)
    "flicker": 0.05,             # flicker fails when the mean alpha change where the picture stood still is above this
    "coverage": (0.03, 0.85),    # the person's share of the frame: below is an empty matte, above a full-frame matte
}
DARK_GROUND = (0.04, 0.04, 0.04)
COLOUR_GROUND = (0.05, 0.35, 0.95)     # a saturated blue
MID_GREY = (0.5, 0.5, 0.5)
_LUM = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)


def _box_sum(x: np.ndarray, r: int) -> np.ndarray:
    """Sum over a (2r+1) x (2r+1) square around each pixel; zero outside the frame."""
    x = np.asarray(x, dtype=np.float64)
    if r <= 0:
        return x
    k = 2 * r + 1
    ii = np.zeros((x.shape[0] + k, x.shape[1] + k))
    ii[1:, 1:] = np.pad(x, r).cumsum(0).cumsum(1)
    return ii[k:, k:] - ii[:-k, k:] - ii[k:, :-k] + ii[:-k, :-k]


def _dilate(mask: np.ndarray, r: int) -> np.ndarray:
    return _box_sum(mask, r) > 0.5 if r > 0 else mask.copy()


def _erode(mask: np.ndarray, r: int) -> np.ndarray:
    """Erosion that treats the outside of the frame as inside: a frame border is not an edge of the person."""
    return ~_dilate(~mask, r) if r > 0 else mask.copy()


def _min4(a: np.ndarray) -> np.ndarray:
    p = np.pad(a, 1, mode="edge")
    return np.minimum.reduce([p[:-2, 1:-1], p[2:, 1:-1], p[1:-1, :-2], p[1:-1, 2:]])


def _contour(a: np.ndarray) -> np.ndarray:
    """Pixels on the inside of the 0.5 alpha contour: alpha >= 0.5 with a 4-neighbour below 0.5."""
    inside = a >= 0.5
    return inside & (_min4(inside.astype(np.float32)) < 0.5)


def _longest_runs(b: np.ndarray) -> np.ndarray:
    """Longest run of True per row."""
    out = np.zeros(b.shape[0], dtype=np.int64)
    if not b.size:
        return out
    d = np.diff(np.pad(b.astype(np.int8), ((0, 0), (1, 1))), axis=1)
    rs, cs = np.nonzero(d == 1)
    _, ce = np.nonzero(d == -1)
    if rs.size:
        np.maximum.at(out, rs, ce - cs)
    return out


def _lum(rgb: np.ndarray) -> np.ndarray:
    return rgb @ _LUM


def _over(img: np.ndarray, a: np.ndarray, ground) -> np.ndarray:
    a3 = a[..., None]
    return a3 * img + (1 - a3) * np.asarray(ground, dtype=np.float32)


def load_rgb(p: Path) -> np.ndarray:
    with Image.open(p) as im:
        return np.asarray(im.convert("RGB"), dtype=np.float32) / 255.0


def load_alpha(p: Path) -> np.ndarray:
    """An alpha PNG as 0..1: 8-bit or 16-bit gray (RVM writes 8-bit), or the first channel of a colour image."""
    with Image.open(p) as im:
        if im.mode.startswith("I"):
            arr = np.asarray(im, dtype=np.float64)
            full = 65535.0 if im.mode.startswith("I;16") or arr.max() > 255 else 255.0
            return np.clip(arr / full, 0, 1).astype(np.float32)
        if im.mode in ("LA", "RGBA"):
            return np.asarray(im.getchannel("A"), dtype=np.float32) / 255.0
        if im.mode != "L":
            im = im.convert("RGB").getchannel("R")
        return np.asarray(im, dtype=np.float32) / 255.0


def _scale(h: int) -> float:
    return max(1.0, h / 1080.0)


def _px(v: float, s: float) -> int:
    return max(1, int(round(v * s)))


def _head(inside: np.ndarray, face) -> tuple[int, int]:
    """(x, y) of the top of the head: from the face box when given, else the topmost covered rows."""
    rows = np.nonzero(inside.sum(1) >= 3)[0]
    if not rows.size:
        return inside.shape[1] // 2, 0
    if face:
        fx, fy, fw, fh = face
        cols = slice(max(0, int(fx)), max(1, int(fx + fw)))
        col_rows = np.nonzero(inside[:, cols].any(1))[0]
        y0 = int(col_rows[0]) if col_rows.size else int(rows[0])
        return int(fx + fw / 2), y0
    y0 = int(rows[0])
    xs = np.nonzero(inside[y0:y0 + 4].any(0))[0]
    return int(xs.mean()) if xs.size else inside.shape[1] // 2, y0


def frame_metrics(img: np.ndarray, a: np.ndarray, face=None, th: dict | None = None) -> dict:
    """The per-frame numbers of the gate: halo, hard edge, frame edges, coverage. See THRESHOLDS."""
    th = {**THRESHOLDS, **(th or {})}
    h, w = a.shape
    s = _scale(h)
    inside = a >= 0.5
    contour = _contour(a)
    n_contour = int(contour.sum())
    out: dict = {"coverage": round(float(a.mean()), 4), "contour_px": n_contour}

    # halo: a bright rim of old background, on a dark and on a saturated ground
    rim = _dilate(contour, _px(th["rim_px"], s)) & (a > 0.02)
    r0, r1 = th["ref_px"]
    ref = _erode(inside, _px(r0, s)) & ~_erode(inside, _px(r1, s))
    win = _px(th["ref_window_px"], s) // 2
    ref_n = _box_sum(ref, win)
    valid = rim & (ref_n >= 3)
    for name, ground in (("dark", DARK_GROUND), ("colour", COLOUR_GROUND)):
        lum = _lum(_over(img, a, ground))
        ref_mean = _box_sum(lum * ref, win) / np.maximum(ref_n, 1)
        excess = lum - np.maximum(ref_mean, float(_lum(np.asarray(ground, dtype=np.float32))))
        ex = excess[valid]
        out[f"halo_{name}"] = round(float((ex > th["halo_delta"]).mean()), 4) if ex.size else 0.0
        out[f"halo_{name}_p95"] = round(float(np.percentile(ex, 95)), 4) if ex.size else 0.0
    out["halo"] = max(out["halo_dark"], out["halo_colour"])
    out["rim_px"] = int(valid.sum())

    # hard edge: opaque pixels right next to fully clear ones
    hard = contour & (a >= 0.98) & (_min4(a) <= 0.02)
    out["hard_share"] = round(float(hard.sum() / n_contour), 4) if n_contour else 0.0
    hx, hy = _head(inside, face)
    if face:
        fx, fy, fw, fh = face
        zone_y1 = int(fy + 0.25 * fh)
        zx0, zx1 = int(fx - 0.35 * fw), int(fx + 1.35 * fw)
    else:
        zone_y1 = int(hy + th["hair_band"] * h)
        zx0, zx1 = 0, w
    zone = np.zeros_like(inside)
    zone[:max(0, zone_y1), max(0, zx0):max(0, zx1)] = True
    zc = int((contour & zone).sum())
    out["hair_contour_px"] = zc
    out["hard_share_hair"] = round(float((hard & zone).sum() / zc), 4) if zc >= 10 else None

    # frame edges: reach the border where the body leaves the frame; no straight cut line inside the picture
    out["border_gaps"] = border_gaps(inside, th, s)
    runs_h = _longest_runs(inside[:-1] != inside[1:])
    runs_v = _longest_runs((inside[:, :-1] != inside[:, 1:]).T)
    out["straight_h_px"] = int(runs_h.max()) if runs_h.size else 0
    out["straight_h_row"] = int(runs_h.argmax()) if runs_h.size else None
    out["straight_v_px"] = int(runs_v.max()) if runs_v.size else 0
    out["straight_v_col"] = int(runs_v.argmax()) if runs_v.size else None
    out["person_x"] = round(float((a.sum(0) * np.arange(w)).sum() / max(a.sum(), 1e-6)), 1)
    out["head"] = [hx, hy]
    return out


def border_gaps(inside: np.ndarray, th: dict, s: float = 1.0) -> dict[str, int]:
    """Per frame border: how many px before the border the matte stops where the body runs towards it (0 = fine).

    Two cases count: (1) the lines just inside the border are covered but the border line holds less than
    `border_reach` of that (the matte fades or stops right at the edge); (2) nothing reaches the border, and the nearest
    covered line (within 15 % of the picture) ends abruptly: as wide as the lines further in, as a straight cut does. A
    rounded head top or shoulder that comes close to the border without touching it is narrow there and passes."""
    d0, d1 = (_px(v, s) for v in th["border_inner_px"])
    gaps = {}
    lines = {"bottom": inside[::-1], "top": inside, "left": inside.T, "right": inside.T[::-1]}
    for side, m in lines.items():
        n = m.shape[0]
        if n <= 2 * d1 + 1:
            continue
        cov = m.sum(1)
        min_cov = max(4.0, th["border_min_share"] * m.shape[1])
        inner = float(cov[d0:d1 + 1].max())
        if inner >= min_cov and cov[0] < th["border_reach"] * inner:
            reach = np.nonzero(cov >= th["border_reach"] * inner)[0]
            gaps[side] = int(reach[0]) if reach.size else n
            continue
        if cov[0] >= min_cov:
            continue
        near = np.nonzero(cov[:max(d1 + 1, int(0.15 * n)) + 1] >= min_cov)[0]
        if near.size:
            g = int(near[0])
            if g > d1 and cov[g] >= 0.6 * cov[min(n - 1, g + 2 * d1)]:
                gaps[side] = g
    return gaps


def pair_flicker(img0: np.ndarray, a0: np.ndarray, img1: np.ndarray, a1: np.ndarray, th: dict | None = None) -> dict:
    """Alpha change between neighbour frames in the edge band, weighted by how still the picture is there (weight 1
    where the picture did not change, 0 where it changed by `still_change` or more). Also the plain ratio of the mean
    alpha change to the mean picture change, for information."""
    th = {**THRESHOLDS, **(th or {})}
    s = _scale(a0.shape[0])
    band = _dilate(_contour(a0) | _contour(a1), _px(th["flicker_band_px"], s))
    d_img = np.abs(img1 - img0).mean(axis=2)
    d_local = _box_sum(d_img, 1) / _box_sum(np.ones_like(d_img), 1)
    weight = np.clip(1 - d_local / th["still_change"], 0, 1) * band
    d_a = np.abs(a1 - a0)
    wsum = float(weight.sum())
    motion = float(d_img[band].mean()) if band.any() else 0.0
    return {"flicker": round(float((weight * d_a).sum() / wsum), 4) if wsum >= 50 else None,
            "still_px": round(wsum), "motion": round(motion, 4),
            "ratio": round(float(d_a[band].mean()) / max(motion, 0.01), 3) if band.any() else None}


def _crop_boxes(a: np.ndarray, face, side: int) -> dict[str, tuple[int, int]]:
    """Top-left corners of the three 200 % crops: hair top, left shoulder, right shoulder."""
    h, w = a.shape
    inside = a >= 0.5
    hx, hy = _head(inside, face)
    boxes = {"hair": (hx - side // 2, hy - side // 3)}
    if face:
        fy1 = face[1] + face[3]
        ys = int(fy1 + 0.6 * (h - fy1))
    else:
        ys = int(hy + 0.75 * (h - hy))
    for name, pick in (("left", lambda xs: xs[0]), ("right", lambda xs: xs[-1])):
        y, x = ys, None
        while y > hy:
            xs = np.nonzero(inside[min(h - 1, y)])[0]
            if xs.size:
                x = int(pick(xs))
                if side // 2 <= x <= w - 1 - side // 2:
                    break
            y -= max(1, side // 4)
        boxes[name] = ((x if x is not None else (0 if name == "left" else w)) - side // 2, max(hy, y) - side // 2)
    return {k: (int(np.clip(x, 0, max(0, w - side))), int(np.clip(y, 0, max(0, h - side)))) for k, (x, y) in
            boxes.items()}


def write_crops(img: np.ndarray, a: np.ndarray, out_dir: Path, face=None) -> dict:
    """200 % crops (nearest neighbour) of hair top, left and right shoulder over mid grey and a saturated colour, and the
    sheet edges-200.jpg with all six side by side. Returns {"crops": {name: path}, "sheet": path}."""
    out_dir = Path(out_dir)
    crops_dir = out_dir / "crops"
    crops_dir.mkdir(parents=True, exist_ok=True)
    h, w = a.shape
    side = int(min(h, w, max(24, round(0.14 * h))))
    boxes = _crop_boxes(a, face, side)
    grounds = (("grey", MID_GREY), ("colour", COLOUR_GROUND))
    tiles: dict[str, Image.Image] = {}
    paths: dict[str, str] = {}
    for gname, ground in grounds:
        comp = np.clip(_over(img, a, ground) * 255 + 0.5, 0, 255).astype(np.uint8)
        for name, (x, y) in boxes.items():
            tile = Image.fromarray(comp[y:y + side, x:x + side]).resize((2 * side, 2 * side), Image.NEAREST)
            key = f"{name}-{gname}"
            p = crops_dir / f"{key}.png"
            tile.save(p)
            tiles[key] = tile
            paths[key] = str(p)
    gap, label = 8, 16
    t = 2 * side
    sheet = Image.new("RGB", (3 * t + 4 * gap, 2 * (t + label) + 3 * gap), (24, 24, 24))
    draw = ImageDraw.Draw(sheet)
    for r, (gname, _) in enumerate(grounds):
        for c, name in enumerate(("hair", "left", "right")):
            x0, y0 = gap + c * (t + gap), gap + r * (t + label + gap)
            draw.text((x0, y0), f"{name} / {gname} / 200 %", fill=(230, 230, 230))
            sheet.paste(tiles[f"{name}-{gname}"], (x0, y0 + label))
    sheet_path = out_dir / "edges-200.jpg"
    sheet.save(sheet_path, quality=92)
    return {"crops": paths, "sheet": str(sheet_path), "boxes": {k: [x, y, side, side] for k, (x, y) in boxes.items()}}


def edge_check(frames_dir: Path, alpha_dir: Path, out_dir: Path, face: tuple | None = None, *,
               every: int | None = None, thresholds: dict | None = None) -> dict:
    """Check the matte's edges on every Nth frame and write edge-check.json, the 200 % crops and edges-200.jpg.

    frames_dir: the picture of the clip as numbered PNGs (any subset; frame k of the clip is named k, e.g. 000120.png).
    alpha_dir: the matte as numbered PNGs (RVM writes 0000.png, 0001.png, ...). Files are matched by number.
    face: (x, y, w, h) of the face in the picture, or None. Returns the result (also written as JSON): "passed",
    "reasons" (one sentence per failed check), "checks" (the numbers per check), "frames", "pairs", "thresholds"."""
    th = {**THRESHOLDS, **(thresholds or {})}
    every = int(every or th["every"])
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    frames = {int(p.stem): p for p in _numbered(frames_dir)}
    alphas = {int(p.stem): p for p in _numbered(alpha_dir)}
    sample = [i for i in sorted(alphas) if i % every == 0 and i in frames]
    face = tuple(int(v) for v in face) if face else None
    reasons: list[str] = []
    per_frame: list[dict] = []
    pairs: list[dict] = []
    size = None
    worst = (-1.0, None)
    for i in sample:
        img, a = load_rgb(frames[i]), load_alpha(alphas[i])
        if img.shape[:2] != a.shape:
            reasons.append(f"size: the matte is {a.shape[1]}x{a.shape[0]}, the picture {img.shape[1]}x{img.shape[0]}; "
                           "it would not sit exactly on the speaker")
            break
        size = [a.shape[1], a.shape[0]]
        fm = {"frame": i, **frame_metrics(img, a, face, th)}
        per_frame.append(fm)
        if fm["halo"] > worst[0]:
            worst = (fm["halo"], i)
        j = i + 1
        if j in alphas and j in frames:
            img1, a1 = load_rgb(frames[j]), load_alpha(alphas[j])
            if img1.shape[:2] == a1.shape == a.shape:
                pairs.append({"frame": i, **pair_flicker(img, a, img1, a1, th)})
    result: dict = {"passed": False, "reasons": reasons, "every": every, "size": size, "face": list(face) if face
                    else None, "frames_checked": len(per_frame), "thresholds": _jsonable(th), "frames": per_frame,
                    "pairs": pairs, "checks": {}}
    if not per_frame and not reasons:
        reasons.append("no frames to check: the picture and the matte share no frame numbers")
    if per_frame:
        checks = _judge(per_frame, pairs, th, size)
        result["checks"] = checks
        reasons += [c["reason"] for c in checks.values() if not c["passed"]]
        result["person_x"] = round(float(np.median([f["person_x"] for f in per_frame])), 1)
        k = worst[1] if worst[1] is not None else sample[len(sample) // 2]
        try:
            result.update(write_crops(load_rgb(frames[k]), load_alpha(alphas[k]), out_dir, face))
            result["crop_frame"] = k
        except Exception as e:    # the crops are for a person to look at; a failure there does not decide anything
            result["crops_error"] = f"{type(e).__name__}: {e}"
    result["passed"] = not reasons
    (out_dir / "edge-check.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def _jsonable(th: dict) -> dict:
    return {k: list(v) if isinstance(v, tuple) else v for k, v in th.items()}


def _judge(per_frame: list[dict], pairs: list[dict], th: dict, size) -> dict:
    def worst(key):
        vals = [(f[key], f["frame"]) for f in per_frame if f.get(key) is not None]
        return max(vals) if vals else (None, None)

    checks: dict = {}
    v, at = worst("halo")
    checks["halo"] = {"passed": v <= th["halo_share"], "worst": v, "frame": at, "limit": th["halo_share"],
                      "mean": round(float(np.mean([f["halo"] for f in per_frame])), 4),
                      "reason": f"halo: {v:.0%} of the edge pixels show a bright rim of old background in frame {at} "
                                f"(limit {th['halo_share']:.0%})" if v > th["halo_share"] else ""}
    v, at = worst("hard_share")
    vh, ath = worst("hard_share_hair")
    parts = []
    if v > th["hard_share"]:
        parts.append(f"{v:.0%} of the outline is a binary cut-out edge in frame {at} (limit {th['hard_share']:.0%})")
    if vh is not None and vh > th["hard_share_hair"]:
        parts.append(f"the hair has no soft edge: {vh:.0%} of it is binary in frame {ath} "
                     f"(limit {th['hard_share_hair']:.0%})")
    checks["hard_edge"] = {"passed": not parts, "worst": v, "frame": at, "limit": th["hard_share"], "worst_hair": vh,
                           "frame_hair": ath, "limit_hair": th["hard_share_hair"],
                           "reason": "hard edge: " + "; ".join(parts) if parts else ""}
    w, h = size
    lim_h = max(th["straight_min_px"] * _scale(h), th["straight_share"] * w)
    lim_v = max(th["straight_min_px"] * _scale(h), th["straight_share"] * h)
    sh, at_h = worst("straight_h_px")
    sv, at_v = worst("straight_v_px")
    gap_frames = [(f["frame"], side, g) for f in per_frame for side, g in f["border_gaps"].items()]
    parts = []
    if gap_frames:
        fr, side, g = gap_frames[0]
        parts.append(f"the matte stops {g} px before the {side} edge in frame {fr}, where the body leaves the frame")
    if sh > lim_h:
        parts.append(f"a straight horizontal matte edge of {sh} px in frame {at_h} (limit {lim_h:.0f} px)")
    if sv > lim_v:
        parts.append(f"a straight vertical matte edge of {sv} px in frame {at_v} (limit {lim_v:.0f} px)")
    checks["frame_edges"] = {"passed": not parts, "border_gaps": [list(x) for x in gap_frames[:10]],
                             "straight_h_px": sh, "straight_h_frame": at_h, "limit_h_px": round(lim_h),
                             "straight_v_px": sv, "straight_v_frame": at_v, "limit_v_px": round(lim_v),
                             "reason": "frame edges: " + "; ".join(parts) if parts else ""}
    vals = [p["flicker"] for p in pairs if p.get("flicker") is not None]
    mean = round(float(np.mean(vals)), 4) if vals else None
    checks["flicker"] = {"passed": mean is None or mean <= th["flicker"], "mean": mean,
                         "worst": max(vals) if vals else None, "pairs": len(vals), "limit": th["flicker"],
                         "reason": f"temporal flicker: the alpha changes by {mean:.3f} on average where the picture "
                                   f"stands still (limit {th['flicker']})" if mean is not None else ""}
    lo, hi = th["coverage"]
    cov = [f["coverage"] for f in per_frame]
    bad = [f for f in per_frame if not lo <= f["coverage"] <= hi]
    checks["coverage"] = {"passed": not bad, "min": min(cov), "max": max(cov), "limits": [lo, hi],
                          "reason": (f"coverage: the person fills {bad[0]['coverage']:.0%} of frame {bad[0]['frame']} "
                                     f"({'an empty' if bad[0]['coverage'] < lo else 'a full-frame'} matte; "
                                     f"limits {lo:.0%} to {hi:.0%})") if bad else ""}
    return checks


# ---- the check for one fetched shot ------------------------------------------------------------------------------
def extract_cmd(clip: Path, out_dir: Path, every: int) -> list[str]:
    sel = f"select=not(mod(n\\,{every}))+not(mod(n-1\\,{every}))"
    return [media.ffmpeg(), "-hide_banner", "-nostdin", "-y", "-v", "error", "-i", str(clip), "-map", "0:v:0",
            "-vf", sel, "-fps_mode", "passthrough", "-start_number", "0", str(Path(out_dir) / "%06d.png")]


def extract_frames(clip: Path, out_dir: Path, every: int, total: int, runner: media.Runner = media.run) -> list[int]:
    """Decode frames 0, 1, N, N+1, 2N, 2N+1, ... of the clip into out_dir, named by their frame number."""
    out_dir = Path(out_dir)
    shutil.rmtree(out_dir, ignore_errors=True)
    out_dir.mkdir(parents=True)
    want = [k for k in range(total) if k % every in (0, 1)]
    rc, text = runner(extract_cmd(clip, out_dir, every), timeout=1800)
    got = sorted(out_dir.glob("*.png"))
    if rc != 0 or len(got) < len(want):
        raise MatteError(f"could not read the frames of {Path(clip).name}: {media.tail(text, 200)}")
    tmp = out_dir / "n"
    tmp.mkdir()
    for p, k in zip(got, want, strict=False):
        p.rename(tmp / f"{k:06d}.png")
    for p in out_dir.glob("*.png"):
        p.unlink()
    for p in tmp.iterdir():
        p.rename(out_dir / p.name)
    tmp.rmdir()
    return want


def check_shot(shot: Shot, runner: media.Runner = media.run, every: int | None = None,
               keep_frames: bool = False) -> dict:
    """Edge check of a fetched shot: decode every Nth frame of the clip here, check, write the decision."""
    every = int(every or THRESHOLDS["every"])
    total = len(_numbered(shot.out_dir / "pha"))
    if not total:
        raise MatteError(f"shot {shot.id}: no alpha frames in {shot.out_dir / 'pha'}")
    frames_dir = shot.out_dir / "frames"
    extract_frames(shot.clip, frames_dir, every, total, runner)
    try:
        res = edge_check(frames_dir, shot.out_dir / "pha", shot.out_dir / "check", shot.face, every=every)
    finally:
        if not keep_frames:
            shutil.rmtree(frames_dir, ignore_errors=True)
    res["decision"] = write_decision(shot.out_dir, res)
    return res


# ---- 4. the composite --------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Place:
    """Where and how big the speaker picture sits in the output frame, exactly as the cut shows it. The person layer
    gets the same crop, size and position, so it is never shrunk or moved against the speaker picture."""

    width: int
    height: int
    x: int = 0
    y: int = 0
    crop: tuple[int, int, int, int] | None = None     # w, h, x, y of the source picture before scaling
    canvas: tuple[int, int] | None = None             # output frame size; None: the speaker fills the frame

    def chain(self, flags: str = "lanczos") -> str:
        if self.width < 2 or self.height < 2:
            raise ValueError("the speaker picture needs a size")
        parts = []
        if self.crop:
            cw, ch, cx, cy = (int(v) for v in self.crop)
            if abs(self.width / cw - self.height / ch) > 0.01 * max(self.width / cw, self.height / ch):
                raise ValueError("crop and size do not keep the picture's proportions")
            parts.append(f"crop={cw}:{ch}:{cx}:{cy}")
        parts.append(f"scale={int(self.width)}:{int(self.height)}:flags={flags}")
        parts.append("setsar=1")
        return ",".join(parts)


def composite_graph(place: Place, fps: float, *, speaker: str = "0:v", graphic: str = "1:v", fgr: str = "2:v",
                    pha: str = "3:v", out: str = "v", flags: str = "lanczos") -> str:
    """The ffmpeg filter graph for one insert span: speaker picture, then the graphic (RGBA, output frame size, at 0:0),
    then the person (RVM's foreground with RVM's alpha) at the speaker's exact size and position."""
    chain = place.chain(flags)
    alpha_chain = place.chain("bicubic")       # same geometry; a softer kernel does not ring at hard alpha edges
    g = [f"[{speaker}]setpts=PTS-STARTPTS,{chain}[spk]"]
    if place.canvas:
        cw, ch = (int(v) for v in place.canvas)
        g.append(f"color=c=black:s={cw}x{ch}:r={fps:g}[bg]")
        g.append(f"[bg][spk]overlay={int(place.x)}:{int(place.y)}:shortest=1[base]")
        base = "base"
    else:
        if place.x or place.y:
            raise ValueError("a speaker that fills the frame sits at 0:0; give canvas= for another layout")
        base = "spk"
    g.append(f"[{graphic}]setpts=PTS-STARTPTS,format=rgba[gfx]")
    g.append(f"[{base}][gfx]overlay=0:0:format=auto:eof_action=pass[mid]")
    g.append(f"[{fgr}]setpts=PTS-STARTPTS,format=rgb24,{chain}[fg]")
    g.append(f"[{pha}]setpts=PTS-STARTPTS,format=gray,{alpha_chain}[al]")
    g.append("[fg][al]alphamerge[person]")
    g.append(f"[mid][person]overlay={int(place.x)}:{int(place.y)}:format=auto:shortest=1,format=yuv420p[{out}]")
    return ";".join(g)


def composite_args(speaker: Path, graphic: Path, matte_dir: Path, *, start_s: float, end_s: float,
                   clip_start_s: float, fps: float, place: Place, out: Path) -> list[str]:
    """ffmpeg arguments for the picture of one insert span with the graphic behind the speaker (no sound; the cut keeps
    the sound). The matte's frame k belongs to clip_start_s + k / fps (see export_shot)."""
    if not end_s > start_s >= clip_start_s:
        raise ValueError("the span must start inside the matte clip")
    first = int(round((start_s - clip_start_s) * fps))
    dur = f"{end_s - start_s:.3f}"
    g = str(graphic)
    if "%" in g:
        gin = ["-framerate", f"{fps:g}", "-i", g]
    elif Path(g).suffix.lower() in (".png", ".webp"):
        gin = ["-loop", "1", "-framerate", f"{fps:g}", "-i", g]
    else:
        gin = ["-i", g]
    seq = [["-framerate", f"{fps:g}", "-start_number", str(first), "-i", str(Path(matte_dir) / sub / "%04d.png")]
           for sub in ("fgr", "pha")]
    return ([media.ffmpeg(), "-hide_banner", "-nostdin", "-y", "-v", "error",
             "-ss", f"{start_s:.3f}", "-t", dur, "-i", str(speaker), *gin, *seq[0], *seq[1],
             "-filter_complex", composite_graph(place, fps), "-map", "[v]", "-t", dur, "-an", "-r", f"{fps:g}",
             "-c:v", "libx264", "-preset", "medium", "-crf", "14", "-pix_fmt", "yuv420p", str(out)])


# ---- 5. the decision ---------------------------------------------------------------------------------------------
class Decision(str):
    """ "behind" or "beside"; `.reason` says why, `.side` says where the graphic goes when beside ("left"/"right")."""

    reason: str
    side: str | None

    def __new__(cls, place: str, reason: str = "", side: str | None = None):
        if place not in ("behind", "beside"):
            raise ValueError(place)
        obj = super().__new__(cls, place)
        obj.reason = reason
        obj.side = side
        return obj

    def to_dict(self) -> dict:
        return {"place": str(self), "reason": self.reason, "side": self.side}


def free_side(check: dict) -> str:
    """The side of the frame with more room next to the face (or the person): where a graphic goes beside."""
    size = check.get("size") or [0, 0]
    face = check.get("face")
    x = face[0] + face[2] / 2 if face else check.get("person_x")
    if not size[0] or x is None:
        return "right"
    return "left" if float(x) > size[0] / 2 else "right"


def decide(check: dict) -> Decision:
    """"behind" when the edge check passed, else "beside" (on the free side next to the face) with the reason."""
    if check.get("passed"):
        return Decision("behind", "the edge check passed")
    reasons = [r for r in check.get("reasons") or [] if r] or ["the edge check did not pass"]
    return Decision("beside", "; ".join(reasons), free_side(check))


def write_decision(shot_dir: Path, check: dict) -> dict:
    """Record the decision next to the matte: render/matte/<shot>/decision.json. Returns it."""
    d = decide(check).to_dict()
    d["at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    d["checks"] = {k: {kk: vv for kk, vv in v.items() if kk != "reason"} for k, v in (check.get("checks") or {}).items()}
    Path(shot_dir).mkdir(parents=True, exist_ok=True)
    (Path(shot_dir) / "decision.json").write_text(json.dumps(d, indent=2), encoding="utf-8")
    return d
