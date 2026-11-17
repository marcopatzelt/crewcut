#!/usr/bin/env python3
"""Machine checks for the motion inserts of an edit plan, or of a review bundle the Critic is reading.

  python3 skills/cut-check/scripts/motion_check.py <episode>/edit/plan-vNNN.json [--ids m1,m2]
  python3 skills/cut-check/scripts/motion_check.py <episode>/review/motion-vNNN
          [--exceptions FILE] [--report FILE] [--pack DIR] [--json]

A plan: the checks run now on the rendered frames (render/inserts/<id>-<hash>/NNNN.png) and the .jsx source, without
the engine. A bundle folder (built by `crewcut render motion-review`): its findings are read from bundle.json, so the
engine's measurements (text sizes, strips) count too.

Checks (motion plan 3.5 and the density rules):
  empty, frozen  a frame shows nothing; a hold where nothing changes for 0.5 s ("the camera stopped")
  sharp          Laplace variance under 35 % of the mean outside the declared transitions; more than 3 such frames
                 in a row is an ERROR
  hue            one hue above 30 % of the coloured pixels at 5 times ("natural": true and the end lockup are exempt)
  text, face     text under min_text_px on screen, outside the safe box, on the face box (engine); overlay pixels on
                 the face box (frames); text sizes under min_text_px written in the source (candidates)
  lint           hard-coded 1920/1080, a font name, Shatter, Temporal Motion Blur (ERROR); rounded rect or filled box
                 with text (CHECK: a heuristic, the Critic decides)
  motion-*       density over the whole plan: lengths, big moments, motion per minute, 6 s gaps, one per sentence,
                 heroes, speaker between full-frame parts, sounds, the first and last seconds, keywords
Prints ERROR / CHECK / NOTE / OK per area like cut_check.py and style_check.py, then the questions only the Critic can
answer. Writes review/motion-check-vNNN.json (plan) or <bundle>/motion-check.json. Exit 0 = no ERROR,
1 = at least one ERROR, 2 = usage.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import checklib as cl  # noqa: E402

AREAS = ["Picture", "Colour", "Text", "Lint", "Density", "Bundle"]
MANUAL = [
    "sheet.jpg and the strips looked at: stutter, missing motion blur, holds longer than planned, glyphs waiting "
    "before their cue.",
    "web-look.md answered for every frame: a web page or app screenshot? a rounded rectangle with text? a word in a "
    "filled box? all shadows one shape although the depths differ? Any yes goes back.",
    "One sentence per big moment on what the reference still does better (critic.md).",
    "At least one named way this video is better than the bar; else it goes back.",
    "Sound: this session cannot hear. Give the user the listening list in critic.md.",
]


def from_bundle(folder: Path) -> dict:
    data = json.loads((folder / "bundle.json").read_text(encoding="utf-8"))
    return {"plan": data.get("plan"), "episode": data.get("episode"), "inserts": [r["id"] for r in data["inserts"]],
            "findings": data["findings"], "engine_note": data.get("engine_note")}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Machine checks for motion inserts (plan or review bundle).")
    ap.add_argument("target", help="edit/plan-vNNN.json or review/motion-vNNN")
    ap.add_argument("--ids", help="only these inserts (plan only), comma separated")
    ap.add_argument("--exceptions", help="default: <episode>/review/cut-check-exceptions.json")
    ap.add_argument("--report", help="default: review/motion-check-vNNN.json or <bundle>/motion-check.json")
    ap.add_argument("--pack", help="style pack folder (default: studio/brand, else packs/neutral)")
    ap.add_argument("--json", action="store_true", help="print the report as JSON")
    a = ap.parse_args(argv)
    target = Path(a.target)
    review = cl.app_module("crewcut.motion.review")
    if target.is_dir() and (target / "bundle.json").is_file():
        res = from_bundle(target)
        ep = target.resolve().parent.parent
        out = Path(a.report) if a.report else target / "motion-check.json"
        what = f"bundle {target.name}"
    elif target.is_file():
        ids = [x.strip() for x in a.ids.split(",") if x.strip()] if a.ids else None
        try:
            res = review.analyze(target, ids, cl.load_pack(a.pack))
        except review.ReviewError as e:
            ap.error(str(e))
        ep = target.resolve().parent.parent
        out = Path(a.report) if a.report else ep / "review" / f"motion-check-{cl.version_of(target)}.json"
        what = f"plan {target.name}"
    else:
        ap.error(f"not a plan file or a bundle folder with bundle.json: {target}")
    exc = Path(a.exceptions) if a.exceptions else ep / "review" / "cut-check-exceptions.json"
    rep = cl.Report(cl.load_exceptions(exc))
    for f in res["findings"]:
        rep.add(f.get("area") or "Bundle", f["level"], f["id"], f["text"], f.get("time"), f.get("fix"))
    n = rep.count()
    report = {"episode": ep.name, "target": str(target), "inserts": res["inserts"], "counts": n,
              "findings": rep.items}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    if a.json:
        print(json.dumps(report, ensure_ascii=False, indent=1))
    else:
        print(f"Motion check {ep.name}, {what}, inserts {', '.join(res['inserts']) or 'none'}")
        if res.get("engine_note"):
            print(f"  NOTE   {res['engine_note']}")
        rep.print(AREAS, out=sys.stdout)
        print("\nCandidates from the lint (rounded-text, box-behind-text) are heuristics: the Critic decides.")
        print("\nBy hand:")
        for line in MANUAL:
            print(f"  [ ] {line}")
        print(f"\nResult: {n['ERROR']} ERROR, {n['CHECK']} CHECK, {n['OK']} OK, {n['NOTE']} NOTE")
        print(f"Report: {out}")
    if n["ERROR"]:
        if not a.json:
            print("NOT PASSED: back to the builder with the errors named.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
