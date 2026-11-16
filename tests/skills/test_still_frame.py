import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from s2_helpers import script  # noqa: E402

sf = script("thumbnail/scripts/still_frame.py", "s2_still_frame")


def test_parse_ranges():
    assert sf.parse_ranges(["0:20", "-30:"], 100.0) == [(0.0, 20.0), (70.0, 100.0)]
    assert sf.parse_ranges(["86,5:89"], 100.0) == [(86.5, 89.0)]
    assert sf.parse_ranges([":"], 10.0) == [(0.0, 10.0)]
    with pytest.raises(ValueError):
        sf.parse_ranges(["50:50.1"], 100.0)
    with pytest.raises(ValueError):
        sf.parse_ranges(["abc"], 100.0)


def test_face_window():
    assert sf.face_window((0.5, 0.375)) == pytest.approx((0.28, 0.0, 0.72, 0.75))
    x0, y0, x1, y1 = sf.face_window((0.95, 0.9))
    assert x1 <= 1.0 and y1 <= 1.0 and x0 >= 0 and y0 >= 0


def test_laplace_and_skin():
    flat = np.full((40, 40), 128, np.uint8)
    noisy = np.random.default_rng(1).integers(0, 255, (40, 40)).astype(np.uint8)
    assert sf.laplace_variance(flat) == 0.0 and sf.laplace_variance(noisy) > 1000
    skin = np.zeros((10, 10, 3), np.uint8) + np.array([200, 150, 120], np.uint8)
    blue = np.zeros((10, 10, 3), np.uint8) + np.array([40, 60, 210], np.uint8)
    assert sf.skin_share(skin) > 0.9 and sf.skin_share(blue) == 0.0


def test_choose():
    entries = [
        {"time": 1.0, "sharp": 100.0, "skin": 0.3},
        {"time": 1.5, "sharp": 110.0, "skin": 0.3},   # too close to 1.0 once 1.5 is chosen first
        {"time": 3.0, "sharp": 40.0, "skin": 0.3},    # blurred (under 60 % of the median)
        {"time": 5.0, "sharp": 300.0, "skin": 0.02},  # graphic, no face
        {"time": 7.0, "sharp": 95.0, "skin": 0.25},
    ]
    chosen, info = sf.choose(entries, 10, spacing=1.0)
    assert [e["time"] for e in chosen] == [1.5, 7.0]
    assert "1 without a face" in info and "1 blurred" in info
    none, msg = sf.choose([{"time": 0, "sharp": 1.0, "skin": 0.0}], 3)
    assert none == [] and "no frame with a face" in msg


def test_time_text():
    assert sf.time_text(88.0) == "1:28.0"
    assert sf.time_text(5.04) == "0:05.0"
