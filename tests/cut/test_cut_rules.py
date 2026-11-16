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
    p, problems = plan.make_plan(_selects(zoom_base=1.12, zoom_punch=1.22, speed=1.1), {"A": SIL, "B": []},
                                 {"format": "landscape", "fps": 25}, mic=1)
    assert problems == []
    ids = [c["id"] for c in p["cuts"]]
    assert ids == ["s1_1", "s1_2", "s2", "s3"]                 # the long pause splits s1
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
