import hashlib
import json

import pytest

from crewcut.cut import ingest, legacy
from crewcut.cut.common import CutError


@pytest.fixture
def imported_recording(episode, monkeypatch):
    source = episode / "legacy" / "01-originals" / "recording.mp4"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"synthetic recording")
    record = {"path": "01-originals/recording.mp4", "bytes": source.stat().st_size,
              "sha256": hashlib.sha256(source.read_bytes()).hexdigest()}
    (episode / "legacy-import.json").write_text(json.dumps({"files": [record]}))
    monkeypatch.setattr(legacy.media, "probe", lambda path: {"format": {"duration": "12"}, "streams": [
        {"codec_type": "video", "width": 1920, "height": 1080, "r_frame_rate": "25/1"}]})
    return source


def test_registration_is_native_without_copy_or_work(episode, imported_recording, studio):
    original = imported_recording.read_bytes()
    project = (episode / "project.json").read_bytes()
    report = legacy.register(episode.name)
    assert report["files"][0]["file"] == "legacy/01-originals/recording.mp4"
    assert report["files"][0]["mic_check"] is None
    assert report["warnings"]
    assert ingest.previous_entries(episode) == report["files"]
    assert not list((episode / "originals").iterdir())
    assert not list((episode / "work").iterdir())
    assert imported_recording.read_bytes() == original
    assert (episode / "project.json").read_bytes() == project
    assert not (studio / ".crewcut" / "crewcut.db").exists()
    with pytest.raises(CutError, match="already"):
        legacy.register(episode.name)


def test_changed_recording_does_not_write_report(episode, imported_recording):
    imported_recording.write_bytes(b"different recording")
    with pytest.raises(CutError, match="changed"):
        legacy.register(episode.name)
    assert not (episode / "brief" / "ingest-legacy.json").exists()


def test_missing_recording_does_not_write_report(episode, imported_recording):
    imported_recording.unlink()
    with pytest.raises(CutError, match="Missing"):
        legacy.register(episode.name)


def test_link_is_rejected(episode, imported_recording, tmp_path):
    external = tmp_path / "external.mp4"
    imported_recording.rename(external)
    imported_recording.symlink_to(external)
    with pytest.raises(CutError, match="links"):
        legacy.register(episode.name)


def test_non_media_is_listed_without_probing(episode, imported_recording):
    manifest = json.loads((episode / "legacy-import.json").read_text())
    manifest["files"].append({"path": "01-originals/notes.json"})
    (episode / "legacy-import.json").write_text(json.dumps(manifest))
    assert legacy.register(episode.name)["skipped_non_media"] == ["01-originals/notes.json"]
