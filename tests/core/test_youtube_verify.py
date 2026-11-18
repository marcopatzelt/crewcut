import json
from datetime import UTC, datetime
from unittest.mock import Mock

import pytest

from crewcut import episodes, paths
from crewcut.youtube.upload import body_of
from crewcut.youtube.verify import verify


@pytest.fixture
def uploaded(crew):
    project = episodes.create("Synthetic published example")
    root = paths.episode_dir(project["id"])
    package = {"title": "Example", "description": "A test", "video": "export/test.mp4", "tags": ["one", "two"]}
    (root / "export" / "upload.json").write_text(json.dumps(package))
    (root / "export" / "upload-result.json").write_text(json.dumps({"video_id": "synthetic-video"}))
    youtube = Mock()
    youtube.videos.return_value.list.return_value.execute.return_value = {"items": [body_of(package)]}
    return project["id"], root, package, youtube


def test_verify_reads_only_and_preserves_approval_state(uploaded):
    episode, root, package, youtube = uploaded
    before = (root / "project.json").read_bytes()
    result = verify(episode, youtube=youtube)
    assert result["matches"]
    assert "caption text" in result["not_checked"]
    assert (root / "review" / "publication-check.json").is_file()
    assert (root / "project.json").read_bytes() == before
    assert [call[0] for call in youtube.mock_calls] == ["videos", "videos().list", "videos().list().execute"]


def test_mismatch_is_not_success(uploaded):
    episode, root, package, youtube = uploaded
    youtube.videos.return_value.list.return_value.execute.return_value["items"][0]["snippet"]["title"] = "Changed"
    assert not verify(episode, youtube=youtube)["matches"]


def test_missing_video_preserves_previous_report(uploaded):
    episode, root, package, youtube = uploaded
    verify(episode, youtube=youtube)
    before = (root / "review" / "publication-check.json").read_bytes()
    youtube.videos.return_value.list.return_value.execute.return_value = {"items": []}
    with pytest.raises(LookupError):
        verify(episode, youtube=youtube)
    assert (root / "review" / "publication-check.json").read_bytes() == before


@pytest.mark.parametrize("status,draft,matches", [("serving", False, True), ("syncing", False, False),
                                                ("failed", False, False), ("serving", True, False)])
def test_captions_require_serving_non_draft_track(uploaded, status, draft, matches):
    episode, root, package, youtube = uploaded
    package["captions"] = [{"language": "en", "name": "Own captions"}]
    (root / "export" / "upload.json").write_text(json.dumps(package))
    youtube.captions.return_value.list.return_value.execute.return_value = {"items": [{"snippet": {
        "language": "en", "name": "Own captions", "status": status, "isDraft": draft}}]}
    assert verify(episode, youtube=youtube)["matches"] is matches


@pytest.mark.parametrize("day,privacy", [(1, "private"), (3, "public")])
def test_schedule_before_and_after_publication(uploaded, day, privacy):
    episode, root, package, youtube = uploaded
    package["publish_at"] = "2026-01-02T12:00:00Z"
    (root / "export" / "upload.json").write_text(json.dumps(package))
    actual = body_of(package)
    actual["status"]["privacyStatus"] = privacy
    if privacy == "public":
        actual["status"].pop("publishAt")
    youtube.videos.return_value.list.return_value.execute.return_value = {"items": [actual]}
    assert verify(episode, youtube=youtube, now=datetime(2026, 1, day, tzinfo=UTC))["matches"]
