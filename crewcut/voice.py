"""The user's own spoken words, the voice sample of the Humanizer pass (`brand/voice/`).

Onboarding takes one to three of the user's own videos where they speak to the camera:

    crewcut brand voice add https://www.youtube.com/watch?v=…    # the video's captions, through yt-dlp
    crewcut brand voice add /import/talk.mp4                     # a recording, transcribed on this machine

Each sample is one Markdown file with its source and the plain spoken text, no time stamps. At most three are kept
(the oldest goes). The Writer reads them before the Humanizer pass; Humanizer's "Embedded" mode keeps the user's own
words and rhythm.

The answers of an episode's interview (crewcut/interview.py) are the user's own words too: they are kept in
`brand/voice/interviews/<episode>.md`, the newest three, next to the video samples.
"""

from __future__ import annotations

import datetime as dt
import html
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from . import paths

KEEP = 3
KEEP_INTERVIEWS = 3


class VoiceError(Exception):
    pass


def folder() -> Path:
    return paths.user_brand_dir() / "voice"


def slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return (s or "sample")[:48]


def vtt_text(vtt: str) -> str:
    """Plain spoken text from WebVTT captions: no cues, no time stamps, no tags, no rolled-up repeats."""
    lines: list[str] = []
    for raw in vtt.splitlines():
        line = raw.strip()
        if not line or line == "WEBVTT" or "-->" in line or re.fullmatch(r"\d+", line):
            continue
        if re.match(r"^(Kind|Language|NOTE|STYLE)\b", line):
            continue
        line = html.unescape(re.sub(r"<[^>]+>", "", line)).strip()
        if line and (not lines or line != lines[-1]):
            lines.append(line)
    text = " ".join(lines)
    return re.sub(r"\s+", " ", text).strip()


def write_sample(title: str, source: str, method: str, text: str) -> Path:
    if len(text.split()) < 40:
        raise VoiceError("too few spoken words for a voice sample (need at least about 40)")
    d = folder()
    d.mkdir(parents=True, exist_ok=True)
    out = d / f"{dt.date.today().isoformat()}-{slug(title)}.md"
    out.write_text(f"# {title}\n\n- source: {source}\n- method: {method}\n- added: {dt.date.today().isoformat()}\n\n"
                   f"{text}\n", encoding="utf-8")
    samples = sorted(d.glob("*.md"), key=lambda p: p.stat().st_mtime)
    for old in samples[:-KEEP]:
        old.unlink()
    return out


def from_url(url: str) -> Path:
    """Captions of one of the user's own videos (manual first, else automatic), through yt-dlp."""
    exe = shutil.which("yt-dlp")
    if not exe:
        raise VoiceError("yt-dlp is not installed in this image; drop a recording into the import folder instead")
    with tempfile.TemporaryDirectory() as tmp:
        cmd = [exe, "--skip-download", "--write-subs", "--write-auto-subs", "--sub-format", "vtt", "--sub-langs",
               "all,-live_chat", "--print-json", "-o", str(Path(tmp) / "v.%(ext)s"), url]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=180, stdin=subprocess.DEVNULL)
        if r.returncode != 0:
            raise VoiceError("yt-dlp could not read the video: " + (r.stderr or "").strip()[-200:])
        info = {}
        try:
            info = json.loads(r.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            pass
        subs = sorted(Path(tmp).glob("v.*.vtt"))
        lang = str(info.get("language") or "")
        subs.sort(key=lambda p: (not p.name.startswith(f"v.{lang}"), "orig" not in p.name, p.name))
        if not subs:
            raise VoiceError("this video has no captions; transcribe a recording of it instead")
        text = vtt_text(subs[0].read_text(encoding="utf-8", errors="replace"))
    return write_sample(str(info.get("title") or url), url, "captions (yt-dlp)", text)


def transcribe(src: Path) -> str:
    """The plain spoken text of a recording, transcribed on this machine (faster-whisper, the heavy lane)."""
    from .conductor import lanes
    from .cut import transcribe as tr
    if not src.is_file():
        raise VoiceError(f"no such file: {src}")
    with tempfile.TemporaryDirectory() as tmp, lanes.heavy(f"transcribe {src.name}"):
        out = Path(tmp) / "words.json"
        tr.transcribe_local(src, out, tr.Engine())
        words = json.loads(out.read_text(encoding="utf-8"))
    return re.sub(r"\s+", " ", " ".join(str(w.get("w", "")).strip() for w in words)).strip()


def from_file(src: Path) -> Path:
    """A recording of the user, transcribed on this machine (faster-whisper)."""
    text = transcribe(src)
    return write_sample(src.stem, src.name, "transcribed on this machine (faster-whisper)", text)


def interview_folder() -> Path:
    return folder() / "interviews"


def write_interview(episode: str, title: str, text: str) -> Path:
    """The answers of an episode's interview as a voice sample (the newest KEEP_INTERVIEWS stay)."""
    if len(text.split()) < 40:
        raise VoiceError("too few spoken words for a voice sample (need at least about 40)")
    d = interview_folder()
    d.mkdir(parents=True, exist_ok=True)
    out = d / f"{slug(episode)}.md"
    out.write_text(f"# Interview: {title}\n\n- source: episodes/{episode} (interview answers)\n- method: the user's own "
                   f"answers in the episode chat\n- added: {dt.date.today().isoformat()}\n\n{text.strip()}\n",
                   encoding="utf-8")
    for old in sorted(d.glob("*.md"), key=lambda p: p.stat().st_mtime)[:-KEEP_INTERVIEWS]:
        old.unlink()
    return out


def add(source: str) -> Path:
    if re.match(r"^https?://", source):
        return from_url(source)
    return from_file(Path(source))


def samples() -> list[Path]:
    """The video samples, then the interview answers."""
    d, i = folder(), interview_folder()
    return (sorted(d.glob("*.md")) if d.is_dir() else []) + (sorted(i.glob("*.md")) if i.is_dir() else [])


__all__ = ["add", "samples", "transcribe", "vtt_text", "write_interview", "write_sample", "VoiceError"]
