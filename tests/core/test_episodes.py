import pytest

from crewcut import episodes


def test_create_and_steps(crew, studio):
    p = episodes.create("Does a $20 plan build a website?")
    eid = p["id"]
    assert eid.startswith("001-")
    d = studio / "episodes" / eid
    assert (d / "project.json").is_file() and (d / "brief" / "BRIEF.md").is_file()
    s = episodes.summary(eid)
    assert [x["id"] for x in s["steps"]][:3] == ["idea", "title", "proof"]
    assert next(x for x in s["steps"] if x["id"] == "blog")["status"] == "skipped"
    episodes.set_step(eid, "idea", "done")
    assert episodes.read(eid)["step"] == "title"
    assert episodes.create("second")["id"].startswith("002-")


def test_slug_and_bad_ids():
    assert episodes.slug("Héllo, Wörld! 100%") == "hello-world-100"
    import pytest

    from crewcut import paths
    with pytest.raises(ValueError):
        paths.episode_dir("../x")


@pytest.mark.parametrize("stage,expected", [
    ("published", "published"), ("posted_by_polo", "published"),
    ("parked", "parked"), ("paused", "paused"), ("archived", "archived"),
    ("final_ready", None), ("awaiting_original", None),
])
def test_historical_status_does_not_grant_upload_approval(crew, stage, expected):
    project = episodes.create("Imported example")
    project["legacy"] = {"stage": stage}
    project["steps"]["upload"] = {"status": "skipped"}
    episodes.write(project["id"], project)
    summary = episodes.summary(project["id"])
    assert summary.get("historical_status") == expected
    assert episodes.read(project["id"])["steps"]["upload"]["status"] == "skipped"


def test_lifecycle_preserves_history_and_starts_no_work(crew):
    from crewcut import db
    project = episodes.create("Earlier episode")
    project["legacy"] = {"stage": "parked"}
    project["steps"]["upload"]["status"] = "skipped"
    episodes.write(project["id"], project)
    for lifecycle in episodes.LIFECYCLES:
        result = episodes.set_lifecycle(project["id"], lifecycle)
        assert result["steps"] == project["steps"]
        assert result["legacy"] == project["legacy"]
        assert episodes.summary(project["id"])["lifecycle"] == lifecycle
    with db.conn() as connection:
        assert connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM cards").fetchone()[0] == 0


def test_lifecycle_refuses_busy_episode(crew):
    from crewcut.conductor import queue
    project = episodes.create("Busy episode")
    queue.add(project["id"], "writer", "script", "Synthetic work")
    with pytest.raises(ValueError, match="Finish or cancel"):
        episodes.set_lifecycle(project["id"], "parked")
    assert "lifecycle" not in episodes.read(project["id"])


def test_invalid_lifecycle_is_rejected(crew):
    project = episodes.create("Example")
    with pytest.raises(ValueError):
        episodes.set_lifecycle(project["id"], "published")


def test_proof_is_optional_and_off_by_default(crew, studio):
    proof = episodes.create("Default studio")["steps"]["proof"]
    assert proof["status"] == "skipped" and proof["note"] == episodes.SWITCHED_OFF
    (studio / "config").mkdir()
    (studio / "config" / "crewcut.toml").write_text("[steps]\nproof = true\n")
    assert episodes.create("Proof switched on")["steps"]["proof"]["status"] == "open"


def test_title_yes_goes_straight_to_script_when_proof_is_off(crew, studio, monkeypatch):
    from crewcut.conductor import flow
    started = []
    monkeypatch.setattr(flow, "start_step", lambda episode, step, seed="": started.append(step))
    (studio / "config").mkdir()
    cfg = studio / "config" / "crewcut.toml"
    cfg.write_text("[steps]\nproof = true\n")
    eid = episodes.create("Began while proof was on")["id"]
    cfg.write_text("[steps]\nproof = false\n")
    episodes.set_step(eid, "idea", "done")
    flow.on_card_decided({"id": 1, "episode": eid, "kind": "title", "status": "accepted", "title": "Pick a title",
                          "options": ["Claude cuts my videos now. Wow!"], "choice": 0})
    assert started == ["script"]
    p = episodes.read(eid)
    assert p["steps"]["proof"]["status"] == "skipped" and p["title"] == "Claude cuts my videos now. Wow!"
