"""Plan parsing, cue resolution, sound references, cache keys, path rules."""

import json
import shutil

import pytest
from render_helpers import basic_plan

from crewcut import brand, paths
from crewcut.render.plan import EXTRA_FRAMES, Plan, PlanError, normalize


def test_defaults_from_pack_and_project(episode):
    plan = Plan(episode(basic_plan()))
    assert plan.format == "landscape" and plan.size == (1920, 1080) and plan.fps == 25
    s1 = plan.by_id("s1")
    assert (s1.start, s1.end, s1.frames) == (25, 75, 50)
    assert s1.render_frames == 50 + EXTRA_FRAMES
    assert s1.data["format"] == "landscape" and s1.data["frames"] == 52 and s1.data["fps"] == 25
    assert s1.data["cues"] == s1.cues
    assert s1.template.name == "counter.html" and [f.name for f in s1.shared] == ["base.css", "motion.js", "scene.js"]
    assert s1.clip.suffix == ".mp4" and plan.by_id("k1").clip.suffix == ".mov"
    assert plan.output.name == "out-v001.mp4"
    assert plan.shown_path.name == "out-v001.mp4.shown"


def test_portrait_from_plan(episode):
    plan = Plan(episode(basic_plan(format="portrait")))
    assert plan.size == (1080, 1920)
    assert plan.by_id("s1").data["format"] == "portrait"


def test_cue_number_word_time(episode):
    plan = Plan(episode(basic_plan()))
    s1 = plan.by_id("s1")
    assert s1.cues["label"] == 4
    assert s1.cues["value"] == round(2.0 * 25) - 25           # "thirty" at 2.0 s, insert starts at frame 25
    assert plan.cue_frame({"time": 2.4}, 25, 1.0) == 35
    assert plan.cue_frame({"time": 2.4, "offset": -2}, 25, 1.0) == 33
    assert plan.cue_frame(12.6, 0, 0.0) == 13


def test_word_matching_rules(episode):
    plan = Plan(episode(basic_plan()))
    assert normalize("Thirty,") == "thirty" and normalize("(cents.)") == "cents"
    assert plan.word_time("thirty") == 2.0
    assert plan.word_time("THIRTY", after=3.0) == 8.0                   # punctuation and case ignored, later occurrence
    assert plan.word_time("a third") == 5.0                             # a phrase of several words
    assert plan.cue_frame({"word": "thirty", "after": 7.5, "offset": 1}, 175, 7.0) == round(8.0 * 25) - 175 + 1
    with pytest.raises(PlanError, match="not found"):
        plan.word_time("forty")
    with pytest.raises(PlanError, match="not found"):
        plan.word_time("people", after=9.5)


def test_cue_by_word_needs_words(episode):
    p = basic_plan()
    p.pop("words")
    with pytest.raises(PlanError, match="needs 'words'"):
        Plan(episode(p))


def test_bad_cues(episode):
    plan = Plan(episode(basic_plan()))
    for bad in (True, "12", {"frame": 3}, None):
        with pytest.raises(PlanError):
            plan.cue_frame(bad, 0, 0.0)


def test_sound_references(episode):
    plan = Plan(episode(basic_plan()))
    assert plan.ref_frame("s1") == 25
    assert plan.ref_frame("s1@value") == 50
    assert plan.ref_frame(2.5) == 62
    with pytest.raises(PlanError, match="no cue 'nope'"):
        plan.ref_frame("s1@nope")
    with pytest.raises(PlanError, match="no insert"):
        plan.ref_frame("x9@value")
    with pytest.raises(PlanError):
        plan.ref_frame(True)


def test_cache_key_changes_with_data_and_brand_tokens(episode, studio):
    path = episode(basic_plan())
    neutral = Plan(path).by_id("s1").out_dir
    assert neutral.parent == path.parent.parent / "render" / "inserts" and neutral.name.startswith("s1-")
    assert Plan(path).by_id("s1").out_dir == neutral                    # stable
    changed = basic_plan()
    changed["inserts"][0]["data"]["value"] = "31"
    assert Plan(episode(changed, "plan-v002.json")).by_id("s1").out_dir != neutral
    # a user pack with another accent colour: new key
    user = studio / "brand"
    shutil.copytree(paths.neutral_pack_dir(), user)
    b = json.loads((user / "brand.json").read_text())
    b["colors"]["accent"] = "#2A7AE2"
    (user / "brand.json").write_text(json.dumps(b))
    assert not brand.load().is_neutral
    accent = Plan(path).by_id("s1").out_dir
    assert accent != neutral
    # loudness is not part of the look: same key
    e = json.loads((user / "edit-style.json").read_text())
    e["loudness_lufs"] = -16.0
    (user / "edit-style.json").write_text(json.dumps(e))
    assert Plan(path).by_id("s1").out_dir == accent


def test_paths_become_file_urls_and_stay_inside(episode):
    ep = episode.dir
    (ep / "graphics").mkdir()
    (ep / "graphics" / "a.png").write_bytes(b"x")
    p = basic_plan()
    p["inserts"].append({"id": "c1", "kind": "2d", "scene": "cards", "start": 6.0, "end": 8.0,
                         "data": {"cards": [{"image": "graphics/a.png", "label": "A"}, {"image": ""}]}})
    plan = Plan(episode(p))
    cards = plan.by_id("c1").data["cards"]
    assert cards[0]["image"] == (ep / "graphics" / "a.png").resolve().as_uri()
    assert cards[1]["image"] == ""
    p["inserts"][-1]["data"]["cards"][0]["image"] = "../../../etc/passwd"
    with pytest.raises(PlanError, match="inside the episode"):
        Plan(episode(p, "plan-v002.json"))
    p["inserts"][-1]["data"]["cards"][0]["image"] = "/etc/passwd"
    with pytest.raises(PlanError, match="inside the studio"):
        Plan(episode(p, "plan-v003.json"))


def test_scene_names_and_kinds(episode):
    for bad in ("../x", "Counter", "a b"):
        p = basic_plan()
        p["inserts"][0]["scene"] = bad
        with pytest.raises(PlanError, match="not valid"):
            Plan(episode(p))
    p = basic_plan()
    p["inserts"][0]["scene"] = "area"
    with pytest.raises(PlanError, match="Available: .*counter"):
        Plan(episode(p))
    p = basic_plan()
    p["inserts"][0]["kind"] = "4d"
    with pytest.raises(PlanError, match="kind"):
        Plan(episode(p))
    p = basic_plan()
    p["inserts"].append({"id": "d1", "kind": "3d", "scene": "box", "start": 6.0, "end": 7.0, "transparent": True})
    with pytest.raises(PlanError, match="full frame"):
        Plan(episode(p))
    p = basic_plan()
    p["inserts"].append(dict(p["inserts"][0]))
    with pytest.raises(PlanError, match="used twice"):
        Plan(episode(p))
    p = basic_plan()
    p["inserts"][0]["end"] = 0.5
    with pytest.raises(PlanError, match="end must be after"):
        Plan(episode(p))


def test_3d_and_clip_inserts(episode):
    ep = episode.dir
    (ep / "broll").mkdir()
    (ep / "broll" / "screen.mp4").write_bytes(b"x")
    p = basic_plan()
    p["inserts"] += [{"id": "d1", "kind": "3d", "scene": "stack", "start": 6.0, "end": 7.0, "data": {"count": 4}},
                     {"id": "v1", "kind": "clip", "file": "broll/screen.mp4", "at": 3.0, "speed": 2.0, "start": 7.0, "end": 8.0}]
    plan = Plan(episode(p))
    d1, v1 = plan.by_id("d1"), plan.by_id("v1")
    assert d1.template.name == "stack.py" and [f.name for f in d1.shared] == ["stage.py"]
    assert (v1.at, v1.speed, v1.clip.name) == (3.0, 2.0, "screen.mp4")
    assert plan.missing(v1) == []
    assert len(plan.missing(d1)) == d1.render_frames


def test_pack_template_copy_wins(episode, studio):
    user = studio / "brand"
    shutil.copytree(paths.neutral_pack_dir(), user)
    own = user / "templates" / "2d"
    own.mkdir(parents=True)
    (own / "counter.html").write_text("<html>own</html>")
    p = episode(basic_plan())
    with pytest.raises(PlanError, match="needs base.css"):
        Plan(p)
    for f in ("base.css", "motion.js", "scene.js"):
        shutil.copy(paths.templates_dir() / "2d" / f, own / f)
    plan = Plan(p)
    assert plan.by_id("s1").template == own / "counter.html"
    assert plan.by_id("k1").template == paths.templates_dir() / "2d" / "keyword.html"


def test_warnings(episode):
    p = basic_plan()
    p["inserts"][0]["cues"]["late"] = 400
    p["inserts"] += [{"id": f"h{i}", "kind": "2d", "scene": "headline", "start": 10 + i, "end": 10.8 + i,
                      "data": {"title": "x"}} for i in range(4)]
    p["inserts"].append({"id": "b1", "kind": "2d", "scene": "bars", "start": 2.0, "end": 3.5, "data": {}})
    w = " | ".join(Plan(episode(p)).warnings)
    assert "s1 and b1 overlap" in w
    assert "cue 'late' at frame 400 lies outside" in w
    assert "4 text cards" in w and "allows 3" in w


def test_missing_counts_existing_frames(episode):
    plan = Plan(episode(basic_plan()))
    s1 = plan.by_id("s1")
    s1.out_dir.mkdir(parents=True)
    for i in range(10):
        (s1.out_dir / f"{i:04d}.png").write_bytes(b"x")
    (s1.out_dir / "notes.txt").write_text("x")
    assert plan.missing(s1) == list(range(10, s1.render_frames))


def test_speaker_marks_limited_by_pack(episode):
    plan = Plan(episode(basic_plan(speaker=[{"at": 2.0, "zoom": 1.5}, {"at": 1.0, "zoom": 1.1}])))
    assert plan.speaker_marks() == [(25, 1.1), (50, 1.15)]
    assert plan.base_color() == "#F1F1EF"


def test_bad_json_and_missing_file(episode, tmp_path):
    with pytest.raises(PlanError, match="not found"):
        Plan(tmp_path / "nope.json")
    bad = episode.dir / "edit" / "bad.json"
    bad.write_text("{nope")
    with pytest.raises(PlanError, match="not valid JSON"):
        Plan(bad)


def test_imported_scene_dependencies_keep_paths_and_invalidate_cache(episode, tmp_path):
    p = brand.load()
    p.is_neutral = False
    p.dir = tmp_path / 'pack'
    folder = p.dir / 'templates/2d'
    (folder / 'legacy').mkdir(parents=True)
    (folder / 'counter.html').write_text('<script src="legacy/core.js"></script>')
    helper = folder / 'legacy/core.js'
    helper.write_text('window.setFrame = n => n;')
    manifest = folder / 'counter.scene.json'
    manifest.write_text(json.dumps({'contract': 'video-studio', 'files': ['legacy/core.js']}))
    # Leave unrelated inserts on the native app templates.
    plan = Plan(episode(basic_plan()), pack=p)
    ins = plan.by_id('s1')
    assert ins.data['scene_contract'] == 'video-studio' and helper in ins.shared
    old_hash = ins.hash
    helper.write_text('window.setFrame = n => n + 1;')
    assert Plan(plan.path, pack=p).by_id('s1').hash != old_hash
    manifest.write_text(json.dumps({'files': ['../../../../outside.js']}))
    with pytest.raises(PlanError, match='escapes'):
        Plan(plan.path, pack=p)
