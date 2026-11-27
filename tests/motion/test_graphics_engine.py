"""The channel's graphic system in the motion templates, through the real EffectCraft: with a pack that declares it
(channel.json graphics.palette with a highlight, edit-style.json graphics with the halo and the Short safe zone),
keyword_pop and number_roll put the key word in the highlight on an ink halo, chapter_card stands on ink with the
number in the highlight, lower_third has the one card form, and a Short keeps 288 / 672 / 48 / 192 px free.
Skipped without the engine (the CI job `motion-imports` and the image run it). CREWCUT_EC_OUT keeps the frames."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from PIL import Image

from crewcut import brand
from crewcut.motion import project as mproject
from crewcut.motion import templates as mtemplates
from crewcut.motion.backend import Backend, BackendError, find_effectcraft
from crewcut.motion.jsx import parse_result
from crewcut.render.plan import brand_context, render_tokens

try:
    find_effectcraft()
except BackendError:
    pytest.skip("effectcraft-cli not found ($EFFECTCRAFT_CLI or PATH)", allow_module_level=True)

INK, PAPER, ACCENT, HIGHLIGHT = "#141413", "#FAF9F5", "#2320D6", "#FFE600"
SIZES = {"landscape": (1920, 1080), "portrait": (1080, 1920)}


def pack(tmp_path: Path) -> brand.Pack:
    d = tmp_path / "brand"
    d.mkdir(exist_ok=True)
    layout = [{"kind": "ring", "x": 0.03, "y": 0.95, "size": 0.52, "thickness": 0.12, "color": ACCENT},
              {"kind": "plus", "x": 0.08, "y": 0.14, "size": 0.13, "thickness": 0.04, "rotation": 18, "color": ACCENT}]
    (d / "brand.json").write_text(json.dumps({
        "colors": {"ink": INK, "paper": PAPER, "accent": ACCENT, "highlight": HIGHLIGHT},
        "motion_graphics": {"palette": [ACCENT, INK, ACCENT], "pastels": False, "ground": PAPER, "ink": INK,
                            "drift_pct_per_s": 0, "background": {"mode": "plain", "shapes_only_on": ["chapter_card"],
                                                                 "layouts": {"landscape": layout, "portrait": layout}}}}))
    (d / "channel.json").write_text(json.dumps({"graphics": {
        "palette": {"ink": INK, "paper": PAPER, "accent": ACCENT, "highlight": HIGHLIGHT},
        "motion": {"enter_s": 0.4, "exit_s": 0.28, "stagger_s": 0.08, "ease": [0.2, 0, 0, 1]}}}))
    (d / "edit-style.json").write_text(json.dumps({"min_text_px": 54, "graphics": {
        "safe_area": {"landscape": {"left": 96, "right": 96, "top": 54, "bottom": 54},
                      "portrait": {"top": 288, "bottom": 672, "left": 48, "right": 192}},
        "contrast": {"overlay_backing": {"kind": "ink halo", "alpha": 0.8, "grow_px": 27, "blur_px": 28,
                                         "side_scrim_alpha": 0.35}}}}))
    return brand.load(d)


def render(tmp_path: Path, name: str, params: dict, fmt: str = "landscape", transparent: bool = True,
           at: float = 2.0, seconds: float = 3.0) -> tuple[Image.Image, dict]:
    p = pack(tmp_path)
    tokens = render_tokens(p)
    assert tokens["graphics"]["highlight"] == HIGHLIGHT and tokens["graphics"]["ease"] == "emphasized"
    w, h = SIZES[fmt]
    ctx = {"format": fmt, "size": [w, h], "fps": 25, "duration": seconds, "transparent": transparent,
           "face": {"x": 0.36, "y": 0.34, "w": 0.26, "h": 0.28} if transparent else None, "backdrop": None,
           "draft": True, "right_free": 0.18, "brand": brand_context(tokens)}
    work = tmp_path / f"w-{name}-{fmt}"
    work.mkdir(parents=True, exist_ok=True)
    be = Backend()
    code, _ = mtemplates.program_path(mtemplates.app_dir() / f"{name}.jsx", params, context=ctx)
    proj = str(work / "s.ecproj")
    mproject.create(be, proj, mproject.comp_params("Main", profile=None, width=w, height=h, fps=25,
                                                   duration=seconds + 2 / 25, bg=None if transparent else PAPER,
                                                   shutter_angle=180, samples=4), motion_blur=True, overwrite=True)
    res = parse_result(be.script(code, project=proj, save=True, name=f"{name}.jsx"))
    out = Path(os.environ.get("CREWCUT_EC_OUT") or tmp_path / "ec-out")
    out.mkdir(parents=True, exist_ok=True)
    png = out / f"graphics-{name}-{fmt}.png"
    be.render_frame(proj, str(png), comp="Main", time=at, max_side=max(w, h), transparent=transparent)
    with Image.open(png) as im:
        return im.convert("RGBA"), res


def share(img: Image.Image, color: str, tol: int = 40, min_alpha: int = 200) -> float:
    rgb = tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))
    px = list(img.getdata())
    hit = sum(1 for p in px if p[3] >= min_alpha and all(abs(p[i] - rgb[i]) <= tol for i in range(3)))
    return hit / len(px)


def test_keyword_pop_highlight_on_a_halo(tmp_path):
    img, _ = render(tmp_path, "keyword_pop", {"words": ["Format", "zählt"], "accentWord": 0})
    assert share(img, HIGHLIGHT) > 0.002, "the accent word is not in the highlight"
    dark = sum(1 for p in img.getdata() if 0 < p[3] < 255 and max(p[:3]) < 60) / (img.width * img.height)
    assert dark > 0.01, "no soft ink halo around the words"


def test_number_roll_highlight_digits(tmp_path):
    img, _ = render(tmp_path, "number_roll", {"value": "13544", "unit": "", "label": "Titel geprüft"}, at=2.4)
    assert share(img, HIGHLIGHT) > 0.002


def test_chapter_card_on_ink_with_the_number_in_the_highlight(tmp_path):
    img, _ = render(tmp_path, "chapter_card", {"number": 3, "title": "Schnitt"}, transparent=False, at=1.6)
    assert share(img, INK, tol=12) > 0.5, "the chapter card stands on ink"
    assert share(img, HIGHLIGHT) > 0.01, "the number is in the highlight"
    assert share(img, ACCENT, tol=50) > 0.005, "the stored shapes are there"


def test_lower_third_card(tmp_path):
    img, res = render(tmp_path, "lower_third", {"variant": "card", "name": "Victor", "role": "Growth bei Composio"})
    assert share(img, PAPER, tol=12) > 0.01, "the paper plate"
    assert share(img, ACCENT, tol=50) > 0.0003, "the accent edge"
    box = res.get("box") if isinstance(res, dict) else None
    if box:
        assert box["x"] + box["w"] <= 1920 - 96 + 1 and box["y"] + box["h"] <= 1080 - 86 + 1


def test_short_keeps_the_channel_safe_zone(tmp_path):
    _, res = render(tmp_path, "lower_third", {"variant": "card", "name": "Victor", "role": "Growth"}, fmt="portrait")
    box = res.get("box") if isinstance(res, dict) else None
    assert box, res
    assert box["x"] >= 48 - 1 and box["x"] + box["w"] <= 1080 - 194 + 1 and box["y"] + box["h"] <= 1920 - 672 + 1
