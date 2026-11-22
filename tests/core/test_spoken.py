"""The spoken-text check, the list-smell heuristic, the script-card gate, the prompter cut and the model per step."""

import re
from pathlib import Path

import pytest

from crewcut import approvals, db, engines, episodes, prompter, spoken

STORY_MD = Path(__file__).resolve().parents[2] / "skills" / "script" / "references" / "story.md"


def example(which: str) -> str:
    """The list and the story of the example pair in skills/script/references/story.md."""
    blocks = re.findall(r"```\n(.*?)```", STORY_MD.read_text(encoding="utf-8"), re.S)
    return blocks[-2] if which == "list" else blocks[-1]


def kinds(text: str) -> set[str]:
    return {f["kind"] for f in spoken.speakable(text)}


def test_marks_that_do_not_read_aloud():
    text = ("Das Ergebnis: rund 35 Cent.\nErst das; dann das.\nDie Karte (eine 4090) rechnet.\nKosten/Nutzen.\n"
            "Rohmaterial -> Schnitt.\n[Kamera nah]\n# Teil 2\n- ein Punkt\nUm 10:30 ging es los.\n")
    assert kinds(text) >= {"colon", "semicolon", "bracket", "slash", "arrow", "heading", "list", "timestamp"}
    assert "colon" not in kinds("Um 10:30 ging es los.\n")          # the timestamp alone, not also a colon


def test_clean_spoken_text_and_notes_below_the_line_pass():
    text = "Ich habe es gemessen. Es dauerte **35 Minuten**.\n\n---\nShots: Karte (4090), Kosten/Zeit -> Grafik\n"
    assert spoken.speakable(text) == []
    spoken.require_speakable(text)


def test_a_notes_section_above_the_line_is_found_and_the_prompter_drops_it():
    text = ("Claude mietet sich eine Grafikkarte.\n\nBildideen (nicht vorlesen):\nKarte groß, dann Kostenbuch.\n\n"
            "---\nNotizen\n")
    assert "notes" in kinds(text)
    shown = prompter.parse_script(text)
    assert [b["text"] for b in shown] == ["Claude mietet sich eine Grafikkarte."]
    # a spoken sentence that starts with a section word is not a heading
    assert "notes" not in kinds("Ich rede.\n\nShots wie dieser kosten Zeit.\n")
    with pytest.raises(spoken.Unspeakable):
        spoken.require_speakable(text)


def test_list_smell_tells_the_list_from_the_story():
    lst, story = spoken.list_smell(example("list")), spoken.list_smell(example("story"))
    assert lst["share"] >= spoken.SMELL_ERROR or lst["longest_run"] >= 3
    assert story["share"] < spoken.SMELL_WARN
    levels = {f["level"] for f in spoken.story(example("list")) if "list smell" in f["text"]}
    assert levels == {"error"}
    assert not [f for f in spoken.story(example("story")) if f["level"] == "error"]


def test_a_bridge_ties_a_paragraph_to_the_one_before():
    assert spoken.bridged("Der Laptop braucht sieben Stunden.", "Deshalb miete ich eine Karte.", "de")
    assert spoken.bridged("Der Laptop braucht sieben Stunden.", "Mein Laptop ist zu langsam.", "de")
    assert not spoken.bridged("Der Laptop braucht sieben Stunden.", "Victor ist 19 Jahre alt.", "de")


def test_story_plan_staged_run_ups_and_the_subscribe_line():
    p = spoken.plan(example("story"))
    assert p["premise"] and len(p["beats"]) == 4 and not p["problems"]
    assert set(p["arc_parts"]) == {"hook", "tension", "turn", "payoff", "close"}
    assert spoken.plan("Text.\n---\nPrämisse: Eine Sache.\nBogen: Einstieg, Problem, Wende, Auflösung, Schluss\n"
                       "Beats: GPU; Wiese; Victor\n")["problems"] == []
    assert "jetzt kommt der teil" in " ".join(spoken.staged("Und jetzt kommt der Teil, der alles ändert.", "de"))
    cut = ("Eins.\n\nIch miete eine Karte.\n\nAbonnier den Kanal.\n\nDabei schaut Claude sich jedes Bild an.\n\n"
           "Drei.\n\nEnde hier.\n")
    assert any("cuts a beat" in m for m in spoken.subscribe_place(cut, "de"))
    assert spoken.subscribe_place("Eins.\n\nZwei.\n\nAbonnier den Kanal.\n\nDrei.\n\nVier.\n", "de") == []


@pytest.fixture
def ep(crew, monkeypatch):
    from crewcut import extskills
    monkeypatch.setattr(extskills, "humanizer_enabled", lambda: False)
    return episodes.create("Spoken gate")["id"]


def test_the_script_card_refuses_marks_and_lists_but_takes_a_story(ep, studio):
    f = studio / "episodes" / ep / "brief" / "SCRIPT-v001.md"
    f.write_text("Das Ergebnis: rund 35 Cent.\n")
    with pytest.raises(spoken.Unspeakable, match="colon"):
        approvals.propose(ep, "script", "script", "Script", file="brief/SCRIPT-v001.md")
    f.write_text(example("list"))
    with pytest.raises(spoken.Unspeakable, match="list"):
        approvals.propose(ep, "script", "script", "Script", file="brief/SCRIPT-v001.md")
    f.write_text(example("story"))
    assert approvals.propose(ep, "script", "script", "Script", file="brief/SCRIPT-v001.md")["status"] == "open"


def test_a_long_script_needs_its_story_plan(ep, studio):
    f = studio / "episodes" / ep / "brief" / "SCRIPT-v002.md"
    f.write_text(example("story").split("\n---\n")[0] + "\n")
    with pytest.raises(spoken.Unspeakable, match="premise"):
        approvals.propose(ep, "script", "script", "Script", file="brief/SCRIPT-v002.md")


def _engine_config(studio, text: str) -> None:
    (studio / "config").mkdir(exist_ok=True)
    (studio / "config" / "crewcut.toml").write_text(text)


def test_model_per_step_and_role_with_the_probe_fallback(studio):
    writer, editor = {"id": "writer", "model": "plan"}, {"id": "editor", "model": "work"}
    assert engines.model_for(writer, "script", "claude") == "opus"        # the default: writing steps on Opus
    assert engines.model_for(editor, "edit", "claude") is None             # the engine's own default
    _engine_config(studio, '[engine.claude]\nplan_model = "sonnet"\nrole_models = {editor = "haiku"}\n'
                           'step_models = {script = "claude-opus-5-5"}\n')
    assert engines.model_for(writer, "script", "claude") == "claude-opus-5-5"
    assert engines.model_for(writer, "edit", "claude") == "sonnet"
    assert engines.model_for(editor, "script", "claude") == "haiku"      # the role wins over the step
    db.kv_set(engines.MODEL_PROBE, '{"claude": {"claude-opus-5-5": false}}')
    assert engines.model_for(writer, "script", "claude") == "sonnet"      # not on this plan: the tier model
    assert set(engines.configured_models("claude")) == {"opus", "claude-opus-5-5", "haiku"}  # idea, title: default


def test_subagents_inherit_the_callers_model(crew, tmp_path):
    from crewcut import plugin
    d = plugin.build(tmp_path / "plugin" / "crewcut")
    assert "model: inherit" in (d / "agents" / "critic.md").read_text(encoding="utf-8")
