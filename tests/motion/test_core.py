"""Unit tests of crewcut.motion: synthetic data only, no EffectCraft binary needed."""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from crewcut.motion import backend as be
from crewcut.motion import effect as fx
from crewcut.motion import export as ex
from crewcut.motion import keyframe as kf
from crewcut.motion import layer as ly
from crewcut.motion import palette as pal
from crewcut.motion import project as pj
from crewcut.motion import templates as tp
from crewcut.motion import text as tx
from crewcut.motion.jsx import js, parse_result, wrap_program
from crewcut.motion.session import Session

LAUNCH = Path(__file__).resolve().parents[2] / "examples" / "launch-film" / "templates"


# ── keyframe ────────────────────────────────────────────────────────────

class TestKeyframe:
    def test_parse_value_vector(self):
        assert kf.parse_value("960,540") == [960, 540]

    def test_parse_value_float_vector(self):
        assert kf.parse_value("1.5,2") == [1.5, 2]

    def test_parse_value_json(self):
        assert kf.parse_value("[1,2,3]") == [1, 2, 3]
        assert kf.parse_value("50") == 50

    def test_parse_value_string(self):
        assert kf.parse_value("hello") == "hello"

    def test_parse_keys_sorted(self):
        assert kf.parse_keys(["1=10", "0=0"]) == [(0.0, 0), (1.0, 10)]

    def test_parse_keys_bad(self):
        with pytest.raises(kf.KeyError_):
            kf.parse_keys(["0:5"])

    def test_parse_keys_negative(self):
        with pytest.raises(kf.KeyError_):
            kf.parse_keys(["-1=5"])

    def test_parse_keys_duplicate(self):
        with pytest.raises(kf.KeyError_):
            kf.parse_keys(["1=5", "1.0=6"])

    def test_resolve_ease_presets(self):
        assert kf.resolve_ease("expo") == (3.0, 97.0)
        assert kf.resolve_ease("linear") is None
        assert kf.resolve_ease(None) == kf.EASES["smooth"]

    def test_resolve_ease_unknown(self):
        with pytest.raises(kf.KeyError_):
            kf.resolve_ease("bouncy")

    def test_resolve_ease_influence_range(self):
        assert kf.resolve_ease("linear", (10, 90)) == (10.0, 90.0)
        with pytest.raises(kf.KeyError_):
            kf.resolve_ease(None, (0, 150))

    def test_key_steps_count_and_shape(self):
        steps = kf.key_steps("Main", 2, "transform/opacity", [(0, 0), (1, 100), (2, 50)], (10, 90))
        assert [s["command"] for s in steps].count("prop.addKey") == 3
        eases = [s for s in steps if s["command"] == "keys.setEase"]
        assert len(eases) == 4
        assert eases[0]["params"]["side"] == "out" and eases[0]["params"]["influence"] == 10
        assert eases[1]["params"]["side"] == "in" and eases[1]["params"]["influence"] == 90
        assert all(s["params"]["timeBase"] == "comp" for s in steps if s["command"] == "prop.addKey")
        assert all("timeBase" not in s["params"] for s in eases)

    def test_key_steps_layer_start(self):
        steps = kf.key_steps("Main", 2, "transform/opacity", [(2, 0), (3, 100)], (10, 90), start=1.5)
        assert [s["params"]["time"] for s in steps if s["command"] == "keys.setEase"] == [0.5, 1.5]

    def test_key_program(self):
        body = kf.key_program("Main", "Box", "transform/position", [(0, [1, 2]), (1, [3, 4])], (3, 97), spring=True)
        assert 'EC.keys("Main", "Box", "transform/position", [[0, [1, 2]], [1, [3, 4]]], [3, 97])' in body
        assert "velocityAtTime" in body

    def test_key_steps_linear_no_ease(self):
        steps = kf.key_steps("Main", 2, "transform/opacity", [(0, 0), (1, 100)], None)
        assert all(s["command"] == "prop.addKey" for s in steps)

    def test_expression_presets(self):
        assert kf.expression("wiggle", freq=3, amp=5) == "wiggle(3, 5)"
        assert "loopOut('pingpong')" == kf.expression("loop", mode="pingpong")
        s = kf.expression("spring")
        assert "velocityAtTime" in s and "{" in s and "{{" not in s
        with pytest.raises(kf.KeyError_):
            kf.expression("nope")


# ── project ─────────────────────────────────────────────────────────────

class TestProject:
    def test_profile_defaults(self):
        p = pj.comp_params("Main")
        assert (p["width"], p["height"], p["frameRate"], p["duration"]) == (1920, 1080, 60, 10.0)

    def test_overrides(self):
        p = pj.comp_params("V", "vertical60", fps=30, duration=3, bg="#ffffff", renderer="advanced3D")
        assert (p["width"], p["height"], p["frameRate"]) == (1080, 1920, 30.0)
        assert p["background"] == "#ffffff" and p["renderer"] == "advanced3D"

    def test_unknown_profile(self):
        with pytest.raises(ValueError):
            pj.comp_params("X", "8k")

    def test_bad_duration(self):
        with pytest.raises(ValueError):
            pj.comp_params("X", duration=0)

    def test_bad_size(self):
        with pytest.raises(ValueError):
            pj.comp_params("X", width=0)

    def test_bad_renderer(self):
        with pytest.raises(ValueError):
            pj.comp_params("X", renderer="raytrace")

    def test_profiles_listed(self):
        assert "1080p60" in pj.list_profiles() and "vertical60" in pj.list_profiles()


# ── layer ───────────────────────────────────────────────────────────────

class TestLayer:
    def test_unknown_kind(self):
        with pytest.raises(ValueError):
            ly.options("sphere")

    def test_text_needs_text(self):
        with pytest.raises(ValueError):
            ly.options("text", name="x")

    def test_shape_kind(self):
        with pytest.raises(ValueError):
            ly.options("shape", kind="blob")

    def test_blend_mode(self):
        with pytest.raises(ValueError):
            ly.options("solid", blend="Glowy")
        assert ly.options("solid", blend="Screen")["blend"] == "Screen"

    def test_options_drop_none(self):
        assert ly.options("solid", color="#fff", w=None) == {"color": "#fff"}

    def test_add_program_footage(self):
        prog = ly.add_program("Main", "footage", {"path": "/a/b.png", "name": "Logo"})
        assert 'EC.footage("Main", "/a/b.png", {"name": "Logo"})' in prog

    def test_switch_and_timing(self):
        assert ly.switch_steps("Main", 1, "threeD", True)[0]["params"]["switch"] == "threeD"
        with pytest.raises(ValueError):
            ly.switch_steps("Main", 1, "laser", True)
        with pytest.raises(ValueError):
            ly.timing_steps("Main", 1, 2.0, 1.0)
        with pytest.raises(ValueError):
            ly.timing_steps("Main", 1, None, None)

    def test_null_and_precomp_programs(self):
        assert "EC.nul(" in ly.add_program("Main", "null", {"name": "N"})
        assert 'EC.precompLayer("Main", "Burst"' in ly.add_program("Main", "precomp", {"source": "Burst"})


# ── effects and text ────────────────────────────────────────────────────

class TestEffectText:
    def test_alias(self):
        assert fx.resolve("glow") == "Glow" and fx.resolve("particles3d") == "Particle Emitter 3D"

    def test_passthrough(self):
        assert fx.resolve("ec.stylize.glow") == "ec.stylize.glow"

    def test_apply_program(self):
        p = fx.apply_program("Main", "Logo", "shatter", {"physics/gravity": 0}, {"force1/force1Strength": [[0, 0], [1, 5]]})
        assert '"Shatter"' in p and '"physics/gravity": 0' in p

    def test_find(self):
        cat = {"effects": [{"name": "Glow", "id": "ec.stylize.glow", "category": "Stylize"}, {"name": "Echo", "id": "ec.time.echo", "category": "Time"}]}
        assert [e["name"] for e in fx.find(cat, "time")] == ["Echo"]

    def test_animator_program(self):
        p = tx.animator_program("Main", 3, ["opacity", "fillColor"], {"opacity": 0}, {"start": [[0, 0], [1, 100]]})
        assert '["opacity", "fillColor"]' in p and "selectors/#1/" in p

    def test_animator_bad_prop(self):
        with pytest.raises(ValueError):
            tx.animator_program("Main", 3, ["glitter"])
        with pytest.raises(ValueError):
            tx.animator_program("Main", 3, [])


# ── jsx ─────────────────────────────────────────────────────────────────

class TestJsx:
    def test_js_literal(self):
        assert js({"a": [1, 2.5], "b": "ü"}) == '{"a": [1, 2.5], "b": "ü"}'

    def test_js_rejects_nan(self):
        with pytest.raises(ValueError):
            js({"x": [math.nan]})

    def test_wrap_program(self):
        code = wrap_program("return 1;", "var EC={};")
        assert code.startswith("var EC={};") and "JSON.stringify(__R" in code and "beginUndoGroup" in code

    def test_parse_result(self):
        assert parse_result({"result": '{"layer": 3}'}) == {"layer": 3}
        assert parse_result({"result": "plain"}) == "plain"
        assert parse_result({"result": 5}) == 5


# ── templates ───────────────────────────────────────────────────────────

GOOD = """/* @template demo
 * @description A demo.
 * @params {"comp": "Main", "t": 0.5,
 *   "colors": ["#ffffff"]}
 * @end */
function demo(P) { return P.t; }
"""


class TestTemplates:
    def test_parse_header(self):
        h = tp.parse_header(GOOD)
        assert h["name"] == "demo" and h["defaults"]["t"] == 0.5 and h["description"] == "A demo."

    def test_missing_header(self):
        with pytest.raises(tp.TemplateError):
            tp.parse_header("function x(){}")

    def test_bad_params(self):
        with pytest.raises(tp.TemplateError):
            tp.parse_header(GOOD.replace('"t": 0.5', "t: 0.5"))

    def test_missing_function(self):
        with pytest.raises(tp.TemplateError):
            tp.parse_header(GOOD.replace("function demo", "function other"))

    def test_merge_strict(self):
        with pytest.raises(tp.TemplateError):
            tp.merge({"a": 1}, {"b": 2})
        assert tp.merge({"a": 1}, {"b": 2}, strict=False) == {"a": 1, "b": 2}
        d = {"a": [1]}
        m = tp.merge(d, {})
        m["a"].append(2)
        assert d == {"a": [1]}

    def test_override_dir_and_program(self, tmp_path):
        (tmp_path / "demo.jsx").write_text(GOOD)
        (tmp_path / "lib").mkdir()
        (tmp_path / "lib" / "ec_lib.jsx").write_text("var EC = {};")
        ts = tp.discover(str(tmp_path))
        assert ts["demo"]["path"] == str(tmp_path / "demo.jsx")
        code, merged = tp.program("demo", {"t": 2}, str(tmp_path))
        assert merged["t"] == 2 and 'demo({"comp": "Main", "t": 2' in code

    def test_shipped_templates_parse(self):
        ts = tp.discover(str(LAUNCH))
        for name in ("burst_rings", "logo_shatter", "cursor_flyin", "app_dock", "pixel_burst", "iris_reveal"):
            assert name in ts, f"template {name} missing"
            assert ts[name]["defaults"].get("comp")


# ── session ─────────────────────────────────────────────────────────────

class TestSession:
    def _proj(self, tmp_path, text="v0"):
        p = tmp_path / "p.ecproj"
        p.write_text(text)
        return p

    def test_undo_redo(self, tmp_path):
        p = self._proj(tmp_path)
        s = Session.load(None, str(p))
        s.snapshot("one")
        p.write_text("v1")
        s.snapshot("two")
        p.write_text("v2")
        s.undo()
        assert p.read_text() == "v1"
        s.undo()
        assert p.read_text() == "v0"
        s.redo()
        assert p.read_text() == "v1"
        s.redo()
        assert p.read_text() == "v2"

    def test_undo_empty(self, tmp_path):
        s = Session.load(None, str(self._proj(tmp_path)))
        with pytest.raises(RuntimeError):
            s.undo()

    def test_new_mutation_drops_redo(self, tmp_path):
        p = self._proj(tmp_path)
        s = Session.load(None, str(p))
        s.snapshot("one")
        p.write_text("v1")
        s.undo()
        s.snapshot("other")
        p.write_text("v3")
        with pytest.raises(RuntimeError):
            s.redo()

    def test_save_and_reload(self, tmp_path):
        p = self._proj(tmp_path)
        s = Session.load(None, str(p))
        s.use_comp("Main")
        s.record("x", {"a": 1})
        s.save()
        s2 = Session.load(None, str(p))
        assert s2.comp == "Main" and s2.data["history"][-1]["command"] == "x"

    def test_require(self, tmp_path):
        s = Session()
        with pytest.raises(RuntimeError):
            s.require_project()
        with pytest.raises(RuntimeError):
            s.require_comp(None)
        assert s.require_comp("A") == "A"


# ── export ──────────────────────────────────────────────────────────────

class TestExport:
    def test_chunks_cover_exactly(self):
        cs = ex.chunks(0, 10, 4, 60)
        assert cs[0] == (0, 4) and cs[-1] == (8, 10)
        frames = sum(round(b * 60) - round(a * 60) for a, b in cs)
        assert frames == 600
        assert all(abs(cs[i][1] - cs[i + 1][0]) < 1e-12 for i in range(len(cs) - 1))

    def test_chunks_frame_aligned(self):
        cs = ex.chunks(0.01, 1.0, 0.33, 60)
        assert all(abs(a * 60 - round(a * 60)) < 1e-9 for a, _ in cs)

    def test_chunks_bad(self):
        with pytest.raises(ValueError):
            ex.chunks(5, 5, 1, 60)
        with pytest.raises(ValueError):
            ex.chunks(0, 5, 0, 60)


# ── palette ─────────────────────────────────────────────────────────────

class TestPalette:
    def test_one_hue_fails(self, tmp_path):
        from PIL import Image
        f = tmp_path / "g.png"
        Image.new("RGB", (64, 64), (15, 110, 92)).save(f)
        r = pal.hue_report(str(f))
        assert not r["ok"] and r["dominant_share"] == 1.0

    def test_mixed_passes(self, tmp_path):
        from PIL import Image
        im = Image.new("RGB", (80, 20))
        cols = [(230, 60, 60), (60, 200, 90), (60, 90, 230), (240, 200, 40)]
        for i, c in enumerate(cols):
            for x in range(i * 20, i * 20 + 20):
                for y in range(20):
                    im.putpixel((x, y), c)
        f = tmp_path / "m.png"
        im.save(f)
        assert pal.hue_report(str(f))["ok"]

    def test_neutral_ok(self, tmp_path):
        from PIL import Image
        f = tmp_path / "n.png"
        Image.new("RGB", (32, 32), (240, 240, 240)).save(f)
        assert pal.hue_report(str(f))["ok"]


# ── backend helpers ─────────────────────────────────────────────────────

class TestBackendHelpers:
    def test_parse_json_with_logs(self):
        assert be._parse_json_out('warn: x\n{"layer": 2}\n') == {"layer": 2}

    def test_parse_json_plain(self):
        assert be._parse_json_out('[1,2]') == [1, 2]

    def test_missing_binary(self, monkeypatch):
        monkeypatch.setenv("EFFECTCRAFT_CLI", "/nonexistent/effectcraft-cli")
        monkeypatch.setattr(be.shutil, "which", lambda _n: None)
        with pytest.raises(be.BackendError) as e:
            be.find_effectcraft()
        assert "cargo build --release -p effectcraft-cli" in str(e.value)
