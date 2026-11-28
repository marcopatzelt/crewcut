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
    assert t["verdict"] == "watch" and t["basis"] == "total views"   # 2 episodes: the decision comes after 4
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


def windowed(fid, day, v7, v28=None, pct=50.0, subs=5, ctr=None, traffic=None, project_traffic=None):
    """An episode with reports of its first 7 (and 28) days, published on 2026-<day>."""
    p = episodes.create(f"{fid} {day}")
    p["show_format"] = fid
    if project_traffic:
        p["traffic_type"] = project_traffic
    episodes.write(p["id"], p)
    ep = paths.episode_dir(p["id"])
    for days, views in ((7, v7), (28, v28)):
        if views is None:
            continue
        r = {"schema": 1, "episode": p["id"], "fetched_at": f"{day}T00:00:00Z", "metrics": {
            "views": views, "averageViewPercentage": pct, "subscribersGained": subs},
            "window": {"first_days": days, "published": day}, **({"traffic": traffic} if traffic else {})}
        (ep / "review" / f"results-{day}-{days}.json").write_text(json.dumps(r))
    if ctr is not None:
        (ep / "analytics").mkdir()
        (ep / "analytics" / "ctr.json").write_text(json.dumps({"ctr": ctr}))
    return p["id"]


def test_first_days_against_the_last_ten_and_decision_after_four(crew):
    for i in range(6):   # alternating: tool-test 2,000 views in its first week, incident-file 1,000
        windowed("tool-test", f"2026-10-{10 + 2 * i:02d}", 2000, subs=20)
        windowed("incident-file", f"2026-10-{11 + 2 * i:02d}", 1000, subs=5)
    rows = {r["episode"]: r for r in scoreboard.episode_rows()}
    last = max((r for r in rows.values() if r["format"] == "tool-test"), key=lambda r: r["published"])
    assert last["x_7d"] == round(2000 / 1500, 2) and last["source"] == "first days"
    by = {f["format"]: f for f in scoreboard.build()["formats"]}
    assert by["tool-test"]["verdict"] == "more" and by["tool-test"]["basis"] == "first days"
    assert by["incident-file"]["verdict"] == "drop" and by["incident-file"]["median_x"] < 0.8
    assert "first 7 days" in scoreboard.line(by["tool-test"]) and "co-views" not in scoreboard.line(by["tool-test"])


def test_early_stop_needs_the_diagnosis(crew):
    for i in range(4):
        windowed("incident-file", f"2026-09-{10 + i:02d}", 2000, pct=50.0, ctr=0.05)
    windowed("claim-check", "2026-09-20", 500, pct=30.0, ctr=0.02)
    windowed("claim-check", "2026-09-21", 600, pct=30.0, ctr=0.02)
    f = {f["format"]: f for f in scoreboard.build()["formats"]}["claim-check"]
    assert f["verdict"] == "stop" and f["diagnosis"] == "weak for us"
    windowed("tool-test", "2026-09-22", 500, pct=60.0, ctr=0.02)
    windowed("tool-test", "2026-09-23", 600, pct=60.0, ctr=0.02)
    t = {f["format"]: f for f in scoreboard.build()["formats"]}["tool-test"]
    assert t["verdict"] == "watch" and t["diagnosis"] == "content carries, packaging weak"


def test_search_formats_wait_for_28_days_and_coviews_are_noted(crew):
    for i in range(4):
        windowed("incident-file", f"2026-10-{10 + i:02d}", 2000, v28=4000)
    search = {"search": 0.7, "browse": 0.2, "other": 0.1, "type": "search"}
    windowed("tool-test", "2026-11-05", 300, traffic=search)
    windowed("tool-test", "2026-11-06", 300, project_traffic="search")
    t = {f["format"]: f for f in scoreboard.build()["formats"]}["tool-test"]
    assert t["traffic_type"] == "search" and t["verdict"] == "watch" and t["basis"].startswith("search")
    windowed("tool-test", "2026-11-07", 300, v28=5000, project_traffic="search")
    windowed("tool-test", "2026-11-08", 300, v28=5000, project_traffic="search")
    t = {f["format"]: f for f in scoreboard.build()["formats"]}["tool-test"]
    assert t["basis"] == "first days" and t["judged"] == 2 and t["median_x"] > 1
    assert t["coview_mixed"] and "co-views" in scoreboard.line(t)
