import json

import pytest

from crewcut import episodes, paths
from crewcut.thumbnail.make import reference_images


@pytest.fixture
def reference_pack(crew):
    episode = episodes.create("Synthetic thumbnail")["id"]
    root = paths.user_brand_dir()
    root.mkdir(parents=True)
    (root / "brand.json").write_text('{"schema":1}')
    (root / "thumbnail.json").write_text(json.dumps({"reference_photo": "photo.png", "style_reference": "style.png"}))
    (root / "photo.png").write_bytes(b"synthetic photo")
    (root / "style.png").write_bytes(b"synthetic style")
    result = paths.episode_dir(episode) / "graphics" / "result.png"
    result.write_bytes(b"synthetic result")
    return episode, root, result


def test_pack_references_precede_episode_results(reference_pack):
    episode, root, result = reference_pack
    assert reference_images(episode, ["graphics/result.png", "graphics/result.png"]) == [
        root / "photo.png", root / "style.png", result]


def test_missing_fixed_photo_stops_generation(reference_pack):
    episode, root, result = reference_pack
    (root / "photo.png").unlink()
    with pytest.raises(FileNotFoundError, match="reference_photo"):
        reference_images(episode, [])


def test_layout_without_person_does_not_attach_photo(reference_pack):
    episode, root, result = reference_pack
    (root / "thumbnail.json").write_text(json.dumps({"face": False, "reference_photo": "photo.png",
                                                   "style_reference": "style.png"}))
    assert reference_images(episode, []) == [root / "style.png"]


def test_pack_reference_cannot_escape_pack(reference_pack):
    episode, root, result = reference_pack
    (root / "photo.png").unlink()
    (root / "photo.png").symlink_to(result)
    with pytest.raises(ValueError):
        reference_images(episode, [])


def test_episode_reference_cannot_escape_episode(reference_pack):
    episode, root, result = reference_pack
    with pytest.raises(ValueError):
        reference_images(episode, ["../../brand/photo.png"])


def test_no_fixed_references_keeps_existing_flow(crew):
    episode = episodes.create("No fixed photos")["id"]
    assert reference_images(episode, []) == []
