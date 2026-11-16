"""The Humanizer pass: the skill comes from GitHub at start (newest, with a way to stay), the record of what changed is
computed from the two files, a script card needs it, and the voice sample comes from the user's own captions."""

import io
import json
import tarfile

import pytest

from crewcut import approvals, episodes, extskills, humanize, voice


def tarball(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for name, text in files.items():
            data = text.encode()
            info = tarfile.TarInfo(f"humanizer-4.0.0/{name}")
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()


SKILL = "---\nname: humanizer\ndescription: test\n---\n\n# Humanizer (test stand-in)\n"
PLUGIN = json.dumps({"name": "humanizer", "skills": ["./"]})


def fake_github(tag="v4.0.0", files=None, online=True):
    files = files or {"SKILL.md": SKILL, ".claude-plugin/plugin.json": PLUGIN}

    def fetch(url, timeout=20):
        if not online:
            raise OSError("offline")
        if url.endswith("/releases/latest"):
            return json.dumps({"tag_name": tag}).encode()
        if "codeload.github.com" in url:
            assert url.endswith(f"/refs/tags/{tag}")
            return tarball(files)
        raise AssertionError(url)
    return fetch


@pytest.fixture
def engine_prefix(tmp_path, monkeypatch):
    monkeypatch.setenv("CREWCUT_ENGINE_PREFIX", str(tmp_path / "engine"))
    return tmp_path / "engine"


def test_update_installs_the_newest_release_and_loads_it_as_a_plugin(engine_prefix):
    res = extskills.update(fetch=fake_github("v4.0.0"))
    assert res[0]["changed"] and res[0]["current"] == "v4.0.0"
    cur = extskills.current("humanizer")
    assert cur["version"] == "v4.0.0" and cur["skill"] == "humanizer" and cur["license"] == "MIT"
    assert extskills.plugin_dirs() == [cur["path"]]
    assert extskills.for_step("script")[0]["name"] == "humanizer"
    assert extskills.for_step("edit") == []
    assert "Humanizer (test stand-in)" in extskills.skill_text("humanizer")


def test_offline_or_broken_keeps_the_current_version(engine_prefix):
    extskills.update(fetch=fake_github("v4.0.0"))
    off = extskills.update(fetch=fake_github("v4.1.0", online=False))
    assert not off[0]["changed"] and "offline" in off[0]["notes"][0]
    broken = extskills.update(fetch=fake_github("v4.2.0", files={"README.md": "no skill here"}))
    assert not broken[0]["changed"] and "could not be installed" in broken[0]["notes"][0]
    assert extskills.current("humanizer")["version"] == "v4.0.0"
    newer = extskills.update(fetch=fake_github("v4.3.0"))
    assert newer[0]["changed"] and extskills.current("humanizer")["version"] == "v4.3.0"


def test_archive_paths_cannot_leave_the_skill_folder(engine_prefix, tmp_path):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        data = b"x"
        info = tarfile.TarInfo("top/../../evil.txt")
        info.size = 1
        tf.addfile(info, io.BytesIO(data))
    with pytest.raises(ValueError):
        extskills._safe_extract(buf.getvalue(), tmp_path / "out")
    assert not (tmp_path / "evil.txt").exists()


def test_changes_are_computed_sentence_by_sentence():
    draft = "I ran five models. This is not just a test, it is a whole new way to work. Fast, cheap and good.\n---\nnote"
    final = "I ran five models. It was a test of one laptop. It was fast and cheap.\n---\nother note"
    ch = humanize.changes(draft, final)
    assert ch == [{"before": "This is not just a test, it is a whole new way to work. Fast, cheap and good.",
                   "after": "It was a test of one laptop. It was fast and cheap."}]
    assert humanize.changes("Same text.", "Same text.") == []


def _script_episode(studio):
    ep = episodes.create("Humanizer test")
    d = studio / "episodes" / ep["id"]
    (d / "work").mkdir(exist_ok=True)
    (d / "work" / "script-draft-v001.md").write_text("It is not a tool, it is a team. And that changes everything.\n")
    (d / "brief" / "SCRIPT-v001.md").write_text("It is a team.\n")
    return ep["id"], d


def test_a_script_card_needs_the_record_of_the_exact_file(studio, engine_prefix, crew):
    extskills.update(fetch=fake_github("v4.0.0"))
    eid, d = _script_episode(studio)
    with pytest.raises(humanize.Missing):
        approvals.propose(eid, "script", "script", "Script, version 1", file="brief/SCRIPT-v001.md")
    (studio / "brand" / "voice").mkdir(parents=True)
    (studio / "brand" / "voice" / "a.md").write_text("# a\n\nwords\n")
    rec = humanize.record(d, "work/script-draft-v001.md", "brief/SCRIPT-v001.md", why="not X but Y")
    assert rec["count"] == 1 and rec["mode"] == "embedded" and rec["skill"]["version"] == "v4.0.0"
    card = approvals.propose(eid, "script", "script", "Script, version 1", file="brief/SCRIPT-v001.md")
    hz = card["data"]["humanizer"]
    assert hz["count"] == 1 and hz["voice"] == ["brand/voice/a.md"] and hz["why"] == "not X but Y"
    # the file changed after the pass: the record no longer fits
    (d / "brief" / "SCRIPT-v001.md").write_text("It is a team. Changed later.\n")
    with pytest.raises(humanize.Missing):
        approvals.propose(eid, "script", "script", "Script, version 1", file="brief/SCRIPT-v001.md")


def test_without_humanizer_installed_or_switched_off_the_card_says_so(studio, engine_prefix, crew, monkeypatch):
    eid, _ = _script_episode(studio)
    card = approvals.propose(eid, "script", "script", "Script", file="brief/SCRIPT-v001.md")
    assert "could not be installed" in card["data"]["humanizer"]["skipped"]
    monkeypatch.setattr(extskills, "humanizer_enabled", lambda: False)
    card = approvals.propose(eid, "script", "script", "Script", file="brief/SCRIPT-v001.md")
    assert card["data"]["humanizer"]["skipped"] == "switched off in this studio"
    other = approvals.propose(eid, "title", "title", "Pick a title")
    assert "humanizer" not in (other.get("data") or {})


def test_voice_sample_from_captions(studio):
    vtt = ("WEBVTT\nKind: captions\nLanguage: en\n\n00:00:00.000 --> 00:00:02.000\n<c>So I ran</c> five models\n\n"
           "00:00:02.000 --> 00:00:04.000\nSo I ran five models\non my laptop &amp; one was fast.\n")
    assert voice.vtt_text(vtt) == "So I ran five models on my laptop & one was fast."
    with pytest.raises(voice.VoiceError):
        voice.write_sample("short", "x", "captions", "too short")
    text = " ".join(["word"] * 60)
    for i in range(4):
        voice.write_sample(f"Video {i}", f"https://example.com/{i}", "captions", text)
    assert len(voice.samples()) <= voice.KEEP
    assert humanize.voice_samples()[0].startswith("brand/voice/")
