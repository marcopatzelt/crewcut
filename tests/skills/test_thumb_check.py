import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from s2_helpers import APP, pack, script  # noqa: E402

tc = script("thumbnail/scripts/thumb_check.py", "s2_thumb_check")


def test_size_findings():
    assert tc.size_findings(1280, 720, 300_000, "JPEG") == []
    levels = [t for _, t in tc.size_findings(1000, 562, 100_000, "PNG")]
    assert any("smaller than 1280x720" in t for t in levels)
    assert any("not 16:9" in t for t in (t for _, t in tc.size_findings(1024, 1024, 100, "PNG")))
    assert any("Upload file" in t for _, t in tc.size_findings(1920, 1080, 3_000_000, "PNG"))
    assert any("Format WEBP" in t for _, t in tc.size_findings(1280, 720, 100, "WEBP"))


def test_colour_shares():
    yellow = Image.new("RGB", (640, 360), (250, 220, 20))
    cs = tc.colour_shares(yellow, [{"name": "yellow", "hue": [42, 68]}, "#FAD814"], (228, 87, 46))
    assert cs["avoid"]["yellow"] > 0.9 and cs["avoid"]["#FAD814"] > 0.9
    assert cs["accent"] == 0.0
    dark = Image.new("RGB", (640, 360), (11, 14, 20))
    assert tc.colour_shares(dark, [], None)["edge_luma"] < 20


def test_text_findings():
    f = dict((lv, t) for lv, t in tc.text_findings("Way too expensive today", None, 3, 1))
    assert "CHECK" in f
    assert tc.text_findings("This is far too many words here", None, 3, 1)[0][0] == "ERROR"
    assert tc.text_findings("GOOD ENOUGH", None, 3, 1)[0][0] == "OK"
    lv = tc.text_findings("0.10 $ vs 3 $", "Local models cost almost nothing", 3, 1)
    assert ("NOTE", "Money or a price in the image.") in lv
    assert any(level == "CHECK" and "numbers" in t for level, t in lv)
    assert any("no title word" in t for _, t in lv)
    assert any("local" in t for _, t in tc.text_findings("LOCAL WINS", "Local models win", 3, 1))


def test_face_findings():
    L = {"face": True, "face_position": "side", "face_min_area": 0.07, "max_faces": 1}
    assert tc.face_findings(None, L)[0][0] == "NOTE"
    assert tc.face_findings([], L)[0][0] == "CHECK"
    big_left = [{"cx": 0.25, "cy": 0.4, "area": 0.12, "height": 0.5}]
    assert all(level == "OK" for level, _ in tc.face_findings(big_left, L))
    small_center = [{"cx": 0.5, "cy": 0.4, "area": 0.03, "height": 0.2}]
    assert [level for level, _ in tc.face_findings(small_center, L)] == ["CHECK", "CHECK"]
    two = big_left + small_center
    assert any("2 faces" in t for _, t in tc.face_findings(two, L))


def test_cover_resize_and_preview():
    img = Image.new("RGB", (1672, 941), (10, 10, 10))
    out = tc.cover_resize(img)
    assert out.size == (1280, 720)
    sq = tc.cover_resize(Image.new("RGB", (1024, 1024)))
    assert sq.size == (1280, 720)
    sheet = tc.preview_sheet([("a.png", out)], [Image.new("RGB", (1280, 720), (90, 90, 90))] * 3, 160)
    assert sheet.width == 8 + 4 * (160 + 8) + 260


def test_checklist_from_skill():
    text = (APP / "skills" / "thumbnail" / "SKILL.md").read_text(encoding="utf-8")
    items = tc.checklist(text)
    assert len(items) >= 5 and items[0].startswith("1.")
    assert tc.checklist("## Checklist\n1. one\n2. two\n## Next\n3. no") == ["1. one", "2. two"]


def test_limits_neutral_and_example():
    L = tc.limits(pack())
    assert L["max_words"] >= 1 and L["accent"] is not None and L["avoid"] == []
    S = tc.limits(pack(APP / "examples" / "striq"))
    assert S["max_words"] == 3 and S["avoid"]


def test_colour_value():
    p = pack()
    assert tc.colour_value("#0B0E14", p) == (11, 14, 20)
    assert tc.colour_value("accent", p) == tc.hex_rgb(p.value("brand.colors.accent"))
    assert tc.colour_value(None, p) is None
