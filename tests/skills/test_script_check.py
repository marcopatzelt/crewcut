from conftest import load_script

sc = load_script("skills/script/scripts/script_check.py")

GOOD = """


Ollama runs five local models on one laptop for 0 euros.
I measured all five on the same task.



Here is the problem it tries to solve.
Cloud models cost money for every request.

---
notes for the edit: screen recording of the terminal
"""


def kinds(r, level=None):
    return [f["area"] for f in r["findings"] if level is None or f["level"] == level]


def test_spoken_part_stops_at_rule():
    assert "notes for the edit" not in sc.spoken_part(GOOD)


def test_good_script_has_no_error(neutral):
    r = sc.check_script(GOOD, neutral, title="Five models for 0 euros", names=["Ollama"])
    assert r["errors"] == 0, r["findings"]
    assert r["stats"]["parts"] == 2


def test_form_errors(neutral):
    text = "# Intro\n\n[camera close]\nAt 0:30 we cut.\n- a list item\n"
    r = sc.check_script(text, neutral)
    msgs = " ".join(f["text"] for f in r["findings"] if f["level"] == "error")
    assert "heading" in msgs and "bracket" in msgs and "timestamp" in msgs and "list" in msgs


def test_long_sentence_and_tech_words(neutral):
    long = " ".join(["word"] * 30) + "."
    r = sc.check_script(long + " Then run setup.py --force.", neutral)
    assert "sentences" in kinds(r, "error") and "words" in kinds(r, "error")


def test_title_number_and_name_follow_the_pack(neutral, striq):
    text = "This tool is fast.\nIt helps.\n"
    r = sc.check_script(text, neutral, title="Ollama saves 90 %", names=["Ollama"])
    assert any(f["area"] == "opening" and f["level"] == "warn" for f in r["findings"])
    assert any(f["area"] == "opening" and f["level"] == "error" for f in r["findings"])
    s = sc.check_script(text, striq, title="Claude spart 90 %")
    assert any(f["area"] == "opening" and f["level"] == "error" and "90" in f["text"] for f in s["findings"])


def test_striq_closing_line_and_end_mention(striq):
    text = "Claude spart 90 Prozent.\nDas Ganze habe ich getestet.\n\nDas war es.\n"
    r = sc.check_script(text, striq, names=["Claude"])
    ending = [f for f in r["findings"] if f["area"] == "ending"]
    assert len(ending) == 2
    ok = text.replace("Das war es.", "Das baue ich mit STRIQ für Firmen. Und danke fürs Zuschauen.")
    r = sc.check_script(ok, striq, names=["Claude"])
    assert not [f for f in r["findings"] if f["area"] == "ending"]


def test_voice_words(neutral):
    neutral.voice = "## Words to avoid\n- basically\n- delve*\n\n## Words to use\n- in fact\n"
    r = sc.check_script("We delved into it. Basically it works.\n", neutral)
    assert "voice" in kinds(r, "error")
    assert "voice" in kinds(r, "hint")


def test_numbers_need_proof(neutral):
    r = sc.check_script("It saved 42 % and took 17 minutes. Two runs.\n", neutral, proof="saving: 42 %")
    warn = [f["text"] for f in r["findings"] if f["area"] == "proof"]
    assert warn and "17" in warn[0] and "42" not in warn[0]


def test_repetition_hints(neutral):
    text = "And then I tried A.\n\nAnd then I tried B.\n\nAnd then I tried C.\n\nThe tool works very well indeed. " \
           "The tool works very well indeed.\n"
    r = sc.check_script(text, neutral)
    assert kinds(r, "hint").count("structure") == 2


def test_length_error_when_far_too_long(neutral):
    text = "\n\n".join(["This is a short sentence with seven words."] * 200)
    r = sc.check_script(text, neutral)
    assert "length" in kinds(r, "error")


def test_sentences_keep_abbreviations():
    assert len(sc.sentences("Use a tool, e.g. this one. Then stop.")) == 2


def test_main(tmp_path, capsys):
    p = tmp_path / "SCRIPT-v001.md"
    p.write_text(GOOD, encoding="utf-8")
    assert sc.main([str(p), "--pack", "packs/neutral"]) == 0
    assert sc.main([str(p), "--text-only"]) == 0
    assert "notes for the edit" not in capsys.readouterr().out
    assert sc.main([str(tmp_path / "missing.md")]) == 2


MARKED = GOOD + """[[motion: number | "five local models"]]
[[motion: compare | "Cloud models cost money for every request"]]
"""


def test_motion_marks_below_the_line_are_counted(neutral):
    marks = sc.motion_marks(MARKED)
    assert [(m["kind"], m["below"]) for m in marks] == [("number", True), ("compare", True)]
    assert marks[0]["words"] == "five local models"
    r = sc.check_script(MARKED, neutral, title="Five models for 0 euros", names=["Ollama"])
    assert r["errors"] == 0, r["findings"]
    assert r["stats"]["motion_marks"] == 2
    assert any(p.startswith("motion marks: 2") for p in r["passed"])
    assert "motion" not in kinds(r)


def test_motion_mark_above_the_line_is_an_error_once(neutral):
    text = 'Ollama runs five local models. [[motion: number | "five local models"]]\n\n---\nnotes\n'
    r = sc.check_script(text, neutral)
    errors = [f for f in r["findings"] if f["level"] == "error"]
    assert [f["area"] for f in errors] == ["motion"] and "above the --- line" in errors[0]["text"]
    assert r["stats"]["motion_marks"] == 0


def test_more_than_five_motion_marks_and_loose_marks(neutral):
    six = GOOD + "".join('[[motion: number | "five local models"]]\n' for _ in range(6))
    r = sc.check_script(six, neutral)
    assert r["stats"]["motion_marks"] == 6
    assert any(f["area"] == "motion" and f["level"] == "error" and "at most 5" in f["text"] for f in r["findings"])
    loose = GOOD + "[[motion: number]]\n[[motion: quote | \"words nobody says\"]]\n"
    r = sc.check_script(loose, neutral)
    assert ("warn", "motion") in [(f["level"], f["area"]) for f in r["findings"]]
    assert any(f["area"] == "motion" and f["level"] == "hint" and "nobody says" in f["text"] for f in r["findings"])


def test_short_counts_motion_marks_too(neutral):
    text = "I tried it.\n\n---\n" + "".join('[[motion: number | "tried"]]\n' for _ in range(6))
    r = sc.check_short(text, neutral)
    assert r["stats"]["motion_marks"] == 6
    assert any(f["area"] == "motion" and f["level"] == "error" for f in r["findings"])


INTERVIEW = """# Interview: Example

## Answers

### Answer 1 (message 12, 2026-11-22)

I measured all five on the same task and one laptop was enough.

## Do not mention (hard rules)

- none
"""


def test_interview_lines_are_marked_and_traced(neutral):
    r = sc.check_script(GOOD, neutral, interview=INTERVIEW)
    assert "interview" in kinds(r, "error")                     # no mark below the line
    marked = GOOD + '[[interview: 1 | "I measured all five on the same task"]]\n'
    r = sc.check_script(marked, neutral, interview=INTERVIEW)
    assert "interview" not in kinds(r), r["findings"]
    assert r["stats"]["interview_marks"] == 1 and r["stats"]["interview_sentences"] == 1
    loose = GOOD + '[[interview: 1 | "words nobody says"]]\n'
    assert "interview" in kinds(sc.check_script(loose, neutral, interview=INTERVIEW), "warn")
    assert "interview_marks" not in sc.check_script(GOOD, neutral)["stats"]   # only with --interview


def test_colons_slashes_and_brackets_are_errors_in_every_mode(neutral):
    text = "Ollama runs five models: all local.\nCost/benefit (roughly) is good.\n\n---\nShots: terminal\n"
    long = {f["text"].split(":")[0] for f in sc.check_script(text, neutral)["findings"] if f["area"] == "speak"}
    assert {"a colon", "a slash", "a bracket"} <= long
    assert any(f["area"] == "speak" for f in sc.check_short(text, neutral, "en")["findings"] if f["level"] == "error")


def test_spoken_mode_runs_only_speak_and_story(tmp_path, capsys):
    f = tmp_path / "SCRIPT-v001.md"
    f.write_text("Here is the result: 35 cents.\n")
    assert sc.main([str(f), "--spoken"]) == 1
    assert "a colon" in capsys.readouterr().out
    f.write_text("Here is the result. It cost 35 cents.\n")
    assert sc.main([str(f), "--spoken"]) == 0
