"""Doubled sentence starts inside a select: a short broken attempt, a pause, the same start again."""

from crewcut.cut import doubles

CFG = {"takes": {"A": {"source": "originals/a.MP4"}},
       "selects": [{"id": "set6", "take": "A", "start": 174.77, "end": 181.0, "text": "So I built it myself."},
                   {"id": "set7", "take": "A", "start": 190.0, "end": 196.0, "text": "A long sentence."}]}
ISLANDS = {"A": [{"start": 174.77, "end": 175.62, "text": ""}, {"start": 175.84, "end": 181.0, "text": ""},
                 {"start": 190.0, "end": 193.5, "text": ""}, {"start": 193.8, "end": 196.0, "text": ""}]}


def test_candidates_are_short_pieces_followed_inside_the_select():
    c = doubles.candidates(CFG, ISLANDS)
    assert c == [{"select": "set6", "take": "A", "a": 174.77, "b": 175.62, "c": 175.84, "d": 181.0}]


def test_double_start_is_found_with_the_fix():
    texts = {174.77: "So I built", 175.84: "So I built it myself."}
    rows = doubles.check(CFG, ISLANDS, lambda take, a, b: texts[a])
    assert rows[0]["double"] and rows[0]["fix"] == "begin the select set6 at 175.84"
    assert "1 doubled starts" in doubles.describe(rows)


def test_different_start_is_fine():
    assert not doubles.is_double("So then", "So I built it")
    assert not doubles.is_double("", "")
    assert doubles.is_double("Deshalb habe ich", "deshalb, habe ich das gebaut")


def test_fast_check_on_a_words_list():
    words = [{"w": "So", "s": 10.0, "e": 10.2}, {"w": "I", "s": 10.25, "e": 10.3}, {"w": "built", "s": 10.35, "e": 10.6},
             {"w": "So", "s": 11.0, "e": 11.2}, {"w": "I", "s": 11.25, "e": 11.3}, {"w": "built", "s": 11.35, "e": 11.6},
             {"w": "it.", "s": 11.65, "e": 11.9}]
    found = doubles.in_words(words, 9.9, 12.0)
    assert len(found) == 1 and found[0]["c"] == 11.0
    assert doubles.in_words(words[3:], 9.9, 12.0) == []
