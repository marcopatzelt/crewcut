"""`crewcut brand preview [--out file.mp4] [--pack DIR]`: a 10-second sample in the active style pack.

A plain background in the pack's colours (no stock footage), a headline card, a counter and a keyword over the
background, assembled with the same workbench as every episode. Onboarding shows it on the profile card.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from collections.abc import Callable
from pathlib import Path

from .. import brand, paths
from . import assemble, html, media
from .plan import Plan, PlanError

SECONDS = 10.0


def plan_data(pack: brand.Pack) -> dict:
    """The preview as an edit plan: 0-3.6 s headline, 3.6-7 s counter, 7-10 s background with a keyword."""
    name = pack.value("channel.name") or (None if pack.is_neutral else pack.value("brand.name"))
    fmt = pack.value("edit_style.format", "landscape")
    return {
        "format": fmt if fmt in ("landscape", "portrait") else "landscape",
        "fps": int(pack.value("edit_style.fps", 25)),
        "base": {"color": "soft", "seconds": SECONDS},
        "voice": None,
        "inserts": [
            {"id": "headline", "kind": "2d", "scene": "headline", "start": 0.0, "end": 3.6, "cues": {"mark": 30},
             "data": {"chips": [name or "Your channel", "Style preview"],
                      "title": "This is how the graphics in your videos will look", "mark": "your videos",
                      "source": "Crewcut preview of your style pack."}},
            {"id": "counter", "kind": "2d", "scene": "counter", "start": 3.6, "end": 7.0,
             "cues": {"label": 4, "value": 52, "unit": 60},
             "data": {"label": "This preview", "value": "10", "unit": "seconds"}},
            {"id": "keyword", "kind": "2d", "scene": "keyword", "start": 7.0, "end": SECONDS, "transparent": True,
             "data": {"words": [{"text": "Key words, not captions", "from": 6, "to": 72}]}},
        ],
        "sound": {"music": None},
        "output": "export/preview.mp4",
        "crf": 18,
    }


def stamp(pack: brand.Pack, plan: dict) -> str:
    """Changes when the pack's look, the preview plan or a 2D template changes."""
    from .plan import render_tokens, tokens_for_hash
    h = hashlib.sha1(json.dumps(plan, sort_keys=True).encode())
    h.update(json.dumps(tokens_for_hash(render_tokens(pack), "2d"), sort_keys=True).encode())
    d = paths.templates_dir() / "2d"
    for f in sorted(d.glob("*")):
        if f.is_file():
            h.update(f.name.encode() + f.read_bytes())
    return h.hexdigest()[:12]


def build(pack: brand.Pack | None = None, out: Path | None = None, runner: media.Runner = media.run,
          log: Callable = print) -> Path:
    pack = pack or brand.load()
    data = plan_data(pack)
    key = stamp(pack, data)
    work = paths.state_dir() / "preview" / key
    (work / "edit").mkdir(parents=True, exist_ok=True)
    plan_file = work / "edit" / "plan.json"
    plan_file.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    plan = Plan(plan_file, pack=pack)
    result = plan.output
    if not result.is_file():
        rows = html.render_2d(plan, runner=runner, log=log)
        bad = [r["id"] for r in rows if not (r["frames_ok"] and r["clip_ok"])]
        if bad:
            raise RuntimeError(f"the preview scenes {', '.join(bad)} did not render")
        assemble.cut(plan, runner, log)
    target = Path(out).resolve() if out else paths.state_dir() / "preview" / "preview.mp4"
    target.parent.mkdir(parents=True, exist_ok=True)
    if target != result:
        shutil.copy2(result, target)
    return target


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="crewcut brand preview", description="A 10-second sample video in the style pack.")
    ap.add_argument("--out", help="where to write the MP4 (default: studio/.crewcut/preview/preview.mp4)")
    ap.add_argument("--pack", help="a style pack folder (default: the active pack)")
    ap.add_argument("--json", action="store_true", help="machine output")
    try:
        a = ap.parse_args(argv)
    except SystemExit as e:
        return 0 if e.code == 0 else 2
    try:
        pack = brand.load(a.pack) if a.pack else brand.load()
        path = build(pack, Path(a.out) if a.out else None, log=(lambda *_: None) if a.json else print)
    except (PlanError, RuntimeError, ValueError, FileNotFoundError) as e:
        print(f"Preview failed: {e}", file=sys.stderr)
        return 1
    if a.json:
        print(json.dumps({"out": str(path), "seconds": SECONDS, "pack": str(pack.dir)}))
    else:
        print(f"Preview: {path}")
    return 0
