from crewcut import episodes, media, paths


def test_imported_cover_is_visible_without_approval(studio):
    project = episodes.create("Earlier finished video")
    project["legacy"] = {"stage": "published"}
    episodes.write(project["id"], project)
    root = paths.episode_dir(project["id"])
    (root / "work" / "cover-preview.jpg").write_bytes(b"synthetic-preview")
    result = media.episode_media(project["id"])
    assert result["cover_preview"].endswith("/work/cover-preview.jpg")
    assert result["imported"] is True
    assert result["thumbnails"] == []
    assert result["cut"] is None


def test_preview_symlink_cannot_expose_outside_file(studio, tmp_path):
    project = episodes.create("No outside files")
    outside = tmp_path / "outside.jpg"
    outside.write_bytes(b"synthetic")
    (paths.episode_dir(project["id"]) / "work" / "cover-preview.jpg").symlink_to(outside)
    assert media.episode_media(project["id"])["cover_preview"] is None
