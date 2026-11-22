"""A declared camera roll correction must be in the rendered preview: the roll is measured on speaker frames, more
than 0.3° left over refuses the card, and an undeclared tilt above 0.5° is a CHECK (episode 019: four previews went out
without the declared -1.0°)."""

import json
import os
import shutil
import subprocess

import numpy as np
import pytest
from PIL import Image, ImageDraw

from crewcut import approvals, episodes, paths
from crewcut.cut import tilt


def room(w: int = 1920, h: int = 1080) -> Image.Image:
    """A synthetic speaker frame: wall, a monitor, a table edge, shelves and a door frame: straight edges."""
    im = Image.new("L", (w, h), 170)
    d = ImageDraw.Draw(im)
    d.rectangle([0, int(h * 0.72), w, h], fill=90)                       # table
    d.rectangle([int(w * 0.58), int(h * 0.18), int(w * 0.9), int(h * 0.55)], fill=30)   # monitor
    for y in (0.12, 0.3, 0.45):                                          # shelves
        d.rectangle([int(w * 0.06), int(h * y), int(w * 0.4), int(h * y) + 10], fill=60)
    d.rectangle([int(w * 0.44), int(h * 0.05), int(w * 0.46), int(h * 0.72)], fill=50)  # door frame
    d.ellipse([int(w * 0.4), int(h * 0.25), int(w * 0.6), int(h * 0.9)], fill=120)       # the speaker
    return im


def tilted(deg: float) -> np.ndarray:
    """Turned clockwise by deg (positive = right side lower), as a camera that hangs to the right."""
    big = room(2400, 1350).rotate(-deg, resample=Image.BICUBIC, fillcolor=170)
    return np.asarray(big.crop((240, 135, 2160, 1215)))


def test_the_angle_of_a_rotated_synthetic_frame():
    assert abs(tilt.angle(tilted(0.0))) <= 0.1
    assert abs(tilt.angle(tilted(1.0)) - 1.0) <= 0.2
    assert abs(tilt.angle(tilted(-0.8)) + 0.8) <= 0.2


def test_declared_correction_formats():
    assert tilt.declared({"camera_roll_correction": {"degrees": -1.0, "method": "rotate"}}) == -1.0
    assert tilt.declared({"camera_roll_correction": "-1,0°"}) == -1.0
    assert tilt.declared({"roll_correction": 0.5}) == 0.5
    assert tilt.declared({"cuts": []}) is None


def test_verdicts():
    assert tilt.verdict(-1.0, [0.67, 0.89, 0.8])[0] == "ERROR"           # the correction is not in the render
    assert tilt.verdict(-1.0, [0.05, -0.04, 0.09])[0] == "OK"
    assert tilt.verdict(None, [0.84, 1.07, 0.9])[0] == "CHECK"            # tilted, nothing declared
    assert tilt.verdict(None, [0.2, 0.3, 0.1])[0] == "OK"
    assert tilt.verdict(-1.0, [0.9, None])[0] == "CHECK"                  # too few frames: by eye, no block


def test_speaker_times_spread_over_the_speaker_stretches():
    runs = [(0, 20), (50, 300), (400, 410), (500, 1000), (1100, 1300), (1400, 1500)]
    assert tilt.speaker_times(runs, 25, n=3) == [9.0, 31.0, 49.0]   # never in the short ones
    assert tilt.speaker_times([(0, 150)], 25) == [0.6, 1.8, 3.0, 4.2, 5.4]


@pytest.fixture
def episode(studio):
    ep = episodes.create("Erst Coding, jetzt Videoschnitt")["id"]
    d = paths.episode_dir(ep)
    for sub in ("edit", "export", "review"):
        (d / sub).mkdir(parents=True, exist_ok=True)
    (d / "edit" / "cut-plan-v013.json").write_text(json.dumps({"camera_roll_correction": {"degrees": -1.0}}))
    (d / "edit" / "plan-v004.json").write_text(json.dumps({"base": "work/speaker-graded-v013.mov"}))
    video = d / "export" / f"{ep}-v004-preview.mp4"
    video.write_bytes(b"not really a video")
    return ep, d, video


def record(d, video, angles):
    st = video.stat()
    tilt.record_path(video, d).write_text(json.dumps({"video": video.name, "size": st.st_size,
                                                      "mtime": int(st.st_mtime), "angles": angles}))


def propose(ep, video):
    return approvals.propose(ep, "edit", "preview", "Vorschau v004", file=str(video.relative_to(paths.episode_dir(ep))),
                             identity="editor")


def test_the_card_waits_for_a_measurement_and_refuses_a_tilted_preview(episode):
    ep, d, video = episode
    with pytest.raises(tilt.Tilted, match="not measured"):
        propose(ep, video)
    record(d, video, [0.67, 0.89, 0.8])
    with pytest.raises(tilt.Tilted, match="still tilt"):
        propose(ep, video)
    record(d, video, [0.05, -0.04, 0.09])
    assert propose(ep, video)["kind"] == "preview"


def test_a_measurement_of_an_older_render_does_not_count(episode):
    ep, d, video = episode
    record(d, video, [0.0, 0.0, 0.0])
    video.write_bytes(b"built again, without the rotation")
    os.utime(video, (video.stat().st_atime, video.stat().st_mtime + 5))
    with pytest.raises(tilt.Tilted, match="not measured"):
        propose(ep, video)


def test_no_declared_correction_never_blocks_the_card(episode):
    ep, d, video = episode
    (d / "edit" / "cut-plan-v013.json").write_text(json.dumps({"cuts": []}))
    assert propose(ep, video)["kind"] == "preview"


@pytest.mark.skipif(not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="ffmpeg is not installed")
def test_measure_reads_speaker_frames_of_a_rendered_video(episode, tmp_path):
    ep, d, video = episode
    png = tmp_path / "frame.png"
    Image.fromarray(tilted(0.9)).save(png)
    video.unlink()
    subprocess.run(["ffmpeg", "-v", "error", "-loop", "1", "-i", str(png), "-t", "4", "-r", "5", "-pix_fmt", "yuv420p",
                    "-c:v", "libx264", str(video)], check=True)
    r = tilt.measure(video, d, [0.5, 1.5, 2.5, 3.5], -1.0)
    assert r["level"] == "ERROR" and all(abs(a - 0.9) <= 0.25 for a in r["angles"])
    with pytest.raises(tilt.Tilted):
        propose(ep, video)


@pytest.mark.skipif(not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="ffmpeg is not installed")
def test_style_check_reports_the_roll_of_the_preview(episode, tmp_path):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills"))
    from s2_helpers import APP, script
    sc = script("cut-check/scripts/style_check.py", "s2_style_check_roll")
    ep, d, video = episode
    png = tmp_path / "frame.png"
    Image.fromarray(tilted(0.9)).save(png)
    video.unlink()
    subprocess.run(["ffmpeg", "-v", "error", "-loop", "1", "-i", str(png), "-f", "lavfi", "-i", "sine=f=220:d=6",
                    "-t", "6", "-r", "5", "-pix_fmt", "yuv420p", "-c:v", "libx264", "-c:a", "aac", "-shortest",
                    str(video)], check=True)
    plan = d / "edit" / "plan-v004.json"
    plan.write_text(json.dumps({"base": "work/speaker-graded-v013.mov", "fps": 25, "inserts": []}))
    os.utime(video, (video.stat().st_atime, plan.stat().st_mtime + 5))
    rep = sc.cl.Report()
    sc.check(plan, video, sc.cl.load_pack(str(APP / "packs" / "neutral")), rep)
    [roll] = [i for i in rep.items if i["id"] == "roll"]
    assert roll["level"] == "ERROR" and "-1.0°" in roll["text"]
    assert tilt.record_path(video, d).is_file()
