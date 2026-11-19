"""brand.json motion_graphics: the palette derived from the accent in OKLCH, pastels, ground and ink, the checks; and
the edit-style.json motion block."""

from __future__ import annotations

import json

import pytest
from PIL import Image

from crewcut import brand
from crewcut.motion.palette import hue_report


def test_oklch_round_trip():
    for c in ("#E4572E", "#111111", "#FFFFFF", "#2F6FDE", "#3BA58B", "#F1F1EF"):
        assert brand.oklch_to_hex(*brand.hex_to_oklch(c)) == c
    L, C, H = brand.hex_to_oklch("#FFFFFF")
    assert L == pytest.approx(1.0, abs=1e-4) and C < 1e-4


def test_derived_palette_keeps_lightness_and_turns_the_hue():
    accent = "#E4572E"
    pal = brand.derive_palette(accent)
    assert len(pal) == 4 and pal[0] == accent
    L0, C0, H0 = brand.hex_to_oklch(accent)
    for c, turn in zip(pal[1:], (180, 40, -40), strict=True):
        L, C, H = brand.hex_to_oklch(c)
        assert L == pytest.approx(L0, abs=0.01)                   # equal lightness
        assert C <= C0 + 0.005                                    # chroma lowered only where sRGB needs it
        assert (H - H0 - turn + 180) % 360 - 180 == pytest.approx(0, abs=2)


def test_derived_palette_passes_the_hue_check(tmp_path):
    """A 4-colour test card in the derived palette of the neutral accent: no hue holds more than 30 %."""
    pal = brand.load().motion_graphics()["palette"]
    card = Image.new("RGB", (400, 400))
    for i, c in enumerate(pal):
        card.paste(Image.new("RGB", (200, 200), c), ((i % 2) * 200, (i // 2) * 200))
    p = tmp_path / "card.png"
    card.save(p)
    r = hue_report(str(p))
    assert r["ok"] and r["dominant_share"] <= 0.30 and len(r["hues"]) == 4


def test_neutral_tokens_resolve_motion_graphics():
    p = brand.load()
    assert p.value("brand.motion_graphics.palette", "unset") == "unset"      # null in the neutral pack: derived
    mg = p.render_tokens()["motion_graphics"]
    assert mg["palette"] == brand.derive_palette(p.value("brand.colors.accent"))
    assert len(mg["pastels"]) == 4 and all(brand.hex_to_oklch(c)[0] > 0.9 for c in mg["pastels"])
    assert mg["ground"] == "#F1F1EF" and mg["ink"] == "#111111" and mg["glass"] is True
    assert (mg["enter_s"], mg["exit_s"], mg["ease"], mg["drift_pct_per_s"]) == (0.4, 0.25, "expo", 2.0)
    assert mg["blur"] == {"shutter": 180, "samples": 16}
    assert mg["plate3d"] == {"material": "glossy", "bevel": 0.05, "extrude": 0.2}
    assert brand.check(p) == []


def _pack(studio, brand_json: dict, edit_style: dict | None = None):
    d = studio / "brand"
    d.mkdir(exist_ok=True)
    (d / "brand.json").write_text(json.dumps(brand_json))
    if edit_style is not None:
        (d / "edit-style.json").write_text(json.dumps(edit_style))
    return brand.load()


def test_a_user_accent_gets_its_own_palette(studio):
    p = _pack(studio, {"colors": {"accent": "#2F6FDE"}})
    assert p.motion_graphics()["palette"][0] == "#2F6FDE"
    assert p.motion_graphics()["palette"] == brand.derive_palette("#2F6FDE")


def test_explicit_values_and_a_dark_ground(studio):
    pal = ["#E4572E", "#2F6FDE", "#F2B84B", "#3BA58B"]
    p = _pack(studio, {"motion_graphics": {"palette": pal, "pastels": ["#F8D5C9", "#CDDBF7", "#FBEACB", "#CBE8DF"],
                                           "ground": "ink", "blur": {"samples": 8}}})
    mg = p.motion_graphics()
    assert mg["palette"] == pal and mg["pastels"][0] == "#F8D5C9"
    assert mg["ground"] == "#111111" and mg["ink"] == "#FFFFFF"           # text on a dark ground is paper
    assert mg["blur"] == {"shutter": 180, "samples": 8}
    p = _pack(studio, {"motion_graphics": {"pastels": False, "ground": "#202020", "ink": "#EEEEEE"}})
    mg = p.motion_graphics()
    assert mg["pastels"] == ["#202020"] * 4 and mg["ink"] == "#EEEEEE"


def test_check_reports_bad_motion_blocks(studio):
    p = _pack(studio, {"motion_graphics": {"palette": ["#E4572E"], "pastels": "yes", "ground": "sky", "glass": 1,
                                           "enter_s": 3, "ease": "bounce", "blur": {"shutter": 900, "samples": 0},
                                           "plate3d": []}},
              {"motion": {"insert_s": [6, 3], "overlay_min_s": 0, "prefer": "html", "min_gap_s": "six",
                          "heroes": "ranking", "template_max_s": {"ranking": "long"}, "big_moments": [5],
                          "shorts": {"total": [5, 3]}},
               "graphics_mix": {"motion": 1.4}})
    problems = "\n".join(brand.check(p))
    for needle in ("motion_graphics.palette", "motion_graphics.pastels", "motion_graphics.ground",
                   "motion_graphics.glass", "motion_graphics.enter_s", "motion_graphics.ease",
                   "motion_graphics.blur.shutter", "motion_graphics.blur.samples", "motion_graphics.plate3d",
                   "motion.insert_s", "motion.overlay_min_s", "motion.prefer", "motion.min_gap_s",
                   "motion.heroes", "motion.template_max_s", "motion.big_moments", "motion.shorts.total",
                   "graphics_mix"):
        assert needle in problems, needle


def test_edit_style_motion_block_and_mix():
    p = brand.load()
    assert p.value("edit_style.motion.prefer") == "motion"
    mix = p.value("edit_style.graphics_mix")
    assert mix["motion"] == 0.4 and sum(mix.values()) == pytest.approx(1.0)


def test_sparse_brand_accent_is_not_a_monochrome_scene(tmp_path):
    image = Image.new('RGB', (100, 100), '#EEEEEE')
    image.paste('#2320D6', (0, 0, 10, 100))
    file = tmp_path / 'accent.png'
    image.save(file)
    assert not hue_report(str(file))['ok']
    r = hue_report(str(file), accent_area_limit=0.2)
    assert r['ok'] and r['sparse_accent'] and r['coloured_share'] == 0.1
    image.paste('#2320D6', (0, 0, 60, 100))
    image.save(file)
    assert not hue_report(str(file), accent_area_limit=0.2)['ok']


def test_background_layout_validation():
    p = brand.load()
    p.brand['motion_graphics'] = {'background': {'mode': 'shapes', 'layouts': {
        'landscape': [{'kind': 'ring', 'x': 0.05, 'y': 0.95, 'size': 0.5, 'thickness': 0.1}]}}}
    assert not brand._check_motion_graphics(p)
    p.brand['motion_graphics']['background']['layouts']['landscape'][0]['size'] = -1
    assert any('background invalid size' in e for e in brand._check_motion_graphics(p))
