"""CC0 3D assets (Poly Haven, ambientCG) for Blender plates and 3D scenes: the Crewcut side of
``blender_lib/crewcut_assets.py`` (which runs inside Blender too).

- ``crewcut render assets fetch SPEC [--res 2k]`` fills the cache here (the studio's ``.crewcut/cache/assets3d`` by
  default, so the files stay with the studio and the container keeps them across restarts);
- a plate script imports ``crewcut_assets`` (the plate bootstrap puts ``blender_lib`` on ``sys.path`` and the cache
  folder in ``CREWCUT_ASSET_CACHE``); on a rented machine the same module fetches into ``/work/assets`` there, so the
  files come from the source's servers, not up through the user's connection;
- ``crewcut render assets list`` shows the cache.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from types import ModuleType

from .. import paths

LIB_DIR = Path(__file__).resolve().parent / "blender_lib"
SOURCES = {
    "polyhaven": {"what": "HDRIs and texture sets", "licence": "CC0 1.0", "page": "https://polyhaven.com/license",
                  "specs": ["polyhaven:hdri/<id>", "polyhaven:tex/<id>"]},
    "ambientcg": {"what": "PBR materials", "licence": "CC0 1.0", "page": "https://docs.ambientcg.com/license/",
                  "specs": ["ambientcg:<id>"]},
}


def lib() -> ModuleType:
    """The shared module ``crewcut_assets`` (loaded from blender_lib/, one copy for Crewcut and Blender)."""
    name = "crewcut_assets"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, LIB_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def cache_dir() -> Path:
    """Here: env CREWCUT_ASSET_CACHE, else the studio's .crewcut/cache/assets3d."""
    env = os.environ.get("CREWCUT_ASSET_CACHE")
    return Path(env) if env else paths.state_dir() / "cache" / "assets3d"


def _with_cache():
    m = lib()
    os.environ.setdefault("CREWCUT_ASSET_CACHE", str(cache_dir()))
    return m


def fetch(spec: str, res: str = "2k", fmt: str | None = None) -> dict:
    return _with_cache().fetch(spec, res, fmt)


def cached() -> list[dict]:
    return _with_cache().cached()


def plate_env() -> dict[str, str]:
    """For a local Blender plate: the module folder on PYTHONPATH and the studio cache."""
    have = os.environ.get("PYTHONPATH", "")
    return {"PYTHONPATH": os.pathsep.join(x for x in (str(LIB_DIR), have) if x),
            "CREWCUT_ASSET_CACHE": str(cache_dir())}
