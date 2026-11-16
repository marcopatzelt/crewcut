"""Take selection: last full attempt wins, spoken instructions win, differences and pickups are listed."""

from crewcut.cut import takes

SCRIPT = """# Working title

> So I built the tool myself. It saves me an hour every week.

[Demo: the dashboard]

That is the whole story.

---
Notes for the editor, not spoken.
"""


def rows(*items):
    return [{"start": a, "end": b, "text": t} for a, b, t in items]


def test_script_text_keeps_only_spoken_words():
    t = takes.script_text(SCRIPT)
    assert t == "So I built the tool myself. It saves me an hour every week. That is the whole story."
    assert takes.sentences(t)[1] == "It saves me an hour every week."


def test_last_full_attempt_wins_and_broken_start_is_skipped():
    a = rows((0.0, 0.9, "So I built"), (1.3, 3.2, "So I built the tool myself."),
             (3.6, 5.8, "It saves me an hour every week."), (6.2, 8.4, "It saves me an hour every week."),
             (9.0, 10.5, "That is the whole story."))
    r = takes.choose(SCRIPT, [("A", a)])
    s1 = r["sentences"][0]
    assert [x["verdict"] for x in s1["attempts"]] == ["broken", "full"] and s1["chosen"] == 2
    assert r["sentences"][1]["chosen"] == 2 and r["sentences"][1]["why"] == "last full attempt"
    sel = r["selects"]
    assert (sel[0]["start"], sel[0]["end"]) == (1.3, 3.2)
    assert (sel[1]["id"], sel[1]["start"], sel[1]["end"]) == ("s02-03", 6.2, 10.5)   # said in one go
    assert r["pickups"] == [] and r["instructions"] == []


def test_later_take_wins_over_earlier_take():
    a = rows((0.0, 2.0, "So I built the tool myself."))
    b = rows((5.0, 7.0, "So I built the tool myself."))
    r = takes.choose("So I built the tool myself.", [("A", a), ("B", b)])
    assert r["selects"][0]["take"] == "B"


def test_scratch_that_discards_the_attempt_before():
    a = rows((0.0, 2.0, "It saves me an hour every week."), (2.1, 2.9, "Scratch that."),
             (3.0, 3.5, "Um."))
    r = takes.choose("It saves me an hour every week.", [("A", a)])
    assert r["sentences"][0]["attempts"][0]["verdict"] == "scratched"
    assert r["selects"] == [] and r["pickups"][0]["sentence"] == 1
    assert r["instructions"][0]["kind"] == "scratch"


def test_take_the_first_version():
    a = rows((0.0, 2.0, "It saves me an hour every week."), (2.5, 4.5, "It saves me an hour every week."),
             (5.0, 6.2, "Take the first version."))
    r = takes.choose("It saves me an hour every week.", [("A", a)])
    assert r["sentences"][0]["chosen"] == 1 and r["selects"][0]["start"] == 0.0
    assert "first full attempt" in r["sentences"][0]["why"]


def test_german_instructions_work_too():
    a = rows((0.0, 2.0, "Das spart mir jede Woche eine Stunde."), (2.5, 4.5, "Das spart mir jede Woche eine Stunde."),
             (5.0, 6.0, "Die erste Version passt."), (6.5, 8.0, "Den Teil mit der Rechnung."),
             (8.2, 9.9, "Den würde ich rausnehmen."))
    r = takes.choose("Das spart mir jede Woche eine Stunde. Den Teil mit der Rechnung.", [("A", a)])
    assert r["sentences"][0]["chosen"] == 1
    assert r["sentences"][1]["chosen"] is None and "left out" in r["sentences"][1]["why"]
    assert [s["id"] for s in r["selects"]] == ["s01"]


def test_keep_pins_an_attempt():
    a = rows((0.0, 2.0, "It saves me an hour every week."), (2.2, 3.0, "Keep that."),
             (3.5, 5.5, "It saves me an hour every week."))
    r = takes.choose("It saves me an hour every week.", [("A", a)])
    assert r["sentences"][0]["chosen"] == 1


def test_what_was_said_wins_with_script_spelling():
    a = rows((0.0, 2.4, "it saves me about an hour every single week"))
    r = takes.choose("It saves me an hour every week.", [("A", a)])
    sel = r["selects"][0]
    assert sel["text"] == "It saves me about an hour every single week."
    assert sel["script"] == "It saves me an hour every week."
    assert len(r["sentences"][0]["differences"]) == 2


def test_never_said_goes_on_the_pickup_list():
    r = takes.choose("One sentence here. Another sentence there.", [("A", rows((0, 1.5, "One sentence here.")))])
    assert r["pickups"] == [{"sentence": 2, "text": "Another sentence there.", "why": "never said"}]


def test_sentences_said_in_one_go_stay_one_select_and_edges_inside_islands_are_marked():
    a = rows((0.0, 3.1, "Hello everyone. Today I build a small tool."), (3.5, 4.6, "And a third one."),
             (5.0, 6.0, "Noise words here"), (6.3, 7.0, "Last one."))
    r = takes.choose("Hello everyone. Today I build a small tool. And a third one. Last one.", [("A", a)])
    first, last = r["selects"]
    assert first["id"] == "s01-03" and (first["start"], first["end"]) == (0.0, 4.6) and "check" not in first
    assert last["id"] == "s04"
    r2 = takes.choose("Today I build a small tool.", [("A", a)])
    assert r2["selects"][0]["check"] == ["start"] and r2["selects"][0]["start"] > 0.0


def test_an_empty_island_between_sentences_keeps_them_apart():
    a = rows((0.0, 1.0, "First sentence."), (1.4, 2.5, ""), (2.9, 4.0, "Second sentence."))
    r = takes.choose("First sentence. Second sentence.", [("A", a)])
    assert [s["id"] for s in r["selects"]] == ["s01", "s02"]


def test_selects_file_and_take_ids():
    assert takes.take_ids(3) == ["A", "B", "C"] and takes.take_ids(28)[26:] == ["AA", "AB"]
    r = takes.choose("One two three.", [("A", rows((0, 1, "One two three.")))])
    f = takes.selects_file("v001", ["originals/a.MP4"], r, "brief/SCRIPT-v001.md")
    assert f["takes"]["A"]["source"] == "originals/a.MP4" and f["selects"][0]["take"] == "A"
    assert "brief/SCRIPT-v001.md" in f["note"]
    assert "S01" in takes.describe(r)
