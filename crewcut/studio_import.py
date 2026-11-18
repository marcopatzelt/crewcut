"""Copy a legacy video studio into private Crewcut data without starting jobs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import shutil
from datetime import UTC, datetime
from pathlib import Path

from .episodes import FOLDERS, SHORT_STEPS, STEPS

EXCLUDED = {
    "node_modules", "__pycache__", "secrets", "credentials", "02-working", "archive",
    "frames", "frames_raw", "cache", "zwischen", "render", "06-resolve", "09-craft",
}
EXTENSIONS = {
    ".md", ".txt", ".json", ".csv", ".toml", ".yaml", ".yml", ".pdf",
    ".mp4", ".mov", ".mkv", ".webm", ".wav", ".mp3", ".m4a", ".flac",
    ".png", ".jpg", ".jpeg", ".webp", ".svg", ".srt", ".vtt",
    ".otf", ".ttf", ".woff", ".woff2", ".blend", ".html", ".css", ".js", ".py",
}
ROOT_FILES = {"studio.json", "README.md", "VERBESSERN.md", "HAUSSTIL-MOTION.md"}
LIBRARIES = {"docs", "shorts-kandidaten", "templates", "assets", "hausstil"}


def permitted(path: Path) -> bool:
    lowered = [part.lower() for part in path.parts]
    if any(part.startswith(".") or part in EXCLUDED for part in lowered):
        return False
    if any(word in path.name.lower() for word in (
        "secret", "credential", "token", "cookie", "session", "sitzung", "password", "auth.json", "login",
    )):
        return False
    if path.stem.isdigit() and path.suffix.lower() in {".png", ".jpg", ".webp"}:
        return False
    return path.suffix.lower() in EXTENSIONS


def inventory(source: Path) -> list[Path]:
    result = []
    for current, directories, filenames in os.walk(source, followlinks=False):
        directories[:] = sorted(name for name in directories
                                if not name.startswith(".") and name.lower() not in EXCLUDED
                                and not (Path(current) / name).is_symlink())
        for name in sorted(filenames):
            path = Path(current) / name
            relative = path.relative_to(source)
            if path.is_file() and not path.is_symlink() and permitted(relative):
                result.append(relative)
    return result


def save_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def copy_checked(source: Path, destination: Path) -> dict:
    before = source.stat()
    destination.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    with source.open("rb") as incoming, destination.open("xb") as outgoing:
        while chunk := incoming.read(4 * 1024 * 1024):
            outgoing.write(chunk)
            digest.update(chunk)
    after = source.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise RuntimeError(f"Source changed during import: {source}")
    if destination.stat().st_size != before.st_size:
        raise RuntimeError(f"Incomplete copy: {destination}")
    shutil.copystat(source, destination)
    return {"bytes": before.st_size, "sha256": digest.hexdigest()}


def script_path(source: Path) -> Path | None:
    brief = source / "00-brief"
    recordings = sorted(brief.glob("AUFNAHME-*.txt"))
    if recordings:
        return recordings[-1]
    project = read_project(source)
    for name in ("teleprompter", "script"):
        relative = Path(project.get("plans", {}).get(name) or "missing")
        if not relative.is_absolute() and ".." not in relative.parts:
            candidate = source / relative
            if candidate.is_file() and not candidate.is_symlink() and permitted(relative):
                return candidate
    candidates = [path for path in brief.glob("*")
                  if path.name.startswith(("SCRIPT-", "SKRIPT-"))
                  and path.suffix in {".md", ".txt"} and "ZETTEL" not in path.name]
    return sorted(candidates, key=lambda path: path.name)[-1] if candidates else None


def read_project(source: Path) -> dict:
    path = source / "project.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() and not path.is_symlink() else {}


def episode_project(source: Path, old: dict, has_script: bool) -> dict:
    from .import_history import initialize

    short = source.name.startswith("S")
    title = old.get("title")
    readme = source / "LIESMICH.md"
    if not title and readme.is_file() and not readme.is_symlink():
        title = next((line.lstrip("# ").strip() for line in readme.read_text(encoding="utf-8").splitlines()
                      if line.startswith("# ")), None)
    steps = {step["id"]: {"status": "unknown"} for step in STEPS}
    project = {
        "id": source.name, "title": title or source.name,
        "imported_at": datetime.now(UTC).isoformat(), "format": "portrait" if short else "landscape",
        "fps": 25, "kind": "short" if short else "episode", "steps": steps,
        "open_items": old.get("open_items", []), "prompter_token": secrets.token_urlsafe(12),
        "legacy": {"id": source.name, "stage": old.get("stage"), "next_action": old.get("next_action"),
                   "publication": old.get("publication"), "project": "legacy/project.json"},
    }
    if short:
        project.update(mode="original", source_episode=None, step_ids=SHORT_STEPS["original"])
        steps["blog"]["absent"] = True
    return initialize(project, source, old)


def import_episode(source: Path, destination: Path) -> dict:
    target = destination / "episodes" / source.name
    marker = target / "legacy-import.json"
    if target.exists():
        if marker.is_file() and json.loads(marker.read_text())["source"] == str(source):
            return {"episode": source.name, "status": "already imported"}
        raise FileExistsError(f"Will not overwrite existing episode: {target}")
    staging = destination / ".crewcut" / "imports" / source.name
    if staging.exists():
        raise FileExistsError(f"Inspect interrupted import before retrying: {staging}")
    staging.mkdir(parents=True)
    for folder in FOLDERS:
        (staging / folder).mkdir()
    records = []
    for relative in inventory(source):
        record = copy_checked(source / relative, staging / "legacy" / relative)
        records.append({"path": relative.as_posix(), **record})
    script = script_path(source)
    if script and script.relative_to(source) in {Path(record["path"]) for record in records}:
        shutil.copy2(staging / "legacy" / script.relative_to(source), staging / "brief" / "SCRIPT-v001.md")
    else:
        script = None
    old = read_project(source)
    from .import_history import initialize

    project = initialize(episode_project(source, old, bool(script)), staging, old)
    save_json(staging / "project.json", project)
    save_json(staging / "legacy-import.json", {"source": str(source), "files": records,
                                              "imported_at": project["imported_at"]})
    (staging / "brief" / "IMPORT.md").write_text(
        f"# Imported: {source.name}\n\nEarlier material is in `legacy/`, with its original structure.\n"
        "Read `legacy/project.json`, `legacy/00-brief/` and `legacy/LIESMICH.md` when present.\n"
        "The previous status is historical, not a new approval. Scripts are drafts until reviewed.\n"
        "Old edit plans are reference material, not executable Crewcut plans. Their paths need conversion.\n"
        "No jobs, uploads or rented machines were started. Original source files remain unchanged.\n",
        encoding="utf-8")
    (destination / "episodes").mkdir(exist_ok=True)
    staging.rename(target)
    return {"episode": source.name, "status": "imported", "files": len(records),
            "bytes": sum(record["bytes"] for record in records), "script": bool(script)}


def library_files(source: Path) -> list[Path]:
    files = [path.relative_to(source) for path in source.iterdir()
             if path.is_file() and not path.is_symlink()
             and (path.name in ROOT_FILES or path.name.startswith("DREHTAG-"))]
    for name in sorted(LIBRARIES):
        directory = source / name
        if directory.is_dir() and not directory.is_symlink():
            files.extend(Path(name) / relative for relative in inventory(directory))
    return files


def expose_episode(target: Path) -> dict:
    from .import_history import safe_file

    legacy = target / "legacy"
    old = read_project(legacy)
    marker = target / "legacy-visible.json"
    if marker.exists():
        return json.loads(marker.read_text())
    copied = []
    delivery = old.get("delivery") or {}
    for key, folder in (("preview", "export"), ("final", "export"), ("cover", "graphics/thumbnail")):
        value = delivery.get(key)
        if isinstance(value, dict):
            value = value.get("path")
        relative = Path((value or "missing").split(" (", 1)[0])
        if relative.is_absolute() or ".." in relative.parts:
            continue
        source = safe_file(legacy, relative.as_posix())
        if source is None:
            continue
        destination = target / folder / source.name
        if source.is_file() and not source.is_symlink() and not destination.exists():
            copy_checked(source, destination)
            copied.append(str(destination.relative_to(target)))
    if not any((target / "export").iterdir()):
        candidates = [path for folder in ("08-export", "schnitt") for path in (legacy / folder).glob("*.mp4")
                      if path.name.startswith(target.name.split("-")[0] + "-")
                      and any(word in path.name for word in ("preview", "final", "short"))
                      and safe_file(legacy, path.relative_to(legacy).as_posix())]
        if candidates:
            source = max(candidates, key=lambda path: path.stat().st_mtime_ns)
            destination = target / "export" / source.name
            copy_checked(source, destination)
            copied.append(str(destination.relative_to(target)))
    readme = legacy / "LIESMICH.md"
    if safe_file(legacy, "LIESMICH.md"):
        destination = target / "brief" / "LEGACY-README.md"
        if not destination.exists():
            copy_checked(readme, destination)
    script = script_path(legacy)
    native_script = target / "brief" / "SCRIPT-v001.md"
    if script and safe_file(legacy, script.relative_to(legacy).as_posix()) and not native_script.exists():
        copy_checked(script, native_script)
    index = ["# Earlier studio work", "", "Historical material, not new approvals or instructions to execute.", "",
             "Shared channel knowledge: /studio/library/video-studio/ and /studio/library/studio-rules/.", "",
             "## Previous state", "", json.dumps(old, ensure_ascii=False, indent=2), "", "## Files", ""]
    manifest = json.loads((target / "legacy-import.json").read_text())
    index.extend(f"- legacy/{record['path']}" for record in manifest["files"])
    (target / "brief" / "LEGACY-INDEX.md").write_text("\n".join(index) + "\n", encoding="utf-8")
    report = {"episode": target.name, "visible_media": copied, "script": native_script.exists()}
    save_json(marker, report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    source, destination = args.source.resolve(), args.destination.resolve()
    if source == destination or source in destination.parents or destination in source.parents:
        parser.error("Source and destination must be separate folders.")
    if any((parent / ".git").exists() for parent in [destination, *destination.parents]):
        parser.error("Destination must be outside a code repository.")
    episodes = sorted(path for path in (source / "episodes").iterdir()
                      if path.is_dir() and not path.is_symlink() and not path.name.startswith("."))
    library = library_files(source)
    total = sum((source / relative).stat().st_size for relative in library)
    for episode in episodes:
        files = inventory(episode)
        size = sum((episode / relative).stat().st_size for relative in files)
        total += size
        print(json.dumps({"episode": episode.name, "files": len(files), "bytes": size}), flush=True)
    print(json.dumps({"episodes": len(episodes), "library_files": len(library), "total_bytes": total}), flush=True)
    if not args.apply:
        return
    destination.mkdir(parents=True, exist_ok=True)
    os.chmod(destination, 0o700)
    if shutil.disk_usage(destination).free < total + 5 * 1024**3:
        parser.error("Not enough free space for independent copies plus 5 GiB reserve.")
    library_target = destination / "library" / "video-studio"
    if not library_target.exists():
        staging = destination / ".crewcut" / "imports" / "library"
        staging.mkdir(parents=True, exist_ok=False)
        records = [{"path": relative.as_posix(), **copy_checked(source / relative, staging / relative)}
                   for relative in library]
        save_json(staging / "import-manifest.json", {"source": str(source), "files": records})
        library_target.parent.mkdir(exist_ok=True)
        staging.rename(library_target)
    for episode in episodes:
        print(json.dumps(import_episode(episode, destination)), flush=True)
        print(json.dumps(expose_episode(destination / "episodes" / episode.name)), flush=True)


if __name__ == "__main__":
    main()
