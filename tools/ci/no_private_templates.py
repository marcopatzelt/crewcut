#!/usr/bin/env python3
"""Marketplace templates never enter this public repository (docs/motion-libraries.md, "Licences").

Mixkit, Envato, Motion Array and LottieFiles items may be used in videos but not passed on, so they live only in a
studio's private folder (library/templates-private/). This check fails when a tracked file (or, with --all, any file
under the folder) is:

- an After Effects, Premiere or Resolve template: .aep .aepx .mogrt .ffx .prproj .drfx .setting .mgt;
- inside a folder named templates-private;
- a Lottie animation (.lottie, or JSON with v, fr, op and layers) without a sibling <file>.attribution whose
  "license:" line names an open licence (MIT, Apache-2.0, BSD, CC0, CC-BY, OFL) and whose "source:" is not a
  marketplace.

    python3 tools/ci/no_private_templates.py [--all] [ROOT]

Exit 0 clean, 1 with the offending paths listed.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path

TEMPLATE_EXT = {".aep", ".aepx", ".mogrt", ".ffx", ".prproj", ".drfx", ".setting", ".mgt"}
OPEN = re.compile(r"\b(MIT|Apache-2\.0|BSD|CC0|CC-BY|OFL)\b", re.I)
MARKETPLACE = re.compile(r"(mixkit|envato|motionarray|motion array|lottiefiles|iconscout|storyblocks|artlist)", re.I)


def tracked(root: Path, every: bool) -> list[Path]:
    if not every:
        try:
            out = subprocess.run(["git", "-C", str(root), "ls-files", "-z"], capture_output=True, check=True).stdout
            return [root / p for p in out.decode("utf-8", "replace").split("\0") if p]
        except (OSError, subprocess.CalledProcessError):
            pass
    skip = {".git", "node_modules", ".venv", "__pycache__"}
    return [p for p in root.rglob("*") if p.is_file() and not (set(p.relative_to(root).parts) & skip)]


def is_lottie(p: Path) -> bool:
    if p.suffix.lower() == ".lottie":
        try:
            with zipfile.ZipFile(p) as z:
                return any(n.startswith("animations/") for n in z.namelist())
        except (OSError, zipfile.BadZipFile):
            return True
    if p.suffix.lower() != ".json" or p.stat().st_size > 30_000_000:
        return False
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(d, dict) and isinstance(d.get("layers"), list) and "fr" in d and "op" in d


def attribution_ok(p: Path) -> str | None:
    """None when the sibling .attribution names an open licence and no marketplace source; else why not."""
    a = p.with_name(p.name + ".attribution")
    if not a.is_file():
        return "no .attribution file with an open licence next to it"
    text = a.read_text(encoding="utf-8", errors="replace")
    lic = next((ln.split(":", 1)[1] for ln in text.splitlines() if ln.lower().startswith("license:")), "")
    src = next((ln.split(":", 1)[1] for ln in text.splitlines() if ln.lower().startswith("source:")), "")
    if not OPEN.search(lic):
        return f"licence {lic.strip()!r} is not an open one"
    if MARKETPLACE.search(src):
        return f"source {src.strip()!r} is a marketplace (those items stay in the private studio folder)"
    return None


def check(root: Path, every: bool = False) -> list[str]:
    bad = []
    for p in tracked(root, every):
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        if "templates-private" in p.relative_to(root).parts:
            bad.append(f"{rel}: inside templates-private (a studio folder, never in the repository)")
        elif p.suffix.lower() in TEMPLATE_EXT:
            bad.append(f"{rel}: {p.suffix} template files never go into the repository")
        elif is_lottie(p):
            why = attribution_ok(p)
            if why:
                bad.append(f"{rel}: a Lottie animation with {why}")
    return bad


def main(argv: list[str]) -> int:
    every = "--all" in argv
    args = [a for a in argv if a != "--all"]
    root = Path(args[0] if args else ".").resolve()
    bad = check(root, every)
    for b in bad:
        print(b)
    if bad:
        print(f"{len(bad)} file(s) look like marketplace templates; keep them in the studio's library/templates-private/.")
        return 1
    print("no marketplace templates in the repository")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
