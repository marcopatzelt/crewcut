"""Test first, then the script (docs/formats.md): a format with a test plan waits for its test result, a script with a
placeholder fails before any Critic round, and a format's kinds have their own structure."""

import json

import pytest

from crewcut import approvals, db, episodes, paths, showformats, stylegate
from crewcut.conductor import flow, plan, prompts, queue


class Res:
    ok = True
    text = ""
    error = ""


@pytest.fixture
def calls(crew, monkeypatch):
    seen = []

    def add(episode, identity, step, task, **k):
        seen.append({"episode": episode, "identity": identity, "step": step, "task": task, **k})
        return len(seen)
    monkeypatch.setattr(queue, "add", add)
    return seen


def planned(fmt="tool-test", kind=None):
    eid = flow.new_episode("A free tool against a paid one")["id"]
    (paths.episode_dir(eid) / "brief" / "FORMAT-v001.md").write_text(
        f"format: {fmt}\n" + (f"kind: {kind}\n" if kind else "") + "length: long\ntopic_type: manufactured\n"
        "input: tool\nreason: A measurable claim.\nrunner_up: claim-check: shorter.\n")
    return eid


def plan_done(eid):
    return plan.after_job({"id": 1, "episode": eid, "identity": "scout", "step": "idea", "data": {"plan": 1}}, Res())


# ---- the test before the script -------------------------------------------------------------------------------------
def test_a_format_with_a_test_plan_waits_for_the_result_and_asks_to_run_it(crew, calls):
    eid = planned(kind="free-vs-paid")
    assert plan_done(eid)
    p = episodes.read(eid)
    assert p["show_format"] == "tool-test" and p["format_kind"] == "free-vs-paid"
    assert p["steps"]["idea"]["status"] == "done" and p["steps"]["script"]["status"] == "waiting"
    assert not [c for c in calls if c["identity"] == "writer"]          # no script before the test
    assert plan.waiting(eid) and showformats.test_pending(eid)
    texts = [m["text"] for m in flow.messages(eid)]
    assert any("Test first, then the script" in t for t in texts)
    card = next(c for c in approvals.list_cards(eid, "open") if (c.get("data") or {}).get("format_test"))
    assert card["title"] == "Run the test plan now?" and card["identity"] == "scout"
    plan.wait_for_test(eid)                                                # idempotent: one card, one message
    assert len([c for c in approvals.list_cards(eid, "open") if (c.get("data") or {}).get("format_test")]) == 1
    # yes: the Scout runs the test plan, writes the result, no script
    flow.on_card_decided({**card, "status": "accepted"})
    job = calls[-1]
    assert (job["identity"], job["step"], job["data"]) == ("scout", "script", {"format_test": 1})
    assert "TEST-RESULT-v001.md" in job["task"] and "spend card" in job["task"] and "Write no script" in job["task"]
    # the result arrives: the worker gives the script to the Writer, once
    (paths.episode_dir(eid) / "brief" / "TEST-RESULT-v001.md").write_text("Test 1: 7 of 9.\n")
    assert showformats.test_result(eid).name == "TEST-RESULT-v001.md" and not showformats.test_pending(eid)
    out = plan.tick(force=True)
    assert out and out[0]["result"] == "TEST-RESULT-v001.md"
    w = calls[-1]
    assert (w["identity"], w["step"]) == ("writer", "script")
    assert w["data"] == {"format_script": 1, "after_test": "brief/TEST-RESULT-v001.md"}
    assert "Read brief/TEST-RESULT-v001.md first" in w["task"] and "never carries a placeholder" in w["task"]
    assert episodes.read(eid)["steps"]["script"]["status"] == "working"
    assert plan.tick(force=True) == [] and not plan.waiting(eid)


def test_the_worker_waits_while_a_job_of_the_episode_runs(crew):
    eid = planned()
    plan_done(eid)
    (paths.episode_dir(eid) / "brief" / "MESSKARTE-v001.md").write_text("Test 1: 7 of 9.\n")
    with db.conn() as c:
        c.execute("UPDATE jobs SET status = 'running' WHERE episode = ?", (eid,))
    assert plan.tick(force=True) == []
    with db.conn() as c:
        c.execute("UPDATE jobs SET status = 'done' WHERE episode = ?", (eid,))
    out = plan.tick(force=True)
    assert out and queue.get(out[0]["job"])["identity"] == "writer"


def test_no_on_the_test_card_keeps_the_script_waiting(crew, calls):
    eid = planned()
    plan_done(eid)
    card = next(c for c in approvals.list_cards(eid, "open") if (c.get("data") or {}).get("format_test"))
    flow.on_card_decided({**card, "status": "declined"})
    assert not [c for c in calls if c["identity"] in ("writer",) or (c.get("data") or {}).get("format_test")]
    assert "Drop the result" in flow.messages(eid)[-1]["text"] and plan.waiting(eid)


def test_a_format_without_a_test_plan_goes_to_the_writer_at_once(crew, calls):
    eid = planned(fmt="incident-file")
    assert plan_done(eid)
    w = calls[-1]
    assert (w["identity"], w["step"], w["data"]) == ("writer", "script", {"format_script": 1})
    assert not plan.waiting(eid) and not showformats.needs_test(eid)


def test_the_writer_task_without_a_result_writes_nothing(crew, calls):
    eid = planned()
    showformats.choose(eid, "tool-test")
    t = prompts.format_script_task(eid)
    assert "Write no script" in t and "keep a placeholder" not in t


def test_the_plan_task_fixes_no_result_and_names_recent_kinds(crew):
    a = episodes.create("Old one")["id"]
    showformats.choose(a, "tool-test", kind="rebuild")
    eid = episodes.create("New one")["id"]
    t = prompts.plan_task(eid, "A free tool")
    assert "never the result" in t and "expected break" in t and "--kind" in t
    assert "tool-test: rebuild" in t and "take a different kind" in t
    assert "the script waits for the test result" in t


def test_a_writer_job_before_the_result_and_a_critic_on_placeholders_are_refused(crew, monkeypatch, capsys):
    from crewcut import cli
    eid = planned()
    plan_done(eid)
    monkeypatch.setenv("CREWCUT_EPISODE", eid)
    assert cli.main(["job", "add", "--identity", "writer", "--step", "script", "write the script"]) == 3
    assert "waits for the test result" in capsys.readouterr().err
    brief = paths.episode_dir(eid) / "brief"
    (brief / "SCRIPT-v001.md").write_text("I measured [ZAHL nach Test] minutes.\n---\nnotes\n")
    assert cli.main(["job", "add", "--identity", "critic", "--step", "script", "review"]) == 3
    assert "placeholder" in capsys.readouterr().err
    (brief / "TESTERGEBNIS-v001.md").write_text("12 minutes.\n")
    (brief / "SCRIPT-v002.md").write_text("I measured 12 minutes.\n---\nnotes\n")
    assert cli.main(["job", "add", "--identity", "critic", "--step", "script", "review"]) == 0
    assert cli.main(["job", "add", "--identity", "writer", "--step", "script", "next draft"]) == 0


def test_formats_test_command(crew, capsys):
    eid = planned()
    showformats.choose(eid, "tool-test")
    assert showformats.main(["test", eid, "--json"]) == 0
    st = json.loads(capsys.readouterr().out)
    assert st["needs_test"] and st["pending"] and st["test_result"] is None
    assert showformats.main(["test", eid, "--wait"]) == 0
    assert plan.waiting(eid) and "starts the Writer" in capsys.readouterr().out


# ---- placeholders ---------------------------------------------------------------------------------------------------
def test_placeholders_are_found_in_the_spoken_part_only():
    text = ("Claude took [ZAHL nach Test] minutes. [Bild: result side by side] [Zahl] of 9.\n"
            "It held [ERGEBNIS: was gleich ist]. Price [PREIS nach Prüfung]. [NUMBER after test] runs.\n"
            "[the clock, after the test run] and [result screen]\n---\nnotes: [ZAHL nach Test] was 12\n")
    found = showformats.placeholders(text)
    assert found == ["[ZAHL nach Test]", "[Zahl]", "[ERGEBNIS: was gleich ist]", "[PREIS nach Prüfung]",
                     "[NUMBER after test]", "[the clock, after the test run]"]
    assert showformats.placeholders("[Bild: Messkarte, Zeile Test 1] 7 von 9.\n") == []
    assert [n for n, _ in showformats.placeholder_lines(text)] == [1, 2, 3]


PASSING_CHECKER = r'''
import json, sys
print(json.dumps({"version": 1, "pass": True, "auto_pass": True, "kritik_offen": [],
                  "checks": [{"id": "S1", "kind": "auto", "pass": True}]}))
'''


@pytest.fixture
def skill(studio):
    d = studio / "skills" / "deutscher-hormozi" / "scripts"
    d.mkdir(parents=True)
    (d.parent / "SKILL.md").write_text("---\nname: deutscher-hormozi\ndescription: test\n---\n")
    (d / "stil_check.py").write_text(PASSING_CHECKER)
    return d


def test_a_placeholder_fails_before_the_checker_and_waits_for_the_test(skill, crew):
    eid = planned()
    plan_done(eid)
    with db.conn() as c:
        c.execute("DELETE FROM kv WHERE k = ?", (plan.WAIT_KEY + eid,))   # as if the wait was never armed
    brief = paths.episode_dir(eid) / "brief"
    (brief / "SCRIPT-v001.md").write_text("Claude took [ZAHL nach Test] minutes.\n---\nnotes\n")
    v = stylegate.check(eid)
    r = v["results"][0]
    assert v["pass"] is False and r["placeholders"] == 1 and r["failed"][0]["id"] == "PLACEHOLDER"
    assert r["open"] == [] and r["exit"] is None   # the checker did not run, no Critic question is open
    out = stylegate.route(eid, v)
    assert out["action"] == "wait_test" and plan.waiting(eid)
    assert any("No Critic reviews it" in m["text"] for m in flow.messages(eid))
    # with the result there, the Writer gets a round to fill the gaps
    (brief / "TESTERGEBNIS-v001.md").write_text("Claude took 12 minutes.\n")
    out = stylegate.route(eid, stylegate.check(eid))
    assert out["action"] == "writer"
    task = queue.get(out["job"])["task"]
    assert "PLACEHOLDER" in task and "fill every one from it" in task
    (brief / "SCRIPT-v002.md").write_text("Claude took 12 minutes.\n---\nnotes\n")
    assert stylegate.check(eid)["pass"] is True


# ---- kinds with their own structure ---------------------------------------------------------------------------------
def studio_format(studio, formats, templates=("t.script.md", "k.script.md", "k.testplan.md")):
    d = studio / "brand" / "show-formats"
    d.mkdir(parents=True, exist_ok=True)
    for t in templates:
        (d / t).write_text("# template\n")
    (d / "formats.json").write_text(json.dumps({"schema": 1, "formats": formats}))
    return d


def test_a_kind_has_its_own_structure_and_templates(studio, crew):
    f = {"id": "stop-paying", "name": "Stop paying", "length": "long", "when": "A paid tool.",
         "topic_types": ["manufactured"], "structure": [{"name": "Opening", "purpose": "Result first."}],
         "script_template": "t.script.md",
         "kinds": [{"id": "rebuild", "name": "Claude rebuilds", "when": "An app with a plan.",
                    "structure": [{"name": "Opening", "purpose": "The rebuild's result."},
                                  {"name": "Unit 3", "purpose": "Where does it break, if at all?"}],
                    "script_template": "k.script.md", "testplan_template": "k.testplan.md"},
                   {"id": "free-way", "name": "Free way", "when": "No tool."}]}
    bad = {**f, "id": "bad-kind", "kinds": [{"id": "x", "name": "X", "when": "w", "structure": [{"name": "U"}]},
                                            {"id": "y", "name": "Y", "when": "w", "script_template": "missing.md"}]}
    d = studio_format(studio, [f, bad])
    lib, problems = showformats.report()
    assert "stop-paying" in lib and "bad-kind" not in lib
    assert any("kind 'x'" in p and "needs name and purpose" in p for p in problems)
    assert any("kind 'y'" in p and "missing.md is missing" in p for p in problems)
    g = lib["stop-paying"]
    assert showformats.structure_of(g, "rebuild")[1]["purpose"] == "Where does it break, if at all?"
    assert showformats.structure_of(g, "free-way") == g["structure"]
    assert showformats.template(g, "script_template", "rebuild") == d / "k.script.md"
    assert showformats.template(g, "script_template", "free-way") == d / "t.script.md"
    eid = episodes.create("Tool")["id"]
    with pytest.raises(ValueError, match="no kind 'nope'"):
        showformats.choose(eid, "stop-paying", kind="nope")
    showformats.choose(eid, "stop-paying", kind="rebuild")
    block = showformats.prompt_block(eid)
    assert "Kind of this episode: rebuild" in block and "Structure of the kind rebuild, in this order" in block
    assert "Where does it break, if at all?" in block and "k.testplan.md" in block
    assert showformats.needs_test(eid) and "Test result: not there yet" in block
    other = episodes.create("Other")["id"]
    showformats.choose(other, "stop-paying")
    b2 = showformats.prompt_block(other)
    assert "Structure of the kind rebuild:" in b2 and not showformats.needs_test(other)
    assert "rebuild (own structure)" in showformats.catalogue()
    assert showformats.recent_kinds("stop-paying") == [(eid, "rebuild")]
    assert showformats.read_choice(eid) is None
    (paths.episode_dir(eid) / "brief" / "FORMAT-v001.md").write_text("format: stop-paying\nkind: rebuild\n")
    assert showformats.read_choice(eid)["kind"] == "rebuild"


def test_starting_the_script_step_by_hand_waits_for_the_test_too(crew, calls):
    eid = planned()
    showformats.choose(eid, "tool-test")
    assert flow.start_step(eid, "script") is None
    assert plan.waiting(eid) and episodes.read(eid)["steps"]["script"]["status"] == "waiting"
    assert not [c for c in calls if c["identity"] == "writer"]
