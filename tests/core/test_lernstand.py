"""The learning loop (crewcut/lernstand.py) and what the Writer is told about the voice (conductor/prompts.py).

A synthetic studio: two episodes with the Critic's answers, a second opinion, a review report and retention units."""

import json

import pytest

from crewcut import approvals, episodes, lernstand, paths, stylegate
from crewcut.conductor import prompts


def kritik(sentences=(), units=(), done=(), k=None) -> dict:
    return {"hormozi_kritik": {"saetze": list(sentences), "einheiten": list(units), "vorherige_funde": list(done)},
            **(k or {})}


@pytest.fixture
def studio_data(studio):
    e1 = studio / "episodes" / "001-first" / "brief"
    e2 = studio / "episodes" / "002-second" / "brief"
    e1.mkdir(parents=True)
    e2.mkdir(parents=True)
    (e1 / "CUES-v001.kritik.json").write_text(json.dumps(kritik(
        sentences=[{"text": "Short explanation of the term.", "wert": False, "pruefrage": "P-S1",
                    "grund": "explains instead of showing", "neu": "Show the counter."},
                   {"text": "A line that is fine.", "wert": True, "pruefrage": "P-S1"}],
        units=[{"einheit": 1, "punch_belohnt": False, "als_short": False, "grund": "the punch repeats the hook"}],
        k={"K-FA": {"antwort": False, "grund": "a number is not in the material"}})))
    (e1 / "CUES-v002.kritik.json").write_text(json.dumps(kritik(
        sentences=[{"text": "Another explanation.", "wert": False, "pruefrage": "P-S1; KRITIK 2",
                    "grund": "explains"}],
        done=[{"text": "Short explanation of the term. (round 1)", "status": "erledigt",
               "wie": "The counter is on screen now; the sentence is gone."}])))
    (e2 / "SCRIPT-v001.kritik.json").write_text(json.dumps(kritik(
        sentences=[{"text": "Yet another explanation.", "wert": False, "pruefrage": "P-S1", "grund": "explains"}],
        units=[{"einheit": 2, "punch_belohnt": False, "grund": "no reward"}])))
    (e2 / "SCRIPT-v001.zweitmeinung.json").write_text(json.dumps({"status": "ok", "agree": False, "points": [
        {"text": "It costs twice as much.", "why": "misleading: it was 1.7 times", "rewrite": "It costs 1.7 times."}]}))
    rev = studio / "episodes" / "002-second" / "review"
    rev.mkdir()
    (rev / "critic-SHORT-v003.md").write_text("# Critic\n\n- \"Subscribe now.\" P-V8: no, cut the ask.\n"
                                              "- Questions: P-V8 checked.\n| \"Fine line\" | P-S1 | ja |\n")
    (rev / "critic-plan-v002.md").write_text("- \"Cut at 1:02\" P-S1 no\n")   # not a script review: ignored
    an = studio / "episodes" / "001-first" / "analytics"
    an.mkdir()
    units = [{"index": 0, "kind": "intro", "drop_per_min": 50, "seconds": 20, "hook": "Intro"},
             {"index": 1, "kind": "unit", "drop_per_min": 30, "seconds": 30, "hook": "Kurz zu dem Problem.",
              "hook_type": "label", "verdict": "loses"},
             {"index": 2, "kind": "unit", "drop_per_min": 3, "seconds": 40, "hook": "Jetzt denkst du dir, 9 von 12.",
              "hook_type": "objection", "verdict": "holds"},
             {"index": 3, "kind": "unit", "drop_per_min": 8, "seconds": 35, "hook": "Punkt drei.", "hook_type": "claim"},
             {"index": 4, "kind": "unit", "drop_per_min": 9, "seconds": 5, "hook": "too short"}]
    (an / "retention-units.json").write_text(json.dumps({"episode": "001-first", "measurements": [
        {"units": units, "sample": {"views": 2000}}]}))
    labels = studio / "brand" / "labels.md"
    labels.parent.mkdir(parents=True)
    labels.write_text("- P-S1 [G03] Does this sentence give the viewer something? {Sicherheit: hoch}\n")
    (studio / "brand" / "flags.json").write_text(json.dumps({"labels": {"punch_belohnt": "Does the punch reward the "
                                                                                          "hook?"},
                                                             "aliases": {"punch_belohnt": "P-U3"}}))
    (studio / "config").mkdir()
    (studio / "config" / "crewcut.toml").write_text(
        '[style_gate]\nlearning_file = "brand/LEARNING.md"\ngold_dir = "brand/gold"\n'
        'learning_labels = ["brand/labels.md", "brand/flags.json"]\nlearning_ignore = ["als_short"]\n'
        'companion_prefix = "LERNEN-"\n')
    return studio


def test_findings_are_grouped_counted_and_named(studio_data):
    items, done = lernstand.findings(ignore=["als_short"])
    cats = [f["category"] for f in items]
    assert cats.count("P-S1") == 3 and "unit: punch_belohnt" in cats and "K-FA" in cats
    assert "unit: als_short" not in cats
    assert "second opinion: wrong or misleading" in cats and "P-V8" in cats   # the report line quotes and says no
    assert all(f["file"] != "review/critic-plan-v002.md" for f in items)
    top = lernstand.top_findings(items, done)
    assert top[0]["category"] == "P-S1" and top[0]["count"] == 3 and top[0]["episodes"] == ["001-first", "002-second"]
    assert top[0]["fix_worked"] and "counter is on screen" in top[0]["best_fix"]
    so = next(f for f in top if f["category"].startswith("second opinion"))
    assert so["best_fix"] == "It costs 1.7 times." and not so["fix_worked"]


def test_units_are_ranked_against_their_own_video(studio_data):
    us = lernstand.units()
    assert [u["index"] for u in us] == [2, 3, 1]   # the intro and the too-short unit are left out
    assert us[0]["relative"] < 0 < us[-1]["relative"]


def test_the_file_has_findings_units_gold_and_rule_proposals(studio_data):
    p = lernstand.refresh(cards=False)
    assert p == studio_data / "brand" / "LEARNING.md"
    text = p.read_text()
    assert "**P-S1** (Does this sentence give the viewer something?): 3x" in text
    assert "Fix that worked: The counter is on screen now" in text
    assert "| 1 | 001-first | 2 | Jetzt denkst du dir, 9 von 12." in text
    assert "## 4. Rule proposals" in text and "P-S1: Check before every draft: Does this sentence give the viewer " \
                                              "something" in text
    assert "proposed, card at one of the next gate runs" in text
    assert "**P-U3**" in text and "unit: punch_belohnt" not in text   # the alias joins the flag to its question
    top = lernstand.prompt_top()
    assert "LEARNING FILE" in top and "P-S1" in top and "Jetzt denkst du dir" in top and "Gold" not in top


def test_a_rule_card_is_proposed_once(studio_data):
    lernstand.refresh(cards=True)
    rules = [c for c in approvals.list_cards() if c["kind"] == "rule"]
    assert len(rules) == 1 and "Does this sentence give the viewer something" in rules[0]["title"]
    lernstand.refresh(cards=True)
    assert len([c for c in approvals.list_cards() if c["kind"] == "rule"]) == 1
    assert "card #" in (studio_data / "brand" / "LEARNING.md").read_text()


def test_a_passing_script_becomes_a_numbered_gold_candidate_once(studio_data, crew):
    ep = episodes.create("Gold test")["id"]
    brief = paths.episode_dir(ep) / "brief"
    (brief / "CUES-v003.md").write_text("## Opening\nLINE1: x\n")
    (brief / "CUES-v003.kritik.json").write_text("{}")
    verdict = {"results": [{"file": "brief/CUES-v003.md", "pass": True, "format": "lang", "hints": 3}]}
    lernstand.after_ready(ep, verdict)
    lernstand.after_ready(ep, verdict)
    gold = studio_data / "brand" / "gold"
    names = sorted(x.name for x in gold.iterdir())
    assert names == [f"CANDIDATE-001-{ep}-CUES-v003.json", f"CANDIDATE-001-{ep}-CUES-v003.kritik.json",
                     f"CANDIDATE-001-{ep}-CUES-v003.md"]
    score = json.loads((gold / f"CANDIDATE-001-{ep}-CUES-v003.json").read_text())
    assert score["number"] == 1 and score["score"] == 25.0 and score["source"] == "brief/CUES-v003.md"
    (brief / "CUES-v004.md").write_text("## Opening\nLINE1: y\n")
    lernstand.after_ready(ep, {"results": [{"file": "brief/CUES-v004.md", "pass": True}]})
    assert (gold / f"CANDIDATE-002-{ep}-CUES-v004.md").is_file()
    assert "CANDIDATE-002" in (studio_data / "brand" / "LEARNING.md").read_text()


def test_hooks_never_fail_the_caller(studio, monkeypatch):
    monkeypatch.setattr(lernstand, "refresh", lambda **kw: (_ for _ in ()).throw(RuntimeError("boom")))
    assert lernstand.safe_refresh() is None
    lernstand.after_ready("nope", {"results": [{"file": "brief/x.md", "pass": True}]})


def test_the_default_learning_file_needs_no_settings(studio):
    p = lernstand.refresh(cards=False)
    assert p == studio / "library" / "learnings" / "script-learning.md" and "No findings yet." in p.read_text()


# ---- what the Writer is told ---------------------------------------------------------------------------------------
@pytest.fixture
def voice_studio(studio_data):
    moves = studio_data / "brand" / "moves"
    moves.mkdir()
    for n in ("hook", "intro", "proof", "transition", "punch", "ending", "short-first", "short-end"):
        (moves / f"{n}.md").write_text(f"# {n}\n")
    (studio_data / "brand" / "voice.json").write_text(json.dumps({"schema": 1, "targets": {"long": {}}}))
    with open(studio_data / "config" / "crewcut.toml", "a") as f:
        f.write('voice_profile = "brand/voice.json"\nreference_moves = "brand/moves"\n')
    return studio_data


def test_the_writer_gets_profile_moves_and_the_companion(voice_studio, crew):
    block = prompts.voice_block()
    assert "brand/voice.json" in block and "hook.md" in block and "ending.md" in block and "short-first" not in block
    assert "brief/LERNEN-SCRIPT-vNNN.md" in block and "Hook / Retain / Reward" in block
    short = prompts.voice_block(short=True)
    assert "short-first.md" in short and "short-end.md" in short and "transition.md" not in short
    ep = episodes.create("Voice test")["id"]
    lernstand.refresh(cards=False)
    from crewcut import team
    sp = prompts.system_prompt(team.get("writer"), ep, "script")
    assert "VOICE AND STRUCTURE" in sp and "LEARNING FILE" in sp
    assert "VOICE AND STRUCTURE" not in prompts.system_prompt(team.get("editor"), ep, "edit")
    assert "LERNEN-SCRIPT-vNNN.md" in prompts.step_task("script", ep)


def test_a_companion_is_never_taken_for_a_script(voice_studio, crew):
    ep = episodes.create("Companion test")["id"]
    brief = paths.episode_dir(ep) / "brief"
    (brief / "SCRIPT-v001.md").write_text("A script.\n")
    (brief / "LERNEN-SCRIPT-v001.md").write_text("Hook / Retain / Reward\n")
    assert stylegate.latest(ep)["SCRIPT"].name == "SCRIPT-v001.md"
    assert stylegate.NAME.match("LERNEN-SCRIPT-v001.md") is None


def test_without_profile_and_moves_the_prompts_stay_as_they_were(studio, crew):
    assert prompts.voice_block() == "" and lernstand.prompt_top() == ""
    ep = episodes.create("Plain")["id"]
    assert "LEARN" not in prompts.step_task("script", ep)


def test_only_lesson_units_are_models_and_placeholder_scripts_teach_nothing(studio_data):
    """Abnahme Hormozi round 2: S2 (watch units are no models) and F2 (no findings from gaps)."""
    an = studio_data / "episodes"
    for i, ep in enumerate(("003-third", "004-fourth", "005-fifth")):
        d = an / ep / "analytics"
        d.mkdir(parents=True)
        units = [{"index": 1, "kind": "unit", "drop_per_min": 2 + i, "seconds": 30, "hook": f"Ich habe {i} getestet.",
                  "hook_type": "number", "verdict": "holds"},
                 {"index": 2, "kind": "unit", "drop_per_min": 20, "seconds": 30, "hook": "Rolle 3 ist der Schnitt.",
                  "hook_type": "label", "verdict": "loses"}]
        (d / "retention-units.json").write_text(json.dumps({"episode": ep, "measurements": [{"units": units}]}))
    us = lernstand.units()
    status = {u["hook_type"]: u["status"] for u in us}
    assert status["number"] == "lesson: holds" and status["label"] == "lesson: loses" and status["objection"] == "watch"
    text = lernstand.refresh(cards=False).read_text()
    models = text.split("**Models")[1].split("**Held well")[0]
    watch = text.split("**Held well, but only watch")[1].split("**Avoid")[0]
    assert "Ich habe 0 getestet." in models and "Jetzt denkst du dir" not in models
    assert "Jetzt denkst du dir" in watch and "watch, do not copy" in text
    assert "Rolle 3 ist der Schnitt." in text.split("**Avoid")[1].split("**Weak")[0]
    assert 'Only units with status "lesson" are models to copy' in text
    assert 'never units marked "watch"' in lernstand.prompt_top()
    # a review of a script with placeholders does not count
    brief = studio_data / "episodes" / "002-second" / "brief"
    before = [f["category"] for f in lernstand.findings()[0]].count("P-S1")
    (brief / "SCRIPT-v001.md").write_text("Claude took [ZAHL nach Test] minutes.\n---\nnotes\n")
    after = lernstand.findings()[0]
    assert [f["category"] for f in after].count("P-S1") == before - 1
    assert not [f for f in after if f["file"] == "brief/SCRIPT-v001.md"]
    (brief.parent / "brief" / "CUES-v009.kritik.json").write_text(json.dumps(kritik(sentences=[
        {"text": "Ich habe [ZAHL nach Test] Clips.", "wert": False, "pruefrage": "P-S6", "grund": "Platzhalter"}])))
    assert "P-S6" not in [f["category"] for f in lernstand.findings()[0]]


def test_the_learning_file_says_when_there_is_no_model_yet(studio_data):
    text = lernstand.refresh(cards=False).read_text()
    assert "None yet. No hook type holds in at least 3 episodes." in text


def test_rule_proposals_show_todays_counts(studio_data):
    """Round 3, hint 5: an old proposal keeps its card, but the file shows the counts of today's findings."""
    p = lernstand.learning_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.with_suffix(".json").write_text(json.dumps({"proposed": [
        {"category": "P-S1", "rule": "Check before every draft: old text, 99 times.", "status": "card #7", "card": 7}]}))
    text = lernstand.refresh(cards=False).read_text()
    rules = text.split("## 4.")[1]
    assert "card #7" in rules and "99 times" not in rules and "3 times" in rules
