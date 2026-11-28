"""The show format library, the New Episode path with length and format, and the plan of a format episode."""

import json

import pytest
from fastapi.testclient import TestClient

from crewcut import episodes, paths, showformats
from crewcut.conductor import flow, plan, prompts, queue


def studio_format(studio, formats, templates=("t.script.md",)):
    d = studio / "brand" / "show-formats"
    d.mkdir(parents=True, exist_ok=True)
    for t in templates:
        (d / t).write_text("# template\n")
    (d / "formats.json").write_text(json.dumps({"schema": 1, "formats": formats}))
    return d


def fmt(**over):
    f = {"id": "my-test", "name": "My test", "length": "long", "when": "A tool to test.",
         "topic_types": ["manufactured"], "structure": [{"name": "Opening", "purpose": "Result first."}],
         "script_template": "t.script.md"}
    f.update(over)
    return f


@pytest.fixture
def calls(crew, monkeypatch):
    seen = []

    def add(episode, identity, step, task, **k):
        seen.append({"episode": episode, "identity": identity, "step": step, "task": task, **k})
        return len(seen)
    monkeypatch.setattr(queue, "add", add)
    return seen


# ---- the library ----------------------------------------------------------------------------------------------------
def test_the_neutral_examples_load_and_are_valid():
    lib, problems = showformats.report()
    assert problems == []
    assert {"tool-test", "claim-check", "incident-file"} <= set(lib)
    t = lib["tool-test"]
    assert t["length"] == "long" and t["checker_format"] == "lang" and t["source"] == "neutral"
    assert showformats.template(t, "script_template").is_file()
    assert showformats.template(t, "cue_template").is_file()
    assert lib["claim-check"]["checker_format"] == "short"
    assert showformats.enabled()


def test_a_studio_format_with_the_same_id_replaces_the_example(studio):
    studio_format(studio, [fmt(id="tool-test", name="Our tool test"), fmt()])
    lib = showformats.load()
    assert lib["tool-test"]["name"] == "Our tool test" and lib["tool-test"]["source"] == "studio"
    assert lib["my-test"]["dir"] == str(studio / "brand" / "show-formats")
    assert "claim-check" in lib


def test_broken_formats_are_left_out_with_clear_errors(studio):
    studio_format(studio, [fmt(id="no-template", script_template="missing.md"), fmt(id="bad-len", length="medium"),
                           fmt(id="bad-topic", topic_types=["someday"]), fmt(id="Bad Id"), fmt(id="no-units", structure=[]),
                           fmt(id="ok-one")])
    lib, problems = showformats.report()
    assert "ok-one" in lib and not {"no-template", "bad-len", "bad-topic", "no-units"} & set(lib)
    text = "\n".join(problems)
    assert "script_template missing.md is missing" in text
    assert "length must be long or short" in text
    assert "unknown topic type 'someday'" in text
    assert "id must be lower-case" in text
    assert "needs structure" in text


def test_a_broken_file_and_paths_outside_are_refused(studio):
    d = studio / "brand" / "show-formats"
    d.mkdir(parents=True)
    (d / "formats.json").write_text("{not json")
    assert any("not readable JSON" in p for p in showformats.report()[1])
    assert any("inside its library" in p for p in showformats.problems_of(fmt(script_template="../x.md")))


def test_examples_can_be_switched_off(studio):
    (studio / "config").mkdir()
    (studio / "config" / "crewcut.toml").write_text("[formats]\ninclude_examples = false\n")
    assert showformats.load() == {} and not showformats.enabled()
    studio_format(studio, [fmt()])
    assert list(showformats.load()) == ["my-test"]


def test_the_rule_guess_is_deterministic_and_respects_length():
    g = showformats.suggest("A free GitHub tool that claims to replace a paid subscription app")
    assert g["format"] == "tool-test" and g["kind"] == "rule" and g["reason"].startswith("Rule guess")
    s = showformats.suggest("My agent deleted the log instead of the cache", length="short")
    assert s["format"] == "incident-file" and s["topic_type"] == "recent_past"
    assert showformats.suggest("A viral tweet claims it is true", length="short")["format"] == "claim-check"
    assert showformats.suggest("zzz qqq") is None
    assert showformats.guess_topic_type("nothing here", source="scout") == "trending"


def test_cli_lists_shows_and_checks(capsys):
    assert showformats.main(["list"]) == 0
    assert "tool-test" in capsys.readouterr().out
    assert showformats.main(["show", "claim-check"]) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown["id"] == "claim-check" and "dir" not in shown and shown["templates"]["script_template"]
    assert showformats.main(["show", "nope"]) == 1
    assert showformats.main(["check"]) == 0


# ---- the episode's pick ---------------------------------------------------------------------------------------------
def test_choose_turns_an_episode_into_an_original_short_and_back(crew):
    eid = episodes.create("Something")["id"]
    p = showformats.choose(eid, "claim-check", topic_type="trending", input_kind="tweet")
    assert (p["kind"], p["mode"], p["format"], p["show_format"], p["form"], p["length"]) == \
        ("short", "original", "portrait", "claim-check", "claim-check", "short")
    assert p["steps"]["thumbnail"]["status"] == "open" and p["topic_type"] == "trending"
    p = showformats.choose(eid, "tool-test")
    assert p["kind"] == "episode" and "mode" not in p and p["format"] == "landscape"
    assert p["steps"]["blog"]["status"] == "skipped" and not p["steps"]["thumbnail"].get("absent")
    with pytest.raises(ValueError, match="no format"):
        showformats.choose(eid, "nope")
    episodes.set_step(eid, "script", "working")
    with pytest.raises(ValueError, match="started later steps"):
        showformats.choose(eid, "claim-check")


def test_read_choice_and_the_prompt_block(crew, studio):
    eid = episodes.create("Tool")["id"]
    showformats.choose(eid, "tool-test", topic_type="manufactured")
    (paths.episode_dir(eid) / "brief" / "FORMAT-v001.md").write_text(
        "format: tool-test\nlength: long\ntopic_type: manufactured\ninput: tool\n"
        "reason: It is a tool with a claim we can measure. The test fits in a day.\n"
        "runner_up: claim-check: the claim alone would fit a Short.\n")
    c = showformats.read_choice(eid)
    assert c["format"] == "tool-test" and c["known"] and c["input"] == "tool"
    assert c["reason"].startswith("It is a tool") and c["runner_up"].startswith("claim-check")
    s = episodes.summary(eid)
    assert s["show_format"]["id"] == "tool-test" and s["show_format"]["reason"].startswith("It is a tool")
    block = showformats.prompt_block(eid)
    assert "SHOW FORMAT of this episode: Tool test" in block and "1. Opening" in block
    assert "tool-test.script.md" in block and "tool-test.cues.md" in block and "HORMOZI" not in block
    ref = studio / "brand" / "references" / "HORMOZI-NIE-OHNE-CONTENT.md"
    ref.parent.mkdir(parents=True)
    ref.write_text("five topic types")
    assert str(ref) in showformats.prompt_block(eid)
    from crewcut import team
    assert "SHOW FORMAT of this episode" in prompts.system_prompt(team.get("writer"), eid, "script")
    plain = episodes.create("Plain")["id"]
    assert "SHOW FORMAT" not in prompts.system_prompt(team.get("writer"), plain, "script")


# ---- New Episode ----------------------------------------------------------------------------------------------------
@pytest.fixture
def client(calls):
    from crewcut.server.app import create_app
    return TestClient(create_app(start_worker=False), base_url="http://localhost:4747")


def test_the_old_body_still_works_and_starts_the_plan(client, calls):
    r = client.post("/api/episodes", json={"text": "https://github.com/example/tool a free tool"})
    assert r.status_code == 200
    eid = r.json()["id"]
    p = episodes.read(eid)
    assert p["length"] == "auto" and p["kind"] == "episode" and "show_format" not in p
    job = calls[-1]
    assert (job["identity"], job["step"], job["data"]) == ("scout", "idea", {"plan": 1})
    assert "brief/FORMAT-v001.md" in job["task"] and f"crewcut formats choose {eid}" in job["task"]
    msgs = flow.messages(eid)
    assert msgs[0]["author"] == "user" and "picks the format" in msgs[-1]["text"]


def test_length_and_format_go_into_the_project(client, calls):
    eid = client.post("/api/episodes", json={"text": "A viral claim", "length": "short"}).json()["id"]
    p = episodes.read(eid)
    assert (p["kind"], p["mode"], p["length"]) == ("short", "original", "short")
    assert "among the short formats" in calls[-1]["task"]
    r = client.post("/api/episodes", json={"text": "A tool", "show_format": "tool-test"}).json()
    p = episodes.read(r["id"])
    assert (p["show_format"], p["form"], p["length"], p["kind"]) == ("tool-test", "tool-test", "long", "episode")
    assert r["show_format"]["id"] == "tool-test"
    assert "The user chose the format `tool-test`" in calls[-1]["task"]


def test_bad_formats_and_lengths_are_refused(client):
    assert client.post("/api/episodes", json={"text": "x", "show_format": "nope"}).status_code == 400
    assert client.post("/api/episodes", json={"text": "x", "length": "short",
                                              "show_format": "tool-test"}).status_code == 400
    assert client.post("/api/episodes", json={"text": "x", "length": "medium"}).status_code == 422


def test_without_formats_the_idea_step_starts_as_before(client, calls, studio):
    (studio / "config").mkdir()
    (studio / "config" / "crewcut.toml").write_text("[formats]\nenabled = false\n")
    eid = client.post("/api/episodes", json={"text": "An idea"}).json()["id"]
    assert calls[-1]["step"] == "idea" and "data" not in calls[-1] and "Find the topic" in calls[-1]["task"]
    assert episodes.read(eid)["length"] == "auto"


def test_get_formats(client):
    body = client.get("/api/formats").json()
    assert body["enabled"] and body["problems"] == []
    ids = [f["id"] for f in body["formats"]]
    assert "tool-test" in ids and all("dir" not in f for f in body["formats"])


# ---- the plan, the script, the cue sheet ----------------------------------------------------------------------------
class Res:
    ok = True
    text = ""
    error = ""


def test_after_the_plan_the_writer_writes_the_full_script(crew, calls):
    eid = flow.new_episode("A free tool against a paid one")["id"]
    (paths.episode_dir(eid) / "brief" / "TESTERGEBNIS-v001.md").write_text("Test 1: 7 of 9.\n")   # the test ran
    (paths.episode_dir(eid) / "brief" / "FORMAT-v001.md").write_text(
        "format: tool-test\nlength: long\ntopic_type: manufactured\ninput: tool\nreason: A measurable claim.\n"
        "runner_up: claim-check: shorter.\n")
    job = {"id": 1, "episode": eid, "identity": "scout", "step": "idea", "data": {"plan": 1}}
    assert plan.after_job(job, Res())
    p = episodes.read(eid)
    assert p["show_format"] == "tool-test" and p["topic_type"] == "manufactured"
    assert p["steps"]["idea"]["status"] == "done" and p["steps"]["script"]["status"] == "working"
    w = calls[-1]
    assert (w["identity"], w["step"], w["data"]) == ("writer", "script", {"format_script": 1})
    assert "brief/SCRIPT-v001.md" in w["task"] and "tool-test.script.md" in w["task"]
    assert "never carries a placeholder" in w["task"] and "about 30 seconds" in w["task"]
    assert "Read brief/TESTERGEBNIS-v001.md first" in w["task"]
    texts = [m["text"] for m in flow.messages(eid)]
    assert any(t.startswith("Format: Tool test (tool-test, long, manufactured). A measurable claim.") for t in texts)
    assert not plan.after_job({**job, "data": {}}, Res())


def test_a_plan_without_a_format_file_says_so(crew, calls):
    eid = flow.new_episode("Something")["id"]
    assert plan.after_job({"id": 1, "episode": eid, "identity": "scout", "data": {"plan": 1}}, Res())
    assert "no brief/FORMAT-v001.md" in flow.messages(eid)[-1]["text"]
    assert episodes.read(eid)["steps"]["idea"]["status"] == "working"


def test_the_short_script_task_and_the_cue_sheet_task(crew, calls):
    eid = flow.new_episode("A claim", show_format="claim-check")["id"]
    t = prompts.format_script_task(eid)
    assert "A Short: sentence 1 is your own case with a number" in t and "no ask" in t.lower()
    assert prompts.cue_sheet_task(eid) is None
    long_id = flow.new_episode("A tool", show_format="tool-test")["id"]
    brief = paths.episode_dir(long_id) / "brief"
    assert prompts.cue_sheet_task(long_id) is None   # no script yet
    (brief / "SCRIPT-v001.md").write_text("# Script\nThe free tool won.\n")
    task = prompts.cue_sheet_task(long_id)
    assert "brief/CUES-v001.md" in task and "tool-test.cues.md" in task
    (brief / "CUES-v001.md").write_text("## Opening\nLINE1: x\n")
    assert prompts.cue_sheet_task(long_id) is None


def test_the_gate_asks_for_the_cue_sheet_before_the_card(crew, calls):
    from crewcut import stylegate
    eid = flow.new_episode("A tool", show_format="tool-test")["id"]
    (paths.episode_dir(eid) / "brief" / "SCRIPT-v001.md").write_text("# Script\n")
    r = stylegate.ready(eid, {"pass": True, "results": []}, "The Critic approves.")
    assert r["action"] == "cue_sheet" and calls[-1]["data"] == {"format_cues": 1}
    plain = episodes.create("Plain")["id"]
    (paths.episode_dir(plain) / "brief" / "SCRIPT-v001.md").write_text("# Script\n")
    assert stylegate.ready(plain, {"pass": True, "results": []}, "ok")["action"] == "ready"


def test_the_title_step_starts_from_the_packaging(crew):
    eid = episodes.create("Tool")["id"]
    showformats.choose(eid, "tool-test")
    assert "PACKAGING-v001.md" in prompts.step_task("title", eid)
    assert "PACKAGING-v001.md (three" not in prompts.step_task("title", episodes.create("Plain")["id"])


def test_a_format_can_gate_the_cue_sheet_first(crew, calls, studio):
    d = studio_format(studio, [fmt(id="cue-first", cue_template="t.cues.md", gate_on="cues"),
                               fmt(id="bad-gate", gate_on="cues")], templates=("t.script.md", "t.cues.md"))
    lib, problems = showformats.report()
    assert lib["cue-first"]["gate_on"] == "cues" and lib["tool-test"]["gate_on"] == "script"
    assert any("gate_on cues needs a cue_template" in p for p in problems)
    eid = flow.new_episode("A tool", show_format="cue-first")["id"]
    task = prompts.format_script_task(eid)
    assert "derive the cue sheet brief/CUES-v001.md" in task and str(d / "t.cues.md") in task
    (paths.episode_dir(eid) / "brief" / "SCRIPT-v001.md").write_text("# Script\n")
    assert prompts.cue_sheet_task(eid) is None
    assert "the gate checks the cue sheet derived" in showformats.prompt_block(eid)
