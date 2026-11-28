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


def test_first_days_window_from_the_upload_record_and_traffic_shares(published):
    episode, root = published
    (root / "export/upload-result.json").write_text(json.dumps({"video_id": "example1234", "at": "2026-11-02T10:00:00Z"}))
    calls = []
    def query(parameters):
        calls.append(parameters)
        if parameters.get("dimensions") == "insightTrafficSourceType":
            return {"rows": [["YT_SEARCH", 70], ["SUBSCRIBER", 20], ["RELATED_VIDEO", 10]]}
        return {"columnHeaders": [{"name": "views"}], "rows": [[100]]}
    report = results(episode, None, None, query=query, first_days=7)
    assert report["period"] == {"start": "2026-11-02", "end": "2026-11-08", "granularity": "calendar_days"}
    assert report["window"] == {"first_days": 7, "published": "2026-11-02"}
    assert report["traffic"] == {"search": 0.7, "browse": 0.2, "other": 0.1, "type": "search"}
    assert (root / "review/results-2026-11-02-2026-11-08.json").is_file()
    with pytest.raises(ValueError):
        results(episode, None, None, query=query, first_days=5)
    (root / "export/upload-result.json").write_text(json.dumps({"video_id": "example1234"}))
    with pytest.raises(ValueError, match="publication day"):
        results(episode, None, None, query=query, first_days=28)
