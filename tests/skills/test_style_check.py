import json
import os
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from s2_helpers import APP, pack, script  # noqa: E402

sc = script("cut-check/scripts/style_check.py", "s2_style_check")

WORDS = [{"word": "Local", "start": 0.5}, {"word": "models", "start": 0.9}, {"word": "cost", "start": 3.0},
         {"word": "thirty", "start": 12.0}, {"word": "cents.", "start": 12.4}, {"word": "Here", "start": 50.0},
         {"word": "is", "start": 50.2}, {"word": "how", "start": 50.4}, {"word": "I", "start": 50.6},
         {"word": "set", "start": 50.8}, {"word": "it", "start": 51.0}, {"word": "up.", "start": 51.2}]


def test_normalize_words_shapes():
    assert sc.normalize_words([{"w": "a", "s": 1}]) == [{"word": "a", "start": 1.0}]
    assert sc.normalize_words({"words": [{"text": "b", "start": 2}]}) == [{"word": "b", "start": 2.0}]
    assert sc.normalize_words([{"words": [{"word": "c", "start": 3}]}]) == [{"word": "c", "start": 3.0}]


def test_cue_frames():
    ins = {"start": 10.0, "cues": {"value": {"word": "thirty"}, "label": 8, "t": {"time": 11.0},
                                   "late": {"word": "cents", "offset": -2}}}
    assert sc.cue_frames(ins, WORDS, 25) == {"value": 50, "label": 8, "t": 25, "late": 58}


def test_speaker_runs_flash_open_close():
    fps = 25
    ins = sc.plan_inserts({"inserts": [
        {"id": "a", "kind": "2d", "scene": "counter", "start": 4.0, "end": 8.0},
        {"id": "b", "kind": "3d", "scene": "stack", "start": 9.0, "end": 12.0},
        {"id": "k", "kind": "2d", "scene": "keyword", "start": 2.0, "end": 3.0, "transparent": True, "data": {"text": "AI"}},
    ]}, [], fps)
    runs = sc.speaker_runs(ins, 60 * fps)
    assert runs == [(0, 100), (200, 225), (300, 1500)]
    assert sc.flashes(runs, 60 * fps, 2.5 * fps) == [(200, 225)]
    assert sc.open_close(runs, 60 * fps, fps) == (4.0, 30.0)
    runs = sc.speaker_runs(ins, 60 * fps, base_until_f=50 * fps)
    assert runs[-1] == (300, 1250)


def test_mix_counts():
    ins = sc.plan_inserts({"inserts": [
        {"id": "h1", "kind": "2d", "scene": "headline", "start": 1, "end": 2, "data": {"title": "A"}},
        {"id": "h2", "kind": "2d", "scene": "headline", "start": 3, "end": 4, "data": {"title": "A"}},
        {"id": "p1", "kind": "2d", "scene": "post", "start": 5, "end": 6, "data": {"name": "B"}},
        {"id": "d1", "kind": "3d", "scene": "box", "start": 7, "end": 9},
        {"id": "k1", "kind": "2d", "scene": "keyword", "start": 10, "end": 11, "transparent": True,
         "data": {"words": [{"text": "ONE"}, "TWO WORDS"]}},
    ]}, [], 25)
    m = sc.mix_counts(ins, 25)
    assert (m["full"], m["text"], m["sources"]) == (4, 3, 2)
    assert m["keywords"] == ["ONE", "TWO WORDS"]
    assert m["sec3d"] == 2.0


def test_scan_italics_and_small_text():
    src = ".unused { font-style: italic }\n.em { font-style: italic }\n<div class=\"em\">x</div>\n/* <i>no</i> */\n"
    assert sc.scan_italics(src) == [2]
    assert sc.scan_small_px("a { font-size: 24px }\nb { font-size: 64px }", 40) == [(1, 24)]


def test_end_card_offset():
    ins = sc.plan_inserts({"inserts": [{"id": "end", "kind": "2d", "scene": "cards", "start": 50.2, "end": 58.0}]},
                          [], 25)
    off = sc.end_card_offset(WORDS, ["set"], ins, 58.0, 25)
    assert abs(off - 0.2) < 1e-9  # sentence starts at "Here" (50.0)
    assert sc.end_card_offset(WORDS, ["missing"], ins, 58.0, 25) is None


def test_pixel_helpers():
    skin = np.zeros((20, 20, 3), np.uint8) + np.array([200, 150, 120], np.uint8)
    blue = np.zeros((20, 20, 3), np.uint8) + np.array([30, 30, 200], np.uint8)
    assert sc.skin_share(skin) > 0.9 and sc.skin_share(blue) == 0.0
    assert sc.face_outliers({1: 0.9, 2: 0.85, 3: 0.3}) == [3]
    flat = np.full((50, 50, 3), 240, np.uint8)
    busy = flat.copy()
    busy[10:40, 10:40] = 20
    assert sc.content_share(flat) == 0.0 and sc.content_share(busy) > 0.3
    assert sc.still_share([flat, flat, flat]) == 1.0
    assert sc.still_share([flat, busy, flat]) == 0.0
    assert sc.corner_box("top-right", 54) == (1920 - 270 - 16, 16, 270, 91)
    assert sc.corner_box("none", 54) is None
    corner = flat.copy()
    assert not sc.logo_found(corner)
    corner[5:20, 5:30] = 0
    assert sc.logo_found(corner)


def test_shown_changed(tmp_path):
    out = tmp_path / "v.mp4"
    out.write_bytes(b"abc")
    assert sc.shown_changed(out) is None
    sha = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    (tmp_path / "v.mp4.shown").write_text(json.dumps({"time": "2026-11-16T10:00:00Z", "sha256": sha}))
    assert sc.shown_changed(out) is False
    out.write_bytes(b"abcd")
    assert sc.shown_changed(out) is True


def test_limits_from_neutral_pack():
    L = sc.limits(pack())
    assert L["lufs"] == -14.0 and L["captions"] in ("none", "keywords", "full")
    assert L["text_share_max"] <= 1.0 and L["open_close"] > 0
    assert L["logo_placement"] == "none"


def test_plan_check_without_media(tmp_path):
    ep = tmp_path / "002-demo"
    (ep / "edit").mkdir(parents=True)
    (ep / "work").mkdir()
    (ep / "work" / "words-v001.json").write_text(json.dumps(WORDS))
    plan = {"format": "landscape", "fps": 25, "words": "work/words-v001.json", "base": "work/speaker-v001.mp4",
            "face": [0.5, 0.38], "tail": 2.0, "inserts": [
                {"id": "s1", "kind": "2d", "scene": "counter", "start": 10.0, "end": 14.0,
                 "cues": {"value": {"word": "thirty"}}, "data": {"value": "30"}},
                {"id": "s2", "kind": "2d", "scene": "headline", "start": 15.0, "end": 18.0, "data": {"title": "X"}},
                {"id": "k1", "kind": "2d", "scene": "keyword", "start": 20.0, "end": 22.0, "transparent": True,
                 "data": {"text": "ONE TWO THREE FOUR FIVE SIX"}}],
            "sound": {"music": "audio/music.wav"}, "output": "export/002-demo-v001-preview.mp4"}
    p = ep / "edit" / "plan-v001.json"
    p.write_text(json.dumps(plan))
    code = sc.main([str(p), "--no-media", "--pack", str(APP / "packs" / "neutral")])
    assert code == 1
    rep = json.loads((ep / "review" / "cut-check-v001.json").read_text())
    lv = {f["id"]: f["level"] for f in rep["findings"]}
    assert lv["flash:0:14.0"] == "ERROR"          # 1 s of speaker between s1 and s2
    assert lv["music-rights"] == "ERROR"          # no sound.music_source
    assert lv["text-share"] == "ERROR"            # 1 of 2 full-screen inserts is text (neutral max 0.4)
    assert lv["keyword-words"] == "ERROR"         # 6 words
    assert lv["open"] == "OK" and lv["video"] == "NOTE"
    assert os.path.exists(ep / "review" / "cut-check-v001.json")
