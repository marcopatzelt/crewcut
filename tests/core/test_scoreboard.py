"""The scoreboard per show format and its line in the channel brief."""

import json

from fastapi.testclient import TestClient

from crewcut import briefing, episodes, paths, scoreboard, shorts


def measured(fid, views, pct, subs, kind="episode", at="2030-01-05T00:00:00Z", key="show_format"):
    p = episodes.create(f"{fid} {views}")
    p[key] = fid
    episodes.write(p["id"], p)
    if views is not None:
        r = {"schema": 1, "episode": p["id"], "fetched_at": at, "period": {"start": "2030-01-01", "end": "2030-01-03"},
             "metrics": {"views": views, "averageViewPercentage": pct, "subscribersGained": subs}}
        (paths.episode_dir(p["id"]) / "review" / "results-2030-01-01-2030-01-03.json").write_text(json.dumps(r))
    return p["id"]


def test_medians_subs_per_thousand_and_verdicts(crew):
    measured("tool-test", 1000, 50.0, 10)
    measured("tool-test", 3000, 40.0, 30)
    measured("claim-check", 100, 20.0, 0)
    measured("claim-check", 200, 30.0, 1)
    measured("incident-file", 5000, 70.0, 50)
    measured("incident-file", None, None, None)
    episodes.create("no format")
    board = scoreboard.build()
    assert board["channel"]["episodes"] == 5 and board["channel"]["median_views"] == 1000
    by = {f["format"]: f for f in board["formats"]}
    t = by["tool-test"]
    assert t["episodes"] == 2 and t["measured"] == 2 and t["median_views"] == 2000
    assert t["median_avg_view_pct"] == 45.0 and t["subs_per_1000"] == 10.0
    assert t["verdict"] == "more" and t["verdict_text"] == "more of this"
    assert by["claim-check"]["verdict"] == "watch"
    assert by["incident-file"]["verdict"] == "thin" and by["incident-file"]["episodes"] == 2
    assert board["formats"][0]["format"] == "tool-test"
    assert t["ctr"] is None and "CTR missing" in scoreboard.line(t)


def test_newest_result_ctr_retention_and_form_fallback(crew):
    eid = measured("tool-test", 100, 10.0, 1, at="2030-01-01T00:00:00Z")
    ep = paths.episode_dir(eid)
    newer = {"fetched_at": "2030-02-01T00:00:00Z", "metrics": {"views": 400, "averageViewPercentage": 30,
                                                               "subscribersGained": 2}}
    (ep / "review" / "results-2030-01-20-2030-01-31.json").write_text(json.dumps(newer))
    (ep / "analytics").mkdir()
    (ep / "analytics" / "ctr.json").write_text(json.dumps({"ctr": 0.051, "impressions": 12000}))
    (ep / "analytics" / "retention-units.json").write_text(json.dumps({"measurements": [{"units": [
        {"kind": "intro", "drop_per_min": 30}, {"kind": "unit", "drop_per_min": 4}, {"kind": "unit", "drop_per_min": 6}]}]}))
    measured("claim-check", 50, 60.0, 1, key="form")
    row = {r["episode"]: r for r in scoreboard.episode_rows()}[eid]
    assert row["views"] == 400 and row["subs_per_1000"] == 5.0 and row["retention_drop_per_min"] == 5.0
    f = {f["format"]: f for f in scoreboard.build()["formats"]}
    assert f["tool-test"]["ctr"] == 0.051 and "CTR 5.1 %" in scoreboard.line(f["tool-test"])
    assert "claim-check" in f


def test_shorts_rows_count_when_there_is_no_results_file(crew):
    p = episodes.create("A short", kind="short", mode="original")
    shorts.add_result({"date": "2030-01-03", "episode": p["id"], "form": "claim-check", "views": 800,
                       "average_view_percentage": 90, "subscribers_gained": 4})
    rows = scoreboard.episode_rows()
    assert rows[0]["format"] == "claim-check" and rows[0]["source"] == "shorts.tsv" and rows[0]["subs_per_1000"] == 5.0


def test_the_brief_gets_one_line_per_measured_format(crew):
    assert "Show formats on this channel" not in briefing.text()
    measured("tool-test", 1000, 50.0, 10)
    measured("claim-check", None, None, None)
    text = briefing.text()
    assert "Show formats on this channel" in text
    assert "- Tool test (tool-test): 1 episodes, 1 measured, median 1,000 views, 50 % watched, 10 subs/1000 views, " \
           "CTR missing: too little data" in text
    assert "Claim check" not in text


def test_cli_and_api(crew, capsys):
    measured("tool-test", 1000, 50.0, 10)
    assert scoreboard.cli() == 0 and "tool-test" in capsys.readouterr().out
    from crewcut import showformats
    assert showformats.main(["score", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["formats"][0]["format"] == "tool-test"
    from crewcut.server.app import create_app
    c = TestClient(create_app(start_worker=False), base_url="http://localhost:4747")
    assert c.get("/api/scoreboard").json()["formats"][0]["median_views"] == 1000
