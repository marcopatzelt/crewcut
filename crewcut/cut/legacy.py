"""Register verified imported recordings without copying, transcribing or approving them."""

from __future__ import annotations

from pathlib import Path

from .. import paths
from ..studio_import import permitted
from . import ingest, media
from .common import CutError, episode_dir, now_iso, read_json, write_new_json

MEDIA_SUFFIXES = {".mp4", ".mov", ".mkv", ".m4v", ".webm", ".avi", ".mts", ".m2ts", ".wav", ".mp3",
                  ".m4a", ".flac", ".aac", ".ogg", ".opus", ".wma", ".aiff", ".aif"}


def register(episode: str) -> dict:
    root = episode_dir(episode)
    destination = root / "brief" / "ingest-legacy.json"
    if destination.exists():
        raise CutError("Imported recordings already have a registration report. Review it before importing again.")
    manifest = read_json(root / "legacy-import.json")
    entries = []
    skipped = []
    for record in manifest.get("files", []):
        relative = Path(record["path"])
        if not relative.parts or relative.parts[0] not in ("01-originals", "originals"):
            continue
        if not permitted(relative) or relative.is_absolute() or ".." in relative.parts:
            raise CutError("An imported recording has an unsafe path.")
        if relative.suffix.lower() not in MEDIA_SUFFIXES:
            skipped.append(relative.as_posix())
            continue
        candidate = root
        for part in ("legacy", *relative.parts):
            candidate = candidate / part
            if candidate.is_symlink():
                raise CutError("Imported recording paths must not be links.")
        source = paths.inside(root / "legacy", relative.as_posix())
        if not source.is_file():
            raise CutError(f"Missing imported recording: {relative}")
        before = source.stat()
        if before.st_size != record["bytes"] or ingest.sha256_file(source) != record["sha256"]:
            raise CutError(f"Imported recording changed: {relative}. Nothing was registered.")
        info = media.probe(source)
        kind = ingest._media_kind(info)
        if kind is None:
            continue
        after = source.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise CutError("An imported recording changed during registration.")
        video = media.video_stream(info)
        created = media.created_at(info)
        entries.append({"source": f"legacy/{relative.as_posix()}", "name": source.name,
                        "file": f"legacy/{relative.as_posix()}", "status": "registered import", "kind": kind,
                        "sha256": record["sha256"], "bytes": before.st_size, "duration": media.duration(info),
                        "created": created.isoformat() if created else None, "hdr": bool(video and media.is_hdr(video)),
                        "summary": media.summary(info), "probe": info, "mic_check": None, "sound_to_end": None})
    if not entries:
        raise CutError("No imported recordings found. Nothing was registered.")
    groups = ingest.split_groups(entries)
    report = {"episode": episode, "at": now_iso(), "files": entries, "skipped_non_media": skipped,
              "recordings": [{"files": [entries[index]["file"] for index in group["index"]],
                              "reason": group["reason"]} for group in groups],
              "warnings": ["Imported recordings have not passed microphone or full-track audio checks.",
                           "Historical take selections and edit plans are not current approvals."],
              "notes": ["Registered existing verified copies. No transcription, copy, job or upload was started."],
              "report": "brief/ingest-legacy.json"}
    write_new_json(destination, report)
    return report
