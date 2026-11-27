"""`crewcut motion`: reachable from the main command, every harness command answers, no REPL left. No engine needed."""

from __future__ import annotations

import json
from pathlib import Path

import click
import pytest

from crewcut.cli import main
from crewcut.motion import cli as mcli

MOTION = Path(__file__).resolve().parents[2] / "crewcut" / "motion"

# the 52 commands of the harness, under their names in `crewcut motion`
COMMANDS = {
    "info", "project new", "project open", "project info", "project save", "project profiles",
    "comp new", "comp list", "comp use", "comp set", "comp motion-blur", "comp info",
    *(f"layer add {k}" for k in ("solid", "text", "shape", "footage", "null", "camera", "light", "precomp")),
    *(f"layer {k}" for k in ("props", "get", "set", "switch", "timing", "parent", "matte", "blend")),
    "key set", "expr set", "expr preset", "effect apply", "effect list", "effect params", "text animator",
    "precompose", "template list", "template show", "run-template",
    "render frame", "render sheet", "render compare", "render video", "render palette",
    "session status", "session undo", "session redo", "session history",
    "exec", "batch", "script", "commands",
}
# the motion workflow (motion plan 3.1, 3.3, 3.6, 3.8): no engine needed
WORKFLOW = {"plan", "library", "new", "style-frame", "promote", "report", "lessons", "reference add",
            "reference from-chat", "reference list", "benchmark add", "benchmark list", "craft-compare", "reuse", "import-source-kit"}
# the ready-made libraries (docs/motion-libraries.md)
LIBRARIES = {"libraries", "style", "hf list", "hf show", "hf sample", "hf lint", "imports list", "imports add",
             "imports use", "imports convert"}


def _leaves(group: click.Group, prefix: str = "") -> set[str]:
    out: set[str] = set()
    for name, cmd in group.commands.items():
        if getattr(cmd, "hidden", False):
            continue
        path = f"{prefix}{name}"
        out |= _leaves(cmd, path + " ") if isinstance(cmd, click.Group) else {path}
    return out


def test_motion_help_lists_the_groups(capsys):
    assert main(["motion", "--help"]) == 0
    text = capsys.readouterr().out
    for group in ("project", "comp", "layer", "key", "expr", "effect", "text", "template", "run-template", "render",
                  "session", "exec", "batch", "script", "commands", "precompose", "info"):
        assert f"  {group} " in text, group


def test_motion_without_arguments_prints_help(capsys):
    assert main(["motion"]) == 0
    assert "Commands:" in capsys.readouterr().out


def test_crewcut_help_lists_motion(capsys):
    with pytest.raises(SystemExit) as e:
        main(["--help"])
    assert e.value.code == 0
    assert "motion" in capsys.readouterr().out


def test_all_52_commands_exist():
    assert len(COMMANDS) == 52
    assert _leaves(mcli.cli) == COMMANDS | WORKFLOW | LIBRARIES


def test_usage_error_is_exit_2(capsys):
    assert main(["motion", "no-such-group"]) == 2
    assert "No such command" in capsys.readouterr().err


def test_missing_engine_is_one_json_error(monkeypatch, capsys):
    monkeypatch.setenv("EFFECTCRAFT_CLI", "/nonexistent/effectcraft-cli")
    monkeypatch.setenv("PATH", "/nonexistent")
    assert main(["motion", "info", "--json"]) == 1
    err = json.loads(capsys.readouterr().out)["error"]
    assert "effectcraft-cli not found" in err and "third_party/effectcraft" in err


def test_palette_exit_3_above_the_limit(tmp_path, capsys):
    from PIL import Image
    one = tmp_path / "one.png"
    Image.new("RGB", (32, 32), (15, 110, 92)).save(one)
    assert main(["motion", "render", "palette", str(one)]) == 3
    assert "REWORK" in capsys.readouterr().out
    assert main(["motion", "--json", "render", "palette", str(one)]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is False
    grey = tmp_path / "grey.png"
    Image.new("RGB", (32, 32), (128, 128, 128)).save(grey)
    assert main(["motion", "render", "palette", str(grey)]) == 0


def test_template_list_reads_the_templates_dir(capsys):
    launch = Path(__file__).resolve().parents[2] / "examples" / "launch-film" / "templates"
    assert main(["motion", "--templates-dir", str(launch), "--json", "template", "list"]) == 0
    listed = {t["name"]: t for t in json.loads(capsys.readouterr().out)}
    own = {p.stem for p in launch.glob("*.jsx")}
    app = {p.stem for p in (MOTION.parents[1] / "templates" / "motion").glob("*.jsx")}
    assert len(own) == 13 and own <= set(listed) and set(listed) == own | app
    assert {"burst_rings", "word_reel", "glass_prompt_typing"} <= set(listed)
    if "path" in listed["word_reel"]:                      # the --templates-dir copy wins over the app's own
        assert Path(listed["word_reel"]["path"]).parent == launch


def test_no_repl_left():
    for p in MOTION.rglob("*.py"):
        text = p.read_text(encoding="utf-8")
        assert "prompt_toolkit" not in text, p.name
        assert "repl_skin" not in text, p.name
        assert "cli_anything" not in text, p.name
