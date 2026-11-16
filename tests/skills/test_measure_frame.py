import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from s2_helpers import pack, script  # noqa: E402

mf = script("3d-scene/scripts/measure_frame.py", "s2_measure_frame")


def frame(accent=(228, 87, 46), bg=239, shadow=170):
    """A synthetic stage: grey wall, floor with a shadow band, one accent block."""
    im = np.full((180, 320, 3), float(bg))
    im[130:170, 60:260] = shadow                 # shadow on the floor
    im[60:120, 120:200] = np.array(accent, float)  # accent object
    return im


def test_helpers():
    assert mf.hex_rgb("#EFEFEC") == (239, 239, 236)
    assert mf.hexa((35.2, 32, 214)) == "#2320D6"
    assert abs(mf.luma((255, 255, 255)) - 1.0) < 1e-9


def test_accent_mask_counts_shaded_accent():
    im = np.zeros((2, 2, 3))
    im[0, 0] = (228, 87, 46)
    im[0, 1] = (140, 54, 28)    # same hue, darker
    im[1, 0] = (120, 120, 120)  # grey
    im[1, 1] = (30, 60, 200)    # other hue
    m = mf.accent_mask(im, (228, 87, 46))
    assert m.tolist() == [[True, True], [False, False]]


def test_measure_and_verdict():
    m = mf.measure(frame(), (228, 87, 46))
    assert abs(m["accent_share"] - (60 * 80) / (180 * 320)) < 1e-6
    assert m["background"] == "#EFEFEF"
    assert m["accent_color"] == "#E4572E"
    assert 0.2 < m["shadow_depth"] < 0.4
    v = mf.verdict(m, "#EFEFEC", "#E4572E", {})
    assert all(level in ("OK", "NOTE") for level, _ in v)
    dark = mf.measure(frame(bg=120), (228, 87, 46))
    assert any(level == "CHECK" for level, _ in mf.verdict(dark, "#EFEFEC", "#E4572E", {}))


def test_pack_has_stage_checks():
    st = pack().value("brand.stage3d", {})
    assert "checks" in st and st["checks"]["accent_share"][0] < st["checks"]["accent_share"][1]
