"""The format library: named thumbnail formats the Designer picks from, built from the user's own references.

A format is a recipe, not a picture: "the person large on one side, two words in heavy type beside the face". The
library lives in the style pack (`thumbnail.formats.library`, default `references/formats/`) as `formats.json`:

    {"schema": 1, "formats": [
      {"id": "house-face-result", "name": "Face points at the result", "kind": "house", "family": "House style",
       "recipe": "...", "fits": "...", "strong": true, "card": "cards/house-face-result.md",
       "images": ["images/house-face-result.png"]}]}

`kind` is "house" (the channel's own style) or "pro" (a format the user collected from outside channels). `strong`
marks the formats worth trying first for this channel. Cards and example images are the user's own references: they
stay in the user's studio and never go into a public repository. The neutral pack ships a small generic library
written in Crewcut's own words, without images; a user library adds to it and replaces formats with the same id.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .. import paths

KINDS = ("house", "pro")
DEFAULT_DIR = "references/formats"


def library_dirs(pack=None) -> list[Path]:
    """The neutral library first, then the active pack's (the later one wins)."""
    if pack is None:
        from .. import brand
        pack = brand.load()
    rel = pack.value("thumbnail.formats.library", DEFAULT_DIR) or DEFAULT_DIR
    dirs = []
    if pack.value("thumbnail.formats.include_default", True) is not False:
        dirs.append(paths.neutral_pack_dir() / DEFAULT_DIR)
    if not pack.is_neutral:
        dirs.append(paths.inside(Path(pack.dir), rel))
    return [d for d in dict.fromkeys(dirs)]


def problems_of(f: Any) -> list[str]:
    if not isinstance(f, dict):
        return ["a format must be an object"]
    out = []
    for key in ("id", "name", "kind", "recipe"):
        if not str(f.get(key) or "").strip():
            out.append(f"format {f.get('id')!r} needs {key}")
    if f.get("kind") and f["kind"] not in KINDS:
        out.append(f"format {f.get('id')!r}: kind must be house or pro")
    return out


def load(pack=None) -> dict[str, dict]:
    """All formats by id. Each entry gets `dir` (its library folder) so cards and images can be found."""
    out: dict[str, dict] = {}
    for d in library_dirs(pack):
        p = d / "formats.json"
        if not p.is_file():
            continue
        data = json.loads(p.read_text(encoding="utf-8"))
        for f in data.get("formats", []):
            if problems_of(f):
                continue
            out[f["id"]] = {**f, "dir": str(d)}
    return out


def check_library(path: Path) -> list[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    out, seen = [], set()
    for f in data.get("formats", []):
        out += problems_of(f)
        fid = f.get("id") if isinstance(f, dict) else None
        if fid in seen:
            out.append(f"format id {fid!r} appears twice")
        seen.add(fid)
        for rel in ([f.get("card")] if isinstance(f, dict) and f.get("card") else []) + list(
                (f.get("images") or []) if isinstance(f, dict) else []):
            if not (path.parent / rel).is_file():
                out.append(f"format {fid!r}: {rel} is missing")
    return out


def line(f: dict) -> str:
    star = "*" if f.get("strong") else " "
    return f"{star} {f['id']:<40} {f['kind']:<5} {f['name']}"


def cli(a) -> int:
    from . import variety
    lib = load()
    if a.formats_cmd == "show":
        if not a.id:
            print("Which format? crewcut thumbnail formats show <id>")
            return 2
        f = lib.get(a.id)
        if not f:
            print(f"No format {a.id!r}. List them with: crewcut thumbnail formats")
            return 1
        card = Path(f["dir"]) / f["card"] if f.get("card") else None
        print(card.read_text(encoding="utf-8") if card and card.is_file() else json.dumps(
            {k: v for k, v in f.items() if k != "dir"}, indent=1, ensure_ascii=False))
        for rel in f.get("images") or []:
            print(f"example: {Path(f['dir']) / rel}")
        return 0
    rows = [f for f in lib.values() if (not a.kind or f["kind"] == a.kind) and (not a.strong or f.get("strong"))]
    if a.json:
        print(json.dumps([{k: v for k, v in f.items() if k != "dir"} for f in rows], indent=1, ensure_ascii=False))
        return 0
    if not rows:
        print("The format library is empty. Put formats.json into the pack's references/formats/.")
        return 1
    cfg = variety.settings()
    print(f"{len(rows)} formats (* = strong for this channel). A test set needs {cfg['per_set']} variants in "
          f"{cfg['per_set']} formats: at least {cfg['min_house']} house and {cfg['min_pro']} pro.")
    for f in sorted(rows, key=lambda f: (f["kind"] != "house", not f.get("strong"), f["id"])):
        print(line(f))
    return 0
