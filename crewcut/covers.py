"""Local card previews, separate from approved publication thumbnails."""

from __future__ import annotations

import io
import json
import re
import subprocess
import tempfile
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

from PIL import Image

from . import episodes, paths


def _inside(file: Path, root: Path) -> bool:
    return file.is_file() and file.resolve().is_relative_to(root.resolve())


def refresh(episode: str, youtube_id: str | None = None, image: str | None = None) -> dict:
    """Fill a missing card cover from local thumbnails, YouTube, or an exported frame. No approval or upload."""
    root = paths.episode_dir(episode)
    episodes.read(episode)
    if youtube_id is not None and not re.fullmatch(r"[A-Za-z0-9_-]{11}", youtube_id):
        raise ValueError("Use an exact YouTube video ID, not a URL.")
    existing = episodes.cover(episode)
    if existing:
        return {"status": "existing", "cover": existing}
    preview = root / 'work' / 'cover-preview.jpg'
    preview.parent.mkdir(parents=True, exist_ok=True)
    if not preview.parent.resolve().is_relative_to(root.resolve()) or preview.is_symlink():
        raise ValueError("The preview must stay inside the episode.")
    source = None
    picture = None
    candidates = []
    if image:
        selected = root / image
        if not _inside(selected, root):
            raise ValueError('Choose an image inside this episode.')
        candidates = [selected]
    else:
        for folder in (root / 'legacy/05-graphics/thumbnail-ai', root / 'legacy/05-graphics/thumbnail'):
            if folder.is_dir():
                candidates.extend(file for file in folder.rglob('*')
                                  if file.suffix.lower() in ('.png', '.jpg', '.jpeg', '.webp') and _inside(file, root))
    if youtube_id and not image:
        for variant in ('maxresdefault', 'hqdefault'):
            url = f'https://i.ytimg.com/vi/{youtube_id}/{variant}.jpg'
            try:
                with urlopen(url, timeout=20) as response:
                    if response.geturl() != url:
                        raise ValueError('Unexpected thumbnail redirect.')
                    data = response.read(5_000_001)
                if len(data) > 5_000_000:
                    raise ValueError('Thumbnail exceeds 5 MB.')
                with Image.open(io.BytesIO(data)) as candidate:
                    if candidate.width < 320:
                        continue
                    candidate.thumbnail((1280, 1280))
                    picture = candidate.convert('RGB')
                source = {'kind': 'youtube-preview', 'video_id': youtube_id}
                break
            except HTTPError as error:
                if error.code != 404:
                    raise
    if picture is None:
        for file in sorted(candidates, key=lambda file: file.stat().st_mtime, reverse=True):
            try:
                with Image.open(file) as candidate:
                    candidate.thumbnail((1280, 1280))
                    picture = candidate.convert('RGB')
                source = {'kind': 'local-thumbnail-preview', 'path': file.relative_to(root).as_posix()}
                break
            except (OSError, ValueError):
                continue
    if picture is None:
        videos = []
        for folder in (root / 'export', root / 'legacy/08-export', root / 'legacy/schnitt'):
            if folder.is_dir():
                videos.extend(file for file in folder.rglob('*.mp4') if _inside(file, root))
        for file in sorted(videos, key=lambda file: file.stat().st_mtime, reverse=True):
            result = subprocess.run(['ffmpeg', '-v', 'error', '-threads', '1', '-ss', '1', '-i', str(file),
                                     '-frames:v', '1', '-vf', 'scale=640:-2', '-threads', '1',
                                     '-f', 'image2pipe', '-vcodec', 'mjpeg', '-'],
                                    capture_output=True, timeout=45, check=False)
            if result.returncode or not result.stdout:
                continue
            with Image.open(io.BytesIO(result.stdout)) as candidate:
                picture = candidate.convert('RGB')
            source = {'kind': 'export-frame-preview', 'path': file.relative_to(root).as_posix()}
            break
    if picture is None:
        return {'status': 'missing', 'reason': 'No existing thumbnail, matched YouTube video, or export.'}
    with tempfile.NamedTemporaryFile(dir=preview.parent, suffix='.jpg', delete=False) as temporary:
        temp = Path(temporary.name)
    try:
        picture.save(temp, 'JPEG', quality=90)
        temp.replace(preview)
    finally:
        temp.unlink(missing_ok=True)
    report = {'status': 'created', 'source': source, 'approved_for_publication': False}
    preview.with_suffix('.json').write_text(json.dumps(report, indent=2) + '\n')
    return report
