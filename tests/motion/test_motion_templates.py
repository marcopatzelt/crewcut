"""Motion template headers (@formats, @kind, @sounds, @version) and where templates, the helper library and the
shared assets are found: --templates-dir, then the style pack, then the app."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from crewcut import paths
from crewcut.motion import templates as tp

LAUNCH = Path(__file__).resolve().parents[2] / "examples" / "launch-film" / "templates"

FULL = """/* @template demo
 * @description A demo
 *   on two lines.
 * @params {"comp": "Main", "t": 0.5,
 *   "colors": ["#ffffff"]}
 * @formats ["landscape", "portrait", "stage"]
 * @kind overlay
 * @sounds [{"at": "in", "sound": "whoosh"},
 *   {"at": 1.2, "sound": "tick"}]
 * @version 3
 * @end */
function demo(P) { return P.t; }
"""


def _tpl(folder: Path, description: str = "x", name: str = "demo") -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    p = folder / f"{name}.jsx"
    p.write_text(f'/* @template {name}\n * @description {description}\n * @params {{"t": 1}}\n * @end */\n'
                 f"function {name}(P) {{ return P.t; }}\n")
    return p


def test_header_fields():
    h = tp.parse_header(FULL)
    assert h["name"] == "demo" and h["description"] == "A demo on two lines."
    assert h["defaults"] == {"comp": "Main", "t": 0.5, "colors": ["#ffffff"]}
    assert h["formats"] == ["landscape", "portrait", "stage"]
    assert h["kind"] == "overlay"
    assert h["sounds"] == [{"at": "in", "sound": "whoosh"}, {"at": 1.2, "sound": "tick"}]
    assert h["version"] == 3


def test_optional_fields_absent_are_none():
    h = tp.parse_header(FULL.split(" * @formats")[0] + "\n * @end */\nfunction demo(P) {}\n")
    assert h["defaults"]["t"] == 0.5
    assert (h["formats"], h["kind"], h["sounds"], h["version"]) == (None, None, None, None)


@pytest.mark.parametrize("old,new", [
    ('["landscape", "portrait", "stage"]', '["landscape", "square"]'),
    ('@formats ["landscape", "portrait", "stage"]', "@formats landscape"),
    ("@kind overlay", "@kind half"),
    ('{"at": 1.2, "sound": "tick"}', '{"at": 1.2}'),
    ('{"at": "in", "sound": "whoosh"}', '"whoosh"'),
    ("@version 3", "@version 0"),
    ("@version 3", "@version two"),
])
def test_bad_optional_fields_are_refused(old, new):
    assert old in FULL
    with pytest.raises(tp.TemplateError):
        tp.parse_header(FULL.replace(old, new))


def test_unknown_params_still_refused(tmp_path):
    (tmp_path / "demo.jsx").write_text(FULL)
    with pytest.raises(tp.TemplateError, match="unknown parameters"):
        tp.program("demo", {"speed": 2}, str(tmp_path))
    code, merged = tp.program("demo", {"t": 2}, str(tmp_path))
    assert merged["t"] == 2 and '"colors": ["#ffffff"]' in code


def test_every_launch_film_template_parses():
    files = sorted(LAUNCH.glob("*.jsx"))
    assert len(files) == 13
    for f in files:
        h = tp.parse_header(f.read_text(encoding="utf-8"))
        assert h["name"] == f.stem and h["defaults"].get("comp") == "Main"


def test_app_lib_and_assets_ship():
    assert tp.lib_path() == paths.templates_dir() / "motion" / "lib" / "ec_lib.jsx"
    assert "var EC = " in tp.lib_source()
    for name in ("cursor.png", "cursor.svg", "cursor.svg.attribution"):
        assert (tp.assets_dir() / name).is_file()


def test_search_order_templates_dir_then_pack_then_app(tmp_path, studio, monkeypatch):
    app = tmp_path / "app-templates"
    _tpl(app / "motion", "from the app")
    _tpl(app / "motion", "only in the app", name="solo")
    (app / "motion" / "lib").mkdir()
    (app / "motion" / "lib" / "ec_lib.jsx").write_text("var EC = {app: true};")
    monkeypatch.setattr(paths, "templates_dir", lambda: app)
    assert tp.discover()["demo"]["description"] == "from the app"

    (studio / "brand").mkdir()
    (studio / "brand" / "brand.json").write_text("{}")
    _tpl(studio / "brand" / "templates" / "motion", "from the pack")
    assert tp.discover()["demo"]["description"] == "from the pack"
    assert tp.discover()["solo"]["description"] == "only in the app"
    assert "app: true" in tp.lib_source()

    extra = tmp_path / "episode-templates"
    _tpl(extra, "from --templates-dir")
    assert tp.discover(str(extra))["demo"]["description"] == "from --templates-dir"
    assert [Path(d) for d in tp.search_path(str(extra))] == [
        extra, studio / "brand" / "templates" / "motion", app / "motion"]

    (studio / "brand" / "templates" / "motion" / "lib").mkdir()
    (studio / "brand" / "templates" / "motion" / "lib" / "ec_lib.jsx").write_text("var EC = {pack: true};")
    assert "pack: true" in tp.lib_source()
    (extra / "lib").mkdir()
    (extra / "lib" / "ec_lib.jsx").write_text("var EC = {extra: true};")
    assert "pack: true" in tp.lib_source(), "a --templates-dir folder never replaces the shared library"


def test_ec_assets_points_at_the_app_assets(tmp_path):
    _tpl(tmp_path)
    code, _ = tp.program("demo", {}, str(tmp_path))
    assert f"var EC_ASSETS = {json.dumps(str(tp.assets_dir()))};" in code
    (tmp_path / "assets").mkdir()
    code, _ = tp.program("demo", {}, str(tmp_path))
    assert f"var EC_ASSETS = {json.dumps(str(tmp_path / 'assets'))};" in code


def test_run_hands_one_script_to_the_backend(tmp_path):
    _tpl(tmp_path)

    class FakeBackend:
        def __init__(self):
            self.calls = []

        def script(self, code, project=None, save=True, name="x.jsx"):
            self.calls.append((code, project, save, name))
            return {"result": json.dumps({"layers": [4]})}

    fb = FakeBackend()
    r = tp.run(fb, "/work/p.ecproj", "demo", {"t": 3}, str(tmp_path))
    assert r == {"template": "demo", "params": {"t": 3}, "result": {"layers": [4]}}
    code, project, save, name = fb.calls[0]
    assert project == "/work/p.ecproj" and save is True and name == "demo.jsx"
    assert code.rstrip().endswith('JSON.stringify(__R === undefined ? null : __R);') and 'demo({"t": 3})' in code
