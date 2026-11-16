"""Where things live. Two roots: the app (code, skills, templates) and the studio (the user's folder)."""

from __future__ import annotations

import os
from pathlib import Path

_PKG = Path(__file__).resolve().parent


def app_root() -> Path:
    """The app root: the repository in development, /app in the container."""
    env = os.environ.get("CREWCUT_APP")
    return Path(env).resolve() if env else _PKG.parent


def studio_root() -> Path:
    """The user's studio folder (brand/, episodes/, config/, .crewcut/). Env CREWCUT_STUDIO, default ./studio."""
    env = os.environ.get("CREWCUT_STUDIO")
    return Path(env).resolve() if env else (Path.cwd() / "studio").resolve()


def state_dir() -> Path:
    p = studio_root() / ".crewcut"
    p.mkdir(parents=True, exist_ok=True)
    return p


def logs_dir() -> Path:
    p = state_dir() / "logs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def db_path() -> Path:
    return state_dir() / "crewcut.db"


def episodes_dir() -> Path:
    p = studio_root() / "episodes"
    p.mkdir(parents=True, exist_ok=True)
    return p


def episode_dir(episode: str) -> Path:
    safe = Path(episode).name
    if safe != episode or safe in ("", ".", ".."):
        raise ValueError(f"bad episode id: {episode!r}")
    return episodes_dir() / safe


def user_brand_dir() -> Path:
    return studio_root() / "brand"


def neutral_pack_dir() -> Path:
    return app_root() / "packs" / "neutral"


def brand_dir() -> Path:
    """The active style pack: studio/brand when it has a brand.json, else packs/neutral."""
    b = user_brand_dir()
    return b if (b / "brand.json").is_file() else neutral_pack_dir()


def skills_dir() -> Path:
    return app_root() / "skills"


def team_dir() -> Path:
    return app_root() / "team"


def templates_dir() -> Path:
    return app_root() / "templates"


def tools_dir() -> Path:
    return app_root() / "tools"


def web_dist_dir() -> Path:
    return app_root() / "web" / "dist"


def inside(base: Path, rel: str) -> Path:
    """Resolve rel under base and refuse anything that escapes it."""
    p = (base / rel).resolve()
    if p != base.resolve() and base.resolve() not in p.parents:
        raise ValueError(f"path escapes {base}: {rel}")
    return p
