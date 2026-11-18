import json

import pytest

from crewcut import episodes, paths
from crewcut.youtube.analytics import NoData
from crewcut.youtube.results import results


@pytest.fixture
def published(crew):
    episode = episodes.create("Synthetic published video")["id"]
    root = paths.episode_dir(episode)
    (root / "export/upload-result.json").write_text(json.dumps({"video_id": "example1234"}))
    return episode, root


def test_maps_headers_and_records_period_without_approvals(published):
    episode, root = published
    before = (root / "project.json").read_bytes()
    requests = []
    def query(parameters):
        requests.append(parameters)
        return {"columnHeaders": [{"name": "likes"}, {"name": "views"}], "rows": [[2, 40]]}
    report = results(episode, "2026-01-01", "2026-01-03", query=query)
    assert report["metrics"] == {"views": 40, "likes": 2}
    assert "averageViewDuration" in report["missing_metrics"]
    assert report["period"]["granularity"] == "calendar_days"
    assert requests[0]["filters"] == "video==example1234"
    assert requests[0]["ids"] == "channel==MINE"
    assert (root / "project.json").read_bytes() == before


def test_empty_rows_preserve_previous_report(published):
    episode, root = published
    path = root / "review/results-2026-01-01-2026-01-02.json"
    path.write_text('previous report')
    with pytest.raises(NoData):
        results(episode, "2026-01-01", "2026-01-02", query=lambda params: {})
    assert path.read_text() == 'previous report'


def test_zero_is_data_not_missing(published):
    episode, root = published
    report = results(episode, "2026-01-01", "2026-01-02", query=lambda params: {
        "columnHeaders": [{"name": "views"}], "rows": [[0]]})
    assert report["metrics"]["views"] == 0


@pytest.mark.parametrize("start,end,video", [("invalid", "2026-01-02", None),
    ("2026-01-03", "2026-01-02", None), ("2026-01-01", "2026-01-02", "x;country==DE")])
def test_invalid_request_stops_before_query(published, start, end, video):
    episode, root = published
    with pytest.raises(ValueError):
        results(episode, start, end, video, query=lambda params: pytest.fail("Must not query"))
