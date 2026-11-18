import json

import pytest

from crewcut import episodes, paths
from crewcut.youtube import upload


@pytest.mark.parametrize("approved", [None, "2026-12-01T12:00:00Z"])
def test_schedule_override_cannot_bypass_package_approval(crew, monkeypatch, approved):
    monkeypatch.setenv("CREWCUT_IDENTITY", "publisher")
    episode = episodes.create("Synthetic schedule")["id"]
    root = paths.episode_dir(episode)
    (root / "export" / "video.mp4").write_bytes(b"synthetic")
    package = {"video": "export/video.mp4", "title": "Example", "description": "Example"}
    if approved:
        package["publish_at"] = approved
    (root / "export" / "upload.json").write_text(json.dumps(package))
    def no_approval(*args):
        pytest.fail("A schedule override must fail before creating or consuming any approval")
    monkeypatch.setattr(upload, "approval", no_approval)
    with pytest.raises(PermissionError, match="schedule differs"):
        upload.upload(episode, publish_at="2026-12-02T12:00:00Z")


def test_schedule_requires_timezone(crew):
    episode = episodes.create("Synthetic schedule")["id"]
    errors = upload.validate(episode, {"publish_at": "2026-12-02T12:00:00"})
    assert "publish_at must include a timezone" in errors
