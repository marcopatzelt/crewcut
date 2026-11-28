"""A title and thumbnail pair whose claim the test reverses never reaches the title card (docs/formats.md, acceptance
round 4, R4-1): the title step marks every pair against the test result, the Critic gets it as a hard question, and the
card refuses an unchecked packaging and a reversed pair."""

import os

import pytest

from crewcut import approvals, episodes, paths, showformats, team, titlepairs
from crewcut.conductor import prompts

PLAN_PACKAGING = """# Packaging v001 (provisional, before the test)

## Paar A: V2 Bevor du (situation)
- Titel: **Before you pay for research, let Claude search** (48 Zeichen)
- Belegplan: Messkarte Test 1 bis 0:15

## Pair B: flip
- Title: "Your Claude is not as current as you think"
- Thumbnail: a real answer with an old date marked [ERGEBNIS: the date]

## Pair C: case
- Title: Claude reads Reddit for your app idea

## Empfehlung, vorläufig
- Title: not a pair
"""


def checked(b="reverses, the test found plain Claude more current (72 against 61)", c="carries"):
    out = PLAN_PACKAGING.replace("(48 Zeichen)\n", "(48 Zeichen)\n- Test: trägt\n")
    out = out.replace("[ERGEBNIS: the date]\n", f"[ERGEBNIS: the date]\n- Test: {b}\n")
    if c:
        out = out.replace("app idea\n", f"app idea\n- Test: {c}\n")
    return out


def test_pairs_and_their_verdicts_are_read_from_the_packaging():
    ps = titlepairs.pairs(checked())
    assert [(p["pair"], p["title"], p["test"]) for p in ps] == [
        ("A", "Before you pay for research, let Claude search", "carries"),
        ("B", "Your Claude is not as current as you think", "reverses"),
        ("C", "Claude reads Reddit for your app idea", "carries")]
    assert [p["test"] for p in titlepairs.pairs(PLAN_PACKAGING)] == [None, None, None]
    for text, want in (("dreht um: normales Claude fand mehr", "reverses"), ("trägt nicht", "reverses"),
                       ("does not hold", "reverses"), ("widerspricht dem Test", "reverses"), ("trägt", "carries"),
                       ("carries, 72 against 61", "carries"), ("offen", None)):
        assert titlepairs.verdict(text) == want, text


def format_episode(crew, result=True):
    eid = episodes.create("A free skill against plain Claude")["id"]
    showformats.choose(eid, "tool-test")
    brief = paths.episode_dir(eid) / "brief"
    (brief / "PACKAGING-v001.md").write_text(PLAN_PACKAGING)
    os.utime(brief / "PACKAGING-v001.md", (1_000_000, 1_000_000))
    if result:
        (brief / "MESSKARTE-v001.md").write_text("Test 1: with the skill 61, plain Claude 72.\n")
        os.utime(brief / "MESSKARTE-v001.md", (2_000_000, 2_000_000))
    return eid, brief


def propose(eid, *options):
    return approvals.propose(eid, "title", "title", "Pick a title", options=list(options))


def test_the_title_card_waits_for_the_check_and_refuses_a_reversed_pair(crew):
    eid, brief = format_episode(crew)
    with pytest.raises(titlepairs.Unchecked, match="older than the test result brief/MESSKARTE-v001.md"):
        propose(eid, "Claude reads Reddit for your app idea")
    (brief / "PACKAGING-v002.md").write_text(checked(c=None))
    with pytest.raises(titlepairs.Unchecked, match="pair C is not checked"):
        propose(eid, "Claude reads Reddit for your app idea")
    (brief / "PACKAGING-v002.md").write_text(checked())
    with pytest.raises(titlepairs.Unchecked, match=r"Option 2 .* is pair B, and the test result reverses its claim"):
        propose(eid, "Before you pay for research, let Claude search",
                "Your Claude is NOT as current as you think! (42 characters)")
    card = propose(eid, "Before you pay for research, let Claude search", "Claude is more current than you think")
    assert card["kind"] == "title" and card["status"] == "open"
    # a newer test result needs a new check
    (brief / "MESSKARTE-v002.md").write_text("Test 1 again.\n")
    os.utime(brief / "MESSKARTE-v002.md", (4_000_000_000, 4_000_000_000))
    assert titlepairs.problems(eid, ["Claude reads Reddit for your app idea"])[0].startswith(
        "brief/PACKAGING-v002.md is older than the test result brief/MESSKARTE-v002.md")


def test_no_check_without_a_format_a_result_or_pairs(crew):
    eid, brief = format_episode(crew, result=False)
    assert propose(eid, "Your Claude is not as current as you think")["status"] == "open"   # before the test
    plain = episodes.create("No format")["id"]
    (paths.episode_dir(plain) / "brief" / "PACKAGING-v001.md").write_text(PLAN_PACKAGING)
    (paths.episode_dir(plain) / "brief" / "MESSKARTE-v001.md").write_text("Test.\n")
    assert titlepairs.problems(plain, ["Your Claude is not as current as you think"]) == []
    (brief / "MESSKARTE-v001.md").write_text("Test.\n")
    (brief / "PACKAGING-v001.md").write_text("# Packaging\nTitles without pair sections.\n")
    assert titlepairs.problems(eid, ["anything"]) == []


def test_the_cli_refuses_the_card_with_the_reason(crew, monkeypatch, capsys):
    from crewcut import cli
    eid, brief = format_episode(crew)
    (brief / "PACKAGING-v002.md").write_text(checked())
    monkeypatch.setenv("CREWCUT_EPISODE", eid)
    assert cli.main(["card", "propose", "--step", "title", "--kind", "title", "--title", "Pick a title",
                     "--option", "Your Claude is not as current as you think"]) == 4
    assert "reverses its claim" in capsys.readouterr().err
    assert approvals.list_cards(eid, "open") == []


def test_the_title_step_and_its_critic_get_the_test_result(crew):
    eid, brief = format_episode(crew)
    task = prompts.step_task("title", eid)
    assert "brief/MESSKARTE-v001.md" in task and "reverses" in task and "`- Test: carries`" in task
    assert "The title card is refused while a pair is unchecked" in task
    critic = prompts.system_prompt(team.get("critic"), eid, "title")
    assert "TITLE AGAINST THE TEST (a hard check, never a hint): read brief/MESSKARTE-v001.md" in critic
    assert "brief/PACKAGING-v001.md" in critic
    assert "TITLE AGAINST THE TEST" not in prompts.system_prompt(team.get("critic"), eid, "script")
    assert "TITLE AGAINST THE TEST" not in prompts.system_prompt(team.get("scout"), eid, "title")
    assert "Never build the image idea of a pair marked `Test: reverses`" in prompts.step_task("thumbnail", eid)
    before = format_episode(crew, result=False)[0]
    assert "reverses" not in prompts.step_task("title", before)
    assert titlepairs.critic_note(before) == ""
