import json
from pathlib import Path

import pytest
import yaml

from crewcut import studio_import


def source_episode(tmp_path, name="S001-example"):
    source = tmp_path / "old" / "episodes" / name
    (source / "00-brief").mkdir(parents=True)
    (source / "00-brief" / "SCRIPT-DE-v001.md").write_text("Earlier draft")
    (source / "00-brief" / "AUFNAHME-DE-v001.txt").write_text("Recording text")
    (source / "project.json").write_text(json.dumps({"title": "Example", "stage": "published"}))
    return source


def test_import_is_private_paused_and_repeatable(tmp_path):
    source = source_episode(tmp_path)
    destination = tmp_path / "private"
    report = studio_import.import_episode(source, destination)
    target = destination / "episodes" / source.name
    project = json.loads((target / "project.json").read_text())
    assert report["script"]
    assert (target / "brief" / "SCRIPT-v001.md").read_text() == "Recording text"
    assert project["kind"] == "short"
    assert project["steps"]["upload"]["status"] == "unknown"
    assert project["steps"]["record"]["status"] == "unknown"
    assert project["production"]["script"]["scope"] == "draft"
    assert project["created"] is None
    assert project["imported_at"]
    assert project["legacy"]["stage"] == "published"
    assert not (destination / ".crewcut" / "crewcut.db").exists()
    assert studio_import.import_episode(source, destination)["status"] == "already imported"
    (target / "legacy" / "00-brief" / "AUFNAHME-DE-v001.txt").write_text("Changed copy")
    assert (source / "00-brief" / "AUFNAHME-DE-v001.txt").read_text() == "Recording text"


def test_excludes_hidden_credentials_symlinks_and_working_files(tmp_path):
    source = source_episode(tmp_path)
    for name in (".env", "token.json", "client_secret.json", "0001.png"):
        (source / name).write_text("excluded")
    for name in (".claude", "02-working", "secrets", "node_modules"):
        (source / name).mkdir()
        (source / name / "private.txt").write_text("excluded")
    (source / "link.txt").symlink_to(source / "project.json")
    assert {str(path) for path in studio_import.inventory(source)} == {
        "project.json", "00-brief/SCRIPT-DE-v001.md", "00-brief/AUFNAHME-DE-v001.txt"}


def test_preserves_existing_episode(tmp_path):
    source = source_episode(tmp_path)
    destination = tmp_path / "private"
    (destination / "episodes" / source.name).mkdir(parents=True)
    with pytest.raises(FileExistsError):
        studio_import.import_episode(source, destination)


def test_no_script_is_not_claimed_done(tmp_path):
    source = tmp_path / "015-example"
    source.mkdir()
    project = studio_import.episode_project(source, {}, False)
    assert project["steps"]["script"]["status"] == "unknown"
    assert project["kind"] == "episode"


def test_manifest_has_copy_hash(tmp_path):
    source = source_episode(tmp_path)
    destination = tmp_path / "private"
    studio_import.import_episode(source, destination)
    manifest = json.loads((destination / "episodes" / source.name / "legacy-import.json").read_text())
    for record in manifest["files"]:
        copied = destination / "episodes" / source.name / "legacy" / record["path"]
        assert copied.stat().st_size == record["bytes"]
        assert studio_import.hashlib.sha256(copied.read_bytes()).hexdigest() == record["sha256"]


def test_development_has_no_personal_mounts_or_credentials():
    root = Path(__file__).resolve().parents[2]
    config = yaml.safe_load((root / "compose.development.yaml").read_text())
    service = config["services"]["crewcut"]
    assert config["name"] == "crewcut-development"
    assert "env_file" not in service
    assert service["environment"] == {"CREWCUT_STUDIO": "/studio", "CREWCUT_PUBLIC_PORT": "4757",
                                      "CREWCUT_PUBLIC_PROMPTER_PORT": "4758"}
    assert all(mount.split(":")[0] in config["volumes"] for mount in service["volumes"])
    assert service["ports"] == ["127.0.0.1:4757:4747", "127.0.0.1:4758:4748"]


def test_exposes_existing_preview_without_running_old_plans(tmp_path):
    source = source_episode(tmp_path)
    (source / "08-export").mkdir()
    (source / "08-export" / "S001-example-v001-preview.mp4").write_bytes(b"preview")
    destination = tmp_path / "private"
    studio_import.import_episode(source, destination)
    target = destination / "episodes" / source.name
    report = studio_import.expose_episode(target)
    assert report["visible_media"] == ["export/S001-example-v001-preview.mp4"]
    assert (target / "brief" / "LEGACY-INDEX.md").is_file()
    assert not list((target / "edit").iterdir())
    assert studio_import.expose_episode(target) == report


def test_explicit_script_reference_wins_over_old_filenames(tmp_path):
    source = source_episode(tmp_path)
    (source / "00-brief" / "AUFNAHME-DE-v001.txt").unlink()
    (source / "00-brief" / "chosen.txt").write_text("Chosen")
    (source / "project.json").write_text(json.dumps({"plans": {"script": "00-brief/chosen.txt"}}))
    assert studio_import.script_path(source).name == "chosen.txt"


def test_delivery_reference_can_have_a_historical_description(tmp_path):
    source = source_episode(tmp_path)
    (source / "08-export").mkdir()
    (source / "08-export" / "final.mp4").write_bytes(b"finished video")
    (source / "project.json").write_text(json.dumps({
        "delivery": {"final": "08-export/final.mp4 (1920x1080, historical approval)"}}))
    destination = tmp_path / "private"
    studio_import.import_episode(source, destination)
    report = studio_import.expose_episode(destination / "episodes" / source.name)
    assert report["visible_media"] == ["export/final.mp4"]


def test_expose_rejects_delivery_linked_parent(tmp_path):
    source = source_episode(tmp_path)
    (source / "project.json").write_text(json.dumps({"delivery": {"final": "external/final.mp4"}}))
    destination = tmp_path / "private"
    studio_import.import_episode(source, destination)
    target = destination / "episodes" / source.name
    outside = tmp_path / "external"
    outside.mkdir()
    (outside / "final.mp4").write_bytes(b"synthetic media")
    (target / "legacy" / "external").symlink_to(outside, target_is_directory=True)
    assert studio_import.expose_episode(target)["visible_media"] == []


def test_exposes_structured_historical_delivery(tmp_path):
    source = source_episode(tmp_path)
    (source / "final.mp4").write_bytes(b"synthetic final")
    (source / "project.json").write_text(json.dumps({"delivery": {"final": {
        "path": "final.mp4", "accepted": True, "accepted_at": "2024-01-02T03:04:05Z"}}}))
    destination = tmp_path / "private"
    studio_import.import_episode(source, destination)
    target = destination / "episodes" / source.name
    assert studio_import.expose_episode(target)["visible_media"] == ["export/final.mp4"]
