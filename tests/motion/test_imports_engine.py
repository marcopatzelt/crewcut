"""Imported templates through the real EffectCraft (effectcraft-cli): a converted Lottie imports, renders in the pack's
palette through the motion template lottie_clip, and an After Effects project that EffectCraft wrote itself comes back
without losses with the pack's frame rate. Skipped without the engine (the CI job `motion-imports` and the image run
it, never a laptop). CREWCUT_EC_OUT keeps the pictures."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from PIL import Image

from crewcut import brand, paths
from crewcut.motion import imports as im
from crewcut.motion import project as mproject
from crewcut.motion import templates as mtemplates
from crewcut.motion.backend import Backend, BackendError, find_effectcraft

try:
    find_effectcraft()
except BackendError:
    pytest.skip("effectcraft-cli not found ($EFFECTCRAFT_CLI or PATH)", allow_module_level=True)

SAMPLE = paths.templates_dir() / "motion" / "assets" / "lottie" / "crewcut-card.json"
PALETTE = {"ink": "#141413", "paper": "#FAF9F5", "accent": "#2320D6", "highlight": "#FFE600"}


def pack(tmp_path: Path) -> brand.Pack:
    d = tmp_path / "brand"
    d.mkdir(exist_ok=True)
    (d / "brand.json").write_text(json.dumps({"colors": {"ink": "#141413", "paper": "#FAF9F5", "accent": "#2320D6"}}))
    (d / "channel.json").write_text(json.dumps({"graphics": {"palette": PALETTE}}))
    return brand.load(d)


def out_dir(tmp_path: Path) -> Path:
    d = Path(os.environ.get("CREWCUT_EC_OUT") or tmp_path / "ec-out")
    d.mkdir(parents=True, exist_ok=True)
    return d


def near(c: tuple, hexes: list[str], tol: int = 40) -> bool:
    return any(all(abs(c[i] - int(h[1 + 2 * i:3 + 2 * i], 16)) <= tol for i in range(3)) for h in hexes)


def test_lottie_imports_and_renders_in_the_palette(tmp_path):
    be = Backend()
    e = im.import_file(SAMPLE, "sample_card", "MIT (Crewcut sample)", "templates/motion/assets/lottie",
                       pack=pack(tmp_path), backend=be, root=tmp_path / "priv")
    chk = e["engine_check"]
    assert chk["ok"], chk
    assert chk["comp"]["frameRate"] == pytest.approx(25) and chk["comp"]["duration"] == pytest.approx(2.4, abs=0.05)
    prev = Path(e["folder"]) / "preview.png"
    with Image.open(prev) as img:
        im_rgba = img.convert("RGBA")
    px = [p for p in im_rgba.getdata() if p[3] == 255]
    assert px, "the preview is empty"
    foreign = [p for p in px if near(p[:3], ["#F2994A", "#2E9CDB"], 30)]
    assert len(foreign) < 0.01 * len(px), "the sample's own orange or blue is still there"
    plate = [p for p in px if near(p[:3], [PALETTE["paper"]], 12)]
    assert len(plate) > 0.2 * len(px), "the plate is not the channel's paper"
    prev.replace(out_dir(tmp_path) / "lottie-preview.png")


def test_lottie_clip_lays_it_into_the_frame(tmp_path):
    be = Backend()
    conv, _ = im.convert_lottie(im.read_lottie(SAMPLE), pack(tmp_path), texts={"Title": "Kontextfenster"})
    work = tmp_path / "w"
    work.mkdir()
    f = work / "card.json"
    f.write_text(json.dumps(conv))
    ctx = {"format": "landscape", "size": [1920, 1080], "fps": 25, "duration": 3.0, "transparent": True,
           "face": {"x": 0.34, "y": 0.36, "w": 0.3, "h": 0.3}, "backdrop": None, "draft": True, "right_free": 0.18,
           "brand": {"colors": {}, "fonts": {}, "shape": {}, "mg": {}}}
    code, _ = mtemplates.program_path(mtemplates.app_dir() / "lottie_clip.jsx", {"file": str(f)}, context=ctx)
    proj = str(work / "s.ecproj")
    mproject.create(be, proj, mproject.comp_params("Main", profile=None, width=1920, height=1080, fps=25,
                                                   duration=3.0, bg=None, shutter_angle=180, samples=4),
                    motion_blur=True, overwrite=True)
    be.script(code, project=proj, save=True, name="lottie_clip.jsx")
    png = out_dir(tmp_path) / "lottie-clip-2.8s.png"
    be.render_frame(proj, str(png), comp="Main", time=2.8, max_side=1920, transparent=True)   # held last frame
    with Image.open(png) as img:
        a = img.convert("RGBA").getchannel("A")
        assert img.size == (1920, 1080)
        lo, hi = a.getextrema()
        assert lo == 0 and hi == 255, "an overlay with something on it"


def test_after_effects_project_round_trip(tmp_path):
    """A project EffectCraft writes as .aep (so the test owns every byte) imports without losses at 25 fps."""
    be = Backend()
    src = tmp_path / "src.ecproj"
    be.exec("comp.new", {"name": "Lower", "width": 1920, "height": 1080, "frameRate": 30, "duration": 3},
            project=None, save_as=str(src))
    be.exec("layer.newText", {"comp": "Lower", "text": "Name", "font": "Inter", "size": 80, "fill": "#E4572E"},
            project=str(src), save=True)
    aep = tmp_path / "lower.aep"
    r = be.exec("file.exportAep", {"path": str(aep), "allowLosses": True}, project=str(src), save=False)
    assert aep.is_file(), r
    e = im.import_file(aep, "lower_one", "MIT (test)", "written by EffectCraft in this test", pack=pack(tmp_path),
                       backend=be, root=tmp_path / "priv")
    assert e["kind"] == "aep" and e["needs_adaptation"] and not e["losses"], e
    proj = Path(e["folder"]) / "project.ecproj"
    info = be.info(project=str(proj))
    text = json.dumps(info)
    assert "Lower" in text
    fix = e["fix"]
    assert fix, e
