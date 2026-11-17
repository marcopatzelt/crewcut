"""Motion part of the image smoke test (tests/smoke/render.sh). Needs effectcraft-cli, ffmpeg and ffprobe; never run
it on a laptop you need.

    python3 tests/smoke/motion.py <out_dir>

1. samples: for every templates/motion/*.jsx whose header parses, the last frame in each of its @formats with the
   neutral pack (draft blur, at most 960 px on the long side, so it fits the time budget), plus the hue check on it.
   A frame fails the hue check when one hue holds more than 30 % of its coloured pixels while coloured pixels cover at
   least 10 % of the frame ("everything one colour"); a small accent alone passes.
2. clips: keyword_pop 1.5 s at 25 fps as an overlay (QuickTime Animation MOV with alpha) and number_roll 3 s as an
   MP4, through `crewcut.render.motion` like a real plan; the frame count of each clip is checked. A template that
   does not exist yet is skipped with a note.

Prints one line per check and the seconds each part took; exit 1 when a check failed.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

from crewcut import brand, paths
from crewcut.motion import project as mproject
from crewcut.motion import templates as mtemplates
from crewcut.motion.backend import Backend, BackendError
from crewcut.motion.palette import hue_report
from crewcut.render import media
from crewcut.render import motion as rmotion
from crewcut.render.plan import Plan, brand_context, render_tokens

SIZES = {"landscape": (1920, 1080), "portrait": (1080, 1920), "stage": (1080, 960)}
FPS = 25
SECONDS = 4.0
FACE = {"x": 0.5, "y": 0.38, "w": 0.32, "h": 0.28}
SAMPLE_SIDE = 960
COLOURED_MIN = 0.10


def say(line: str) -> None:
    print(line, flush=True)


def library() -> list[tuple[Path, dict]]:
    """The app's templates whose header parses (pinned old versions, name.vN.jsx, left out)."""
    out = []
    for p in sorted(mtemplates.app_dir().glob("*.jsx")):
        if "." in p.stem:
            continue
        try:
            out.append((p, mtemplates.parse_header(p.read_text(encoding="utf-8"))))
        except mtemplates.TemplateError as e:
            say(f"motion sample {p.name}: header does not parse, skipped ({e})")
    return out


def samples(out: Path, fonts: Path, lib: list[tuple[Path, dict]]) -> bool:
    pack = brand.load(paths.neutral_pack_dir())
    tokens = render_tokens(pack)
    mg = tokens["motion_graphics"]
    be = Backend(env=rmotion.font_env(fonts))
    ok = True
    for path, h in lib:
        overlay = h.get("kind") == "overlay"
        for fmt in h.get("formats") or ["landscape"]:
            w, hh = SIZES[fmt]
            ctx = {"format": fmt, "size": [w, hh], "fps": FPS, "duration": SECONDS, "transparent": overlay,
                   "face": FACE if overlay and fmt != "stage" else None, "backdrop": None, "draft": True,
                   "right_free": 0.18, "brand": brand_context(tokens)}
            work = out / ".work" / f"{h['name']}-{fmt}"
            work.mkdir(parents=True, exist_ok=True)
            proj = str(work / "s.ecproj")
            png = out / f"{h['name']}-{fmt}.png"
            t0 = time.monotonic()
            try:
                code, _ = mtemplates.program_path(path, {}, context=ctx)
                comp = mproject.comp_params("Main", profile=None, width=w, height=hh, fps=FPS,
                                            duration=SECONDS + 2 / FPS, bg=None if overlay else mg["ground"],
                                            shutter_angle=180, samples=8)
                mproject.create(be, proj, comp, motion_blur=True, overwrite=True)
                be.script(code, project=proj, save=True, name=f"{h['name']}.jsx")
                be.render_frame(proj, str(png), comp="Main", frame=round(SECONDS * FPS) - 1, max_side=SAMPLE_SIDE,
                                transparent=overlay)
            except (BackendError, mtemplates.TemplateError, ValueError) as e:
                say(f"motion sample {h['name']} {fmt}: FAILED {str(e)[-300:]}")
                ok = False
                continue
            if not png.is_file():
                say(f"motion sample {h['name']} {fmt}: FAILED (no frame written)")
                ok = False
                continue
            r = hue_report(str(png))
            hue_ok = r["ok"] or r["coloured_share"] < COLOURED_MIN
            ok = ok and hue_ok
            say(f"motion sample {h['name']} {fmt}: {'ok' if hue_ok else 'HUE CHECK FAILED'} "
                f"(coloured {r['coloured_share']:.0%}, top hue {r['dominant_share']:.0%}) "
                f"in {time.monotonic() - t0:.1f} s")
    shutil.rmtree(out / ".work", ignore_errors=True)
    return ok


def probe(clip: Path) -> dict:
    r = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
                        "stream=codec_name,pix_fmt,nb_read_frames", "-of", "json", str(clip)],
                       capture_output=True, text=True)
    try:
        return json.loads(r.stdout)["streams"][0]
    except (ValueError, KeyError, IndexError):
        return {}


def clips(out: Path, lib: list[tuple[Path, dict]]) -> bool:
    have = {h["name"] for _, h in lib}
    want = [("keyword_pop", 0.5, 2.0, True), ("number_roll", 2.5, 5.5, False)]
    inserts = []
    for name, a, b, overlay in want:
        if name not in have:
            say(f"motion clip {name}: skipped (no templates/motion/{name}.jsx yet)")
            continue
        inserts.append({"id": name.replace("_", "-"), "kind": "motion", "scene": name, "start": a, "end": b,
                        "transparent": overlay, "data": {}})
    if not inserts:
        return True
    ep = paths.studio_root() / "episodes" / "001-motion-smoke"
    (ep / "edit").mkdir(parents=True, exist_ok=True)
    plan_file = ep / "edit" / "plan-v001.json"
    plan_file.write_text(json.dumps({"format": "landscape", "fps": FPS, "base": {"color": "soft", "seconds": 6},
                                     "inserts": inserts, "output": "export/motion-smoke-v001.mp4"}))
    plan = Plan(plan_file, pack=brand.load(paths.neutral_pack_dir()))
    for w in plan.warnings:
        say(f"motion clip plan: warning: {w}")
    r = rmotion.render_motion(plan, location="local", draft=True, runner=media.run, log=say)
    ok = True
    for row in r["rows"]:
        ins = plan.by_id(row["id"])
        clip = Path(row["clip"])
        s = probe(clip) if clip.is_file() else {}
        n = int(s.get("nb_read_frames") or 0)
        good = bool(row["clip_ok"]) and n == ins.render_frames
        if ins.transparent:
            good = good and s.get("codec_name") == "qtrle" and s.get("pix_fmt") == "argb"
        else:
            good = good and s.get("codec_name") == "h264"
        ok = ok and good
        say(f"motion clip {ins.scene}: {'ok' if good else 'FAILED'} ({n} of {ins.render_frames} frames, "
            f"{s.get('codec_name')} {s.get('pix_fmt')})")
        if clip.is_file():
            shutil.copy2(clip, out / f"{ins.scene}{clip.suffix}")
    return ok


def main(argv: list[str]) -> int:
    out = Path(argv[1] if len(argv) > 1 else "/tmp/crewcut-smoke/motion")
    out.mkdir(parents=True, exist_ok=True)
    fonts = out / ".fonts"
    fonts.mkdir(exist_ok=True)
    t0 = time.monotonic()
    lib = library()
    ok = samples(out, fonts, lib)
    t1 = time.monotonic()
    say(f"motion samples took {t1 - t0:.0f} s")
    ok = clips(out, lib) and ok
    say(f"motion clips took {time.monotonic() - t1:.0f} s")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
