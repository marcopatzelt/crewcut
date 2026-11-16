"""SRT from the speaker cut: groups of split selects, block and line limits, word-snapped borders, time format."""

from crewcut.cut import srt

MANIFEST = {"fps": 25, "clips": [
    {"id": "a_1", "expected_text": "First part of a sentence.", "timeline_in_frame": 0, "timeline_out_frame": 50},
    {"id": "a_2", "expected_text": "First part of a sentence.", "timeline_in_frame": 50, "timeline_out_frame": 75},
    {"id": "b", "expected_text": "Second.", "timeline_in_frame": 75, "timeline_out_frame": 100},
]}


def test_split_selects_are_one_group():
    g = srt.groups(MANIFEST)
    assert [(x["id"], x["start"], x["end"]) for x in g] == [("a", 0.0, 3.0), ("b", 3.0, 4.0)]


def test_blocks_and_lines_stay_short():
    text = ("This is a long sentence that keeps going, and it goes on and on until it needs a second block, "
            "because nobody can read that much at once.")
    parts = srt.blocks(text)
    assert len(parts) == 3 and all(len(p) <= 84 for p in parts)
    assert parts[0].endswith(",")
    for p in parts:
        assert all(len(line) <= 42 or " " not in line for line in srt.lines(p).split("\n"))
        assert srt.lines(p).count("\n") <= 1


def test_time_format_rounds_into_the_next_second():
    assert srt.stamp(3723.4567) == "01:02:03,457"
    assert srt.stamp(1.9996) == "00:00:02,000"


def test_cues_and_render():
    cues = srt.cues(MANIFEST)
    assert [round(a, 2) for a, _, _ in cues] == [0.05, 3.05]
    out = srt.render(cues)
    assert out.startswith("1\n00:00:00,050 --> 00:00:02,950\nFirst part of a sentence.\n\n2\n")


def test_borders_snap_to_word_times():
    text = ("We measured everything on the laptop first, then on a rented card for comparison. "
            "The rented card was nine times faster.")
    m = {"fps": 25, "clips": [{"id": "x", "expected_text": text, "timeline_in_frame": 0, "timeline_out_frame": 250}]}
    words = [{"w": "The", "s": 5.3, "e": 5.4}, {"w": "The", "s": 9.9, "e": 10.0}]
    cues = srt.cues(m, words)
    assert len(cues) == 2 and abs(cues[0][1] - (5.3 - 0.04)) < 1e-9 and abs(cues[1][0] - 5.28) < 1e-9
