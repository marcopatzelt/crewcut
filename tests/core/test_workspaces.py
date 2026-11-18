import json
import subprocess
import sys

import pytest

from crewcut import cli, engines, plugin, workspaces
from crewcut.conductor import prompts, queue


def test_create_reuse_and_run_project(studio):
    result = workspaces.create("render-study", "015-example")
    project = workspaces.root() / "render-study"
    source = project / "code" / "estimate.py"
    source.write_text("print(240 * 2.5)\n")
    manifest = (project / "workspace.json").read_text()
    assert workspaces.create("render-study") == result
    assert source.read_text() == "print(240 * 2.5)\n"
    assert (project / "workspace.json").read_text() == manifest
    assert json.loads(manifest)["episode"] == "015-example"
    assert subprocess.check_output([sys.executable, str(source)], cwd=project, text=True).strip() == "600.0"
    assert result["path"] == str(studio / "workspaces" / "render-study")
    assert workspaces.list_workspaces() == [{"name": "render-study", "path": str(project)}]


@pytest.mark.parametrize("name", ["../app", "/tmp/test", "", ".", "../episodes/test", "name with spaces"])
def test_reject_invalid_names(name):
    with pytest.raises(ValueError):
        workspaces.create(name)


@pytest.mark.parametrize("link", ["workspaces", "workspaces/test", "workspaces/test/code",
                                  "workspaces/test/workspace.json"])
def test_reject_symlink_destinations(studio, tmp_path, link):
    target = tmp_path / "outside"
    target.mkdir()
    destination = studio / link
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.symlink_to(target, target_is_directory=True)
    with pytest.raises(ValueError):
        workspaces.create("test")
    assert list(target.iterdir()) == []


def test_cli(capsys):
    assert cli.main(["workspace", "list"]) == 0
    assert json.loads(capsys.readouterr().out) == []
    assert cli.main(["workspace", "create", "study"]) == 0
    assert json.loads(capsys.readouterr().out)["name"] == "study"
    assert cli.main(["workspace", "create", "../bad"]) == 1


@pytest.mark.parametrize("engine", ["claude", "codex"])
@pytest.mark.parametrize("scope", ["channel", "episode"])
def test_job_capabilities_for_both_engines(crew, monkeypatch, engine, scope):
    monkeypatch.setattr(queue, "plugin_dir", lambda: None)
    job = {"id": 1, "identity": "scout", "episode": "001-test" if scope == "episode" else None,
           "step": "proof", "task": "Research and calculate", "data": {"conversation_scope": scope}}
    task = queue.build_task(job, engines.get(engine), job["data"])
    assert task.env["CREWCUT_WORKSPACES"] == str(workspaces.root())
    assert str(workspaces.root()) in task.extra_dirs
    assert "workspace create" in task.system
    assert "Never touch files outside the studio folder and the episode" not in task.system
    assert "Do not present an estimate as a measurement" in task.system
    assert "No mouse, keyboard" in task.system
    assert "Crewcut's source" in task.system
    assert "Never bypass Crewcut's cards" in task.system


def test_subagent_instructions_include_workspace_capabilities():
    agent = plugin.agent_markdown({"id": "scout", "name": "Scout", "role": "Research", "skills": []})
    assert "workspace create" in agent
    assert "no spending, no publishing" in agent
    assert "No mouse, keyboard" in agent
    assert "workspaces" in prompts.channel_task("Build a small comparison script")
