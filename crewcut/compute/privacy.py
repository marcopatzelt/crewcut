"""Only code and fonts go to rented hosts (plus small scene assets such as images and plan JSON).

Vast.ai is a marketplace of other people's machines. So recordings (video, audio), raw folders of an episode, the
studio state, keys and anything holding a secret never go up. There is no switch to allow it.

One narrow exception, for "graphics behind the speaker" only (crewcut/motion/matte.py, docs/motion-matte.md): the
picture of one shot may go to the rented machine that separates the speaker from the background. All of these must
hold, or the file is refused like any other recording:

- the file lies directly in an episode's `render/matte/` folder, where Crewcut itself cut it for one shot;
- it holds exactly one video stream and nothing else: no sound, no subtitles, no data (checked with ffprobe);
- its sha256 is named on an accepted spend card of the running compute session, and that card says in plain words that
  the shot's picture goes to the rented machine and is deleted with it (`Session(picture=...)` makes that card).

Raw originals, sound, transcripts and every other file keep the rules above, also inside such a session.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from collections.abc import Callable, Collection
from pathlib import Path

from .. import paths
from .errors import Refused
from .scrub import has_secret

RAW_MEDIA = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v", ".mxf", ".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg",
             ".opus", ".aiff", ".braw", ".r3d"}
RAW_FOLDERS = {"originals", "audio", "inbox", "broll", "export", "work"}   # work/ holds transcripts
SECRET_NAMES = {".env", "id_rsa", "id_ed25519", "id_ecdsa", "credentials.json", "token.json", "client_secret.json"}
SECRET_SUFFIXES = {".pem", ".key", ".p12", ".pfx"}
SCAN_LIMIT = 5 * 1024 * 1024
MATTE_FOLDER = ("render", "matte")          # <studio>/episodes/<episode>/render/matte/<shot>.mp4
MATTE_SUFFIXES = {".mp4", ".mkv", ".mov"}   # matte.export_shot (mp4) and the speaker backdrop of a rented comp (mov)

# ffprobe goes through this name so tests can fake it: (argv) -> (exit code, output)
ProbeRunner = Callable[[list[str]], tuple[int, str]]


def _run_probe(argv: list[str]) -> tuple[int, str]:
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as e:
        return 127, str(e)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


_probe: ProbeRunner = _run_probe


def use_probe(runner: ProbeRunner | None) -> None:
    """Tests: replace ffprobe. None restores the real one."""
    global _probe
    _probe = runner or _run_probe


def stream_types(path: Path) -> list[str]:
    """The codec types of every stream in a media file ("video", "audio", "subtitle", "data", ...), in file order.

    Raises Refused when ffprobe cannot read the file: what cannot be checked does not go up."""
    exe = os.environ.get("CREWCUT_FFPROBE") or shutil.which("ffprobe") or "ffprobe"
    rc, out = _probe([exe, "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(path)])
    if rc != 0:
        raise Refused(f"{path.name}: ffprobe cannot read it, so it cannot be checked and does not go up")
    return [x.strip().strip(",") for x in out.splitlines() if x.strip()]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def matte_clip_reason(f: Path, allowed: Collection[str]) -> str | None:
    """None when `f` is a picture-only shot clip the session's card allows; else why not (one sentence)."""
    r = f.resolve()
    eps = paths.studio_root().resolve() / "episodes"
    if eps not in r.parents:
        return "it is not in an episode folder"
    rel = r.relative_to(eps).parts
    if len(rel) != 4 or tuple(rel[1:3]) != MATTE_FOLDER:
        return "only clips directly in an episode's render/matte/ folder may go up for matting"
    if f.suffix.lower() not in MATTE_SUFFIXES:
        return f"a matte clip is {' or '.join(sorted(MATTE_SUFFIXES))}"
    kinds = stream_types(f)
    if kinds != ["video"]:
        extra = sorted({k for k in kinds if k != "video"})
        what = ", ".join(extra) if extra else f"{kinds.count('video')} video streams"
        return f"it must hold one picture stream and nothing else (found: {what})"
    if sha256(f) not in set(allowed):
        return "the spend card you accepted does not name this exact file"
    return None


def check_upload(sources: list[Path], picture_ok: Collection[str] = ()) -> int:
    """Raise Refused naming the first file that must not leave this machine. Returns the number of files checked.

    `picture_ok`: sha256 digests of shot clips that an accepted spend card of the running session names (see the module
    text). Empty outside such a session, and then every recording is refused."""
    state_dir = (paths.studio_root() / ".crewcut").resolve()
    n = 0
    for src in sources:
        for f in _files(Path(src)):
            n += 1
            r = f.resolve()
            name = f.name.lower()
            if state_dir == r or state_dir in r.parents:
                raise Refused(f"{f.name}: the studio state (.crewcut) never goes to a rented machine")
            if name in SECRET_NAMES or name.startswith(".env") or f.suffix.lower() in SECRET_SUFFIXES or \
                    "secrets" in {part.lower() for part in r.parts}:
                raise Refused(f"{f.name}: looks like a key or secret; it never goes to a rented machine")
            if f.suffix.lower() in RAW_MEDIA:
                if not picture_ok:
                    raise Refused(f"{f.name}: recordings (video and audio) never go to marketplace GPUs; "
                                  "only code and fonts do")
                why = matte_clip_reason(f, picture_ok)
                if why:
                    raise Refused(f"{f.name}: refused, {why}. Recordings go to marketplace GPUs only as the "
                                  "picture of one shot, cut by Crewcut into render/matte/, with your yes on the card")
                continue        # the one allowed picture: its bytes are video, a text scan says nothing about it
            eps = paths.studio_root().resolve() / "episodes"
            if eps in r.parents:
                rel = r.relative_to(eps).parts
                if len(rel) > 1 and rel[1] in RAW_FOLDERS:
                    raise Refused(f"{f.name}: files from an episode's {rel[1]}/ folder never go to a rented machine")
            if f.stat().st_size <= SCAN_LIMIT and has_secret(f.read_bytes()):
                raise Refused(f"{f.name}: holds something that looks like a key or token; remove it first")
    return n


def _files(p: Path):
    if p.is_symlink():
        raise Refused(f"{p.name}: links are not uploaded; copy the file instead")
    if p.is_dir():
        for f in sorted(p.rglob("*")):
            if f.is_symlink():
                raise Refused(f"{f.name}: links are not uploaded; copy the file instead")
            if f.is_file():
                yield f
    elif p.is_file():
        yield p
    else:
        raise Refused(f"{p}: not found")
