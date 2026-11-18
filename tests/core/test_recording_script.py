import pytest

from crewcut import db, episodes, paths, prompter


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
