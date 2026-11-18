"""Persistent user projects, separate from Crewcut's application files."""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

from . import paths


def root() -> Path:
    location = paths.studio_root() / "workspaces"
    if location.is_symlink():
        raise ValueError("The workspaces folder must not be a symbolic link.")
    return paths.inside(paths.studio_root(), "workspaces")


def create(name: str, episode: str | None = None) -> dict:
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,79}", name):
        raise ValueError("Use a project name with lowercase letters, numbers, dashes or underscores.")
    if episode:
        paths.episode_dir(episode)
    location = root() / name
    if location.is_symlink():
        raise ValueError("A workspace must not be a symbolic link.")
    location.mkdir(parents=True, exist_ok=True)
    for folder in ("code", "research", "results", "logs"):
        child = location / folder
        if child.is_symlink():
            raise ValueError(f"The {folder} folder must not be a symbolic link.")
        child.mkdir(exist_ok=True)
    manifest = location / "workspace.json"
    if manifest.is_symlink():
        raise ValueError("The workspace record must not be a symbolic link.")
    if not manifest.exists():
        with manifest.open("x", encoding="utf-8") as handle:
            json.dump({"name": name, "episode": episode}, handle, indent=2)
            handle.write("\n")
    return {"name": name, "path": str(location), "folders": ["code", "research", "results", "logs"]}


def list_workspaces() -> list[dict]:
    location = root()
    if not location.exists():
        return []
    return [{"name": child.name, "path": str(child)} for child in sorted(location.iterdir())
            if child.is_dir() and not child.is_symlink()]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="crewcut workspace", description="User research and coding projects.")
    commands = parser.add_subparsers(dest="command", required=True)
    make = commands.add_parser("create", help="create or reuse a persistent project without replacing files")
    make.add_argument("name")
    make.add_argument("--episode", default=os.environ.get("CREWCUT_EPISODE") or None)
    commands.add_parser("list", help="list user projects")
    commands.add_parser("path", help="show the persistent project root")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = create(args.name, args.episode) if args.command == "create" else (
            list_workspaces() if args.command == "list" else {"path": str(root())})
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError) as error:
        print(str(error))
        return 1
