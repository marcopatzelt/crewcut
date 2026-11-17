"""The motion skill: files, language, pictures, the example template, and every command it names against the real CLI."""

from __future__ import annotations

import argparse
import importlib
import re
from pathlib import Path

import click
import pytest
from conftest import ROOT

SKILL = ROOT / "skills" / "motion"
REFERENCES = ("pipeline", "harness", "templates", "engine-pitfalls", "blender-plates", "review", "lessons",
              "director", "ratchet", "calm-in-video", "matte", "cost")
PICTURE_MAX = 150 * 1024
PICTURES_MAX = 3 * 1024 * 1024

# Commands the skill names that other branches add (motion pass, custom motion, library, ratchet, matte, retention).
# They exist after those branches are merged; until then their test is an expected failure.
PENDING = (
    "render motion", "render motion-review", "render matte", "render plates",
    "motion plan", "motion new", "motion library", "motion promote", "motion report",
    "youtube retention",
)

# Common German words that never appear in English text (words that are English too, like "die" or "an", are left out).
GERMAN = {"und", "der", "das", "nicht", "ist", "für", "auf", "wird", "eine", "einen", "auch", "oder", "wenn",
          "noch", "nur", "bei", "nach", "über", "sind", "werden", "kann", "muss", "jetzt", "schon", "immer", "keine",
          "sehr", "zum", "zur", "beim", "aber", "weil", "dass", "hier", "dann", "ich", "wir", "sie", "ein", "dem",
          "des", "vom", "bis", "beispiel", "schritt", "datei", "ordner", "bild", "vergleich", "platten"}
MENTION = re.compile(r"(?<![\w./-])crewcut((?: +[a-z0-9][a-z0-9_-]*)+)")


def texts() -> dict[Path, str]:
    return {p: p.read_text(encoding="utf-8") for p in sorted(SKILL.rglob("*.md"))}


def pictures() -> list[Path]:
    return sorted(p for p in SKILL.rglob("*") if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".gif"})


# ---------------------------------------------------------------- the real CLI as a tree of command names

def _argparse_tree(p: argparse.ArgumentParser) -> dict:
    out: dict = {}
    for a in p._actions:
        if isinstance(a, argparse._SubParsersAction):
            for name, sub in a.choices.items():
                out[name] = _argparse_tree(sub)
    return out


def _click_tree(cmd: click.Command) -> dict:
    return {n: _click_tree(c) for n, c in cmd.commands.items()} if isinstance(cmd, click.Group) else {}


def _module_tree(mod) -> dict:
    for attr in ("build_parser", "parser", "_parser"):
        f = getattr(mod, attr, None)
        if callable(f):
            p = f()
            if isinstance(p, argparse.ArgumentParser):
                return _argparse_tree(p)
    for v in vars(mod).values():
        if isinstance(v, click.Group) and v.name in (None, "cli"):
            return _click_tree(v)
    raise AssertionError(f"{mod.__name__}: no argparse parser or click group found")


def cli_tree() -> dict:
    """`crewcut` as {command: {subcommand: {...}}}, read from the parsers the CLI itself uses (top level and every
    delegated part)."""
    from crewcut import cli
    tree = _argparse_tree(cli.build_parser())
    for cmd, (modname, _with_cmd) in cli.DELEGATED.items():
        sub = _module_tree(importlib.import_module(modname))
        # crewcut.cut.cli parses the whole word list itself ("ingest", "transcribe", "cut ..."), the others the rest
        tree[cmd] = sub[cmd] if cmd in sub and modname == "crewcut.cut.cli" else sub
    return tree


def resolve(tree: dict, words: list[str]) -> str | None:
    """None when the command path exists; else the first word that is not a command. Words after a leaf command are
    its arguments."""
    node = tree
    for w in words:
        if not node:
            return None
        if w not in node:
            return w
        node = node[w]
    return None


def mentions() -> dict[str, list[str]]:
    """'group command' -> the files that name it, for every `crewcut ...` in the skill."""
    out: dict[str, list[str]] = {}
    for p, t in texts().items():
        for m in MENTION.finditer(t):
            words = m.group(1).split()
            out.setdefault(" ".join(words), []).append(str(p.relative_to(ROOT)))
    return out


# ---------------------------------------------------------------- files and words

def test_files_exist():
    assert (SKILL / "SKILL.md").is_file()
    for name in REFERENCES:
        assert (SKILL / "references" / f"{name}.md").is_file(), name
    skill = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    assert skill.startswith("---\nname: motion\ndescription: ")
    for name in REFERENCES:
        assert f"references/{name}.md" in skill, f"SKILL.md does not point to references/{name}.md"


def test_no_local_paths():
    for p, t in texts().items():
        for bad in ("/home/", "/root/", "~/dev"):
            assert bad not in t, f"{p.relative_to(ROOT)} holds a local path ({bad})"


def test_english_only():
    for p, t in texts().items():
        assert not re.search(r"[äöüÄÖÜß]", t), f"{p.relative_to(ROOT)} holds German letters"
        words = {w.lower() for w in re.findall(r"[A-Za-z]+", t)}
        hits = sorted(words & GERMAN)
        assert not hits, f"{p.relative_to(ROOT)} holds German words: {hits}"


def test_pictures_are_light_and_all_named():
    pics = pictures()
    assert pics, "no lesson pictures"
    assert all(p.parent == SKILL / "references" / "lessons" for p in pics)
    for p in pics:
        assert p.stat().st_size <= PICTURE_MAX, f"{p.name}: {p.stat().st_size} bytes (at most {PICTURE_MAX})"
    assert sum(p.stat().st_size for p in pics) <= PICTURES_MAX
    lessons = (SKILL / "references" / "lessons.md").read_text(encoding="utf-8")
    named = set(re.findall(r"lessons/([\w.-]+\.jpg)", lessons))
    assert named == {p.name for p in pics}


def test_example_template_parses_and_passes_the_lint():
    from crewcut.motion import review, templates
    text = (SKILL / "references" / "templates.md").read_text(encoding="utf-8")
    src = re.search(r"```js\n(.*?)```", text, re.S).group(1)
    h = templates.parse_header(src)
    assert h["kind"] == "overlay" and h["formats"] == ["landscape", "portrait", "stage"] and h["version"] == 1
    assert {s["at"] for s in h["sounds"]} <= set(h["defaults"]) | {"in", "out"}
    errors = [x for x in review.lint_jsx(src, h["defaults"]) if x["level"] == "ERROR"]
    assert errors == []


# ---------------------------------------------------------------- commands against the real CLI

def test_the_cli_tree_reads_the_real_parsers():
    tree = cli_tree()
    assert {"card", "compute", "render", "motion", "cut", "say"} <= set(tree)
    assert "frame" in tree["motion"]["render"] and "text" in tree["motion"]["layer"]["add"]
    assert "estimate" in tree["compute"] and "probe" in tree["render"] and "build" in tree["cut"]
    assert resolve(tree, ["motion", "layer", "add", "nothing"]) == "nothing"
    assert resolve(tree, ["render", "plan", "edit"]) is None


def test_every_named_command_exists():
    tree = cli_tree()
    found = mentions()
    assert len(found) >= 20
    missing = {}
    for cmd, where in found.items():
        words = cmd.split()
        if " ".join(words[:2]) in PENDING:
            continue
        bad = resolve(tree, words)
        if bad is not None:
            missing[cmd] = (bad, where)
    assert not missing, f"commands the CLI does not know: {missing}"


def test_pending_commands_are_named_in_the_skill():
    named = {" ".join(c.split()[:2]) for c in mentions()}
    assert set(PENDING) <= named, sorted(set(PENDING) - named)


@pytest.mark.parametrize("cmd", [pytest.param(c, marks=pytest.mark.xfail(
    strict=False, reason="added by a parallel branch of the motion plan; exists after the merge")) for c in PENDING])
def test_pending_command_exists(cmd):
    assert resolve(cli_tree(), cmd.split()) is None, f"crewcut {cmd} is not in the CLI yet"
