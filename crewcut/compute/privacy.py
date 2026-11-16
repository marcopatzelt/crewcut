"""Only code and fonts go to rented hosts (plus small scene assets such as images and plan JSON).

Vast.ai is a marketplace of other people's machines. So recordings (video, audio), raw folders of an episode, the
studio state, keys and anything holding a secret never go up. There is no switch to allow it.
"""

from __future__ import annotations

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


def check_upload(sources: list[Path]) -> int:
    """Raise Refused naming the first file that must not leave this machine. Returns the number of files checked."""
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
                raise Refused(f"{f.name}: recordings (video and audio) never go to marketplace GPUs; "
                              "only code and fonts do")
            eps = paths.studio_root().resolve() / "episodes"
            if eps in r.parents:
                rel = r.relative_to(eps).parts
                if len(rel) > 1 and rel[1] in RAW_FOLDERS:
                    raise Refused(f"{f.name}: files from an episode's {rel[1]}/ folder never go to a rented machine")
            if f.stat().st_size <= SCAN_LIMIT and has_secret(f.read_bytes()):
                raise Refused(f"{f.name}: holds something that looks like a key or token; remove it first")
    return n
