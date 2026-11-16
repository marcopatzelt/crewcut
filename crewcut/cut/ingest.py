"""Save recordings into an episode and check their sound to the end.

Originals are copied with their sha256 in the name and never overwritten. Files the user dropped into the browser
(studio/inbox/<episode>/) are moved instead, so a 4 GB file does not take the disk twice. Files from any other folder
(a mounted card) are only read: nothing is written or deleted there.

Every ingest writes brief/ingest-<time>.json with what was saved and what the checks found.
"""

from __future__ import annotations

import hashlib
import os
import re
from datetime import datetime
from pathlib import Path

from .. import paths
from . import audio, media
from .common import CutError, episode_dir, now_iso, read_json, rel, stamp, write_new_json

CHUNK = 16 << 20
SPLIT_MIN_BYTES = 3_800_000_000      # cameras split a recording at about 4 GB (FAT32 limit 4 294 967 296 bytes)
SPLIT_MAX_BYTES = 4_300_000_000
SPLIT_GAP_SECONDS = 3.0              # creation_time has 1 s resolution
_GOPRO = re.compile(r"^(G[HXLP])(\d{2})(\d{4})(\.\w+)$", re.IGNORECASE)
_NUMBERED = re.compile(r"^(.*?)(\d+)(\.\w+)$")


def sha256_file(p: Path) -> str:
    with Path(p).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def safe_name(name: str) -> str:
    n = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(name).name).strip("._")
    return n or "recording"


def original_name(sha: str, name: str) -> str:
    return f"{sha[:12]}-{safe_name(name)}"


def inbox_dir(episode: str) -> Path:
    return paths.studio_root() / "inbox" / Path(episode).name


def inbox_files(episode: str) -> list[Path]:
    d = inbox_dir(episode)
    if not d.is_dir():
        return []
    return sorted(p for p in d.iterdir() if p.is_file() and not p.name.startswith(".") and not p.name.endswith(".part"))


def _copy_hashing(src: Path, dest: Path) -> str:
    h = hashlib.sha256()
    with src.open("rb") as s, dest.open("xb") as t:
        while b := s.read(CHUNK):
            h.update(b)
            t.write(b)
    return h.hexdigest()


def _place(part: Path, dest: Path) -> None:
    """Give the verified copy its final name without ever replacing an existing file."""
    try:
        os.link(part, dest)
        part.unlink()
    except FileExistsError:
        raise
    except OSError:                       # a file system without hard links
        if dest.exists():
            raise FileExistsError(dest) from None
        os.replace(part, dest)


def save_original(src: Path, originals: Path, move: bool = False) -> tuple[Path, str, str]:
    """Copy (or, for the inbox, move) src into originals/<sha12>-<name>. Returns (dest, sha256, status)."""
    originals.mkdir(parents=True, exist_ok=True)
    size = src.stat().st_size
    name = safe_name(src.name)
    if move or any(p.is_file() and p.stat().st_size == size for p in originals.glob(f"*-{name}")):
        sha = sha256_file(src)
        dest = originals / original_name(sha, src.name)
        if dest.exists():
            if dest.stat().st_size != size:
                raise CutError(f"{dest.name} exists with another size. Nothing was overwritten.")
            if move:
                src.unlink()
            return dest, sha, "already saved"
        if move:
            try:
                os.link(src, dest)       # same disk: instant, and it fails instead of overwriting
                src.unlink()
                return dest, sha, "moved"
            except FileExistsError:
                raise
            except OSError:
                pass                     # another disk: copy below, then remove the inbox file
    part = originals / f".{name}.part"
    part.unlink(missing_ok=True)
    sha = _copy_hashing(src, part)
    if sha256_file(part) != sha:
        part.unlink(missing_ok=True)
        raise CutError(f"the copy of {src.name} is faulty. Check the card or disk. The source was not touched.")
    dest = originals / original_name(sha, src.name)
    if dest.exists():
        part.unlink()
        status = "already saved"
    else:
        _place(part, dest)
        status = "copied"
    if move:
        src.unlink()
        status = "moved" if status == "copied" else status
    return dest, sha, status


# ---- split recordings ----------------------------------------------------------------------------------------------
def _key(name: str):
    m = _GOPRO.match(name)
    if m:
        return ("gopro", m.group(1).upper(), m.group(3), m.group(4).lower()), int(m.group(2))
    m = _NUMBERED.match(name)
    if m:
        return ("numbered", m.group(1), len(m.group(2)), m.group(3).lower()), int(m.group(2))
    return None, None


def _as_time(v) -> float | None:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, datetime):
        return v.timestamp()
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _same_recording(a: dict, b: dict, kind: str) -> str | None:
    """Why b continues a, or None. a and b have consecutive numbers."""
    if kind == "gopro":
        return "GoPro chapters of one recording"
    size = a.get("bytes") or 0
    if not SPLIT_MIN_BYTES <= size <= SPLIT_MAX_BYTES:
        return None
    ta, tb, da = _as_time(a.get("created")), _as_time(b.get("created")), a.get("duration")
    if ta is not None and tb is not None and da:
        gap = tb - (ta + float(da))
        if abs(gap) <= SPLIT_GAP_SECONDS:
            return f"the camera split one recording at 4 GB (the second file starts {gap:+.1f} s after the first ends)"
        return None
    return "probably one recording: consecutive numbers and the first file stops at 4 GB (times unknown)"


def split_groups(files: list[dict]) -> list[dict]:
    """Group files that are parts of one recording.

    files: [{"name", "bytes", "created" (ISO time or datetime or None), "duration" (s or None)}].
    Returns [{"files": [names in order], "index": [input positions], "reason": str or None}], one group per
    recording, in input order.
    Two files with consecutive numbers are usually ONE recording when the first one stopped at about 4 GB and the
    second starts where the first ends. Then there is no "better take" to choose between them.
    """
    keyed = []
    for i, f in enumerate(files):
        k, n = _key(f["name"])
        if k is not None:
            keyed.append((k, n, i))
    keyed.sort()
    parent = list(range(len(files)))
    reasons: dict[int, str] = {}

    def root(i: int) -> int:
        while parent[i] != i:
            i = parent[i]
        return i

    for (ka, na, ia), (kb, nb, ib) in zip(keyed, keyed[1:], strict=False):
        if ka == kb and nb == na + 1:
            why = _same_recording(files[ia], files[ib], ka[0])
            if why:
                parent[root(ib)] = root(ia)
                reasons[root(ia)] = why
    groups: dict[int, list[int]] = {}
    for i in range(len(files)):
        groups.setdefault(root(i), []).append(i)
    out = []
    for r, members in sorted(groups.items(), key=lambda kv: min(kv[1])):
        members.sort(key=lambda i: next((n for _, n, j in keyed if j == i), 0))
        out.append({"files": [files[i]["name"] for i in members], "index": members,
                    "reason": reasons.get(r) if len(members) > 1 else None})
    return out


# ---- ingest --------------------------------------------------------------------------------------------------------
def _media_kind(info: dict) -> str | None:
    if media.video_stream(info):
        return "video"
    if media.audio_streams(info):
        return "audio"
    return None


def _source_label(src: Path) -> str:
    try:
        return src.resolve().relative_to(paths.studio_root().resolve()).as_posix()
    except ValueError:
        return str(src)


def check_sound(path: Path, info: dict) -> tuple[dict | None, dict | None]:
    """Microphone check and sound-to-the-end check of one saved file."""
    streams = media.audio_streams(info)
    if not streams:
        return None, None
    dur = media.duration(info)
    channels = int(streams[0].get("channels") or 1)
    mic = audio.mic_check(path, dur) if channels >= 2 else {
        "levels_db": None, "verdict": "mono", "channel": None, "message": "One sound channel."}
    tail = audio.sound_to_end(path, channels=channels, duration=dur)
    return mic, tail


def previous_entries(ep: Path) -> list[dict]:
    out = []
    for p in sorted((ep / "brief").glob("ingest-*.json")):
        try:
            data = read_json(p)
        except CutError:
            continue
        out += [f for f in data.get("files", []) if isinstance(f, dict) and f.get("file")]
    return out


def ingest(episode: str, files: list[Path]) -> dict:
    ep = episode_dir(episode)
    inbox = inbox_dir(episode).resolve()
    entries, warnings, notes = [], [], []
    for src in files:
        src = Path(src)
        if not src.is_file():
            raise CutError(f"not a file: {src}")
        info = media.probe(src)
        kind = _media_kind(info)
        if kind is None:
            raise CutError(f"{src.name} has no picture and no sound. Nothing was saved.")
        move = inbox in src.resolve().parents
        dest, sha, status = save_original(src, ep / "originals", move=move)
        mic, tail = check_sound(dest, info)
        v = media.video_stream(info)
        entry = {
            "source": _source_label(src), "name": src.name, "file": rel(ep, dest), "status": status, "kind": kind,
            "sha256": sha, "bytes": dest.stat().st_size, "duration": media.duration(info),
            "created": (lambda t: t.isoformat() if t else None)(media.created_at(info)),
            "hdr": bool(v and media.is_hdr(v)), "summary": media.summary(info), "mic_check": mic, "sound_to_end": tail,
            "probe": info,
        }
        entries.append(entry)
        if not media.audio_streams(info):
            warnings.append(f"{src.name}: WARNING: no sound track.")
        for check in (mic, tail):
            if check and check.get("message", "").startswith("WARNING"):
                warnings.append(f"{src.name}: {check['message']}")
        if entry["hdr"]:
            notes.append(f"{src.name}: HDR recording. Choose the colour conversion before the cut; nothing is "
                         "converted on its own.")
    known = {e["file"]: e for e in previous_entries(ep)}
    for e in entries:
        known[e["file"]] = e
    every = list(known.values())
    groups = split_groups([{"name": e["name"], "bytes": e.get("bytes"), "created": e.get("created"),
                            "duration": e.get("duration")} for e in every])
    recordings = [{"files": [every[i]["file"] for i in g["index"]], "reason": g["reason"]} for g in groups]
    for g in recordings:
        if len(g["files"]) > 1:
            notes.append(f"{' + '.join(Path(f).name for f in g['files'])} are one recording: {g['reason']}. There is "
                         "no better take to choose between them.")
    report = {"episode": episode, "at": now_iso(), "files": entries, "recordings": recordings,
              "warnings": warnings, "notes": notes}
    name = f"ingest-{stamp()}.json"
    target = ep / "brief" / name
    n = 2
    while target.exists():
        target = ep / "brief" / f"ingest-{stamp()}-{n}.json"
        n += 1
    write_new_json(target, report)
    report["report"] = rel(ep, target)
    return report


def describe(report: dict) -> str:
    lines = []
    for e in report["files"]:
        dur = f"{e['duration']:.0f} s" if e.get("duration") else "length unknown"
        lines.append(f"{e['status']}: {e['file']} ({e['kind']}, {dur})")
        for key in ("mic_check", "sound_to_end"):
            c = e.get(key)
            if c and not c.get("message", "").startswith("WARNING"):
                lines.append(f"  {c['message']}")
    lines += report["notes"]
    lines += report["warnings"]
    lines.append(f"report: {report['report']}")
    return "\n".join(lines)
