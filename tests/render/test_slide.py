"""The slide check (crewcut/render/slide.py): a full-frame insert whose camera stands still and whose frame is flat
reads as a slide. Pure functions on synthetic frames, the whole measurement through a fake ffmpeg, and, where ffmpeg
is installed, real videos: a still slide, the same slide with a camera push, and the launch film's beats.

Calibration on real data (2026-11-23, not in the repository because it is a user's video): a long video's review reel
of 51 inserts. 35 of its 37 full-frame graphics were flagged, every flat text window, role card and number box among
them; the two that passed move (a film strip that slides, an end card with a 1.5 % push). The 6 beats of the launch
film pass (test below), and 29 of 31 windows of 2.5 s across it; the two flagged windows sit on its typing hold, where
the camera really rests for about 1.1 s at 320 %."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

from crewcut.render import slide

APP = Path(__file__).resolve().parents[2]
LAUNCH = APP / "docs" / "launch" / "crewcut-launch-web.mp4"
FFMPEG = shutil.which("ffmpeg")
needs_ffmpeg = pytest.mark.skipif(not FFMPEG, reason="ffmpeg is not installed")
BEATS = [(0, 2.7), (2.7, 6.85), (6.85, 10.05), (10.05, 12.25), (12.25, 15.05), (15.05, 17.5)]


def slide_image(w: int = 480, h: int = 270, gap: bool = False) -> np.ndarray:
    """A slide: white ground, one centred window with three text lines (or an icon far from its label)."""
    im = Image.new("RGB", (w, h), (250, 250, 252))
    d = ImageDraw.Draw(im)
    if gap:
        d.ellipse([w * 0.12, h * 0.35, w * 0.28, h * 0.65], fill=(40, 40, 220))
        for i in range(3):
            d.rectangle([w * 0.62, h * (0.38 + i * 0.09), w * 0.86, h * (0.42 + i * 0.09)], fill=(20, 20, 30))
    else:
        d.rounded_rectangle([w * 0.25, h * 0.3, w * 0.75, h * 0.7], radius=8, fill=(255, 255, 255),
                            outline=(200, 200, 215))
        for i in range(3):
            d.rectangle([w * 0.3, h * (0.38 + i * 0.09), w * (0.62 - i * 0.05), h * (0.42 + i * 0.09)], fill=(20, 20, 30))
    return np.asarray(im)


def texture(w: int = 320, h: int = 180, seed: int = 3) -> np.ndarray:
    """A picture with detail everywhere (a stand-in for a rendered world)."""
    rng = np.random.default_rng(seed)
    small = rng.integers(0, 255, (h // 6, w // 6, 3), dtype=np.uint8)
    return np.asarray(Image.fromarray(small).resize((w, h), Image.BICUBIC))


def zoomed(img: np.ndarray, s: float) -> np.ndarray:
    g = np.stack([slide.warp(img[..., c].astype(np.float32), s) for c in range(3)], -1)
    return np.clip(g, 0, 255).astype(np.uint8)


# ---------------------------------------------------------------- pure functions


def test_a_still_frame_is_frozen_and_does_not_move():
    a = slide.gray(slide_image(320, 180))
    c = slide.camera(a, a.copy(), 0.5)
    assert c["frozen"] == 1.0 and c["rate"] == 0.0 and c["moving"] is False


def test_a_slow_push_is_measured_as_a_camera_move():
    img = texture()
    a, b = slide.gray(img), slide.gray(zoomed(img, 1.01))      # 1 % in 0.5 s = 2 % per second
    c = slide.camera(a, b, 0.5)
    assert c["moving"] is True
    assert 0.012 <= c["zoom"] <= 0.03
    assert c["frozen"] < slide.FROZEN_MOVE


def test_one_element_that_animates_is_not_a_camera_move():
    base = slide_image(320, 180)
    moved = base.copy()
    moved[60:80, 100:140] = 0                                   # a new word appears in the window
    c = slide.camera(slide.gray(base), slide.gray(moved), 0.5)
    assert c["moving"] is False


def test_layout_names_a_flat_ground_one_block_and_an_icon_far_from_its_label():
    centred = slide.layout(slide_image())
    assert centred["ground"] >= slide.GROUND_FLAT and centred["centre_off"] <= slide.CENTRE_OFF
    words = slide.flat_reasons(centred)
    assert any("one flat ground colour" in w for w in words) and "one block in the middle of the frame" in words
    apart = slide.layout(slide_image(gap=True))
    assert apart["gap"] >= slide.GAP_SHARE
    assert any("icon far from its label" in w for w in slide.flat_reasons(apart))
    assert slide.flat_reasons(slide.layout(texture(480, 270))) == []


def _pair(moving: bool, counted: bool = True) -> dict:
    return {"rate": 0.02 if moving else 0.0, "frozen": 0.1 if moving else 0.8, "moving": moving, "counted": counted}


def test_judge_needs_most_of_the_hold_moving_and_leaves_flashes_out():
    flat = slide.layout(slide_image())
    assert slide.judge([_pair(True)] * 3 + [_pair(False)], flat, "2d", 3.0)["verdict"] == "moves"
    r = slide.judge([_pair(True), _pair(False)], flat, "2d", 1.5)
    assert r["verdict"] == "slide" and r["level"] == "ERROR" and r["reasons"]
    # a white flash between two scenes has no texture: it neither moves nor stands still
    assert slide.judge([_pair(True), _pair(False, counted=False)], flat, "2d", 1.5)["verdict"] == "moves"
    rich = slide.layout(texture(480, 270))
    assert slide.judge([_pair(False)] * 3, rich, "3d", 2.0)["verdict"] == "still"
    assert slide.judge([_pair(False)] * 3, flat, "clip", 2.0)["level"] == "CHECK"
    assert slide.judge([], flat, "2d", 0.3)["verdict"] == "short"


def test_hold_leaves_out_the_entrance_and_the_exit():
    assert slide.hold(10.0, 15.0) == (10.0 + slide.LEAD_S, 15.0 - slide.TAIL_S)
    a, b = slide.hold(0.0, 1.0)
    assert 0 < a < b < 1.0


# ---------------------------------------------------------------- the measurement through a fake ffmpeg


class FakeVideo:
    """Answers the ffmpeg calls of slide.frames: raw RGB frames of a still picture or of a camera push."""

    def __init__(self, push: float = 0.0):
        self.push, self.calls = push, []

    def __call__(self, argv: list[str]) -> bytes:
        self.calls.append(argv)
        vf = argv[argv.index("-vf") + 1]
        fps = float(vf.split(",")[0].split("=")[1])
        w, h = (int(x) for x in vf.split("scale=")[1].split(",")[0].split(":"))
        dur = float(argv[argv.index("-t") + 1])
        t0 = float(argv[argv.index("-ss") + 1])
        n = max(1, int(round(dur * fps)) if fps < 30 else 1)
        base = texture(w, h) if self.push else slide_image(w, h)
        out = b""
        for k in range(n):
            t = t0 + k / fps
            out += (zoomed(base, 1 + self.push * t) if self.push else base).tobytes()
        return out


def test_measure_flags_a_still_slide_and_passes_a_push():
    still = slide.measure("v.mp4", 2.0, 7.0, "2d", runner=FakeVideo())
    assert still["verdict"] == "slide" and still["level"] == "ERROR" and still["pairs"] >= 4
    push = slide.measure("v.mp4", 2.0, 7.0, "motion", runner=FakeVideo(push=0.02))
    assert push["verdict"] == "moves" and push["level"] == "OK"


def test_check_leaves_overlays_out_and_names_the_fix():
    found = slide.check("v.mp4", [{"id": "win", "kind": "2d", "start": 0.0, "end": 5.0},
                                  {"id": "kw", "kind": "2d", "start": 6.0, "end": 8.0, "full": False}],
                        runner=FakeVideo())
    assert [f["id"] for f in found] == ["slide:win"]
    assert found[0]["level"] == "ERROR" and "reads as a slide" in found[0]["text"] and found[0]["fix"]


# ---------------------------------------------------------------- real videos


def _video(path: Path, frames: list[np.ndarray], fps: int = 30) -> Path:
    h, w = frames[0].shape[:2]
    subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", str(fps),
                    "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "16", str(path)],
                   input=b"".join(f.tobytes() for f in frames), check=True)
    return path


@needs_ffmpeg
def test_a_rendered_slide_fails_and_the_same_picture_with_a_push_passes(tmp_path):
    base = slide_image(640, 360)
    still = _video(tmp_path / "still.mp4", [base] * 120)
    found = slide.check(str(still), [{"id": "s", "kind": "2d", "start": 0.0, "end": 4.0}])
    assert found[0]["level"] == "ERROR" and found[0]["measured"]["verdict"] == "slide"
    world = texture(640, 360)
    pushed = _video(tmp_path / "push.mp4", [zoomed(world, 1 + 0.025 * k / 30) for k in range(120)])
    found = slide.check(str(pushed), [{"id": "p", "kind": "2d", "start": 0.0, "end": 4.0}])
    assert found[0]["level"] == "OK", found[0]["text"]


@needs_ffmpeg
@pytest.mark.skipif(not LAUNCH.is_file(), reason="the launch film is not in this checkout")
def test_every_beat_of_the_launch_film_passes():
    found = slide.check(str(LAUNCH), [{"id": f"beat{i}", "kind": "motion", "start": a, "end": b}
                                      for i, (a, b) in enumerate(BEATS, 1)])
    assert [f["level"] for f in found] == ["OK"] * len(BEATS), [f["text"] for f in found if f["level"] != "OK"]
