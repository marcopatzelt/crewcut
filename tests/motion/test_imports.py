"""Imported templates: the Lottie converter (palette, fonts, frame rate, texts), the private folder, the plan entry,
the After Effects path with a fake engine, and the guard that keeps marketplace files out of the repository."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from crewcut import brand, paths
from crewcut.motion import imports as im
from crewcut.motion import studio_style

SAMPLE = paths.templates_dir() / "motion" / "assets" / "lottie" / "crewcut-card.json"
ROOT = Path(__file__).resolve().parents[2]


def pack(tmp_path: Path) -> brand.Pack:
    d = tmp_path / "brand"
    d.mkdir(exist_ok=True)
    (d / "brand.json").write_text(json.dumps({
        "colors": {"ink": "#141413", "paper": "#FAF9F5", "accent": "#2320D6"},
        "fonts": {"display": {"family": "Manrope", "weight": 800}, "body": {"family": "Manrope", "weight": 500}}}))
    (d / "channel.json").write_text(json.dumps({"graphics": {"palette": {"highlight": "#FFE600"}}}))
    return brand.load(d)


def test_palette_roles_and_source(tmp_path):
    p = pack(tmp_path)
    assert studio_style.palette(p) == {"ink": "#141413", "paper": "#FAF9F5", "accent": "#2320D6",
                                       "highlight": "#FFE600"}
    assert studio_style.source(p) == "channel graphics.palette"
    neutral = brand.load(paths.neutral_pack_dir())
    assert studio_style.palette(neutral)["highlight"] == studio_style.palette(neutral)["accent"]


def test_sample_converts_to_the_pack(tmp_path):
    doc = im.read_lottie(SAMPLE)
    out, rep = im.convert_lottie(doc, pack(tmp_path))
    assert out["fr"] == 25 and rep["fps"] == {"from": 30.0, "to": 25}
    assert out["op"] == pytest.approx(72 * 25 / 30) and rep["seconds"] == pytest.approx(2.4)
    # every colour is now one of the four
    left = set(im.colors(out))
    assert left <= {"#141413", "#FAF9F5", "#2320D6", "#FFE600"}, left
    roles = {v["role"] for v in rep["colors"].values()}
    assert {"accent", "ink", "paper"} <= roles
    # the colour that paints the most area (the orange plate) is the surface: light, so paper; the blue bar is an
    # edge, so the accent; the dark text stays readable as ink on the paper card
    assert rep["colors"]["#F2994A"]["role"] == "paper" and rep["colors"]["#2E9CDB"]["role"] == "accent"
    assert rep["colors"]["#1A1A1F"]["role"] == "ink"
    # fonts: bold styles to the display font, the rest to the body font; glyph outlines and web links dropped
    fl = out["fonts"]["list"]
    assert {f["fName"] for f in fl} == {"Manrope-ExtraBold", "Manrope-Medium"} and all("fPath" not in f for f in fl)
    title = next(x for x in out["layers"] if x["nm"] == "Title")
    assert title["t"]["d"]["k"][0]["s"]["f"] == "Manrope-ExtraBold"
    # keyframe times scaled (frames 8 and 20 at 30 fps are 6.67 and 16.67 at 25 fps)
    ks = title["ks"]["p"]["k"]
    assert [k["t"] for k in ks] == [pytest.approx(8 * 25 / 30, abs=1e-3), pytest.approx(20 * 25 / 30, abs=1e-3)]
    assert out["markers"][0]["tm"] == pytest.approx(10.0)
    assert doc["fr"] == 30, "the original stays as it was"


def test_texts_by_layer_name(tmp_path):
    out, rep = im.convert_lottie(im.read_lottie(SAMPLE), pack(tmp_path), texts={"Title": "Kontextfenster"})
    assert im.text_layers(out)["Title"] == "Kontextfenster" and rep["texts_set"] == ["Title"]
    _, rep2 = im.convert_lottie(im.read_lottie(SAMPLE), pack(tmp_path), texts={"Headline": "x"})
    assert rep2["texts_missing"] == ["Headline"] and "no text layer named Headline" in rep2["warnings"][-1]


def test_gradient_and_solid_colours(tmp_path):
    doc = {"v": "5.7", "fr": 50, "ip": 0, "op": 50, "w": 100, "h": 100, "layers": [
        {"ty": 1, "nm": "bg", "sc": "#ff0000", "sw": 100, "sh": 100, "ip": 0, "op": 50, "st": 0, "ks": {}},
        {"ty": 4, "nm": "g", "ip": 0, "op": 50, "st": 0, "ks": {}, "shapes": [
            {"ty": "rc", "s": {"a": 0, "k": [20, 20]}},
            {"ty": "gf", "g": {"p": 2, "k": {"a": 0, "k": [0, 0, 0.8, 0, 1, 0.98, 0.98, 0.98]}}}]}]}
    out, rep = im.convert_lottie(doc, pack(tmp_path))
    assert out["layers"][0]["sc"] == "#faf9f5"          # the red solid paints the most: the (light) surface, paper
    g = out["layers"][1]["shapes"][1]["g"]["k"]["k"]
    assert [round(x, 3) for x in g[1:4]] == [round(0x23 / 255, 3), round(0x20 / 255, 3), round(0xD6 / 255, 3)]
    assert [round(x, 3) for x in g[5:8]] == [round(0xFA / 255, 3), round(0xF9 / 255, 3), round(0xF5 / 255, 3)]
    assert rep["colors"]["#00CC00"]["role"] == "accent"


def test_text_on_a_dark_surface_takes_the_highlight(tmp_path):
    from crewcut.motion import studio_style
    assert studio_style.role_of("#0B1B3A", surface=True) == "ink"
    assert studio_style.role_of("#FF7A00", text=True, on_dark=True) == "highlight"
    assert studio_style.role_of("#FF7A00", text=True, on_dark=False) == "accent"
    assert studio_style.role_of("#EEEEEE") == "paper" and studio_style.role_of("#333333") == "ink"


def test_import_into_the_private_folder_and_use_it(tmp_path, studio):
    (studio / "episodes" / "007-x").mkdir(parents=True)
    e = im.import_file(SAMPLE, "sample_card", "MIT (Crewcut sample)", "templates/motion/assets/lottie",
                       pack=pack(tmp_path))
    folder = Path(e["folder"])
    assert folder == studio / "library" / "templates-private" / "sample_card"
    assert (folder / "original" / SAMPLE.name).read_bytes() == SAMPLE.read_bytes()
    meta = json.loads((folder / "template.json").read_text())
    assert meta["kind"] == "lottie" and meta["private"] is True and meta["licence"].startswith("MIT")
    assert [x["name"] for x in im.entries()] == ["sample_card"]
    r = im.use("sample_card", "007-x", "m4", {"Title": "Kontextfenster"})
    assert r["file"] == "motion/m4/sample_card.json" and r["plan_entry"]["scene"] == "lottie_clip"
    used = json.loads((studio / "episodes" / "007-x" / r["file"]).read_text())
    assert im.text_layers(used)["Title"] == "Kontextfenster"
    assert "Licence: MIT" in (studio / "episodes" / "007-x" / "motion" / "m4" / "SOURCE.md").read_text()
    with pytest.raises(im.ImportError_, match="already imported"):
        im.import_file(SAMPLE, "sample_card", "MIT", "x", pack=pack(tmp_path))


@pytest.mark.parametrize("name, licence, source, why", [
    ("Bad Name", "MIT", "x", "lower-case"),
    ("ok_name", "", "x", "licence"),
    ("ok_name", "all rights reserved", "x", "licence"),
    ("ok_name", "MIT", "", "where the file came from"),
])
def test_import_needs_name_licence_and_source(tmp_path, name, licence, source, why):
    with pytest.raises(im.ImportError_, match=why):
        im.import_file(SAMPLE, name, licence, source, pack=pack(tmp_path))


def test_no_linux_path_and_never_into_the_app(tmp_path, monkeypatch):
    f = tmp_path / "x.mogrt"
    f.write_bytes(b"zip")
    with pytest.raises(im.ImportError_, match="Windows or macOS"):
        im.import_file(f, "x_y", "Mixkit Free License", "https://example.org", pack=pack(tmp_path))
    with pytest.raises(im.ImportError_, match="inside the app folder"):
        im.import_file(SAMPLE, "inside", "MIT", "x", pack=pack(tmp_path), root=paths.app_root() / "tmp-private")
    assert not (paths.app_root() / "tmp-private").exists()


class FakeEngine:
    def __init__(self, losses: dict | None = None):
        self.calls = []
        self.losses = losses or {}

    def exec(self, command, params=None, project=None, save=True, save_as=None):
        self.calls.append((command, params, save_as))
        if params.get("dryRun"):
            return {"report": {"imported": {"comps": 1}, "losses": self.losses}}
        if save_as:
            Path(save_as).write_text("{}")
        return {"folder": 1, "comps": [2], "items": [3], "report": {}}

    def script(self, code, project=None, save=True, name=""):
        self.calls.append(("script", code, project))
        return {"comps": 1, "texts": 2}


def test_after_effects_needs_a_lossless_import(tmp_path):
    aep = tmp_path / "lower-third.aep"
    aep.write_bytes(b"RIFX")
    eng = FakeEngine({"effects": {"count": 2, "details": ["Element 3D (third-party)"]}})
    with pytest.raises(im.ImportError_, match="effects: 2"):
        im.import_file(aep, "lt_one", "Mixkit Free License", "https://mixkit.co/x", backend=eng, pack=pack(tmp_path),
                       root=tmp_path / "priv")
    eng = FakeEngine()
    e = im.import_file(aep, "lt_two", "Mixkit Free License", "https://mixkit.co/x", backend=eng, pack=pack(tmp_path),
                       root=tmp_path / "priv")
    assert e["kind"] == "aep" and e["needs_adaptation"] and (Path(e["folder"]) / "project.ecproj").is_file()
    code = next(c[1] for c in eng.calls if c[0] == "script")
    assert "frameRate = 25" in code and '"Manrope"' in code
    monkeypatch_dir = tmp_path / "priv"
    assert (monkeypatch_dir / "lt_two" / "original" / "lower-third.aep").is_file()


def test_the_repository_holds_no_marketplace_templates(tmp_path):
    from importlib import util
    spec = util.spec_from_file_location("guard", ROOT / "tools" / "ci" / "no_private_templates.py")
    guard = util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    assert guard.check(ROOT) == []
    # a copy with a template file, an unattributed Lottie and a private folder fails on all three
    bad = tmp_path / "repo"
    (bad / "templates-private").mkdir(parents=True)
    (bad / "templates-private" / "x.json").write_text("{}")
    (bad / "t.aep").write_bytes(b"RIFX")
    shutil.copy(SAMPLE, bad / "anim.json")
    found = guard.check(bad, every=True)
    assert len(found) == 3 and any("t.aep" in x for x in found) and any("anim.json" in x for x in found)
    (bad / "anim.json.attribution").write_text("license: MIT\nsource: https://lottiefiles.com/free/x\n")
    assert any("marketplace" in x for x in guard.check(bad, every=True))
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "ci" / "no_private_templates.py"), str(ROOT)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout
