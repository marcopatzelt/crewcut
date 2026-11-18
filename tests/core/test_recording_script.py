import pytest

from crewcut import db, episodes, paths, prompter


def test_reading_line_and_mirror_persist_without_starting_playback(crew):
    episode = episodes.create("Reading line")["id"]
    prompter.set_control(episode, {"guide": 57, "mirror": True})
    saved = prompter.control(episode)
    assert saved["guide"] == 57 and saved["mirror"] is True and saved["playing"] is False
    assert prompter.set_control(episode, {"guide": 200})["guide"] == 85
    assert prompter.set_control(episode, {"guide": -20})["guide"] == 10
    assert prompter.set_control(episode, {"guide": float("nan")})["guide"] == 10


def test_qr_is_an_inline_svg_without_xml_declaration():
    from xml.etree import ElementTree
    svg = prompter.qr_svg("http://localhost:4748/p/synthetic")
    assert svg.startswith("<svg")
    assert "<?xml" not in svg
    root = ElementTree.fromstring(svg)
    path = root.find("{http://www.w3.org/2000/svg}path")
    assert path is not None and path.get("d")


def test_selected_partial_script_is_visible_without_approval(crew):
    episode = episodes.create("Partial recording")["id"]
    root = paths.episode_dir(episode)
    (root / "brief/block-a.md").write_text("Only the first section.")
    before = episodes.read(episode)["steps"]
    prompter.select_script(episode, "brief/block-a.md", partial=True)
    script = prompter.script(episode)
    assert script["file"] == "brief/block-a.md"
    assert script["note"].startswith("Partial script")
    assert episodes.read(episode)["steps"] == before
    with db.conn() as connection:
        assert connection.execute("SELECT COUNT(*) FROM cards").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 0
    (root / "brief/block-a.md").unlink()
    with pytest.raises(FileNotFoundError, match="selected"):
        prompter.script(episode)


def test_script_selection_rejects_escape_and_non_text(crew, tmp_path):
    episode = episodes.create("Recording")["id"]
    secret = tmp_path / "outside.txt"
    secret.write_text("synthetic")
    (paths.episode_dir(episode) / "brief/link.txt").symlink_to(secret)
    with pytest.raises(ValueError):
        prompter.select_script(episode, "brief/link.txt")
    with pytest.raises(ValueError):
        prompter.select_script(episode, "project.json")


def test_selection_does_not_replace_an_approved_script(crew):
    episode = episodes.create("Approved recording")["id"]
    root = paths.episode_dir(episode)
    for name in ("approved", "draft"):
        (root / f"brief/{name}.md").write_text(name)
    db.insert("cards", episode=episode, step="script", identity="writer", kind="script", title="Approved script",
              file="brief/approved.md", status="accepted", created=db.now())
    with pytest.raises(ValueError, match="approved"):
        prompter.select_script(episode, "brief/draft.md")
    assert prompter.script_file(episode) == root / "brief/approved.md"
