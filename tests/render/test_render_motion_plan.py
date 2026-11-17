"""Edit plans with kind "motion": templates (scene, pinned versions, episode comps), word anchors, cues in seconds,
the cache key, backdrop and layer, formats, length and density warnings, sound events and the context (CC_CTX)."""

from __future__ import annotations

import json

import pytest
from motion_helpers import install, template_src
from render_helpers import basic_plan

from crewcut import doctor
from crewcut.render.plan import Plan, PlanError, motion_context

README_KEYS = {"format", "size", "fps", "duration", "transparent", "face", "backdrop", "draft", "right_free", "layer",
               "plates", "brand"}


def roll(**over) -> dict:
    e = {"id": "m1", "kind": "motion", "scene": "number_roll", "start": {"word": "costs", "offset": -0.6}, "end": 5.0,
         "cues": {"landAt": {"word": "thirty"}}, "data": {"value": "30", "unit": "cents"}}
    e.update(over)
    return e


def pop(**over) -> dict:
    e = {"id": "k2", "kind": "motion", "scene": "keyword_pop", "start": 8.0, "end": 10.0, "data": {"words": ["Thirty"]}}
    e.update(over)
    return e


def make(episode, studio, *inserts, **plan_over) -> Plan:
    """The basic plan (2D counter s1 at 1-3 s, 2D keyword k1 at 4-6 s) plus these motion inserts."""
    install(studio)
    p = basic_plan(**plan_over)
    p["inserts"] += list(inserts)
    return Plan(episode(p))


def test_scene_word_start_cues_in_seconds_and_params(episode, studio):
    plan = make(episode, studio, roll(end={"word": "third", "offset": 0.5}))
    x = plan.by_id("m1")
    assert (x.start_s, x.end_s) == (0.4, 5.7)                  # costs at 1.0 - 0.6; third at 5.2 + 0.5 (after start)
    assert (x.start, x.end, x.frames, x.render_frames) == (10, 142, 132, 134)
    assert x.cues == {"landAt": 40} and x.data["landAt"] == 1.6     # thirty at 2.0, local to the insert
    assert x.params == {"comp": "Main", "value": "30", "unit": "cents", "label": "", "landAt": 1.6}
    assert x.format == "landscape" and x.size == (1920, 1080) and not x.transparent      # @kind full
    assert x.template.name == "number_roll.jsx" and x.version is None and x.source is None
    assert [p.name for p in x.shared] == ["ec_lib.jsx", "cc_frame.jsx"]
    assert x.out_dir.name == f"m1-{x.hash}" and x.clip.suffix == ".mp4"
    row = plan.summary()["inserts"][2]
    assert row["kind"] == "motion" and row["format"] == "landscape" and row["hash"] == x.hash


def test_start_anchor_by_time_and_after(episode, studio):
    plan = make(episode, studio, roll(start={"word": "thirty", "after": 5.0, "offset": -0.2}, end={"time": 9.5}))
    x = plan.by_id("m1")
    assert (x.start_s, x.end_s) == (7.8, 9.5)                  # the second "Thirty," at 8.0
    with pytest.raises(PlanError, match="'nowhere' not found"):
        make(episode, studio, roll(start={"word": "nowhere"}))


def test_cues_and_data_are_checked_against_the_header(episode, studio):
    with pytest.raises(PlanError, match=r"cue nope is not a parameter of number_roll \(parameters: comp, label"):
        make(episode, studio, roll(cues={"nope": {"word": "thirty"}}))
    with pytest.raises(PlanError, match="value is set in data and in cues"):     # the plan's sketch in 3.2 did that
        make(episode, studio, roll(cues={"value": {"word": "thirty"}}))
    with pytest.raises(PlanError, match="landAt is set in data and in cues"):
        make(episode, studio, roll(data={"landAt": 2.0}))
    with pytest.raises(PlanError, match=r"unknown parameters \['colour'\]"):
        make(episode, studio, roll(data={"colour": "red"}))


def test_exactly_one_of_scene_or_source(episode, studio):
    with pytest.raises(PlanError, match="exactly one of scene"):
        make(episode, studio, roll(source="motion/m1/comp.jsx"))
    e = roll()
    del e["scene"]
    with pytest.raises(PlanError, match="exactly one of scene"):
        make(episode, studio, e)
    with pytest.raises(PlanError, match="no motion template 'nope'"):
        make(episode, studio, roll(scene="nope"))


def test_episode_comp_changes_only_its_own_hash(episode, studio):
    comp = episode.dir / "motion" / "m3" / "comp.jsx"
    comp.parent.mkdir(parents=True)
    comp.write_text(template_src("gpu_handoff", "full", ["landscape"], 1, None, {"comp": "Main", "jobs": 1}))
    inserts = [roll(), {"id": "m3", "kind": "motion", "source": "motion/m3/comp.jsx", "start": 6.0, "end": 11.0,
                        "cues": {"jobs": 9.0}}]
    a = make(episode, studio, *inserts)
    x = a.by_id("m3")
    assert x.source == comp and x.scene == "gpu_handoff" and x.data == {"jobs": 0.36}   # a number is a frame: 9 / 25
    comp.write_text(comp.read_text().replace("return {ok: true};", "return {ok: 2};"))
    b = Plan(a.path)
    assert b.by_id("m3").hash != x.hash and b.by_id("m1").hash == a.by_id("m1").hash
    with pytest.raises(PlanError, match="inside the episode folder"):
        make(episode, studio, {**inserts[1], "source": "../../brand/templates/motion/ranking.jsx"})
    with pytest.raises(PlanError, match="relative to the episode folder"):
        make(episode, studio, {**inserts[1], "source": str(comp)})


def test_a_lib_file_changes_every_motion_hash(episode, studio):
    a = make(episode, studio, roll(), pop())
    lib = studio / "brand" / "templates" / "motion" / "lib"
    lib.mkdir()
    from crewcut.motion import templates as tp
    (lib / "cc_frame.jsx").write_text((tp.app_dir() / "lib" / "cc_frame.jsx").read_text() + "\n// changed\n")
    b = Plan(a.path)
    assert all(b.by_id(i).hash != a.by_id(i).hash for i in ("m1", "k2"))
    assert b.by_id("s1").hash == a.by_id("s1").hash                    # 2D inserts do not care


def test_pinned_versions(episode, studio):
    d = install(studio)
    (d / "number_roll.v1.jsx").write_text(template_src("number_roll", "full", ["landscape"], 1, None,
                                                       {"comp": "Main", "value": "0", "landAt": 1.0}))
    a = make(episode, studio, roll(scene="number_roll@2"))
    assert a.by_id("m1").template.name == "number_roll.jsx" and a.by_id("m1").version == 2     # current is @2
    b = make(episode, studio, roll(scene="number_roll@1", data={"value": "30"}))
    assert b.by_id("m1").template.name == "number_roll.v1.jsx" and b.by_id("m1").hash != a.by_id("m1").hash
    with pytest.raises(PlanError, match="no motion template 'number_roll@3'"):
        make(episode, studio, roll(scene="number_roll@3"))
    with pytest.raises(PlanError, match="not a template name"):
        make(episode, studio, roll(scene="number-roll@x"))


def test_hash_covers_tokens_engine_pin_and_fonts(episode, studio, monkeypatch):
    a = make(episode, studio, roll())
    h0, h2d = a.by_id("m1").hash, a.by_id("s1").hash
    (studio / "brand" / "brand.json").write_text(json.dumps({"motion_graphics": {"enter_s": 0.45}}))
    b = Plan(a.path)
    assert b.by_id("m1").hash != h0 and b.by_id("s1").hash == h2d       # motion_graphics: motion only
    (studio / "brand" / "brand.json").write_text("{}")
    with monkeypatch.context() as m:
        m.setattr(doctor, "read_pin", lambda: {"commit": "f" * 40, "patches": 2})
        assert Plan(a.path).by_id("m1").hash != h0
    assert Plan(a.path).by_id("m1").hash == h0
    font = studio / "brand" / "fonts" / "Brand-Bold.ttf"
    font.parent.mkdir()
    font.write_bytes(b"font-v1")
    (studio / "brand" / "brand.json").write_text(json.dumps(
        {"fonts": {"display": {"family": "Brand", "weight": 700, "files": ["fonts/Brand-Bold.ttf"]}}}))
    c = Plan(a.path).by_id("m1").hash
    font.write_bytes(b"font-v2, a longer file")
    assert Plan(a.path).by_id("m1").hash != c
    assert Plan(a.path).by_id("m1").hash == Plan(a.path).by_id("m1").hash      # stable


def test_draft_has_its_own_folder(episode, studio):
    plan = make(episode, studio, roll())
    x = plan.by_id("m1")
    d = plan.motion_draft(x)
    assert d.hash != x.hash and d.out_dir != x.out_dir and plan.by_id("m1").hash == x.hash


def test_backdrop_and_layer(episode, studio):
    (episode.dir / "work" / "speaker-v001.mp4").write_bytes(b"speaker")
    over = {"base": "work/speaker-v001.mp4", "speaker": [{"at": 6.0, "zoom": 1.1}]}
    plan = make(episode, studio, roll(scene="prompt_bar", data={"text": "hi"}, cues={}, start=6.0, end=11.0,
                                      backdrop="speaker"), pop(start=12.0, end=14.0, layer="behind"), **over)
    x, k = plan.by_id("m1"), plan.by_id("k2")
    assert x.backdrop == "speaker" and k.layer == "behind" and k.transparent and k.clip.suffix == ".mov"
    assert plan.backdrop_key(x.start, x.render_frames).endswith(f":150:{x.render_frames}:1.1:(0.5, 0.38)")
    (episode.dir / "work" / "speaker-v001.mp4").write_bytes(b"another speaker cut")
    assert Plan(plan.path).by_id("m1").hash != x.hash                    # the backdrop by what it is made of
    with pytest.raises(PlanError, match="backdrop must be null or"):
        make(episode, studio, roll(backdrop="screen"), **over)
    with pytest.raises(PlanError, match="for full-frame inserts"):
        make(episode, studio, roll(backdrop="speaker", transparent=True), **over)
    with pytest.raises(PlanError, match="for overlays"):
        make(episode, studio, roll(layer="behind"), **over)
    with pytest.raises(PlanError, match="layer must be null or"):
        make(episode, studio, pop(layer="front"), **over)


def test_formats_and_the_stage(episode, studio):
    portrait = {"format": "portrait", "layout": "proof-top"}
    plan = make(episode, studio, roll(), pop(), **portrait)
    x, k = plan.by_id("m1"), plan.by_id("k2")
    assert (x.format, x.size, x.place) == ("stage", (1080, 960), "top")
    assert (k.format, k.size, k.place) == ("portrait", (1080, 1920), "full")
    assert motion_context(plan, x)["size"] == [1080, 960]
    full = make(episode, studio, roll(place="full"), **portrait).by_id("m1")
    assert (full.format, full.size) == ("portrait", (1080, 1920))
    with pytest.raises(PlanError, match="template ranking has no portrait format"):
        make(episode, studio, roll(scene="ranking", cues={}, data={}), format="portrait")


def test_context_matches_the_template_contract(episode, studio):
    plan = make(episode, studio, roll(), pop(), face=[0.42, 0.36, 0.2, 0.3])
    c = motion_context(plan, plan.by_id("m1"))
    assert set(c) == README_KEYS
    assert c["face"] is None and c["backdrop"] is None and c["duration"] == 4.6 and c["fps"] == 25
    assert set(c["brand"]) == {"colors", "fonts", "shape", "mg"}
    assert c["brand"]["fonts"]["display"] == {"family": "Inter", "weight": 800}
    assert c["brand"]["mg"]["palette"][0] == c["brand"]["colors"]["accent"]
    k = motion_context(plan, plan.by_id("k2"), draft=True, backdrop="/x/backdrop.mov")
    assert k["face"] == {"x": 0.42, "y": 0.36, "w": 0.2, "h": 0.3} and k["transparent"] and k["draft"]
    assert k["backdrop"] == "/x/backdrop.mov" and k["right_free"] == 0.18 and k["layer"] is None and c["layer"] is None
    dict_face = make(episode, studio, pop(), face={"x": 0.6, "y": 0.4})
    assert motion_context(dict_face, dict_face.by_id("k2"))["face"] == {"x": 0.6, "y": 0.4, "w": 0.32, "h": 0.28}
    assert dict_face.face == (0.6, 0.4)


def test_lengths_kinds_and_density_warnings(episode, studio):
    """The density rules come from crewcut.motion.density; the plan hands it what parsing decided."""
    plan = make(episode, studio,
                roll(start=0.4, end=2.4),                                           # full frame 2 s: too short
                pop(id="k3", start=2.4, end=3.4),                                   # overlay 1 s; 2.0 s after m1
                pop(start=8.0, end=10.0, transparent=False),                        # an overlay template as full frame
                {"id": "r1", "kind": "motion", "scene": "ranking", "start": 10.5, "end": 16.5},
                {"id": "r2", "kind": "motion", "scene": "ranking", "start": 17.0, "end": 23.0})
    w = "\n".join(plan.warnings)
    assert "m1 (number_roll) runs 2.0 s; full frame needs 3 to 6 s" in w
    assert "k3 (keyword_pop) runs 1.0 s; an overlay needs at least 1.5 s" in w        # overlay by its @kind
    assert "k2: keyword_pop is an overlay template but the insert is full frame" in w
    assert "r1 (ranking) runs" not in w                                     # ranking may take up to 8 s
    assert "m1 and k3 start 2.0 s apart (never 2 inside 6 s)" in w
    assert "2 motion moments in the sentence at 0:00.4: m1, k3" in w
    assert "Hero templates {'ranking': 2}" in w
    assert "m1 starts at 0.4 s; the first 3 s show the speaker alone" in w
    assert "5 motion moments in 0.2 min" in w


def test_shorts_limits_and_keywords(episode, studio):
    (studio / "brand").mkdir(parents=True, exist_ok=True)
    (studio / "brand" / "edit-style.json").write_text(json.dumps({"keywords_max": 1}))
    plan = make(episode, studio, roll(start=3.5, end=7.0), roll(id="m2", start=7.5, end=11.0, cues={}),
                roll(id="m3", start=11.5, end=15.0, cues={}), format="portrait", base={"color": "soft", "seconds": 20})
    w = "\n".join(plan.warnings)
    assert "3 full-frame motion inserts (at most 2 in a Short)" in w
    assert "apart" not in w                                                # Shorts have no 6 s gap rule
    plan = make(episode, studio, pop(start=8.0, end=10.0))
    assert "2 keywords (keyword + keyword_pop) over the speaker (at most 1)" in plan.warnings


def test_one_statement_one_form(episode, studio):
    plan = make(episode, studio, roll(start=6.0, end=10.0, cues={}))
    assert any("m1: the number 30 is also a 2D counter" in w for w in plan.warnings)


def test_plates_are_validated_data(episode, studio):
    good = [{"id": "gpu", "script": "motion/m3/plates/gpu3d.py", "args": {"t0": 0.0}, "frames": 120}]
    x = make(episode, studio, roll(plates=good)).by_id("m1")
    assert x.plates == tuple(good)
    for bad in ([{"id": "gpu", "script": "gpu3d.py", "frames": 0}], {"id": "x"},
                [{"id": "a b", "script": "p.py", "frames": 3}], [good[0], good[0]]):
        with pytest.raises(PlanError, match="plate"):
            make(episode, studio, roll(plates=bad))


def test_sound_events_from_template_sounds(episode, studio):
    plan = make(episode, studio,
                roll(sound=True),                                           # hit at landAt: 0.4 + 1.6 = 2.0 s
                pop(id="k3", start=6.0, end=8.0, sound=True),               # pop at "in" -> hits at 6.0
                pop(start=8.5, end=10.5, sound=True),                       # keyword_pop right after one: silent
                {"id": "p1", "kind": "motion", "scene": "prompt_bar", "start": 11.0, "end": 16.0, "sound": True},
                {"id": "l1", "kind": "motion", "scene": "lower_third", "start": 16.0, "end": 20.0, "sound": True},
                {"id": "r1", "kind": "motion", "scene": "ranking", "start": 20.0, "end": 26.0, "sound": True},
                sound={"hits": ["s1@value"], "whooshes": [3.0]})
    events, notes = plan.motion_sounds()
    assert events == {"hits": [2.0, 6.0], "whooshes": [11.0, 19.76], "typing": []}   # one per insert; out = end - 6 frames
    assert "k2: no sound (a keyword_pop right after a keyword_pop stays silent)" in notes
    assert "r1: sound is on, but template ranking names no usable sound (@sounds)" in notes
    assert plan.sound_entries("hits") == ["s1@value", 2.0, 6.0]
    assert plan.sound_entries("whooshes") == [3.0, 11.0, 19.76]
    plan.drop(["s1", "m1"], "test")
    assert plan.sound_entries("hits") == [6.0] and "m1" in plan.dropped


def test_no_sound_unless_asked(episode, studio):
    assert make(episode, studio, roll(), pop()).motion_sounds() == ({"hits": [], "whooshes": [], "typing": []}, [])


def test_images_in_params_become_files_inside_the_episode(episode, studio):
    shot = episode.dir / "broll" / "shot.png"
    shot.parent.mkdir()
    from PIL import Image
    Image.new("RGB", (8, 8)).save(shot)
    plan = make(episode, studio, {"id": "r1", "kind": "motion", "scene": "ranking", "start": 10.0, "end": 16.0,
                                  "data": {"image": "broll/shot.png", "items": [{"label": "a"}]}})
    x = plan.by_id("r1")
    assert x.data["image"] == str(shot) and x.assets == (shot,)
    h = x.hash
    Image.new("RGB", (9, 9)).save(shot)
    assert Plan(plan.path).by_id("r1").hash != h


def test_neutral_pack_has_the_motion_block():
    from crewcut import brand
    p = brand.load()
    m = p.value("edit_style.motion")
    assert m["insert_s"] == [3, 6] and m["overlay_min_s"] == 1.5 and m["prefer"] == "motion"
    assert m["min_gap_s"] == 6 and m["shorts"]["big_max"] == 2 and m["big_moments"] == [3, 5]
    from crewcut.motion import density
    assert {k: v for k, v in m.items() if k != "prefer"} == density.NEUTRAL    # one set of numbers
    assert p.value("edit_style.graphics_mix") == {"motion": 0.4, "2d": 0.4, "3d": 0.0, "text": 0.2}
