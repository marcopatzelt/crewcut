"""Cut rules. Every case here was a real error in a preview of an earlier studio; ported with the same numbers."""

from crewcut.cut import plan, verify

# Pauses of one take around "filled in, | writes" and "around. | So"
SIL = [(146.30, 146.33), (146.42, 146.53), (148.27, 148.40), (148.99, 149.58), (149.86, 150.08), (264.91, 265.50)]


def test_face_ends_up_in_the_middle():
    for face in ([0.41, 0.41], [0.49, 0.385]):
        for z in (1.22, 1.36):
            cx, cy = plan.centre(face, z, 0.45)
            free = 1 - 1 / z
            assert abs(cx * free + 0.5 / z - face[0]) < 0.01           # face centre x in the crop
            assert abs((face[1] - cy * free) * z - 0.45) < 0.01        # face at 45 % height


def test_no_zoom_means_no_crop_offset():
    assert plan.centre([0.3, 0.3], 1.0, 0.4) == [0.5, 0.5]


def test_padding_stays_in_silence_and_never_reaches_the_next_word():
    end = plan.pad_end(SIL, 146.75, hard=False)        # no silence after the word -> tiny pad
    assert end < 146.80
    assert plan.pad_end(SIL, 148.99, False) <= 149.58 - 0.03
    assert plan.pad_end(SIL, 264.04, hard=True) == 264.07      # "around." then "So" without a pause
    assert plan.pad_start(SIL, 150.08) >= 149.86 + 0.03


def test_long_inner_pause_is_shortened_not_removed():
    parts = plan.split(SIL, 148.0, 151.0)                # contains the 0.59 s pause at 148.99
    assert len(parts) == 2
    kept = (parts[0][1] - 148.99) + (149.58 - parts[1][0])
    assert abs(kept - 0.26) < 0.005


def test_clipped_last_word_is_an_edge_issue():
    clips = [{"id": "form", "expected_text": "Has my agent filled in this form before,"},
             {"id": "notes", "expected_text": "it writes itself a cheat sheet."}]
    heard = [{"text": "Has my agent filled in this form befo."}, {"text": "it writes itself a cheat sheet. So"}]
    issues = verify.edge_issues(clips, heard)
    assert {(i["select"], i["where"]) for i in issues} == {("form", "end"), ("notes", "end")}


def test_split_select_is_checked_as_one():
    clips = [{"id": "a_1", "expected_text": "One two three four."}, {"id": "a_2", "expected_text": "One two three four."}]
    heard = [{"text": "One two"}, {"text": "three four."}]
    assert verify.edge_issues(clips, heard) == []


def _selects(**kw):
    cfg = {"version": "v001", "takes": {"A": {"source": "originals/a-C0001.MP4", "face": [0.49, 0.385], "lock": []},
                                        "B": {"source": "originals/b-C0002.MP4", "face": [0.5, 0.4],
                                              "zoom_factor": 1.2}},
           "selects": [{"id": "s1", "take": "A", "start": 148.0, "end": 151.0, "text": "First part."},
                       {"id": "s2", "take": "A", "start": 160.0, "end": 162.0, "text": "Second part.", "tail": 0.24},
                       {"id": "s3", "take": "B", "start": 10.0, "end": 12.0, "text": "From the pickup."}]}
    cfg.update(kw)
    return cfg


def test_plan_applies_the_rules():
    p, problems = plan.make_plan(_selects(zoom_base=1.12, zoom_punch=1.22, speed=1.1, pause_gap_open=0.30),
                                 {"A": SIL, "B": []}, {"format": "landscape", "fps": 25}, mic=1)
    assert problems == []
    ids = [c["id"] for c in p["cuts"]]
    assert ids == ["s1_1", "s1_2", "s2", "s3"]                 # a pause over pause_gap_open splits s1
    zooms = [c["zoom"] for c in p["cuts"]]
    assert zooms == [1.12, 1.22, 1.12, round(1.12 * 1.2, 3)]  # punch every second cut in a take; pickup factor
    assert p["cuts"][2]["tail"] == 0.24 and "tail" not in p["cuts"][0]
    assert p["width"] == 1920 and p["height"] == 1080 and p["fps"] == 25
    assert p["voice_filter"].startswith("pan=stereo|c0=c1|c1=c1,highpass")
    assert p["expected_script"] == "First part. Second part. From the pickup."
    assert p["cuts"][0]["speed"] == 1.1 and p["estimated_seconds"] > 0


def test_plan_problems_locked_range_music_and_unknown_take():
    cfg = _selects(music_seconds=2.0)
    cfg["takes"]["A"]["lock"] = [[149.0, 150.0, "hand at the camera"]]
    cfg["selects"].append({"id": "s4", "take": "Z", "start": 1, "end": 2, "text": "x"})
    _, problems = plan.make_plan(cfg, {"A": SIL}, {})
    text = " ".join(problems)
    assert "locked range" in text and "longer than the music" in text and "unknown take" in text


def test_plan_reads_taste_from_the_style_pack(studio):
    import json
    import shutil

    from crewcut import paths
    shutil.copytree(paths.neutral_pack_dir(), studio / "brand")
    es = json.loads((studio / "brand" / "edit-style.json").read_text())
    es["cut"] = {"speed": 1.1, "zoom_base": 1.12}
    (studio / "brand" / "edit-style.json").write_text(json.dumps(es))
    p, _ = plan.make_plan(_selects(), {"A": SIL, "B": []}, {"format": "portrait"})
    assert p["cuts"][0]["speed"] == 1.1 and p["cuts"][0]["zoom"] == 1.12
    assert (p["width"], p["height"]) == (1080, 1920)


def test_mic_channel_choice():
    assert plan.mic_for_takes({"mic_channel": 0}, {"A": 1}) == 0
    assert plan.mic_for_takes({}, {"A": 1, "B": 1}) == 1
    assert plan.mic_for_takes({}, {"A": 1, "B": None}) is None


# ---- pauses: a dense opening, natural pauses after it, one deliberate pause (26 Nov 2026) ----------------------
# Take A: s1 to 10.0 | pause 0.6 | s2 10.6-14.0 with inner pauses of 0.85 s (11.5) and 1.2 s (12.3) | pause 2.5 |
# s3 16.5-18.0 | pause 0.5 | s4 18.5-20.0
BODY_SIL = [(10.0, 10.6), (11.5, 12.35), (12.6, 13.8), (14.0, 16.5), (18.0, 18.5)]


def _body(**kw):
    cfg = {"version": "v001", "takes": {"A": {"source": "originals/a.MP4", "face": [0.5, 0.4]}},
           "selects": [{"id": "s1", "take": "A", "start": 5.0, "end": 10.0, "text": "Opening."},
                       {"id": "s2", "take": "A", "start": 10.6, "end": 14.0, "text": "First content."},
                       {"id": "s3", "take": "A", "start": 16.5, "end": 18.0, "text": "Before the key."},
                       {"id": "s4", "take": "A", "start": 18.5, "end": 20.0, "text": "The key sentence."}],
           "first_content": "s2"}
    cfg.update(kw)
    return cfg


def _cut(p, cid):
    return next(c for c in p["cuts"] if c["id"] == cid)


def test_the_opening_keeps_pauses_up_to_0_7_s_and_shortens_longer_ones():
    p, problems = plan.make_plan(_selects(), {"A": SIL, "B": []}, {})
    assert problems == [] and [c["id"] for c in p["cuts"]] == ["s1", "s2", "s3"]   # 0.59 s stays in the opening
    sil = SIL + [(149.6, 149.85)]
    p, _ = plan.make_plan(_selects(selects=[{"id": "s1", "take": "A", "start": 148.0, "end": 151.0, "text": "x"}],
                                   pause_gap_open=0.5), {"A": sil}, {})
    assert [c["id"] for c in p["cuts"]] == ["s1_1", "s1_2"]


def test_after_the_first_content_natural_pauses_up_to_a_second_stay():
    p, problems = plan.make_plan(_body(), {"A": BODY_SIL}, {})
    assert problems == []
    ids = [c["id"] for c in p["cuts"]]
    assert ids == ["s1", "s2_1", "s2_2", "s3", "s4"]          # only the 1.2 s pause inside s2 is shortened
    a, b = _cut(p, "s2_1"), _cut(p, "s2_2")
    assert abs((a["end"] - 12.6) + (13.8 - b["start"]) - 0.26) < 0.005
    assert a["start"] < 11.5 < a["end"]                        # the 0.85 s pause is inside the clip, untouched
    s4 = _cut(p, "s4")
    assert s4["start"] == _cut(p, "s3")["end"] and s4["join"] == 0.5   # the take's own 0.5 s pause between sentences
    assert _cut(p, "s2_1")["join"] == 0.6                      # into the first content: at most 0.7 s
    cfg = _body()
    cfg["selects"][1]["start"] = 10.8                          # a 0.8 s pause before the first content is too long
    p, _ = plan.make_plan(cfg, {"A": [(10.0, 10.8), *BODY_SIL[1:]]}, {})
    assert "join" not in _cut(p, "s2_1")
    assert p["pauses"] == {"opening_until": "s2", "open_max": 0.7, "keep_up_to": 1.0}


def test_without_a_mark_the_opening_is_the_first_25_seconds():
    p, _ = plan.make_plan(_body(first_content=None), {"A": BODY_SIL}, {})
    assert [c["id"] for c in p["cuts"]] == ["s1", "s2_1", "s2_2", "s2_3", "s3", "s4"]  # all 25 s: 0.85 s split too
    assert not any("join" in c for c in p["cuts"])
    assert p["pauses"]["opening_until"] == "25 s"
    p2, _ = plan.make_plan(_body(first_content=None, open_seconds=4), {"A": BODY_SIL}, {})
    assert [c["id"] for c in p2["cuts"]] == ["s1", "s2_1", "s2_2", "s3", "s4"]


def test_one_deliberate_pause_before_the_key_sentence():
    cfg = _body()
    cfg["selects"][3]["pause_before"] = 2.0                    # s3 -> s4: the take has only 0.5 s of silence
    p, problems = plan.make_plan(cfg, {"A": BODY_SIL}, {})
    assert problems == []
    s3, s4 = _cut(p, "s3"), _cut(p, "s4")
    gap = (s3["end"] - 18.0) + s3.get("tail", 0) + (18.5 - s4["start"])
    assert abs(gap - 2.0) < 0.01 and s4["pause_before"] == 2.0
    assert s3["tail"] > 1.0                                    # the rest is a held tail of the sentence before

    cfg = _body()
    cfg["selects"][2]["pause_before"] = 2.0                    # s2 -> s3: the take has 2.5 s of its own silence
    p, problems = plan.make_plan(cfg, {"A": BODY_SIL}, {})
    assert problems == []
    s2, s3 = _cut(p, "s2_2"), _cut(p, "s3")
    assert "tail" not in s2 and abs((s2["end"] - 14.0) + (16.5 - s3["start"]) - 2.0) < 0.01


def test_deliberate_pause_problems():
    cfg = _body()
    cfg["selects"][1]["pause_before"] = 2.0                    # s2 is the first content: allowed
    cfg["selects"][3]["pause_before"] = 2.0
    _, problems = plan.make_plan(cfg, {"A": BODY_SIL}, {})
    assert any("more than one deliberate pause" in x for x in problems)
    cfg = _body()
    cfg["selects"][3]["pause_before"] = 4.0
    _, problems = plan.make_plan(cfg, {"A": BODY_SIL}, {})
    assert any("outside 1.5 to 3" in x for x in problems)
    cfg = _body(first_content="s4")
    cfg["selects"][2]["pause_before"] = 2.0
    _, problems = plan.make_plan(cfg, {"A": BODY_SIL}, {})
    assert any("does not belong in the opening" in x for x in problems)
    _, problems = plan.make_plan(_body(first_content="nope"), {"A": BODY_SIL}, {})
    assert any("first_content 'nope'" in x for x in problems)


def test_verify_accepts_planned_pauses_and_still_catches_wrong_ones():
    joins = [{"pause": 0.3}, {"pause": 0.62, "planned": 0.6}, {"pause": 2.1, "planned": 2.0},
             {"pause": 0.8}, {"pause": 1.4, "planned": 2.0}]
    bad = verify.bad(joins, 0.17, 0.45)
    assert bad == [{"pause": 0.8}, {"pause": 1.4, "planned": 2.0}]
    assert verify.planned({"join": 0.5}) == 0.5 and verify.planned({"pause_before": 2.0}) == 2.0
    assert verify.planned({}) is None
