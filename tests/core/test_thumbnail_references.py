import json
import os

import pytest

from crewcut import episodes, paths
from crewcut.thumbnail.make import reference_images


def test_generated_codex_artifact_is_recovered_only_inside_image_folder(tmp_path, monkeypatch):
    from PIL import Image

    from crewcut.thumbnail.make import recover_codex_image
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex"))
    image = tmp_path / "codex/generated_images/run/image.png"
    image.parent.mkdir(parents=True)
    Image.new("RGB", (16, 16), "blue").save(image)
    out = tmp_path / "thumbnail.png"
    assert recover_codex_image(f"[Generated PNG]({image})", out, 0)
    assert Image.open(out).size == (16, 16)
    assert not recover_codex_image(f"[Other file]({out})", tmp_path / "bad.png", 0)
    assert not recover_codex_image(f"[Old image]({image})", tmp_path / "old.png", image.stat().st_mtime + 10)


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


FAKE_CODEX = r'''#!/usr/bin/env python3
"""Parses like `codex exec`: --image takes every following value, the prompt comes from stdin otherwise.
Like Codex in the container, it saves the image in its own folder only, because its sandbox cannot copy it."""
import json, os, re, sys
args, images, positional, i = sys.argv[2:], [], [], 0
while i < len(args):
    if args[i] == "--image":
        i += 1
        while i < len(args) and not args[i].startswith("-"):
            images.append(args[i]); i += 1
    elif args[i] in ("--sandbox", "-c"):
        i += 2
    elif args[i].startswith("-"):
        i += 1
    else:
        positional.append(args[i]); i += 1
prompt = positional[0] if positional else sys.stdin.read()
if not prompt.strip():
    print("No prompt provided via stdin."); sys.exit(1)
json.dump({"images": images, "prompt": prompt}, open(os.environ["FAKE_CODEX_SEEN"], "w"))
from PIL import Image
folder = os.path.join(os.environ["CODEX_HOME"], "generated_images", "01a2-thread")
os.makedirs(folder, exist_ok=True)
Image.new("RGB", (1672, 941), "white").save(os.path.join(folder, "exec-1.png"))
print(json.dumps({"type": "thread.started", "thread_id": "01a2-thread"}))
print(json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": "The sandbox blocked saving."}}))
'''


def test_codex_way_attaches_every_reference_and_keeps_the_prompt(tmp_path, monkeypatch):
    from PIL import Image

    from crewcut.thumbnail.make import codex_command, make_codex
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "codex").write_text(FAKE_CODEX)
    (bin_dir / "codex").chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_CODEX_SEEN", str(tmp_path / "seen.json"))
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex"))
    refs = [tmp_path / "photo.jpg", tmp_path / "style.png"]
    for r in refs:
        r.write_bytes(b"synthetic")
    assert codex_command(refs)[-2:] == ["--image", str(refs[1])]
    out = make_codex("Marco points at the result. Text: SCHNITT.", refs, tmp_path / "thumb" / "a.png")
    seen = json.loads((tmp_path / "seen.json").read_text())
    assert seen["images"] == [str(r) for r in refs]
    assert seen["prompt"].endswith("PROMPT:\nMarco points at the result. Text: SCHNITT.") and "16:9" in seen["prompt"]
    assert Image.open(out).size == (1672, 941) and "--json" in codex_command(refs)
