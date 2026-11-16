"""The engine is never held back: every flag passes, nothing is swallowed, the newest version comes in with a way back."""

import json
from pathlib import Path

import pytest

from crewcut import engines, plugin, team
from crewcut.engines import claude_code, versions


def test_layers_pass_unknown_flags_and_user_wins():
    eng = engines.get("claude")
    t = engines.Task(prompt="go", system="ctx", cwd=Path("."), model="sonnet", effort="high", agent="crewcut:editor",
                     extra_args=["--effort", "max", "--flag-from-the-future", "x", "--output-format", "text",
                                 "--fallback-model", "opus"],
                     engine_options={"plugin_dirs": ["/p"]}, name="Editor · 001 · edit")
    cmd = eng.command(t)
    assert cmd[1:6] == ["-p", "go", "--output-format", "stream-json", "--verbose"]
    assert cmd.count("--output-format") == 1                      # layer 1 is protected
    assert cmd[cmd.index("--effort") + 1] == "max" and cmd.count("--effort") == 1   # the user wins over layer 2
    assert "--flag-from-the-future" in cmd and cmd[cmd.index("--flag-from-the-future") + 1] == "x"
    assert cmd[cmd.index("--agent") + 1] == "crewcut:editor" and cmd[cmd.index("--plugin-dir") + 1] == "/p"
    assert "--fallback-model" in cmd and "--name" in cmd
    assert any("ignored --output-format" in n for n in t.engine_options["notes"])


def test_empty_model_means_engine_default():
    cmd = engines.get("claude").command(engines.Task(prompt="go", system="", cwd=Path(".")))
    assert "--model" not in cmd and "--effort" not in cmd and "--append-system-prompt" not in cmd


def test_nothing_is_swallowed():
    eng = engines.get("claude")
    state = {"texts": [], "usage": {}, "session": None, "result": None, "cost": 0.0, "turns": 0, "error": ""}
    evs = eng.parse({"type": "stream_event_of_tomorrow", "x": 1}, state)
    assert evs and evs[0].kind == "raw" and "stream_event_of_tomorrow" in evs[0].text
    evs = eng.parse({"type": "assistant", "parent_tool_use_id": "t1",
                     "message": {"content": [{"type": "text", "text": "subagent says hi"}]}}, state)
    assert evs[0].kind == "subagent" and state["texts"] == []
    assert claude_code.describe_tool({"name": "mcp__crewcut__card_propose", "input": {}}) == "crewcut: card_propose"
    assert claude_code.describe_tool({"name": "Task", "input": {"subagent_type": "crewcut:critic",
                                                                "description": "check v1"}}) == "Hands over to critic: check v1"
    assert claude_code.describe_tool({"name": "BrandNewTool", "input": {"title": "Doing a thing"}}) == \
        "BrandNewTool: Doing a thing"
    codex = engines.get("codex")
    assert codex.parse({"type": "thread.archived"}, state)[0].kind == "raw"


def test_codex_passes_effort_config_and_extra():
    cmd = engines.get("codex").command(engines.Task(prompt="go", system="rules", cwd=Path("."), effort="high",
                                                    extra_args=["--oss"],
                                                    engine_options={"config": ['model_verbosity="low"']}))
    assert 'model_reasoning_effort="high"' in cmd and 'model_verbosity="low"' in cmd and "--oss" in cmd


class FakeNpm:
    """npm and the engine binary, without network: versions on channels, installs that create the binary."""

    def __init__(self, latest="2.0.1", broken=()):
        self.latest, self.broken, self.calls = latest, set(broken), []

    def __call__(self, cmd, timeout):
        self.calls.append(cmd)
        if cmd[:2] == ["npm", "view"]:
            return 0, self.latest + "\n"
        if cmd[:2] == ["npm", "install"]:
            prefix = Path(cmd[cmd.index("--prefix") + 1])
            (prefix / "bin").mkdir(parents=True, exist_ok=True)
            (prefix / "bin" / "claude").write_text("#!/bin/sh\n")
            return 0, "added 1 package"
        version = Path(cmd[0]).parent.parent.name
        if cmd[1] == "--version":
            return (1, "crash") if version in self.broken else (0, f"{version} (Claude Code)")
        if cmd[1] == "--help":
            return 0, "--output-format --verbose --append-system-prompt --resume --agents --plugin-dir"
        return 0, ""


@pytest.fixture
def prefix(tmp_path, monkeypatch):
    monkeypatch.setenv("CREWCUT_ENGINE_PREFIX", str(tmp_path / "engine"))
    return tmp_path / "engine"


def test_update_switches_after_smoke_and_rolls_back(prefix):
    npm = FakeNpm("2.0.1")
    r = versions.update("claude", run=npm, with_login=False)
    assert r["changed"] and versions.current_version("claude") == "2.0.1"
    assert (prefix / "current" / "claude" / "bin" / "claude").exists()
    assert versions.update("claude", run=npm, with_login=False)["notes"] == ["already on the newest version"]
    npm.latest = "2.0.2"
    assert versions.update("claude", run=npm, with_login=False)["current"] == "2.0.2"
    # a content error does not count, two engine errors in a row roll back
    assert versions.note_job("claude", False, "the script check found 3 errors", 1) is None
    assert versions.note_job("claude", False, "error: unknown option '--verbose'", 1) is None
    msg = versions.note_job("claude", False, "error: unknown option '--verbose'", 1)
    assert msg and "2.0.2 failed twice. Back on 2.0.1" in msg
    assert versions.current_version("claude") == "2.0.1" and "2.0.2" in versions.status("claude")["bad"]


def test_broken_version_is_never_used_and_offline_keeps_current(prefix):
    npm = FakeNpm("2.0.1")
    versions.update("claude", run=npm, with_login=False)
    npm.latest, npm.broken = "2.0.5", {"2.0.5"}
    r = versions.update("claude", run=npm, with_login=False)
    assert not r["changed"] and versions.current_version("claude") == "2.0.1"
    assert not (prefix / "versions" / "claude" / "2.0.5" / "bin" / "claude").exists() or "2.0.5" in \
        versions.status("claude")["bad"]
    offline = lambda cmd, t: (1, "network error")  # noqa: E731
    assert "offline" in versions.update("claude", run=offline, with_login=False)["notes"][0]


def test_plugin_has_crew_agents_skills_and_guard(tmp_path):
    d = plugin.build(tmp_path / "crewcut")
    meta = json.loads((d / ".claude-plugin" / "plugin.json").read_text())
    assert meta["name"] == "crewcut" and (d / "README.md").is_file()
    agents = sorted(p.stem for p in (d / "agents").glob("*.md"))
    assert agents == sorted(x["id"] for x in team.all_identities())
    editor = (d / "agents" / "editor.md").read_text()
    assert editor.startswith("---\nname: editor\n") and "spend money" in editor
    assert (d / "skills" / "edit" / "SKILL.md").is_file()
    hooks = json.loads((d / "hooks" / "hooks.json").read_text())
    assert hooks["hooks"]["PreToolUse"][0]["matcher"] == "Bash"


def test_guard_hook_rights():
    bash = lambda c, agent=None: {"tool_name": "Bash", "tool_input": {"command": c},  # noqa: E731
                                  **({"agent_type": agent} if agent else {})}
    assert not plugin.guard_decision(bash("crewcut youtube upload --episode 1", "crewcut:writer"), None)[0]
    assert plugin.guard_decision(bash("crewcut youtube upload --episode 1", "crewcut:publisher"), None)[0]
    assert not plugin.guard_decision(bash("crewcut compute rent --episode 1"), "scout")[0]
    assert plugin.guard_decision(bash("crewcut compute rent --episode 1"), "editor")[0]
    assert plugin.guard_decision(bash("crewcut thumbnail make --way codex --prompt p"), "writer")[0]
    assert not plugin.guard_decision(bash("crewcut thumbnail make --way api --prompt p"), "writer")[0]
    assert plugin.guard_decision({"tool_name": "Read", "tool_input": {}}, "writer")[0]


def test_crew_modes(crew, monkeypatch, studio):
    from crewcut import config, episodes
    from crewcut.conductor import queue
    monkeypatch.setattr(queue, "plugin_dir", lambda: "/plugin/crewcut")
    eid = episodes.create("x")["id"]
    job = {"id": 7, "episode": eid, "step": "edit", "identity": "editor", "task": "cut it", "data": {}}
    t = queue.build_task(job, engines.get("claude"), {})
    assert t.agent == "crewcut:editor" and "I work." not in t.system and t.env["CREWCUT_IDENTITY"] == "editor"
    assert t.engine_options["plugin_dirs"] == ["/plugin/crewcut"] and t.model is None
    orig_load = config.load
    monkeypatch.setattr(config, "load", lambda name: {**orig_load(name), "engine": {
        **orig_load(name).get("engine", {}), "claude": {**orig_load(name)["engine"]["claude"], "crew": "subagents"}}})
    t2 = queue.build_task(job, engines.get("claude"), {})
    assert t2.agent == "crewcut:showrunner" and t2.env["CREWCUT_CREW_MODE"] == "subagents"
    assert "crewcut:editor" in t2.prompt and "--forward-subagent-text" in t2.engine_options["flags"]
    monkeypatch.setenv("CREWCUT_IDENTITY", "showrunner")
    monkeypatch.setenv("CREWCUT_CREW_MODE", "subagents")
    from crewcut import approvals
    approvals.require_right("publish")  # one session holds the crew; the hook checks the subagent
