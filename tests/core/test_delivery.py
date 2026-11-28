"""The delivery guide and the reading version of a script (crewcut/delivery.py)."""

import sys

import pytest

from crewcut import delivery, episodes, paths, stylegate

SCRIPT = """Ein Gratis-Tool hat aus drei Videos neun Clips gemacht. Ich habe es gegen OpusClip laufen lassen.

Punkt eins. Das Tool verspricht zwei Minuten, und bei mir waren es elf. [beide Uhren nebeneinander] Die KI hat 24/7 gerechnet.

Schnell ist es nicht. Billig schon.

---
Notizen: Quelle work/material-v001.md
"""

READING = """Ein Gratis-Tool hat aus DREI Videos / NEUN Clips gemacht. Ich habe es gegen OpusClip laufen lassen.

Punkt eins. Das Tool verspricht ZWEI Minuten, / und bei mir waren es // ELF. [beide Uhren nebeneinander] Die KI hat 24/7 gerechnet.

Schnell ist es NICHT. // BILLIG schon.

---
andere Notizen, die nicht zählen
"""


@pytest.fixture
def files(tmp_path):
    s = tmp_path / "SCRIPT-v001.md"
    s.write_text(SCRIPT)
    r = tmp_path / "LESEN-SCRIPT-v001.md"
    r.write_text(READING)
    return s, r


CFG = {"reading_prefix": "LESEN-", "reading_max_stress": 2, "delivery_guide": None}


def test_a_reading_version_with_the_same_words_and_marks_passes(files):
    s, r = files
    res = delivery.check(r, cfg=CFG)
    assert res["pass"] is True, res["problems"]
    assert res["script"] == str(s)
    # KI is in capitals in the script too, so it is no stress; 24/7 is a word of the script, not a mark
    assert res["stats"] == {"sentences": 7, "stressed": 6, "pauses": 2, "long_pauses": 2}


def test_a_changed_word_fails_with_the_place(files):
    s, r = files
    r.write_text(READING.replace("NEUN Clips", "ZEHN Clips"))
    res = delivery.check(r, cfg=CFG)
    assert res["pass"] is False
    assert "word 7" in res["problems"][0]["why"] and "neun" in res["problems"][0]["why"].lower()


@pytest.mark.parametrize("change, why", [
    (("Schnell ist es NICHT.", "SCHNELL IST ES NICHT."), "stressed words in one sentence"),
    (("ZWEI Minuten, / und", "ZWEI Minuten, // und"), "long pauses in one paragraph"),
    (("Ein Gratis-Tool", "/ Ein Gratis-Tool"), "never at the start or the end"),
    (("[beide Uhren nebeneinander]", "[beide / Uhren nebeneinander]"), "inside a [picture cue]"),
    (("Videos / NEUN", "Videos/ NEUN"), "stands alone"),
    (("Videos / NEUN", "Videos / / NEUN"), "two pause marks in a row"),
])
def test_marks_a_speaker_cannot_follow_fail(files, change, why):
    s, r = files
    r.write_text(READING.replace(*change))
    res = delivery.check(r, cfg=CFG)
    assert res["pass"] is False and any(why in p["why"] for p in res["problems"]), res["problems"]


def test_no_marks_and_no_script_fail(files, tmp_path):
    s, r = files
    r.write_text(SCRIPT)
    assert any("no marks" in p["why"] for p in delivery.check(r, cfg=CFG)["problems"])
    orphan = tmp_path / "LESEN-SCRIPT-v009.md"
    orphan.write_text(READING)
    assert any("no script" in p["why"] for p in delivery.check(orphan, cfg=CFG)["problems"])


def test_names_and_marks():
    assert delivery.reading_name("SCRIPT-v002.md", CFG) == "LESEN-SCRIPT-v002.md"
    assert delivery.reading_name("SCRIPT-v002.md", {"reading_prefix": None}) is None
    assert delivery.script_of(paths.Path("/x/LESEN-SHORT-v003.md"), CFG).name == "SHORT-v003.md"
    assert delivery.strip_marks("Das / war // ELF.") == "Das war ELF."


@pytest.fixture
def episode(studio, crew):
    ep = episodes.create("Clips im Test")["id"]
    for s in ("idea", "title"):
        episodes.set_step(ep, s, "done")
    episodes.set_step(ep, "script", "working")
    return ep


def _config(studio, extra=""):
    (studio / "config").mkdir(exist_ok=True)
    (studio / "config" / "crewcut.toml").write_text('[style_gate]\nreading_prefix = "LESEN-"\n' + extra)


def test_no_glob_mistakes_the_reading_version_for_the_script(studio, episode):
    from crewcut import prompter
    _config(studio)
    brief = paths.episode_dir(episode) / "brief"
    (brief / "SCRIPT-v001.md").write_text(SCRIPT)
    (brief / "LESEN-SCRIPT-v001.md").write_text(READING)
    (brief / "DREHZETTEL-v001.md").write_text("# Einstieg\n\nEin Satz.\n")
    assert stylegate.latest(episode)["SCRIPT"].name == "DREHZETTEL-v001.md"
    assert delivery.newest_full_script(episode).name == "SCRIPT-v001.md"
    assert prompter.script_file(episode).name == "DREHZETTEL-v001.md"


def test_the_writer_is_asked_for_the_reading_version_until_it_passes(studio, episode):
    brief = paths.episode_dir(episode) / "brief"
    (brief / "SCRIPT-v001.md").write_text(SCRIPT)
    assert delivery.writer_task(episode) == ""                  # no prefix: no reading version
    _config(studio)
    task = delivery.writer_task(episode)
    assert "brief/LESEN-SCRIPT-v001.md" in task and "crewcut voice reading" in task and "CAPITALS" in task
    (brief / "LESEN-SCRIPT-v001.md").write_text(READING.replace("NEUN", "ZEHN"))
    assert delivery.writer_task(episode)                         # it fails: asked again
    (brief / "LESEN-SCRIPT-v001.md").write_text(READING)
    assert delivery.writer_task(episode) == ""


PASSING_CHECKER = '''
import json
print(json.dumps({"version": 1, "pass": True, "auto_pass": True, "kritik_offen": [],
                  "checks": [{"id": "S1", "kind": "auto", "pass": True}]}))
'''


def test_the_gate_puts_the_reading_version_before_the_card(studio, episode):
    from crewcut.conductor import queue
    d = studio / "skills" / "deutscher-hormozi" / "scripts"
    d.mkdir(parents=True)
    (d.parent / "SKILL.md").write_text("---\nname: deutscher-hormozi\ndescription: test\n---\n")
    (d / "stil_check.py").write_text(PASSING_CHECKER)
    _config(studio)
    (paths.episode_dir(episode) / "brief" / "SCRIPT-v001.md").write_text(SCRIPT)
    v = stylegate.check(episode)
    out = stylegate.ready(episode, v, "Done.")
    task = queue.get(out["job"])["task"]
    assert "First write the reading version brief/LESEN-SCRIPT-v001.md" in task
    assert task.index("LESEN-SCRIPT-v001.md") < task.index("Then propose your script card")


def test_the_voice_block_names_the_delivery_guide(studio, episode):
    from crewcut.conductor import prompts
    assert prompts.voice_block() == ""
    (studio / "brand").mkdir(exist_ok=True)
    (studio / "brand" / "SPRECHWEISE.md").write_text("# Sprechweise\n")
    _config(studio, 'delivery_guide = "brand/SPRECHWEISE.md"\n')
    block = prompts.voice_block()
    assert "delivery guide" in block and "SPRECHWEISE.md" in block and "no delivery marks in a script" in block


def test_the_command_line(files, studio, monkeypatch, capsys):
    from crewcut import cli
    s, r = files
    monkeypatch.setattr(sys, "argv", ["crewcut"])
    assert cli.main(["voice", "reading", str(r)]) == 0          # the prefix comes from the file name
    assert "PASS" in capsys.readouterr().out
    r.write_text(READING.replace("NEUN", "ZEHN"))
    assert cli.main(["voice", "reading", str(r)]) == 1
    assert cli.main(["voice", "reading", str(r.parent / "missing.md")]) == 2
