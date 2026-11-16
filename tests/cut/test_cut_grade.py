"""Grade: signalstats parsing, patch means, targets, the before/after sheet. ffmpeg never runs."""

import pytest
from PIL import Image

from crewcut.cut import grade

STATS = """frame:0    pts:0       pts_time:3
lavfi.signalstats.YMIN=16
lavfi.signalstats.YLOW=28
lavfi.signalstats.YAVG=101.34
lavfi.signalstats.YHIGH=190
lavfi.signalstats.YMAX=235
lavfi.signalstats.SATAVG=31.2
"""


def test_signalstats():
    assert grade.parse_signalstats(STATS) == {"YLOW": 28.0, "YAVG": 101.3, "YHIGH": 190.0, "YMAX": 235.0,
                                              "SATAVG": 31.2}


def test_patch_means(tmp_path):
    png = tmp_path / "still.png"
    im = Image.new("RGB", (200, 100), (200, 200, 200))
    im.paste((180, 140, 120), (100, 0, 200, 100))
    im.save(png)
    assert grade.patch(png, [10, 10, 50, 50]) == {"rgb": [200.0, 200.0, 200.0], "luma": 200.0}
    assert grade.patch(png, [120, 10, 40, 40])["rgb"] == [180.0, 140.0, 120.0]


def test_targets():
    ok = {"wall": {"rgb": [150, 151, 152], "luma": 151}, "skin": {"rgb": [190, 150, 130], "luma": 160},
          "frame": {"YLOW": 28, "YHIGH": 190, "YMAX": 235}}
    assert grade.verdicts(ok) == []
    bad = {"wall": {"rgb": [160, 150, 140], "luma": 151}, "skin": {"rgb": [130, 150, 140], "luma": 120},
           "frame": {"YLOW": 12, "YHIGH": 220, "YMAX": 254}}
    misses = " | ".join(grade.verdicts(bad))
    for word in ("wall not neutral", "skin colour order", "skin luma", "too bright", "crushed", "clip"):
        assert word in misses
    assert grade.verdicts({"frame": {}}) == []


def test_skin_spread_across_times():
    rows = [{"after": {"skin": {"luma": 150}}}, {"after": {"skin": {"luma": 170}}}]
    assert "differs" in grade.skin_spread(rows)
    assert grade.skin_spread(rows[:1]) is None


def test_rects_and_commands():
    assert grade.parse_rect("60,120,120,160") == [60, 120, 120, 160]
    assert grade.parse_rect(None) is None
    with pytest.raises(ValueError):
        grade.parse_rect("1,2,3")
    cmd = grade.stats_cmd("p.mov", 3, "eq=contrast=1.1", (1920, 1080))
    assert cmd[cmd.index("-vf") + 1] == ("scale=1920:1080,eq=contrast=1.1,format=yuv420p,signalstats,"
                                         "metadata=print:file=-")
    assert grade.frame_cmd("p.mov", 3, "", "o.png", (1080, 1920))[-2] == "scale=1080:1920"
    a = grade.apply_cmd("p.mov", grade.BASE, "o.mov")
    assert a[a.index("-c:v") + 1] == "prores_ks" and a[a.index("-c:a") + 1] == "copy" and "-n" in a


def test_base_filter_from_the_pack():
    assert grade.base_filter() == grade.BASE


def test_sheet(tmp_path):
    pngs = []
    for k in range(4):
        p = tmp_path / f"{k}.png"
        Image.new("RGB", (192, 108), (k * 50, 0, 0)).save(p)
        pngs.append(p)
    out = grade.sheet(pngs, tmp_path / "sheet.jpg", width=96)
    with Image.open(out) as im:
        assert im.size == (2 * 96 + 12, 2 * (54 + 4) + 4)
