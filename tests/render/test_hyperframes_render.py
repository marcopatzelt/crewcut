"""The real HyperFrames: every template renders a few frames per format through the pinned CLI and headless Chrome,
with the right size, count and alpha; one still each is kept for people to look at. Runs only where HyperFrames is
installed and CREWCUT_HF_RENDER=1 (the CI job `hyperframes` and the image), never on a developer's laptop.
CREWCUT_HF_OUT keeps the stills (default: the test's temporary folder)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from PIL import Image

from crewcut import brand
from crewcut.render import hyperframes as hf
from crewcut.render import media

pytestmark = pytest.mark.skipif(not (os.environ.get("CREWCUT_HF_RENDER") == "1" and hf.available()),
                                reason="needs HyperFrames (CI job hyperframes) and CREWCUT_HF_RENDER=1")

DATA = {
    "keyword": [("landscape", {"words": ["Dreißig", "Cent"], "sub": "pro Million Tokens"}),
                ("portrait", {"number": "13.544", "unit": "Zeilen"})],
    "card": [("landscape", {"title": "Kontextfenster", "line": "was das Modell auf einmal liest", "mark": True}),
             ("portrait", {"variant": "tag", "title": "Eigene Szene, Blender"})],
    "chapter": [("landscape", {"number": "2", "word": "Recherche"}), ("portrait", {"number": "3", "word": "Prüfung"})],
    "snippet": [("landscape", {}), ("portrait", {"mode": "code", "highlight": [2]})],
    "diagram": [("landscape", {}), ("portrait", {"nodes": ["Idee", "Skript", "Schnitt"], "highlight": 1})],
}


def out_dir(tmp_path: Path) -> Path:
    d = Path(os.environ.get("CREWCUT_HF_OUT") or tmp_path / "hf-out")
    d.mkdir(parents=True, exist_ok=True)
    return d


def striq_like(tmp_path: Path) -> brand.Pack:
    """A pack with the four-colour system (ink, paper, accent, highlight) and the Short safe zone in pixels."""
    d = tmp_path / "pack"
    d.mkdir()
    (d / "brand.json").write_text(json.dumps({"colors": {"ink": "#141413", "paper": "#FAF9F5", "accent": "#2320D6",
                                                         "highlight": "#FFE600"}}))
    (d / "channel.json").write_text(json.dumps({"graphics": {"palette": {
        "ink": "#141413", "paper": "#FAF9F5", "accent": "#2320D6", "highlight": "#FFE600"}}}))
    (d / "edit-style.json").write_text(json.dumps({"min_text_px": 54, "graphics": {
        "safe_area": {"portrait": {"top": 288, "bottom": 672, "left": 48, "right": 192}},
        "text": {"min_px_short": 48}}}))
    return brand.load(d)


def test_lint_every_template(tmp_path):
    pack = striq_like(tmp_path)
    for t in hf.listing(pack):
        folder = hf.find(t["name"], pack)
        m = hf.manifest(folder)
        ctx = hf.context(fmt="landscape", size=(1920, 1080), fps=25, frames=75, transparent=m["kind"] == "overlay",
                         face={"x": 0.34, "y": 0.36, "w": 0.3, "h": 0.3}, pack=pack)
        project = hf.build_project(folder, tmp_path / f"lint-{t['name']}", hf.merge_params(m, {}), ctx, pack)
        rc, text = hf.runner_with_env(media.run)(hf.lint_cmd(project), timeout=300)
        print(t["name"], rc, text[-1500:])
        assert rc == 0, f"hyperframes lint {t['name']}: {text[-1500:]}"


@pytest.mark.parametrize("name", sorted(DATA))
def test_a_few_frames_with_alpha_and_size(name, tmp_path):
    pack = striq_like(tmp_path)
    out = out_dir(tmp_path)
    m = hf.manifest(hf.find(name, pack))
    for fmt, data in DATA[name]:
        size = (1920, 1080) if fmt == "landscape" else (1080, 1920)
        r = hf.sample(name, tmp_path / f"{name}-{fmt}", fmt=fmt, seconds=0.32, data=dict(data), pack=pack,
                      log=print)
        assert r["ok"], f"{name} {fmt}: render failed"
        frames = sorted(Path(r["frames"]).glob("*.png"))
        assert len(frames) == 8, (name, fmt, len(frames))
        for f in (frames[0], frames[-1]):
            with Image.open(f) as im:          # an overlay carries alpha; a full frame may come as plain RGB
                assert im.size == size and (im.mode == "RGBA" or m["kind"] == "full"), (name, fmt, im.size, im.mode)
        rep = hf.alpha_report(frames[-1])
        if m["kind"] == "overlay":
            assert rep["transparent_share"] > 0.5, (name, fmt, rep)      # the speaker shows through
        else:
            assert rep["opaque_share"] > 0.99, (name, fmt, rep)          # a full frame covers everything
        # one still in the middle of the hold, for people to look at
        secs = (m.get("length_s") or [3.0])[-1]
        s = hf.sample(name, out / f"{name}-{fmt}", fmt=fmt, seconds=secs, data=dict(data), pack=pack,
                      at=min(secs - 0.6, 1.4), log=print)
        assert s["ok"], f"{name} {fmt}: still failed"
        with Image.open(s["still"]) as im:
            assert im.size == size
            ext = im.getchannel("A").getextrema() if "A" in im.getbands() else (255, 255)
            assert ext[1] == 255, f"{name} {fmt}: the still shows nothing"
        print(name, fmt, rep, s["still"])
