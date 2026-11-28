"""The graphics gate (crewcut/graphicsgate.py): a style pack's graphic system checked on the edit plan before the
video renders.

The pack here is synthetic (its own four colours, a test font, five types a to e). The failing case replays the
timeline of a real long video whose graphics failed review (40 inserts, the same times, kinds and file locations,
neutral ids and filler words): 63 % speaker, a quarter of the video full-screen graphics, eight inserts a minute,
pill keywords, finished graphics without a type, full screens back to back, two overlays at once. The clean plan
follows every rule and passes.
"""

import json
from pathlib import Path

import pytest

from crewcut import approvals, brand, db, episodes, graphicsgate, paths
from crewcut.render import workbench

INK, PAPER, ACCENT, HIGHLIGHT = "#101820", "#F7F7F2", "#0057FF", "#FFD400"

GRAPHICS = {
    "types": {
        "a_keyword": {"what": "keyword or number beside the speaker", "templates": ["keyword_pop",
                                                                                 "number_roll (transparent)"]},
        "b_card": {"what": "one card shape", "templates": ["lower_third"]},
        "c_chapter": {"what": "chapter card", "templates": ["chapter_card"]},
        "d_explainer": {"what": "3D stage or calm diagram", "templates": ["3d-scene", "2D diagram"]},
        "e_proof": {"what": "proof film", "templates": ["clip"]},
    },
    "palette": {"highlight_for": ["keyword", "number"]},
    "text": {"font": "Testsans", "weights": {"keyword": 800, "secondary": 500}, "italics": False,
             "min_px_landscape": 54, "min_px_short": 48, "keyword_max_words": 4, "full_sentences": False},
    "density": {"first_60s_max": 10, "per_minute_after": [3, 5]},
    "full_screen": {"share_max": 0.15, "seconds": [3, 6], "seconds_to_read_max": 8, "speaker_between_min_s": 2.5,
                    "counts": ["c_chapter", "d_explainer"]},
    "speaker_share_min": 0.75,
    "elements_max": 4,
    "sync": {"arrive_tolerance_frames": 2, "lead_s": [0.3, 0.5], "hold_after_word_s": 0.5},
    "sound": {"per_graphic_max": 1, "chapter_change_pair": ["whoosh", "pop"], "per_minute": [3, 6],
              "shorts": "dry"},
    "shapes_background": {"allowed_on": ["c_chapter", "end_lockup"]},
    "logo": {"allowed_on": ["end_lockup"]},
    "safe_area": {"landscape": {"left": 96, "right": 96, "top": 54, "bottom": 54},
                  "portrait": {"top": 288, "bottom": 672, "left": 48, "right": 192}},
}


@pytest.fixture
def pack(studio):
    b = studio / "brand"
    b.mkdir()
    (b / "brand.json").write_text(json.dumps({
        "name": "Test", "colors": {"ink": INK, "paper": PAPER, "accent": ACCENT, "highlight": HIGHLIGHT},
        "fonts": {"display": {"family": "Testsans", "weight": 800, "files": []},
                  "body": {"family": "Testsans", "weight": 500, "files": []}},
        "motion_graphics": {"palette": [ACCENT, INK], "pastels": False, "ground": PAPER, "ink": INK,
                            "background": {"mode": "plain", "shapes_only_on": ["chapter_card", "end_lockup"],
                                           "max_shapes": 2}},
        "logo": {"file": None, "placement": "none"}}))
    (b / "channel.json").write_text(json.dumps({"language": "en", "graphics": {
        "palette": {"ink": INK, "paper": PAPER, "accent": ACCENT, "highlight": HIGHLIGHT},
        "motion": {"enter_s": 0.4, "exit_s": 0.28, "stagger_s": 0.08, "ease": [0.2, 0, 0, 1]}}}))
    (b / "edit-style.json").write_text(json.dumps({"fps": 25, "speaker_share_min": 0.75, "speaker_min_seconds": 2.5,
                                                   "graphics": GRAPHICS}))
    return brand.load()


def gate_mode(studio: Path, mode: str) -> None:
    (studio / "config").mkdir(exist_ok=True)
    (studio / "config" / "crewcut.toml").write_text(f'[graphics_gate]\nmode = "{mode}"\n')


def write_words(ep: Path, name: str, seconds: float, said: dict[float, str]) -> str:
    """Filler words every 0.4 s, with the given words at their times."""
    words, t = [], 0.0
    keys = sorted(said)
    while t < seconds:
        while keys and keys[0] <= t + 0.2:
            k = keys.pop(0)
            words.append({"w": said[k], "s": round(k, 2), "e": round(k + 0.38, 2)})
        words.append({"w": "wort", "s": round(t, 2), "e": round(t + 0.3, 2)})
        t += 0.4
    words.sort(key=lambda w: w["s"])
    (ep / "work").mkdir(parents=True, exist_ok=True)
    (ep / "work" / name).write_text(json.dumps(words))
    return f"work/{name}"


def write_plan(ep: Path, plan: dict, name: str = "plan-v001.json") -> Path:
    (ep / "edit").mkdir(parents=True, exist_ok=True)
    p = ep / "edit" / name
    p.write_text(json.dumps(plan))
    return p


# ---- the replay of a failing long video ----------------------------------------------------------------------------
# (start, end, kind, where, overlay): where "r" = a finished graphic under render/inserts, "b" = a recording in broll/
REPLAY = [
    (0.0, 2.2, "clip", "b", False), (2.2, 4.48, "clip", "b", False), (10.08, 12.08, "2d", "kw", True),
    (12.88, 19.28, "clip", "r", True), (23.96, 26.08, "clip", "r", False), (29.24, 34.24, "clip", "r", True),
    (34.28, 37.96, "clip", "r", False), (41.4, 47.08, "clip", "b", False), (51.48, 57.32, "clip", "b", False),
    (64.48, 69.0, "clip", "r", False), (73.24, 76.68, "clip", "r", True), (76.88, 81.08, "clip", "r", False),
    (86.12, 88.48, "clip", "r", True), (88.52, 92.64, "clip", "r", False), (92.64, 95.48, "clip", "r", False),
    (95.48, 98.44, "clip", "r", False), (102.76, 105.04, "clip", "r", False), (110.24, 114.24, "clip", "r", False),
    (118.04, 122.52, "clip", "r", True), (122.6, 125.0, "clip", "r", False), (129.08, 134.12, "clip", "r", True),
    (136.12, 139.44, "clip", "b", False), (143.84, 147.44, "clip", "r", True), (147.6, 151.44, "clip", "r", False),
    (159.44, 163.84, "clip", "r", False), (170.24, 175.24, "clip", "r", False), (175.24, 178.44, "clip", "r", False),
    (178.44, 180.84, "clip", "r", False), (195.56, 199.16, "clip", "b", False), (210.28, 217.2, "clip", "r", False),
    (217.2, 219.68, "clip", "b", False), (219.68, 222.16, "clip", "b", False), (222.16, 224.56, "clip", "b", False),
    (224.92, 235.04, "clip", "r", True), (235.12, 238.92, "clip", "r", False), (238.92, 242.44, "clip", "r", False),
    (269.2, 273.6, "clip", "b", False), (276.28, 278.36, "2d", "kw", True), (277.76, 280.92, "clip", "r", True),
    (281.04, 286.18, "clip", "r", False),
]


def replay(ep: Path) -> Path:
    words = write_words(ep, "words-v001.json", 283.4, {11.0: "Tage.", 277.08: "kostenlos"})
    inserts = []
    for i, (s, t, kind, where, overlay) in enumerate(REPLAY, 1):
        iid = f"g{i:02d}"
        x = {"id": iid, "kind": kind, "start": {"time": s}, "end": {"time": t}}
        if kind == "2d":
            word = "Tage" if i == 3 else "kostenlos"
            x.update(scene="keyword", transparent=True, cues={},
                     data={"words": [{"text": word, "from": 22 if i == 3 else 20, "x": 0.84, "y": 0.5,
                                      "style": "accent"}]})
        else:
            x.update(file=(f"render/inserts/{iid}-0123456789.{'mov' if overlay else 'mp4'}" if where == "r"
                           else f"broll/take-{i:02d}.mp4"), at=0.0, speed=1.0)
            if overlay:
                x["transparent"] = True
        inserts.append(x)
    comp = ep / "motion" / "g07" / "comp.jsx"
    comp.parent.mkdir(parents=True)
    comp.write_text('/* @template counter_wall */\nfunction counter_wall(P) {\n'
                    '  var veil = EC.shape(c, { kind: "ellipse", fill: "#FFFFFF" });\n  return {};\n}\n')
    return write_plan(ep, {"format": "landscape", "fps": 25, "words": words, "base": "work/speaker.mov",
                           "inserts": inserts, "sound": {"hits": [54.84], "whooshes": [2.2]}, "tail": 2.5})


def ids(v: dict, prefix: str) -> list[str]:
    return [f["id"] for f in v["fails"] if f["id"].startswith(prefix)]


def test_replay_of_a_failing_video_fails_with_its_known_problems(pack, studio):
    ep = studio / "episodes" / "019-replay"
    v = graphicsgate.check_plan(replay(ep))
    m = v["metrics"]
    assert not v["pass"] and v["skipped"] is None
    assert {"G1", "G2", "G5", "G6", "G7", "G9"} <= {f["rule"] for f in v["fails"]}
    # the speaker is on screen 63 % (at least 75 %), full-screen graphics a quarter of the video (at most 15 %)
    assert m["speaker_share"] == pytest.approx(0.63, abs=0.01) and "G5-speaker" in ids(v, "G5-speaker")
    assert m["graphics_share"] == pytest.approx(0.249, abs=0.01) and ids(v, "G5-full-share")
    assert m["full_screen_parts"] == 29
    # 28 finished graphics without a type and the two pill keywords (the 2D chip is not the pack's keyword template)
    assert len(ids(v, "G1-type")) == 30 and m["untyped"] == 28
    assert "keyword_pop" in next(f["text"] for f in v["fails"] if f["id"] == "G1-type:g03")
    # full screens back to back (no speaker between) and too short or too long
    assert len(ids(v, "G5-between")) == 9 and "G5-between:g14-g15" in ids(v, "G5-between")
    assert len(ids(v, "G5-length")) == 7 and "G5-length:g30" in ids(v, "G5-length")
    # eight inserts a minute after the first minute (at most 5); the first minute is fine
    assert m["first_60s"] == 9 and m["per_minute_after"] == pytest.approx(8.2, abs=0.1) and ids(v, "G6-per-minute")
    # keywords a third of a second late, and two overlays at once
    assert ids(v, "G7-sync") == ["G7-sync:g03", "G7-sync:g38"]
    assert ids(v, "G9-overlap") == ["G9-overlap:g38-g39"]
    # the counter's own source paints a white veil (not the paper of the palette)
    assert ids(v, "G2-source") == ["G2-source:g07"] and "#FFFFFF" in v["fails"][[f["id"] for f in v["fails"]].index(
        "G2-source:g07")]["text"]
    # what the plan cannot say is listed, not guessed
    assert "G7" in v["not_measured"]
    out = graphicsgate.text(v)
    assert "speaker 63%" in out and "G5" in out and "Fix:" in out


# ---- a clean long video ------------------------------------------------------------------------------------------
def clean(ep: Path, extra: list[dict] | None = None, **plan_keys) -> Path:
    said = {}
    inserts: list[dict] = [{"id": "open-proof", "kind": "clip", "file": "broll/open.mp4", "at": 0.0, "start": 0.0,
                            "end": 3.6}]
    kw_times = [8.0, 14.0, 20.0, 27.0, 34.0, 41.0, 49.0, 56.0]
    for i, t in enumerate(kw_times):
        w = f"stichwort{i}"
        said[t] = w
        inserts.append({"id": f"kw{i}", "kind": "2d", "scene": "hf-keyword", "transparent": True,
                        "start": round(t - 0.6, 2), "end": round(t + 1.8, 2), "cues": {"land": {"word": w}},
                        "data": {"words": [w.capitalize()]}})
    # after the first minute: 3 chapter cards, 3 explainers, 1 proof film, keywords and a lower third
    timeline = [("c1", 64.0, "chapter"), ("k10", 75.0, "kw"), ("d1", 86.0, "explainer"), ("k11", 98.0, "kw"),
                ("lt", 110.0, "card"), ("k12", 122.0, "kw"), ("c2", 134.0, "chapter"), ("k13", 146.0, "kw"),
                ("d2", 158.0, "explainer"), ("k14", 170.0, "kw"), ("p1", 182.0, "proof"), ("k15", 194.0, "kw"),
                ("c3", 206.0, "chapter"), ("k16", 218.0, "kw"), ("d3", 230.0, "explainer"), ("k17", 242.0, "kw"),
                ("k18", 252.0, "kw")]
    for iid, t, what in timeline:
        w = f"wort{iid}"
        said[t] = w
        if what == "kw":
            inserts.append({"id": iid, "kind": "motion", "scene": "keyword_pop", "transparent": True,
                            "start": round(t - 0.5, 2), "end": round(t + 1.6, 2), "cues": {"cueAt": {"word": w}},
                            "data": {"words": [w.capitalize()]}})
        elif what == "chapter":
            inserts.append({"id": iid, "kind": "motion", "scene": "chapter_card", "start": {"word": w},
                            "end": round(t + 3.5, 2), "data": {"number": int(iid[1]), "title": w.capitalize()},
                            "sound": True, "beat": int(iid[1]), "column": "c"})
        elif what == "explainer":
            inserts.append({"id": iid, "kind": "3d", "scene": "stack", "start": {"word": w}, "end": round(t + 5.0, 2),
                            "data": {"label": w.capitalize()}, "beat": 10 + int(iid[1]), "column": "d"})
        elif what == "card":
            inserts.append({"id": iid, "kind": "motion", "scene": "lower_third", "transparent": True,
                            "start": round(t - 0.4, 2), "end": round(t + 4.0, 2), "cues": {"cueAt": {"word": w}},
                            "data": {"name": "Dana Beispiel", "role": "Tontechnik"},
                            "graphic": {"box": [1180, 760, 644, 220]}})
        else:
            inserts.append({"id": iid, "kind": "clip", "file": "broll/proof.mp4", "at": 0.0, "start": {"word": w},
                            "end": round(t + 4.0, 2)})
    inserts += extra or []
    words = write_words(ep, "words-v001.json", 268.0, said)
    plan = {"format": "landscape", "fps": 25, "words": words, "base": "work/speaker.mov", "inserts": inserts,
            "sound": {"hits": ["kw0", "k12"], "whooshes": []}, "tail": 2.0}
    plan.update(plan_keys)
    return write_plan(ep, plan)


def test_a_clean_plan_passes(pack, studio):
    v = graphicsgate.check_plan(clean(studio / "episodes" / "100-clean"))
    assert v["pass"], graphicsgate.text(v)
    m = v["metrics"]
    assert m["speaker_share"] > 0.8 and m["graphics_share"] < 0.15
    assert m["first_60s"] == 9 and 3 <= m["per_minute_after"] <= 5 and m["untyped"] == 0
    assert {g["type"] for g in v["graphics"]} == {"a_keyword", "b_card", "c_chapter", "d_explainer", "e_proof"}
    assert "Graphics check passes" in graphicsgate.text(v)


def test_neutral_pack_skips(studio):
    v = graphicsgate.check_plan(clean(studio / "episodes" / "100-clean"))
    assert v["pass"] and "no graphic system" in v["skipped"]


# ---- single rules ------------------------------------------------------------------------------------------------
def one(studio: Path, insert: dict, **plan_keys) -> dict:
    return graphicsgate.check_plan(clean(studio / "episodes" / "100-clean", [insert], **plan_keys))


def rules_of(v: dict) -> set[str]:
    return {f["id"].split(":")[0] for f in v["fails"]}


def test_colours_type_and_shapes(pack, studio):
    v = one(studio, {"id": "x", "kind": "motion", "scene": "keyword_pop", "transparent": True, "start": 101.0,
                     "end": 103.0, "data": {"words": ["Pastell"]},
                     "graphic": {"colors": ["#DEE9FD", "ink"], "font": "Comic Sans", "weights": [800, 300],
                                 "italic": True, "text_px": 40, "shapes": 3, "logo": True}})
    assert {"G2-colour", "G3-font", "G3-weight", "G3-italic", "G3-size", "G4-shapes", "G4-count",
            "G4-logo"} <= rules_of(v)


def test_highlight_never_on_paper_and_only_for_keywords(pack, studio):
    v = one(studio, {"id": "x", "kind": "3d", "scene": "stack", "start": 100.0, "end": 104.0,
                     "graphic": {"ground": "paper", "colors": ["highlight"]}})
    assert "G2-highlight-paper" in rules_of(v)
    v = one(studio, {"id": "x", "kind": "clip", "file": "render/inserts/x-0123456789.mp4", "start": 100.0,
                     "end": 104.0, "graphic": {"type": "d", "ground": "paper", "colors": [HIGHLIGHT, INK]}})
    assert {"G2-highlight", "G2-highlight-paper"} <= rules_of(v)


def test_a_declared_type_makes_a_finished_graphic_count(pack, studio):
    x = {"id": "x", "kind": "clip", "file": "render/inserts/x-0123456789.mp4", "start": 100.0, "end": 104.0}
    assert "G1-type" in rules_of(one(studio, x))
    v = one(studio, {**x, "graphic": {"type": "d"}})
    assert "G1-type" not in rules_of(v) and next(g for g in v["graphics"] if g["id"] == "x")["type"] == "d_explainer"
    v = one(studio, {**x, "graphic": {"type": "z"}})
    assert "not a type of the pack" in next(f["text"] for f in v["fails"] if f["id"] == "G1-type:x")
    # a keyword never covers the frame
    v = one(studio, {**x, "graphic": {"type": "a"}})
    assert "G1-place" in rules_of(v)


def test_words_sentences_elements_and_overlaps(pack, studio):
    v = one(studio, {"id": "x", "kind": "motion", "scene": "keyword_pop", "transparent": True, "start": 101.0,
                     "end": 103.0, "data": {"words": ["Das", "ist", "ein", "ganzer", "Satz."]},
                     "graphic": {"elements": 6}})
    assert {"G9-words", "G9-sentence", "G9-elements"} <= rules_of(v)
    v = one(studio, {"id": "x", "kind": "motion", "scene": "keyword_pop", "transparent": True, "start": 98.5,
                     "end": 100.5, "data": {"words": ["Zweiter"]}})
    assert "G9-overlap" in rules_of(v)


def test_word_sync_and_hold(pack, studio):
    ep = studio / "episodes" / "100-clean"
    early = {"id": "x", "kind": "motion", "scene": "keyword_pop", "transparent": True, "start": 99.0, "end": 103.0,
             "data": {"words": ["Spaet"]}, "graphic": {"on": "wortk11"}}
    v = graphicsgate.check_plan(clean(ep, [early]))
    assert "G7-sync" in rules_of(v)
    late_end = {**early, "start": 97.6, "end": 98.2, "id": "y"}
    v = graphicsgate.check_plan(clean(ep, [late_end]))
    assert "G7-hold" in rules_of(v) and "G7-sync" not in rules_of(v)
    missing = {**early, "id": "z", "graphic": {"on": "nirgends"}}
    assert "G7-word" in rules_of(graphicsgate.check_plan(clean(ep, [missing])))


def test_sounds_per_graphic_and_dry_shorts(pack, studio):
    v = one(studio, {"id": "x", "kind": "motion", "scene": "keyword_pop", "transparent": True, "start": 101.0,
                     "end": 103.0, "data": {"words": ["Laut"]}}, sound={"hits": ["x", "x@cueAt"], "whooshes": []})
    assert "G10-sounds" in rules_of(v)
    ep = studio / "episodes" / "200-short"
    words = write_words(ep, "words-v001.json", 40.0, {5.0: "eins"})
    short = {"format": "portrait", "fps": 25, "words": words, "base": "work/s.mov", "layout": "proof-top",
             "inserts": [{"id": "k", "kind": "2d", "scene": "hf-keyword", "transparent": True, "start": 4.4,
                          "end": 6.5, "cues": {"land": {"word": "eins"}}, "data": {"words": ["Eins"]}}],
             "sound": {"hits": ["k"]}}
    v = graphicsgate.check_plan(write_plan(ep, short))
    assert rules_of(v) == {"G10-short-dry"}
    short["sound"] = {}
    assert graphicsgate.check_plan(write_plan(ep, short))["pass"]


def test_safe_zones(pack, studio):
    v = one(studio, {"id": "x", "kind": "motion", "scene": "lower_third", "transparent": True, "start": 101.0,
                     "end": 105.0, "data": {"name": "Rand"}, "graphic": {"box": [1500, 900, 400, 160]}})
    assert "G11-box" in rules_of(v)
    ep = studio / "episodes" / "200-short"
    words = write_words(ep, "words-v001.json", 40.0, {5.0: "eins"})
    short = {"format": "portrait", "fps": 25, "words": words, "base": "work/s.mov",
             "inserts": [{"id": "k", "kind": "2d", "scene": "hf-keyword", "transparent": True, "start": 4.4,
                          "end": 6.5, "data": {"words": ["Eins"]}, "graphic": {"box": [60, 300, 900, 300]}}]}
    assert "G11-box" in rules_of(graphicsgate.check_plan(write_plan(ep, short)))


def test_back_to_back_full_screens_may_be_one_piece(pack, studio):
    a = {"id": "n1", "kind": "clip", "file": "render/inserts/n1-0123456789.mp4", "start": 100.0, "end": 102.0,
         "graphic": {"type": "d"}}
    b = {"id": "n2", "kind": "clip", "file": "render/inserts/n2-0123456789.mp4", "start": 102.0, "end": 104.5,
         "graphic": {"type": "d"}}
    v = graphicsgate.check_plan(clean(studio / "episodes" / "100-clean", [a, b]))
    assert {"G5-between", "G5-length"} <= rules_of(v)
    b["graphic"]["joins_previous"] = True
    v = graphicsgate.check_plan(clean(studio / "episodes" / "100-clean", [a, b]))
    assert "G5-between" not in rules_of(v) and "G5-length" not in rules_of(v)


# ---- in the render step: block, warn, the card -------------------------------------------------------------------
class FakePlan:
    def __init__(self, path: Path, episode: str):
        self.path, self.episode, self.episode_dir, self.pack = path, episode, path.parent.parent, brand.load()


@pytest.fixture
def episode(studio, crew):
    return episodes.create("Graphics in test")["id"]


def test_block_stops_the_render_with_one_card_and_its_yes_goes_to_the_editor(pack, studio, episode):
    gate_mode(studio, "block")
    p = replay(paths.episode_dir(episode))
    with pytest.raises(workbench.Waiting) as e:
        workbench.graphics_gate(FakePlan(p, episode))
    card = approvals.get(e.value.card_id)
    assert card["step"] == "edit" and card["status"] == "open" and "Graphics check fails" in card["title"]
    assert "G5" in card["body"] and "Fix:" in card["body"]
    with pytest.raises(workbench.Waiting) as again:          # the same plan, the same findings: the same card
        workbench.graphics_gate(FakePlan(p, episode))
    assert again.value.card_id == card["id"]
    approvals.decide(card["id"], True)
    with db.conn() as c:
        jobs = db.rows(c.execute("SELECT * FROM jobs WHERE episode = ? AND identity = 'editor'", (episode,)))
    assert jobs and "graphics check fails" in jobs[-1]["task"] and "G5" in jobs[-1]["task"]


def test_a_passing_plan_closes_the_open_card(pack, studio, episode):
    gate_mode(studio, "block")
    ep = paths.episode_dir(episode)
    with pytest.raises(workbench.Waiting) as e:
        workbench.graphics_gate(FakePlan(replay(ep), episode))
    v = workbench.graphics_gate(FakePlan(clean(ep), episode))
    assert v["pass"] and approvals.get(e.value.card_id)["status"] == "expired"


def test_warn_and_off_never_stop_the_render(pack, studio, episode):
    p = replay(paths.episode_dir(episode))
    lines: list[str] = []
    v = workbench.graphics_gate(FakePlan(p, episode), log=lines.append)     # default: warn
    assert not v["pass"] and v["mode"] == "warn" and any("graphics gate (warn)" in x for x in lines)
    assert not graphicsgate._open_cards(episode)
    gate_mode(studio, "off")
    assert workbench.graphics_gate(FakePlan(p, episode)) is None


def test_cli(pack, studio, capsys):
    from crewcut import cli
    p = replay(studio / "episodes" / "019-replay")
    assert cli.main(["graphics-gate", str(p)]) == 1
    out = capsys.readouterr().out
    assert "Graphics gate (warn): FAIL" in out and "G6" in out
    assert cli.main(["graphics-gate", str(clean(studio / "episodes" / "100-clean")), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["pass"] is True
