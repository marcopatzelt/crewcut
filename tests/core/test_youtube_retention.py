"""`crewcut youtube retention` against a recorded YouTube Analytics answer (motion plan 3.8 check 5): per-moment
numbers, single findings are "watch", a finding seen in 3 videos becomes one lesson, and no data changes nothing.

The fixture ``data/youtube-analytics-retention.json`` has the shape of a ``reports.query`` answer for
``audienceWatchRatio`` by ``elapsedVideoTimeRatio``: a 100 s video whose audience holds flat over the number at
20-24 s and drops 5 points more than its slope over the keyword at 60-62 s."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from crewcut import cli, episodes, paths
from crewcut.motion import lessons, library, ratchet
from crewcut.youtube import analytics, auth

ANSWER = json.loads((Path(__file__).parent / "data" / "youtube-analytics-retention.json").read_text())
EMPTY = {**ANSWER, "rows": []}


def video(title: str = "Published video", vid: str = "abc123XYZ") -> str:
    eid = episodes.create(title)["id"]
    ep = paths.episode_dir(eid)
    words = [{"w": f"w{i}.", "s": float(i), "e": i + 0.5} for i in range(100)]
    (ep / "work" / "words-v001.json").write_text(json.dumps(words))
    plan = {"words": "work/words-v001.json", "tail": 0.5, "inserts": [
        {"id": "m1", "kind": "motion", "scene": "number_roll", "start": 20.0, "end": 24.0},
        {"id": "m2", "kind": "motion", "scene": "keyword_pop", "start": 60.0, "end": 62.0, "transparent": True},
        {"id": "k1", "kind": "2d", "scene": "keyword", "start": 40.0, "end": 42.0}]}
    (ep / "edit" / "plan-v001.json").write_text(json.dumps(plan))
    (ep / "export" / "upload-result.json").write_text(json.dumps({"video_id": vid, "at": "2026-11-10T10:00:00Z"}))
    return eid


class Recorded:
    def __init__(self, answer=ANSWER):
        self.answer, self.params = answer, []

    def __call__(self, params):
        self.params.append(params)
        return self.answer


def test_the_scope_is_requested():
    assert analytics.SCOPE in auth.SCOPES


def test_moments_get_numbers_and_single_findings_are_watch(studio):
    eid = video()
    q = Recorded()
    res = analytics.retention(eid, query=q)
    p = q.params[0]
    assert p["metrics"].startswith("audienceWatchRatio") and p["dimensions"] == "elapsedVideoTimeRatio"
    assert p["filters"] == "video==abc123XYZ" and p["ids"] == "channel==MINE" and p["startDate"] == "2026-11-10"
    assert res["duration_s"] == 100.0 and res["points"] == 100
    m = {x["id"]: x for x in res["moments"]}
    assert set(m) == {"m1", "m2"}, "only motion moments"
    assert m["m1"]["label"] == "held" and m["m1"]["delta"] == pytest.approx(0.054, abs=0.005)
    assert m["m1"]["at_start"] == pytest.approx(0.88, abs=1e-3) and m["m1"]["change"] == pytest.approx(0, abs=1e-3)
    assert m["m2"]["label"] == "dropped" and m["m2"]["delta"] == pytest.approx(-0.05, abs=0.005)
    assert all(x["status"] == "watch" for x in res["moments"])
    assert res["summary"]["held"] == 1 and res["summary"]["dropped"] == 1 and res["lessons"] == []
    saved = json.loads((paths.episode_dir(eid) / "review" / "retention.json").read_text())
    assert saved["video_id"] == "abc123XYZ" and len(saved["moments"]) == 2
    notes = library.read_index()["number_roll"]["notes"]
    assert notes[-1]["text"].startswith("retention: held viewers in 1 of 1 uses") and notes[-1]["source"] == "retention"
    assert lessons.read() == []
    # into the motion report
    md = ratchet.render_md({"version": 1, "episode": eid, "bar": None, "verdict_text": "x", "summary":
                            {"better": "", "behind": "", "next": ""}, "better": [], "behind": [], "upgrades": [],
                            "pieces": [], "proposals": {"library": [], "baseline": False, "merge_lessons": False},
                            "verdict": "back", "lessons": [], "measured": {}, "bar_measured": {},
                            "retention": saved})
    assert "m1 (number_roll) 0:20.0: held, +5.1 points" in md and "(watch)" in md


def test_a_finding_in_three_videos_becomes_one_lesson(studio):
    first, second = video("One", "v1"), video("Two", "v2")
    analytics.retention(first, query=Recorded())
    analytics.retention(second, query=Recorded())
    third = video("Three", "v3")
    res = analytics.retention(third, query=Recorded())
    m1 = next(x for x in res["moments"] if x["id"] == "m1")
    assert m1["status"] == "lesson" and m1["videos"] == 3
    got = lessons.read()
    assert len(got) == 2 and all(x["source"] == "retention" for x in got)
    assert "number_roll holds viewers" in got[0]["rule"] and "[number_roll:held]" in got[0]["rule"]
    analytics.retention(third, query=Recorded())
    assert len(lessons.read()) == 2, "a lesson is written once"
    notes = library.read_index()["number_roll"]["notes"]
    assert notes[-1]["text"].startswith("retention: held viewers in 3 of 3 uses")


def test_no_data_changes_nothing(studio, monkeypatch, capsys):
    eid = video()
    with pytest.raises(analytics.NoData):
        analytics.retention(eid, query=Recorded(EMPTY))
    assert not (paths.episode_dir(eid) / "review" / "retention.json").exists()
    assert library.read_index() == {} and lessons.read() == []
    monkeypatch.setattr(analytics, "api_query", Recorded(EMPTY))
    assert cli.main(["youtube", "retention", eid]) == 0
    assert capsys.readouterr().out.strip() == "no retention data"
    assert not (paths.episode_dir(eid) / "review" / "retention.json").exists()


def test_cli_prints_the_moments(studio, monkeypatch, capsys):
    eid = video()
    monkeypatch.setattr(analytics, "api_query", Recorded())
    assert cli.main(["youtube", "retention", eid]) == 0
    out = capsys.readouterr().out
    assert "1 held, 1 dropped of 2 motion moments" in out and "A hint, not proof." in out
    assert "m1" in out and "(watch)" in out


def test_without_an_upload_there_is_no_data(studio):
    eid = episodes.create("Not published")["id"]
    with pytest.raises(analytics.NoData, match="no uploaded video"):
        analytics.retention(eid, query=Recorded())
