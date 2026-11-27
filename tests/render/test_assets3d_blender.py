"""The CC0 asset path in real Blender on the CPU: the plate bootstrap gives a plate `import crewcut_assets`, which
fetches one Poly Haven HDRI and one ambientCG material (1k) and lights a tiny Cycles frame with them. Runs only with
CREWCUT_ASSET_RENDER=1 and Blender (the CI job `blender-assets`); it downloads about 7 MB from Poly Haven and
ambientCG. CREWCUT_ASSET_OUT keeps the frame."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest
from PIL import Image, ImageStat

from crewcut.render import assets3d, media, plate_quality, plates

HERE = Path(__file__).resolve().parent
BLENDER = os.environ.get("CREWCUT_BLENDER") or shutil.which("blender") or ""   # read before the fixtures clear it
pytestmark = pytest.mark.skipif(
    os.environ.get("CREWCUT_ASSET_RENDER") != "1" or not (BLENDER and Path(BLENDER).exists() or shutil.which(BLENDER)),
    reason="needs Blender, the network and CREWCUT_ASSET_RENDER=1 (CI job blender-assets)")


def test_hdri_and_material_light_a_tiny_cycles_frame(tmp_path, monkeypatch):
    monkeypatch.setenv("CREWCUT_ASSET_CACHE", str(tmp_path / "cache"))
    out = tmp_path / "plate"
    profile = {"version": 1, "size": [320, 180], "samples": 16}
    cmd = plates.blender_cmd(BLENDER, str(HERE / "data" / "hdri_plate.py"), str(out), "1-1",
                             {"hdri": "studio_small_09", "material": "Paper005", "res": "1k"}, quality=profile,
                             gpu=False, lib=str(assets3d.LIB_DIR), cache=str(tmp_path / "cache"))
    rc, text = media.run(cmd, timeout=900)
    print(text[-3000:])
    assert rc == 0, text[-2000:]
    ok, why = plate_quality.verify(out, 1, profile, probe=False, gpu=False)
    assert ok, why
    with Image.open(out / "0001.png") as im:
        st = ImageStat.Stat(im.convert("RGB"))
    assert 30 < sum(st.mean) / 3 < 245, st.mean                   # lit, not black, not blown out
    assert max(st.stddev) > 8, st.stddev                          # a picture, not one flat colour
    cached = {r["spec"] for r in assets3d.cached()}
    assert {"polyhaven:hdri/studio_small_09", "ambientcg:Paper005"} <= cached
    keep = os.environ.get("CREWCUT_ASSET_OUT")
    if keep:
        Path(keep).mkdir(parents=True, exist_ok=True)
        shutil.copy2(out / "0001.png", Path(keep) / "hdri-plate.png")
