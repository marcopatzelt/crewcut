"""Bring your own skills: the studio's own skills reach the right crew member on the right step, on both engines, as a
Claude Code plugin with links to the user's folders, and win over Crewcut's generic skills on content and style. The
channel brief reaches every job."""

import json
from pathlib import Path

import pytest

from crewcut import cli, engines, ownskills, plugin, team
from crewcut.conductor import prompts, queue

SKILL = "---\nname: {name}\ndescription: test skill\n---\n\n# {name}\n\nRule: {rule}\n"


def make_skill(studio: Path, name: str, rule: str, adapter: str | None = None, where: str | None = None) -> Path:
    d = studio / (where or f"skills/{name}")
    (d / "scripts").mkdir(parents=True)
    (d / "SKILL.md").write_text(SKILL.format(name=name, rule=rule), encoding="utf-8")
    (d / "scripts" / "check.py").write_text("print('checked')\n", encoding="utf-8")
    if adapter:
        (d / "CREWCUT.md").write_text(adapter, encoding="utf-8")
    return d


def configure(studio: Path, entries: list[dict]) -> None:
    (studio / "config").mkdir(exist_ok=True)
    lines = []
    for e in entries:
        lines.append("[[skills.own]]")
        for k, v in e.items():
            lines.append(f"{k} = {json.dumps(v)}")
        lines.append("")
    (studio / "config" / "crewcut.toml").write_text("\n".join(lines), encoding="utf-8")


@pytest.fixture
def own(studio, crew):
    make_skill(studio, "my-titles", "titles in German, at most 45 characters", adapter="Old tools/x.py -> crewcut y")
    make_skill(studio, "my-ideas", "ideas solve an operations problem")
    make_skill(studio, "my-showrunner", "run the episode in this order")
    configure(studio, [
        {"name": "my-titles", "steps": ["title"], "replaces": ["title"]},
        {"name": "my-ideas", "steps": ["idea"], "roles": ["scout"]},
        {"name": "my-showrunner", "steps": ["*"], "roles": ["showrunner"]},
        {"name": "missing", "steps": ["script"]},
        {"name": "escape", "steps": ["script"], "path": "../outside"},
    ])
    return studio


def test_config_matching_and_problems(own):
    by = {s["name"]: s for s in ownskills.configured()}
    assert by["my-titles"]["ok"] and by["my-titles"]["adapter"].endswith("CREWCUT.md")
    assert not by["missing"]["ok"] and "SKILL.md" in by["missing"]["problem"]
    assert not by["escape"]["ok"] and "leaves the studio" in by["escape"]["problem"]
    assert [s["name"] for s in ownskills.for_job("scout", "title")] == ["my-titles"]
    assert [s["name"] for s in ownskills.for_job("scout", "idea")] == ["my-ideas"]
    assert ownskills.for_job("writer", "idea") == []                     # roles limit who gets it
    assert [s["name"] for s in ownskills.for_job("showrunner", None)] == ["my-showrunner"]  # "*" covers channel work
    assert ownskills.for_job("writer", "script") == []                   # broken entries never reach a job


def test_claude_loads_them_as_a_plugin_with_links_to_the_studio(own, monkeypatch):
    monkeypatch.setattr(queue, "plugin_dir", lambda: "/plugin/crewcut")
    job = {"id": 3, "episode": None, "step": "title", "identity": "scout", "task": "five titles", "data": {}}
    t = queue.build_task(job, engines.get("claude"), {})
    pdir = Path(t.engine_options["plugin_dirs"][-1])
    assert t.engine_options["plugin_dirs"][0] == "/plugin/crewcut"
    assert json.loads((pdir / ".claude-plugin" / "plugin.json").read_text())["name"] == "studio"
    link = pdir / "skills" / "my-titles"
    assert link.is_symlink() and (link / "scripts" / "check.py").resolve() == (
        own / "skills" / "my-titles" / "scripts" / "check.py").resolve()
    assert "`studio:my-titles`" in t.system and "wins over Crewcut's generic skills" in t.system
    assert "overrides Crewcut's `title`" in t.system and "CREWCUT.md" in t.system
    assert "before any Crewcut skill" in t.system
    assert "Rule: titles in German" not in t.prompt                     # Claude reads it as a skill, not as text
    before = (pdir / ".crewcut-links.json").stat().st_mtime_ns
    ownskills.build_plugin()
    assert (pdir / ".crewcut-links.json").stat().st_mtime_ns == before  # unchanged set: not rebuilt under a run


def test_codex_gets_the_text_with_the_adapter_note(own):
    job = {"id": 4, "episode": None, "step": "title", "identity": "scout", "task": "five titles", "data": {}}
    t = queue.build_task(job, engines.get("codex"), {})
    assert "Rule: titles in German, at most 45 characters" in t.prompt
    assert "Old tools/x.py -> crewcut y" in t.prompt
    assert "operations problem" not in t.prompt                         # only the skills of this step
    assert "`studio:my-titles`" in t.system


def test_subagent_mode_selects_by_the_worker_and_agent_files_list_them(own, monkeypatch):
    from crewcut import config
    monkeypatch.setattr(queue, "plugin_dir", lambda: "/plugin/crewcut")
    orig = config.load
    monkeypatch.setattr(config, "load", lambda name: {**orig(name), "engine": {
        **orig(name).get("engine", {}), "claude": {**orig(name)["engine"]["claude"], "crew": "subagents"}}})
    job = {"id": 5, "episode": None, "step": "idea", "identity": "scout", "task": "an idea", "data": {}}
    t = queue.build_task(job, engines.get("claude"), {})
    assert t.agent == "crewcut:showrunner" and "`studio:my-ideas`" in t.system
    md = plugin.agent_markdown(team.get("scout"))
    assert "`studio:my-ideas` (idea)" in md and "`studio:my-titles` (title)" in md
    assert "my-showrunner" not in md


def test_every_run_of_a_step_loads_its_own_skill(own, monkeypatch):
    """The step run, a job from the chat and the answer to a card (a resumed conversation) are each told in their own
    task to load the step's own skill, the same one, not only in the system text."""
    from crewcut import approvals, db, episodes
    from crewcut.conductor import flow
    monkeypatch.setattr(queue, "plugin_dir", lambda: "/plugin/crewcut")
    episode = episodes.create("Synthetic episode")["id"]
    step_run = flow.start_step(episode, "title")
    db.update("jobs", step_run, data={"engine": "claude", "session": "synthetic-session"})
    card = approvals.propose(episode, "title", "rule", "New rule for title: synthetic", identity="scout",
                             data={"step": "title", "rule": "synthetic", "source": "test"}, job=step_run)
    approvals.decide(card["id"], accepted=False, reason="Not like this")
    with db.conn() as c:
        answer = queue.get(c.execute("SELECT MAX(id) AS id FROM jobs").fetchone()["id"])
    assert answer["task"].startswith("The user did not accept card") and answer["data"]["resume"]
    from_chat = queue.get(queue.add(episode, "scout", "title", "The user asked for shorter titles."))
    for job in (queue.get(step_run), answer, from_chat):
        for engine in ("claude", "codex"):
            t = queue.build_task(job, engines.get(engine), dict(job.get("data") or {}))
            assert "load the user's own skill for this work, `studio:my-titles`" in t.prompt
            assert "also when this conversation loaded it before" in t.prompt
            assert "not those of Crewcut's `title` skill" in t.prompt
            assert "my-ideas" not in t.prompt and "my-showrunner" not in t.prompt
    chat_reply = {"id": 9, "episode": episode, "step": None, "identity": "showrunner", "task": "answer", "data": {}}
    assert "load the user's own skill" not in queue.build_task(chat_reply, engines.get("claude"), {}).prompt


def test_a_long_skill_is_named_instead_of_pasted(own):
    skills = ownskills.for_job("scout", "title")
    assert "too long to include" in ownskills.skill_texts(skills, limit=10)


def test_no_own_skills_changes_nothing(studio, crew, monkeypatch):
    monkeypatch.setattr(queue, "plugin_dir", lambda: "/plugin/crewcut")
    job = {"id": 6, "episode": None, "step": "title", "identity": "scout", "task": "x", "data": {}}
    t = queue.build_task(job, engines.get("claude"), {})
    assert t.engine_options["plugin_dirs"] == ["/plugin/crewcut"] and "studio:" not in t.system
    assert ownskills.build_plugin() is None


def test_cli_lists_own_skills(own, capsys):
    assert cli.main(["skills", "own", "--json"]) == 0
    rows = json.loads(capsys.readouterr().out)
    assert {r["name"]: r["ok"] for r in rows}["my-titles"] is True


def test_channel_brief_reaches_every_job(studio, crew):
    from crewcut import approvals, briefing
    pack = approvals.ensure_user_pack()
    (pack / "channel.json").write_text(json.dumps({"name": "Test channel", "language": "de",
                                                   "topics_to_avoid": ["drama"]}), encoding="utf-8")
    (pack / "brief.md").write_text("Ideas solve one operations problem of the business.\n", encoding="utf-8")
    review = studio / "episodes" / "001-x" / "review"
    review.mkdir(parents=True)
    (studio / "episodes" / "001-x" / "project.json").write_text(json.dumps({"title": "A real title"}))
    (review / "results-2026-11-01-2026-11-03.json").write_text(json.dumps({
        "episode": "001-x", "fetched_at": "2026-11-04T10:00:00", "period": {"start": "2026-11-01", "end": "2026-11-03"},
        "metrics": {"views": 146, "averageViewPercentage": 56.2, "subscribersGained": 3}}))
    text = briefing.text()
    assert "Test channel" in text and "Avoid: drama" in text and "channel language (de)" in text
    assert "operations problem" in text
    assert "001-x “A real title”" in text and "146 views" in text and "56 % watched" in text
    for scope in ("episode", "channel"):
        s = prompts.system_prompt(team.get("showrunner"), None, None, conversation_scope=scope)
        assert "operations problem" in s and "CHANNEL BRIEF" in s


def test_neutral_studio_has_no_brief(studio):
    from crewcut import briefing
    assert briefing.text() == ""


def test_an_unreadable_folder_is_reported_not_a_crash(own, monkeypatch):
    real_is_file = Path.is_file

    def is_file(self):
        if self.name == "SKILL.md" and self.parent.name == "my-ideas":
            raise PermissionError(13, "Permission denied")
        return real_is_file(self)
    monkeypatch.setattr(Path, "is_file", is_file)
    by = {s["name"]: s for s in ownskills.configured()}
    assert not by["my-ideas"]["ok"] and "cannot be read" in by["my-ideas"]["problem"]
    assert by["my-titles"]["ok"]
    text = prompts.system_prompt(team.get("scout"), None, "idea")
    assert "`studio:my-ideas`" not in text and "`my-ideas` belongs to this work but cannot be used" in text


def test_a_replaced_crewcut_skill_points_to_the_users_own(own):
    ident = {**team.get("scout"), "skills": ["title", "idea"]}
    text = prompts.system_prompt(ident, None, "title")
    assert "title/SKILL.md (here only for Crewcut's commands and workflow: the user's `studio:my-titles` comes first)" \
        in text
    assert "idea/SKILL.md (here only" not in text
