import pytest
from PIL import Image

from crewcut import covers, episodes


def test_local_preview_never_becomes_a_publish_thumbnail(studio, crew):
    episode = episodes.create('An imported video')['id']
    root = studio / 'episodes' / episode
    source = root / 'legacy/05-graphics/thumbnail-ai/selected.jpg'
    source.parent.mkdir(parents=True)
    Image.new('RGB', (640, 360), 'blue').save(source)
    before = episodes.read(episode)
    result = covers.refresh(episode)
    assert result['status'] == 'created'
    assert result['approved_for_publication'] is False
    assert episodes.cover(episode).endswith('/work/cover-preview.jpg')
    assert not (root / 'graphics/thumbnail').exists()
    assert episodes.read(episode) == before
    assert covers.refresh(episode)['status'] == 'existing'


def test_missing_source_and_invalid_video_id(studio, crew):
    episode = episodes.create('Not recorded yet')['id']
    assert covers.refresh(episode)['status'] == 'missing'
    with pytest.raises(ValueError, match='exact YouTube'):
        covers.refresh(episode, 'http://127.0.0.1/private')


def test_cover_does_not_follow_outside_symlink(studio, crew, tmp_path):
    episode = episodes.create('Private boundary')['id']
    folder = studio / 'episodes' / episode / 'graphics/thumbnail'
    folder.mkdir(parents=True)
    outside = tmp_path / 'outside.jpg'
    Image.new('RGB', (320, 180)).save(outside)
    (folder / 'escape.jpg').symlink_to(outside)
    assert episodes.cover(episode) is None


def test_explicit_image_stays_inside_episode(studio, crew, tmp_path):
    episode = episodes.create('Chosen local preview')['id']
    outside = tmp_path / 'outside.jpg'
    Image.new('RGB', (640, 360)).save(outside)
    with pytest.raises(ValueError, match='inside'):
        covers.refresh(episode, image=str(outside))


def test_youtube_preview_uses_fixed_host_and_preserves_approval(studio, crew, monkeypatch):
    import io

    episode = episodes.create('Exact published video')['id']
    content = io.BytesIO()
    Image.new('RGB', (640, 360), 'blue').save(content, 'JPEG')
    expected = 'https://i.ytimg.com/vi/abcdefghijk/maxresdefault.jpg'

    class Response(io.BytesIO):
        def geturl(self):
            return expected

    def fetch(url, timeout):
        assert url == expected and timeout == 20
        return Response(content.getvalue())

    monkeypatch.setattr(covers, 'urlopen', fetch)
    result = covers.refresh(episode, youtube_id='abcdefghijk')
    assert result['source'] == {'kind': 'youtube-preview', 'video_id': 'abcdefghijk'}
    assert result['approved_for_publication'] is False
