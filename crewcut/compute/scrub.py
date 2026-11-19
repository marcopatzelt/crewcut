"""Secrets never come back from a rented machine.

Everything fetched lands in a temporary folder first. `scrub_dir` replaces known secret values (the Vast key, Claude
and other API keys from this process's environment) and secret patterns (Claude tokens, `CONTAINER_API_KEY=...`,
`Authorization: Bearer ...`). Media files are only checked for exact secret values, not patterns. If a known secret
value is still there after scrubbing, nothing is handed on.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from .errors import ComputeError

MASK = b"[REMOVED]"
SECRET_ENVS = ("VAST_API_KEY", "ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN", "OPENAI_API_KEY", "CONTAINER_API_KEY",
               "GITHUB_TOKEN", "HF_TOKEN")
PATTERNS = [
    re.compile(rb"sk-ant-[A-Za-z0-9_\-]{12,}"),
    re.compile(rb"sk-(?:proj-)?[A-Za-z0-9_\-]{32,}"),
    re.compile(rb"((?:CONTAINER_API_KEY|VAST_API_KEY|CLAUDE_CODE_OAUTH_TOKEN|ANTHROPIC_API_KEY|OPENAI_API_KEY)"
               rb"\s*[=:]\s*[\"']?)[^\s\"'\\]+"),
    re.compile(rb"(?i)(authorization:\s*bearer\s+)[^\s\"'\\]+"),
]
MEDIA = {".mp4", ".mov", ".webm", ".mkv", ".avi", ".gif", ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".exr", ".tif",
         ".tiff", ".wav", ".mp3", ".aac", ".m4a", ".flac", ".otf", ".ttf", ".woff", ".woff2", ".blend", ".gz", ".zip",
         ".xz", ".npz", ".npy", ".safetensors", ".ckpt", ".pt"}
MAX_BYTES = 400 * 1024 * 1024


class SecretLeft(ComputeError):
    pass


def known_secrets() -> list[bytes]:
    out = []
    for name in SECRET_ENVS:
        v = os.environ.get(name, "").strip()
        if len(v) >= 12:
            out.append(v.encode())
    from .vast import credential
    key = credential()
    if len(key) >= 12 and key.encode() not in out:
        out.append(key.encode())
    return out


def _sub(m: re.Match) -> bytes:
    return (m.group(1) if m.re.groups else b"") + MASK


def scrub_bytes(data: bytes, patterns: bool = True, secrets: list[bytes] | None = None) -> bytes:
    for s in known_secrets() if secrets is None else secrets:
        data = data.replace(s, MASK)
    if patterns:
        for p in PATTERNS:
            data = p.sub(_sub, data)
    return data


def scrub_text(text: str) -> str:
    return scrub_bytes(text.encode("utf-8", "replace")).decode("utf-8", "replace")


def scrub_dir(root: Path) -> list[str]:
    """Scrub every file under root in place. Returns the changed files (relative). Raises SecretLeft if a known
    secret value survives (then the caller must not hand the folder on)."""
    root = Path(root)
    secrets = known_secrets()
    changed = []
    for p in sorted(root.rglob("*")):
        if p.is_symlink():
            p.unlink()  # a link could point anywhere on this machine; fetched results never need one
            continue
        if not p.is_file() or p.stat().st_size > MAX_BYTES:
            continue
        data = p.read_bytes()
        new = scrub_bytes(data, patterns=p.suffix.lower() not in MEDIA, secrets=secrets)
        if new != data:
            p.write_bytes(new)
            changed.append(str(p.relative_to(root)))
    if secrets:
        left = [str(p.relative_to(root)) for p in root.rglob("*")
                if p.is_file() and not p.is_symlink() and p.stat().st_size <= MAX_BYTES
                and any(s in p.read_bytes() for s in secrets)]
        if left:
            raise SecretLeft(f"a secret is still in {len(left)} fetched files; nothing was handed on")
    return changed


def has_secret(data: bytes) -> bool:
    return scrub_bytes(data) != data
